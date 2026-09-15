# Packet M4-2 — wire credential staging into dispatch

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
("channel instances — many subscriptions per provider, universally"), M4
("credential staging at dispatch"). Supervised via `/supervise`. Follows
M4-1 (`src/lee_llm_router/staffing/credentials.py`, already committed,
router commit `dca7f70`), which built and independently reviewed the
staging-home module in isolation but wired it into nothing.

## Packet fields

Kind: impl
Declared size: 4 files (2 source, 2 test), approximately 250 changed lines
Owned paths: `src/lee_llm_router/staffing/run.py`, `src/lee_llm_router/doctor.py`, `tests/test_staffing_run.py`, `tests/test_doctor.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_run.py tests/test_doctor.py -q`
Review: independent review required after the oracle passes
Runtime bound: 60 minutes

## Objective

Make `lee-llm-router run` actually stage the chosen channel instance's
credential before launching a worker subprocess, for the two harnesses
`credentials.py` supports (`opencode`, `pi`), and fail closed (exit 3,
nothing launched, nothing registered) when staging is required but cannot
happen safely. A channel with no declared `instances` (the implicit
single-instance default) must behave **exactly as it does today** — no
staging, no env changes, no new failure modes. This packet does not touch
`src/lee_llm_router/staffing/credentials.py` at all; only *calls into* it.

## Background facts (already verified in this repo, use verbatim)

- `doctor.py`'s `_run_run()` calls `select_route(...)` at line ~1768 to get a
  `SelectionOutcome` named `outcome`. `outcome.channel_instance` (`str |
  None`) already carries the chosen instance id (M3-3). `outcome.route` is a
  `catalog.Route` with `.harness` (e.g. `"opencode"`, `"pi"`, `"omp"`,
  `"codex"`, `"claude"`) and `.channel` (the channel id string). `catalog`
  (a loaded `StaffingCatalog`) is already in scope at that point as
  `catalog.channels.channels: tuple[Channel, ...]`, each with `.channel_id`,
  `.instances: tuple[ChannelInstance, ...]`, and `.effective_instances()`
  (returns `.instances` verbatim when non-empty, else one synthesized
  implicit instance — see `catalog.py`, already committed, do not change).
  Each `ChannelInstance` has `.instance_id` and `.credential_ref`.
- `_execute_registered()` (closure defined at line ~1837) is where
  `dispatch_route(outcome.route, prompt, ...)` is actually called (line
  ~1841), and is where `RunSelectionError`/`RunDispatchError` style
  failures are already handled by this file's `fail(...)` helper.
- `dispatch_route()` (`src/lee_llm_router/staffing/run.py`, ~line 2630) is
  the function that builds argv, wraps `popen`, and calls
  `run_supervised_dispatch()` (~line 2389) with `launch_kwargs` and finally
  `popen(argv, **launch_kwargs)` (~line 2497). Today, `launch_kwargs["env"]`
  is only ever set inside one conditional branch (`os.name == "posix" and
  real_popen and _LinuxDescendantTree.available()`) that copies
  `os.environ` and injects a private provenance marker for Linux process
  tracking — an unrelated concern from credential staging. Outside that
  branch, `env` is never set, so the child inherits the parent's real
  environment untouched.

## Required changes

### 1. `src/lee_llm_router/staffing/run.py`

- Add an optional parameter `extra_env: dict[str, str] | None = None` to
  both `run_supervised_dispatch()` and `dispatch_route()` (the latter passes
  it straight through to the former — no other plumbing).
- In `run_supervised_dispatch()`, when `extra_env` is not `None` (or
  non-empty), it must always be merged into the child's environment — build
  `child_env = os.environ.copy()`, apply `child_env.update(extra_env)`, set
  `launch_kwargs["env"] = child_env`. This must happen **unconditionally**,
  independent of the existing `os.name == "posix" and real_popen and
  _LinuxDescendantTree.available()` branch (which handles a completely
  separate concern, the provenance marker, and must keep working exactly as
  today — including still injecting its own marker into `child_env` when
  both conditions apply at once; write this so both env contributions can
  coexist in the same `child_env` dict rather than one silently overwriting
  the other). When `extra_env` is `None`/empty and the provenance branch
  does not apply, `env` must stay unset exactly as today (no behavior
  change for callers that pass nothing, including every existing test that
  calls `run_supervised_dispatch`/`dispatch_route` without this new
  parameter).
