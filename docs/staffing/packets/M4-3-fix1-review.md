# Review packet — M4-3 + M4-3-fix1 (harness auth literal; file mode; backslash refs)

You are the independent reviewer. Author route: `agy-gemini-3-8-flash-high-gemini-sub`.
Read `docs/staffing/packets/M4-3-harness-auth-type-literal.md`,
`docs/staffing/packets/M4-3-fix1-mode-and-backslash.md`, the prior review
`docs/staffing/packets/M4-3-review.md` (REJECT: 2 high, 1 medium), and the current uncommitted diff
(`git diff -- src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py`).
Owned paths are read-only for you — do not edit anything.

Verify, citing exact lines:
1. The staged auth entry uses the harness literal (`opencode` → `api`, `pi` → `api_key`), with one
   test per harness.
2. The staged auth file is mode 0600, with a test asserting `stat.S_IMODE(...) == 0o600`.
3. A `credential_ref` containing a backslash is rejected as `invalid_credential_ref`, with a test;
   `..` and leading `/` rejection remain; tests use fabricated neutral refs only.
4. Nothing else regressed: `malformed_credential` cases, OSError wrapping, cleanup in `finally`,
   required `provider_key`, no real secret or real system path in tests.

If you can run commands, run `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q`
and quote the exit code; otherwise say you reviewed statically only.

Output exactly one JSON object: {"verdict": "PASS" | "REJECT", "findings": [{"severity", "location",
"finding"}], "verification": {...}}.
