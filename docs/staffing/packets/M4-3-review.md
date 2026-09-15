# Review packet — M4-3 (per-harness auth `type` literal)

You are the independent reviewer. Author route: `agy-gemini-3-8-flash-high-gemini-sub`.
Read `docs/staffing/packets/M4-3-harness-auth-type-literal.md` (the packet) and the current
uncommitted diff of the two owned files (`git diff -- src/lee_llm_router/staffing/credentials.py
tests/test_staffing_credentials.py`). Owned paths are read-only for you — do not edit anything.

Verify, citing exact lines:
1. The staged auth entry uses the harness literal (`opencode` → `api`, `pi` → `api_key`), not the
   stored credential's `type`, and there is one test per harness asserting the literal.
2. Nothing else regressed: traversal rejection (`..`, leading `/`, backslash), `malformed_credential`
   (missing `key`, invalid JSON, invalid UTF-8), OSError → `CredentialStagingError`, staged file 0600,
   cleanup in `finally`, `provider_key` still required.
3. No real credential path or secret appears in tests (fabricated `tmp_path` values only).

If you can run commands, run `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q`,
`.venv/bin/black --check` and `.venv/bin/ruff check` on the two files and quote exit codes. If you
cannot, say so and review statically only — never claim to have run something you did not.

Output exactly one JSON object: {"verdict": "PASS" | "REJECT", "findings": [{"severity", "location",
"finding"}], "verification": {...}}.
