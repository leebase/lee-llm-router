# Packet M4-3-fix2 — update the M4-2 dispatch test to the M4-3 pi auth literal

Parent: `M4-3-harness-auth-type-literal.md` (committed `9ee6fbf`). M4-3 changed the staged pi auth
entry from the stored `type` to pi's own literal `api_key`; the M4-2 wiring test in
`tests/test_doctor.py` still expects `{"type": "api", …}` for the pi-staged auth file and now fails.
M4-3's oracle did not include `tests/test_doctor.py` (supervisor's scope gap).

Owned paths: `tests/test_doctor.py`
Oracle: `.venv/bin/python -m pytest tests/test_doctor.py -q`
Runtime bound: 10 minutes

Change only the expectation(s) in `tests/test_doctor.py` that assert the content of a **pi**-staged
auth file: the `opencode-go` entry's `"type"` must be `"api_key"`. Any **opencode**-staged
expectation stays `"api"`. No production code changes; no other test changes. Run the oracle and
`.venv/bin/black --check tests/test_doctor.py`; report both exit codes.
