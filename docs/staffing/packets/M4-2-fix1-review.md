# Review packet M4-2-fix1 — corrected auth.json shape, path safety, OSError handling

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Independent re-review after `docs/staffing/packets/M4-2-review.md`
returned **REJECT** with three findings, and
`docs/staffing/packets/M4-2-fix1-credential-shape-and-safety.md` was
dispatched to fix all three. Author route:
`agy-gemini-3-8-flash-high-gemini-sub` (excluded from this review for
independence — same author as the rejected M4-2 and its repair).

Owned paths under review (read-only for you — do not edit): `src/lee_llm_router/staffing/credentials.py`, `src/lee_llm_router/doctor.py`, `tests/test_staffing_credentials.py`, `tests/test_doctor.py`

## The three original findings, and what should now be fixed

1. **(was blocking)** Staged `auth.json` copied the resolved credential file
   verbatim instead of nesting it under the channel's provider key (e.g.
   `{"opencode-go": {"type": "api", "key": "..."}}`), and leaked router
   bookkeeping fields (`instance_id`, `placed_at`, `placed_by`) into the
   entry. Confirmed against the real files on this machine:
   `~/.local/share/opencode/auth.json` and `~/.pi/agent/auth.json` are both
   provider-keyed dicts whose `"opencode-go"` entry is exactly `{"type":
   ..., "key": ...}` (two keys only).
2. **(was high)** `resolve_credential_path` joined `credential_ref` onto the
   credentials root with no check the result stays under that root — a
   `..`-containing or absolute `credential_ref` could resolve outside the
   credential store.
3. **(was high)** `OSError` during staging (temp dir creation, file
   read/write) was not caught into the governed `CredentialStagingError`
   path, risking an unhandled traceback instead of exit 3.

Verify by actually running (do not just read):

```bash
.venv/bin/python -m pytest tests/test_staffing_credentials.py tests/test_staffing_run.py tests/test_doctor.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/credentials.py src/lee_llm_router/doctor.py tests/test_staffing_credentials.py tests/test_doctor.py
.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py src/lee_llm_router/doctor.py tests/test_staffing_credentials.py tests/test_doctor.py
```

If you have no command-execution tool available, say so explicitly and
review statically only — do not claim you ran commands you did not run.

## What to check

1. For each of the three findings above, confirm the fix is actually
   present and correct — read the exact diff, don't just trust a summary.
   In particular: does the staged `auth.json`/entry now contain **exactly**
   `{provider_key: {"type": ..., "key": ...}}` with no extra keys, for both
   `opencode` and `pi`? Does `resolve_credential_path` reject a `..`/
   absolute `credential_ref` before checking file existence? Does an
   `OSError` during staging surface as `CredentialStagingError`, not a bare
   traceback?
2. **No invented translation:** confirm the fix does **not** hardcode a
   `"type"` value translation (e.g. forcing `"api_key"` for `pi`) — the
   credential's own `type` field must pass through unmodified. This was
   explicitly declared out of scope for this repair (deferred to the
   plan's already-gated live smoke); a reviewer should flag it as a defect
   if the worker invented a translation anyway, since that would be
   unverified guessing about harness internals this repo cannot check.
3. **No real secrets touched:** confirm no test or source file reads,
   writes, prints, or logs a real credential value — only `tmp_path`
   fixtures.
4. **Regression safety:** confirm the three existing M4-2 tests
   (`test_run_dispatch_staged_credential_visible_to_harness`,
   `test_run_dispatch_missing_credential_fails_closed_exit_3`,
   `test_run_dispatch_unsupported_harness_fails_closed_exit_3`) were updated
   to use well-formed `{"type": ..., "key": ...}` fixtures and assert the
   correctly-wrapped shape, and that `outcome.route.channel` is what's
   passed as `provider_key` at both call sites in `doctor.py` (the
   pre-registration validation call and the actual dispatch call inside
   `_execute_registered`).
5. Any other correctness, safety, or test-quality defect you find.

## Verdict

State PASS/ACCEPT or REJECT with concrete findings, each citing the exact
line(s) and why it is a defect (not a style preference). If you ran the
commands above, quote their exit codes/output in your verdict.
