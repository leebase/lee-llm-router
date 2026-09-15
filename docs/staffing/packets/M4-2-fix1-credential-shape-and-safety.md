# Packet M4-2-fix1 — correct staged auth.json shape, path safety, OSError handling

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Repair packet after independent review of M4-2
(`docs/staffing/packets/M4-2-review.md`) returned **REJECT** with three
findings, all confirmed by the supervisor reading the real on-disk files on
this machine (read-only; the real secret value was never printed or logged
by the supervisor and must never be printed or logged by you either).

## Packet fields

Kind: impl
Owned paths: `src/lee_llm_router/staffing/credentials.py`, `src/lee_llm_router/doctor.py`, `tests/test_staffing_credentials.py`, `tests/test_doctor.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_credentials.py tests/test_staffing_run.py tests/test_doctor.py -q`
Runtime bound: 40 minutes

## Owned paths (exact)

- `src/lee_llm_router/staffing/credentials.py`
- `src/lee_llm_router/doctor.py`
- `tests/test_staffing_credentials.py`
- `tests/test_doctor.py`

## Forbidden

`src/lee_llm_router/staffing/run.py` (already reviewed clean — the merge
logic for the extra environment overrides is correct and must not change);
every other file in the repository.

## Confirmed finding 1 (blocking) — wrong staged `auth.json` shape

