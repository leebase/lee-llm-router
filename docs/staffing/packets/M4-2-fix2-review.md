# Review packet M4-2-fix2 — UnicodeDecodeError now caught

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Third-round independent review of the M4 credential-staging dispatch
wiring. Prior rounds: M4-2 (REJECT, 3 findings), M4-2-fix1 (fixed all 3;
re-review REJECT, 1 new finding — `UnicodeDecodeError` from
`credential_path.read_text(encoding="utf-8")` not caught before the
malformed-credential handler), M4-2-fix2 (this round's subject — narrow fix
for exactly that one finding). Author route:
`agy-gemini-3-8-flash-high-gemini-sub` (excluded for independence).

Owned paths under review (read-only for you — do not edit): `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`

## Full context, so you don't need to re-derive it

M4-1 (committed) built a credential-staging module. M4-2 (uncommitted, still
pending this review chain) wires it into `lee-llm-router run` dispatch in
`doctor.py`/`run.py`. Across two prior rejected rounds, four things were
found and fixed: (1) staged `auth.json` now correctly nests the credential
under the channel's provider key instead of copying raw bytes; (2)
`resolve_credential_path` now rejects a `..`/absolute `credential_ref`
before checking existence; (3) `OSError` during staging now converts to
`CredentialStagingError` instead of an unhandled traceback; (4) — the
subject of this round — `UnicodeDecodeError` from reading a non-UTF-8
credential file now also converts to `CredentialStagingError(kind=
"malformed_credential")` instead of escaping uncaught.

Verify by actually running (do not just read):

```bash
.venv/bin/python -m pytest tests/test_staffing_credentials.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
```

If you have no command-execution tool available, say so explicitly and
review statically only.

## What to check

1. Confirm `credential_path.read_text(encoding="utf-8")` (or however it is
   now written) can no longer raise an exception that escapes uncaught: a
   credential file containing invalid UTF-8 bytes must raise
   `CredentialStagingError`, not `UnicodeDecodeError`.
2. Confirm the new test actually writes genuinely invalid UTF-8 bytes (not
   valid UTF-8 that merely fails JSON parsing — those are two different
   failure modes) and asserts the correct exception type.
3. Confirm nothing else in this file regressed — re-check (quickly; these
   were already reviewed clean twice) that the auth-shape wrapping, path-
   traversal guard, and OSError handling are all still intact and untouched
   in ways that would reintroduce a prior defect.
4. Any other correctness or test-quality defect you find in this narrow
   diff.

## Verdict

State PASS/ACCEPT or REJECT with concrete findings, each citing exact
line(s). If you ran the commands above, quote their exit codes/output.
