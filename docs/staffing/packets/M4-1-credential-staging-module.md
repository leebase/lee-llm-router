# Packet M4-1 — credential staging module (channel instances)

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
("channel instances — many subscriptions per provider, universally"), M4
("credential staging at dispatch"). Supervised via `/supervise`.

## Packet fields

Kind: impl
Declared size: 2 files (1 new source, 1 new test), approximately 250 lines
Owned paths: `src/lee_llm_router/staffing/credentials.py` (new file), `tests/test_staffing_credentials.py` (new file)
Oracle: `pytest tests/test_staffing_credentials.py -q`
Review: independent review required after the oracle passes
Runtime bound: 30 minutes

## Objective

Add a small, self-contained module that (a) resolves a channel instance's
`credential_ref` string (e.g. `"opencode-go/b"`, already present on
`catalog.ChannelInstance`, M1) to the real credential file on disk under
`~/.local/state/lee-llm-router/credentials/`, and (b) builds a fresh,
temporary, per-run "staging home" directory containing only that one
credential, laid out at the exact relative path the target harness reads its
auth from, plus the environment variable overrides needed to point that
harness's subprocess at the staging home instead of the real `$HOME`.

This packet is a pure, independently-testable module. It is **not wired into
dispatch yet** — no other file changes, no `run.py`/`doctor.py` edits. That
wiring is M4-2, a separate packet, once this module's contract is proven.

## Background facts (from repo research, use verbatim — do not re-derive)

- The real credential convention already in production use:
  `~/.local/state/lee-llm-router/credentials/<credential_ref>.json` — e.g.
  `~/.local/state/lee-llm-router/credentials/opencode-go/b.json`. This
  matches every other `DEFAULT_*_DIR = Path("~/.local/state/lee-llm-router/<subdir>")`
  constant already in this codebase (`events.py`, `ledger.py`, `census.py`,
  `availability.py`) — follow that exact naming/placement convention for a
  new `DEFAULT_CREDENTIALS_DIR`.
- Per-harness auth file layout, confirmed against real on-disk files and the
  existing `tests/test_shims_native_smoke.py` native-smoke fixtures (read
  that file's `test_native_smoke_opencode` and `test_native_smoke_pi` for
  the proven contract, but do not import from it — it is a `@pytest.mark.native`
  fixture file, unrelated and not to be touched):
  - **opencode** (`route.harness == "opencode"`): set `HOME` to the staging
    home. The harness reads `<HOME>/.local/share/opencode/auth.json`.
  - **pi** (`route.harness == "pi"`): set both `HOME` and
    `PI_CODING_AGENT_DIR` to point at the staging home (`PI_CODING_AGENT_DIR`
    = `<staging home>/.pi/agent`). The harness reads
    `<PI_CODING_AGENT_DIR>/auth.json`, i.e. `<home>/.pi/agent/auth.json`.
  - **omp** (`route.harness == "omp"`): **do not implement.** Research found
    that omp's real auth path is a SQLite-backed credential vault managed by
    `omp auth-broker` (subcommands `serve|token|login|logout|import|migrate|status|list`),
    not a static JSON file at a fixed path — it does not fit this module's
    "copy one JSON file into a staged home" mechanism the way opencode/pi do.
    This is a genuine open question for the plan author (Chief/Lee), not
    something to invent a workaround for here. Leave omp entirely out of
    this module's supported-harness table. A caller that asks this module to
    stage a harness it does not know about (omp, codex, claude, or anything
    else) must get a clear, typed failure — never a silent no-op and never an
    improvised mechanism.

## Required changes (in `src/lee_llm_router/staffing/credentials.py`)

1. `DEFAULT_CREDENTIALS_DIR = Path("~/.local/state/lee-llm-router/credentials")`
   (unexpanded, matching the existing `DEFAULT_*_DIR` convention — callers/
   tests expand and override it, same pattern as `DEFAULT_EVENTS_DIR` etc.).

2. `class CredentialStagingError(Exception)`: carries a `message` and a
   stable machine `kind` (e.g. `"missing_credential"`, `"unsupported_harness"`),
   same shape convention as `RunSelectionError` in `run.py` (`kind` keyword,
   not a bespoke subclass per case). This is the exception M4-2 will later
   catch and turn into a fail-closed exit 3 — this packet only needs to
   define and raise it correctly, not catch it.

