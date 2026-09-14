# Packet M4-1-fix1 — eager unsupported-harness check

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Repair packet for `docs/staffing/packets/M4-1-credential-staging-module.md`
after direct supervisor verification found a real defect (not a platform/tooling
issue): `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q` →
`1 failed, 5 passed`.

## Packet fields

Kind: impl
Owned paths: `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`
Forbidden: every other file, in particular anything under `src/lee_llm_router/staffing/run.py` or `src/lee_llm_router/doctor.py` (M4-2, not this packet)
Oracle: `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q`
Runtime bound: 15 minutes

## The exact failure

```
tests/test_staffing_credentials.py::test_stage_omp_is_unsupported_before_temp_directory_creation FAILED
    with pytest.raises(CredentialStagingError) as raised:
>       stage_harness_home("omp", credential_path)
E       Failed: DID NOT RAISE CredentialStagingError
```

`stage_harness_home` is currently written as a single `@contextlib.contextmanager`
generator function. Calling `stage_harness_home("omp", credential_path)` on its
own (no `with`) only *constructs* the generator — none of the function body
runs, so the `CredentialStagingError` for an unsupported harness is never
raised until something calls `__enter__()` (i.e. actually enters a `with`
block). The packet's own test calls it bare, without `with`, and expects the
error immediately. This is a real behavioral gap, not a test bug: a caller
that does `credentials.stage_harness_home("omp", path)` and only later enters
the `with` (or checks `isinstance`/logs it before entering) would not fail
closed as early as the module's docstring and M4-1's packet both promise
("Raises `CredentialStagingError` ... immediately (before creating any temp
directory) for any harness not in the mapping").

## Required fix

In `src/lee_llm_router/staffing/credentials.py`, split `stage_harness_home`
into two pieces:
- A plain (non-generator) public function `stage_harness_home(harness, credential_path)`
  that looks up `_HARNESS_AUTH_LAYOUTS`, raises `CredentialStagingError(kind="unsupported_harness")`
  synchronously when the harness is unknown, and otherwise returns the
  context manager for the actual staging work (call sites, including the
  existing tests for `"opencode"`/`"pi"` using `with stage_harness_home(...) as env:`,
  must keep working unchanged).
- A private `@contextmanager`-decorated generator (e.g. `_stage_harness_home`)
  that does the `tempfile.mkdtemp` / copy / yield / `finally: rmtree` work
  exactly as today, called only after the harness is already known-valid.

Do not change `resolve_credential_path`, `_HARNESS_AUTH_LAYOUTS`, or anything
else in the file. Do not change the public signature or return type of
`stage_harness_home` (still usable as `with stage_harness_home(harness, path) as env:`).

## Required evidence

- `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q` → all
  tests pass (6 passed), full stdout included.
- `.venv/bin/python -m pytest -q` (full suite) → zero new failures, full
  stdout included.
- `.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`
  and `.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`
  both exit 0.
- `git diff --stat` limited to exactly `src/lee_llm_router/staffing/credentials.py`
  (the test file should not need edits — if you find you must change the
  test file too, explain exactly why in your report before doing it).

## Stop / escalation condition

If fixing this requires changing the test's expected contract (e.g. deciding
unsupported-harness detection should only happen on `__enter__`, not on bare
call), stop and report that as a design question rather than editing the
test to match a weaker implementation.
