# Packet M4-1-fix2 — Black formatting only

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Second repair packet for `docs/staffing/packets/M4-1-credential-staging-module.md`
(after `M4-1-fix1-eager-unsupported-harness.md` landed and passed pytest).
Direct supervisor verification: `.venv/bin/black --check
src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`
exits 1, "would reformat" both files (two long function-signature lines that
Black wants collapsed onto one line each — trivial, mechanical).

## Packet fields

Kind: impl
Owned paths: `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`
Forbidden: every other file; do not change any logic, only formatting
Oracle: `.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`
Runtime bound: 10 minutes

## Required change

Run `.venv/bin/black src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`
(no `--check`, so it rewrites in place). Do not hand-edit formatting
yourself — run the actual `black` binary and let it rewrite the files. Do not
touch any test assertion, any function body, or any behavior. Then confirm
`.venv/bin/python -m pytest tests/test_staffing_credentials.py -q` still
passes (6 passed) and `.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py
tests/test_staffing_credentials.py` still exits 0 — Black must not have
broken anything.

## Required evidence

- `.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py` → exit 0.
- `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q` → 6 passed.
- `.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py` → exit 0.
- `git diff` of both files, showing only whitespace/line-break changes, no
  logic changes.

## Stop / escalation condition

If running `black` changes anything beyond whitespace/line breaks (e.g. it
appears to want to restructure logic — it should not, Black never does
this), stop and report exactly what changed rather than accepting it.