The real credential file the router reads (path pattern:
`~/.local/state/lee-llm-router/credentials/<credential_ref>.json`) is a
**flat** JSON object: `{"type": "api", "key": "<secret>", "instance_id":
"b", "placed_at": "...", "placed_by": "..."}` (`instance_id`/`placed_at`/
`placed_by` are the router's own placement bookkeeping, not part of any
harness's auth format).

The real files each harness actually reads are **provider-keyed** —
confirmed directly against the real files present on this machine:
- `~/.local/share/opencode/auth.json` (opencode): a dict whose top-level
  keys are provider/channel ids (e.g. `"opencode-go"`, `"openai"`,
  `"openrouter"`); the `"opencode-go"` entry is exactly `{"type": "api",
  "key": "<secret>"}` — two keys only.
- `~/.pi/agent/auth.json` (pi): same shape, a dict of provider/channel ids
  (e.g. `"opencode-go"`, `"openai-codex"`, `"anthropic"`,
  `"openrouter"`); the `"opencode-go"` entry there is `{"type": "api_key",
  "key": "<secret>"}` — same `key` value as opencode's file, but note the
  `"type"` string literal differs (`"api"` for opencode's file, `"api_key"`
  for pi's file, for the same underlying credential).

The current `_stage_harness_home` (`credentials.py`) copies the resolved
credential file's raw bytes verbatim to the harness's auth path. This is
wrong two ways: (a) it never wraps the content under the provider/channel
key the harness's auth.json format requires — every harness would find no
matching entry at all; (b) it would leak the router's own bookkeeping
fields (`instance_id`, `placed_at`, `placed_by`) into that entry.

### Required fix

- `stage_harness_home` (and the private generator it delegates to) gains a
  new required parameter, e.g. `provider_key: str` — the channel id to nest
  the credential under (callers pass `outcome.route.channel`, e.g.
  `"opencode-go"`; the parameter name/position is your call, but it must be
  required, not defaulted, since silently guessing the wrong key is exactly
  this bug).
- Before writing the staged auth file, read and parse the resolved
  credential JSON file (`json.load`). It must contain a `"type"` key and a
  `"key"` key (strings); if either is missing or the file is not valid
  JSON, raise `CredentialStagingError` with a new stable `kind` (e.g.
  `"malformed_credential"`) — fail closed, do not guess or default.
- Write the staged auth file's content as
  `{provider_key: {"type": <credential's own "type" value, unmodified>,
  "key": <credential's own "key" value, unmodified>}}` — i.e. pass the
  credential's `type` value straight through **without translating it**
  (do not hardcode `"api_key"` for pi or any other harness-specific
  literal — the exact `"api"` vs `"api_key"` distinction observed above is
  explicitly **out of scope for this repair**: it will surface, if it
  matters, during the plan's already Lee-gated live two-account smoke, not
  here). Drop every other field from the source credential (`instance_id`,
  `placed_at`, `placed_by`, or anything else present) — the staged entry
  must contain exactly the two keys `type` and `key`, nothing more.
- Do not merge into or read any pre-existing content at the staged auth
  path (the staging home is always fresh/empty) — always write a single-
  entry JSON object.

## Confirmed finding 2 (high) — no path-traversal guard on `credential_ref`

`resolve_credential_path` joins `credential_ref` directly onto the
credentials root (`(root or DEFAULT_CREDENTIALS_DIR).expanduser() /
f"{credential_ref}.json"`) with no check that the result stays under that
root. A `credential_ref` containing `..` segments, or one that is itself
absolute, could resolve outside the credential store.

### Required fix

After building the candidate path, resolve both it and the root
(`Path.resolve()`, not just `expanduser()`) and verify the candidate is
`.is_relative_to(resolved_root)` (Python 3.10+ has `PurePath.is_relative_to`;
this project targets 3.10+ per `AGENTS.md`). If not, raise
`CredentialStagingError` with a stable `kind` (e.g. `"invalid_credential_ref"`)
before ever checking file existence — do not leak whether an out-of-root
path exists via a different error message than the missing-file case, but
you do not need to security-harden the message wording beyond "invalid
credential_ref" style; this is defense in depth for a value that is
normally trusted config, not adversarial input, so keep the fix simple and
correct rather than elaborate.

## Confirmed finding 3 (high) — unhandled `OSError` during staging

`_execute_registered()` in `doctor.py` only catches `(LLMRouterError,
credentials.CredentialStagingError)` around the dispatch call. If the
actual staging (`tempfile.mkdtemp`, `mkdir`, file write) inside the
`with credentials.stage_harness_home(...)` block hits an `OSError` (disk
full, permission error, etc.), it propagates as an unhandled traceback
instead of the governed exit-3 failure path.

### Required fix

In `credentials.py`, catch `OSError` around the actual staging operations
(temp dir creation, parent `mkdir`, credential read, staged-file write) and
re-raise as `CredentialStagingError` with a stable `kind` (e.g.
`"staging_failed"`), preserving the original error via `raise ... from exc`.
This means `doctor.py`'s existing `except (LLMRouterError,
credentials.CredentialStagingError)` in `_execute_registered()` already
covers it — you should not need to widen that except clause, but if you
find a path where an `OSError` can still escape uncaught after your
`credentials.py` fix, report exactly where rather than reflexively
widening the `except` in `doctor.py` to bare `OSError` (which could mask
unrelated bugs).

## Tests (required, extend the existing owned test files)

In `tests/test_staffing_credentials.py`:
- `stage_harness_home("opencode", <fake credential path>, provider_key="opencode-go")`
  with a fake credential file containing `{"type": "api", "key": "secret",
  "instance_id": "b", "placed_at": "...", "placed_by": "..."}`: the staged
  `auth.json` content is exactly `{"opencode-go": {"type": "api", "key":
  "secret"}}` — assert the full parsed JSON equals this, not just that it
  contains the right substring (this must catch both missing wrapping and
  leaked bookkeeping fields).
- Same for `"pi"`, asserting the staged file at
  `<home>/.pi/agent/auth.json` has the identical two-key shape under the
  same `provider_key`.
- A credential file missing `"type"` or missing `"key"` raises
  `CredentialStagingError(kind="malformed_credential")`.
- A `credential_ref` containing `"../"` (e.g. `"../../etc/passwd"`) passed
  to `resolve_credential_path` raises `CredentialStagingError` before any
  file-existence check succeeds (use a `root` under `tmp_path` and prove
  the traversal target, even if it happens to exist on the test machine,
  is still rejected).
- Inject a failure (e.g. monkeypatch `shutil.copyfile`... — note: after
  your fix, staging no longer uses `shutil.copyfile` for the harness auth
  file at all, since it now writes parsed/re-serialized JSON; adapt this
  test to whatever the new write call actually is, e.g. monkeypatch
  `pathlib.Path.write_text`/`json.dump` to raise `OSError`) and confirm
  `stage_harness_home` raises `CredentialStagingError(kind="staging_failed")`,
  not a bare `OSError`.

In `tests/test_doctor.py`: update every existing M4-2 test that calls
`stage_harness_home`/exercises the staged auth file's content (the three
tests added in M4-2: `test_run_dispatch_staged_credential_visible_to_harness`,
`test_run_dispatch_missing_credential_fails_closed_exit_3`,
`test_run_dispatch_unsupported_harness_fails_closed_exit_3`) so their fake
credential fixtures are well-formed `{"type": ..., "key": ...}` objects
(not the malformed token-only JSON the review flagged), and so their
assertions on the staged auth file check the correctly-wrapped
`{provider_key: {"type": ..., "key": ...}}` shape instead of the raw
verbatim bytes. Also update the call site in `doctor.py`'s `_run_run()` (and
the pre-registration validation call) to pass the new `provider_key`
argument (`outcome.route.channel`).

## Before you finish

Run `.venv/bin/black src/lee_llm_router/staffing/credentials.py src/lee_llm_router/doctor.py tests/test_staffing_credentials.py tests/test_doctor.py` (no `--check`) and `.venv/bin/ruff check --fix src/lee_llm_router/staffing/credentials.py src/lee_llm_router/doctor.py tests/test_staffing_credentials.py tests/test_doctor.py` as your own last edits, then re-run the oracle, `tests/test_staffing_run.py` (must still pass unchanged — you are not touching `run.py`), and the full suite, and confirm all exit 0, before you report done.

## Oracle (deterministic, required)

```bash
.venv/bin/python -m pytest tests/test_staffing_credentials.py tests/test_staffing_run.py tests/test_doctor.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/credentials.py src/lee_llm_router/doctor.py tests/test_staffing_credentials.py tests/test_doctor.py
.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py src/lee_llm_router/doctor.py tests/test_staffing_credentials.py tests/test_doctor.py
```

Do not prefix any command with `PYTHONPATH=src`. All four commands must
exit 0. Full suite must show strictly more or equal passed tests than the
pre-packet baseline (1909 passed, 6 skipped) and zero new failures.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the four owned paths.
- Explicit confirmation (one paragraph) that no test or source file prints,
  logs, or writes the literal secret value of any real credential — only
  fabricated `tmp_path` fixture values are ever used, matching M4-1's
  existing convention.

## Stop / escalation condition

If you find any place in the existing (already-committed) `credentials.py`
or `doctor.py` M4-2 code that reads a *real* file under
`~/.local/state/lee-llm-router/credentials/`, `~/.local/share/opencode/`,
or `~/.pi/agent/` outside of a test's `tmp_path`-scoped fixture, stop and
report it rather than "fixing" it by deleting evidence — that would be a
scope violation this packet did not introduce and must not paper over.
