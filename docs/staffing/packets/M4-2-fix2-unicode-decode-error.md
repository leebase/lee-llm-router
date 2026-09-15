# Packet M4-2-fix2 — catch UnicodeDecodeError from credential read

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Narrow repair after independent review of M4-2-fix1
(`docs/staffing/packets/M4-2-fix1-review.md`) returned REJECT with one
confirmed finding (all four previously-fixed items — auth shape, path
safety, OSError wrapping, no invented type translation — passed static
review).

## Packet fields

Kind: impl
Owned paths: `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q`
Runtime bound: 10 minutes

## Owned paths (exact)

- `src/lee_llm_router/staffing/credentials.py`
- `tests/test_staffing_credentials.py`

## Forbidden

Every other file, in particular `src/lee_llm_router/doctor.py`,
`src/lee_llm_router/staffing/run.py`, `tests/test_doctor.py`,
`tests/test_staffing_run.py` — none of those need any change for this fix.

## Confirmed finding

In `_stage_harness_home` (`src/lee_llm_router/staffing/credentials.py`,
around line 134-141):

```python
try:
    content = credential_path.read_text(encoding="utf-8")
except OSError as exc:
    raise CredentialStagingError(
        f"Failed to read credential file {credential_path}: {exc}",
        kind="staging_failed",
    ) from exc
```

`Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError` when the
file's bytes are not valid UTF-8. `UnicodeDecodeError` is a subclass of
`ValueError`, **not** `OSError` (confirmed: `issubclass(UnicodeDecodeError,
OSError)` is `False`). So a credential file containing invalid UTF-8 bytes
raises `UnicodeDecodeError` here, which is not caught by this `except
OSError` — it propagates as an unhandled exception instead of the intended
governed `CredentialStagingError`. The `except (json.JSONDecodeError,
UnicodeDecodeError, ValueError)` a few lines below (around
`json.loads(content)`) never gets a chance to run, because `read_text`
already failed before that line executes.

## Required fix

Change the `except OSError` on the `read_text` call to also catch
`UnicodeDecodeError` (e.g. `except (OSError, UnicodeDecodeError) as exc:`),
raising the existing `CredentialStagingError(kind="malformed_credential")`
for the `UnicodeDecodeError` case specifically (a decode failure is a
malformed-credential condition, not a staging/OS failure — use whichever
`kind` correctly reflects that distinction; either reuse
`"malformed_credential"` for both branches of this except, or split into
two except blocks with different `kind`s, your call, as long as an invalid-
UTF-8 credential file raises `CredentialStagingError`, never a bare
`UnicodeDecodeError`). Do not change any other behavior.

## Required test

Add a test writing a credential file containing invalid UTF-8 bytes (e.g.
`credential_path.write_bytes(b"\xff\xfe\x00invalid")`) and asserting that
`stage_harness_home(...)` (entering the `with`) raises
`CredentialStagingError` (not `UnicodeDecodeError`), with a `kind` you
choose consistently with the fix above.

## Before you finish

Run `.venv/bin/black src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py` (no `--check`) and `.venv/bin/ruff check --fix src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`, then re-run the oracle and confirm it exits 0.

## Oracle (deterministic, required)

```bash
.venv/bin/python -m pytest tests/test_staffing_credentials.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
```

All four must exit 0. Full suite must show >= 1912 passed, 6 skipped, zero
new failures.

## Required evidence

- Full stdout of all four oracle commands.
- `git diff --stat` limited to exactly the two owned paths.