- Do not change process-group, watchdog, stall, or usage-capture logic. Do
  not change any existing function signature's meaning, only add the one
  new trailing optional keyword parameter to each of the two functions.

### 2. `src/lee_llm_router/doctor.py`

In `_run_run()`:

- Import `credentials` (`from lee_llm_router.staffing import credentials` or
  equivalent — match this file's existing import style for sibling
  `staffing` submodules).
- Immediately after the existing `outcome = select_route(...)` /
  `except RunSelectionError` block (line ~1784-1786) and before the
  existing oracle-argv parsing block (~1790), determine whether credential
  staging is required for this dispatch:
  - Find the `Channel` in `catalog.channels.channels` whose `channel_id ==
    outcome.route.channel`.
  - Staging is required only when that channel's `.instances` tuple is
    **non-empty** (a genuinely declared multi/single-instance channel, not
    the implicit default) **and** `outcome.channel_instance is not None`.
    When staging is not required (no declared `instances`, or no channel
    instance resolved), proceed exactly as today: no staging, no env
    changes, `credential_path = None` for the rest of this packet's logic.
  - When staging is required: find the matching `ChannelInstance` in that
    channel's `.effective_instances()` whose `.instance_id ==
    outcome.channel_instance`. Its `.credential_ref` is what you resolve.
  - Call `credentials.resolve_credential_path(credential_ref)`. If it
    raises `credentials.CredentialStagingError`, return
    `fail(f"credential staging failed: {exc}", as_json=as_json,
    exit_code=3)` — nothing is registered, nothing launches. This is the
    plan's "a missing credential file fails closed before launch (exit 3)."
  - Then validate harness support the same way, *before* registration:
    call `credentials.stage_harness_home(outcome.route.harness,
    credential_path)` once without entering it (do not use `with` here;
    just call the function — per M4-1-fix1, `stage_harness_home` validates
    the harness synchronously and raises immediately on an unsupported
    harness, before any temp directory is created, so a bare call is a
    correct, side-effect-free pre-flight check). Catch
    `credentials.CredentialStagingError` here too and fail closed the same
    way (exit code 3) — this is what makes an unsupported harness (e.g. a
    hypothetical future `omp` route against a multi-instance channel) fail
    closed instead of silently dispatching without isolation. Discard the
    returned context manager without entering it; it will be constructed
    again (this is intentional and cheap — no temp directory exists until
    something enters it) at actual dispatch time in `_execute_registered()`
    below.
- Inside `_execute_registered()`, where `dispatch = dispatch_route(...)` is
  currently called directly (line ~1841): when `credential_path` is not
  `None` (staging required, already validated above), wrap the call as:

  ```python
  with credentials.stage_harness_home(
      outcome.route.harness, credential_path
  ) as extra_env:
      dispatch = dispatch_route(
          outcome.route,
          prompt,
          workdir=args.workdir,
          timeout_seconds=args.timeout,
          stall_minutes=getattr(args, "stall_minutes", 10.0),
          progress_minutes=raw_prog if raw_prog and raw_prog > 0 else None,
          stall_action=getattr(args, "stall_action", "kill"),
          watch_dirs=owned_paths,
          extra_env=extra_env,
      )
  ```

  and when `credential_path is None`, call `dispatch_route(...)` exactly as
  today (no `extra_env` argument, or `extra_env=None` — either is fine as
  long as the call is unchanged for every existing non-staged route). The
  existing `try: ... except LLMRouterError as exc: return fail(...)` around
  this call must still wrap whichever branch runs. `CredentialStagingError`
  is not expected to be raised at this point (it was already validated
  before registration), but if catching it defensively here is simpler than
  proving it cannot happen, that is acceptable — just do not let it become
  an unhandled traceback.
- The real `$HOME` is never modified anywhere in this flow — confirm your
  own diff does not set `os.environ` directly at module or process scope.

## Tests (required)

In `tests/test_staffing_run.py`:
- `dispatch_route(..., extra_env={"HOME": "/fake/staged/home"})` with an
  injected fake `popen` captures the env actually passed to the fake popen
  and asserts it contains `HOME=/fake/staged/home` (merged over/alongside
  `os.environ`, not replacing every other existing variable the child would
  otherwise need — assert at least one unrelated inherited variable, e.g.
  `PATH`, survives untouched, proving this is a merge, not a replace).
- Without `extra_env` (existing call sites), behavior and the env passed to
  the injected fake popen are unchanged from before this packet (regression
  proof — reuse an existing test's fake-popen assertion pattern and confirm
  it still passes with no `env` key forced, or an `env` matching plain
  `os.environ` when the provenance branch doesn't apply).
- If the existing provenance-marker branch is reachable in a test today
  (real POSIX popen path), prove `extra_env` and the provenance marker can
  coexist in the same merged env without one clobbering the other.

In `tests/test_doctor.py`:
- Using a test fixture catalog/channel with declared `instances` (reuse or
  extend an existing multi-instance fixture from the M3-1/M3-2/M3-3 test
  suites — do not invent a new fixture shape if a suitable one already
  exists) and a fake credential file under `tmp_path` matching the
  resolved `credential_ref` path (inject the credentials root via
  monkeypatching `credentials.DEFAULT_CREDENTIALS_DIR` or an equivalent
  seam — do not touch the real `~/.local/state/lee-llm-router/credentials/`
  directory in any test):
  - A `run` dispatch against a route on that channel, with a real credential
    file present and an `opencode` or `pi` harness, launches (via an
    injected fake popen/dispatch path — do not spawn a real subprocess in
    tests) with a staged `HOME` env visible to the fake dispatch boundary.
  - A `run` dispatch where the resolved credential file is missing exits 3
    with a clear error, and — critically — nothing was registered (assert
    no live entry in the run registry after the call, or equivalently that
    `register_run`/the registry file was never touched; reuse this file's
    existing registry-assertion pattern) and no dispatch/popen call was
    ever attempted (inject a fake popen/dispatch spy and assert it was
    never called).
  - A `run` dispatch against a channel with **no declared `instances`**
    (today's normal single-instance channels, e.g. `openai-sub`) behaves
    identically to before this packet — no credential lookup attempted, no
    `CredentialStagingError` possible, existing tests for these channels
    continue to pass unchanged.

## Forbidden

Every other file, in particular:
- `src/lee_llm_router/staffing/credentials.py` (M4-1, already committed —
  do not modify; call into it only)
- `src/lee_llm_router/staffing/catalog.py`, `src/lee_llm_router/staffing/eligibility.py`,
  `src/lee_llm_router/staffing/block.py` (M1/M3, do not touch)
- Any real file under `~/.local/state/lee-llm-router/credentials/`
- `context.md`, `sprint-plan.md`, `result-review.md` (the supervisor updates
  these after the packet is verified)

## Before you finish

Run `.venv/bin/black src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py` (no `--check`) and `.venv/bin/ruff check --fix src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py` as your own last edits, then re-run the oracle and the full suite yourself and confirm both exit 0, before you report done.

## Oracle (deterministic, required)

Run, in order, from the repo root with the project's `.venv`:

```bash
.venv/bin/python -m pytest tests/test_staffing_run.py tests/test_doctor.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
.venv/bin/ruff check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
```

All four commands must exit 0. Do not prefix any command with `PYTHONPATH=src` — this project's `.venv` already has the package installed editable; that prefix is not valid argv for this router's own `--oracle` parser. The full-suite run must show strictly more passed tests than the pre-packet baseline (1902 passed, 6 skipped, confirmed by the supervisor after M4-1) and zero new failures.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the four owned paths above.
- Confirmation (one paragraph) that a dispatch against a single-instance
  (no declared `instances`) channel was tested and is provably unchanged.

## Stop / escalation condition

If merging `extra_env` into `launch_kwargs["env"]` cannot coexist cleanly
with the existing provenance-marker branch without restructuring watchdog
or process-tree logic beyond adding the merge itself, stop and report the
exact conflict rather than removing or weakening the provenance marker. If
no suitable multi-instance test fixture exists anywhere in
`tests/test_doctor.py`/`tests/test_staffing_run.py`/`tests/fixtures/staffing/`
to adapt, stop and report exactly what's missing rather than inventing a
new fixture convention that diverges from M3's.