3. `resolve_credential_path(credential_ref: str, *, root: Path | None = None) -> Path`:
   returns `(root or DEFAULT_CREDENTIALS_DIR).expanduser() / f"{credential_ref}.json"`.
   Raises `CredentialStagingError(kind="missing_credential")` if that path
   does not exist or is not a regular file — this is the exact "fail closed
   if the credential_ref is missing" behavior the plan requires, expressed
   as a raised exception (the CLI-level exit-3 wiring is M4-2's job, not
   this function's). Never creates, modifies, or writes the resolved file —
   read-only resolution only.

4. A private mapping of the two supported harnesses to their relative auth
   path and the env vars they need, e.g. (illustrative, not prescriptive
   syntax) `{"opencode": (".local/share/opencode/auth.json", ()), "pi":
   (".pi/agent/auth.json", ("PI_CODING_AGENT_DIR",))}` — the exact shape is
   your call, but it must make harness support a explicit, enumerable set
   (`"opencode"`, `"pi"` only) rather than an implicit fallback.

5. `stage_harness_home(harness: str, credential_path: Path) -> AbstractContextManager[dict[str, str]]`
   (a `@contextlib.contextmanager` generator function is fine): on entry,
   creates a fresh temporary directory (`tempfile.mkdtemp`, prefixed
   `lee-llm-router-cred-`), creates the harness's exact relative parent
   directories inside it, copies the *bytes* of `credential_path` (already
   resolved and validated to exist by `resolve_credential_path`) to the
   exact relative auth path for that harness — the real credential file
   itself is never opened for writing, never modified, and its path is
   never included in the yielded env dict or returned by reference. Yields
   a `dict[str, str]` of every env var that harness needs, each pointing
   somewhere under the staging home (`HOME` always; plus
   `PI_CODING_AGENT_DIR` for `pi`). On exit — **always, including on
   exception** — deletes the entire staging home
   (`shutil.rmtree(..., ignore_errors=True)` is acceptable, but prefer
   raising if deletion hits an unexpected non-missing error, your call, as
   long as a normal run always cleans up). Raises
   `CredentialStagingError(kind="unsupported_harness")` immediately (before
   creating any temp directory) for any harness not in the mapping —
   including `"omp"`.

## Tests (required, in `tests/test_staffing_credentials.py`)

Use only `tmp_path` fixtures — never touch the real
`~/.local/state/lee-llm-router/credentials/` directory or any real
credential file.

- `resolve_credential_path` with a `root=tmp_path` containing
  `<tmp_path>/opencode-go/b.json` and `credential_ref="opencode-go/b"`
  returns that exact path.
- `resolve_credential_path` for a `credential_ref` whose file does not exist
  under `root` raises `CredentialStagingError` with `kind ==
  "missing_credential"`.
- `stage_harness_home("opencode", <fake credential path under tmp_path>)`:
  the yielded env dict's `HOME` points at a directory containing
  `.local/share/opencode/auth.json` with byte-identical content to the fake
  credential file; after the `with` block exits, that staging directory no
  longer exists on disk.
- `stage_harness_home("pi", ...)`: yielded env has both `HOME` and
  `PI_CODING_AGENT_DIR` set, `PI_CODING_AGENT_DIR` equals
  `<HOME>/.pi/agent`, and `<PI_CODING_AGENT_DIR>/auth.json` has the fake
  credential's exact content; cleaned up after the `with` block exits.
- `stage_harness_home("omp", ...)` raises `CredentialStagingError` with
  `kind == "unsupported_harness"`, and — this is the fail-closed proof —
  no temporary directory is left behind (assert no new entries appear
  under a scratch `tempfile.gettempdir()` prefix scan, or inject a fake
  `tempfile.mkdtemp` via monkeypatch and assert it is never called).
- Cleanup-on-exception: raising inside the `with stage_harness_home(...)`
  block still deletes the staging directory (assert the directory is gone
  after the exception propagates past the `with`).
- The two real credential file contents used across these tests must be
  fabricated fixture bytes (e.g. `{"fake": "credential"}`), never anything
  resembling a real API key or token shape.

## Forbidden

Every other file in the repository, in particular:
- `src/lee_llm_router/staffing/run.py`, `src/lee_llm_router/doctor.py` (M4-2's
  owned paths — do not wire this module into dispatch)
- `src/lee_llm_router/staffing/catalog.py` (already has everything this
  packet needs — `ChannelInstance.credential_ref` — no changes needed here)
- `tests/test_shims_native_smoke.py` (read for the proven auth-path facts
  quoted above; do not edit)
- Any real file under `~/.local/state/lee-llm-router/credentials/`
- `context.md`, `sprint-plan.md`, `result-review.md` (the supervisor updates
  these after the packet is verified, not the worker)

## Before you finish

Run `.venv/bin/black src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py` (no `--check`) and `.venv/bin/ruff check --fix src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py` as your own last edits, then re-run the oracle and the full suite and confirm both exit 0, before you report done.

## Oracle (deterministic, required)

Run, in order, from the repo root with the project's `.venv`:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_credentials.py -q
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
```

All four commands must exit 0. The full-suite `pytest -q` run must show
strictly more passed tests than the pre-packet baseline (confirm the current
baseline yourself before you start) and zero new failures.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git status --short` limited to exactly the two new owned paths above (no
  other file touched or created, including no `__pycache__`/`.pyc`).

## Stop / escalation condition

If a supported-harness's real auth-file relative path or required env vars
turn out to differ from what this packet states (e.g. you find the real
`~/.local/share/opencode/auth.json` or `~/.pi/agent/auth.json` on this
machine has a shape that contradicts the stated contract), stop and report
the exact discrepancy rather than guessing a different layout. Do not
attempt to add omp support by inventing a credential mechanism (e.g. an
`OMP_PROFILE` override or shelling out to `omp auth-broker import`) — that
is explicitly out of scope pending a ruling from the plan author.
