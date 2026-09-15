# Packet M4-3-fix1 — staged auth file mode 0600; reject backslash refs; test hygiene

Parent: `M4-3-harness-auth-type-literal.md` (oracle green; review `M4-3-review.md` REJECTED with
two high and one medium finding). Single authorized repair for M4-3.

Owned paths: `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q`
Runtime bound: 10 minutes
Review: independent review required after the oracle passes

## Findings to close

1. **high** — the staged auth file is written with `write_text()` and never set to mode 0600.
   Required: write the file then `os.chmod(path, 0o600)` (or open with `os.open(..., 0o600)`),
   and add a test asserting `stat.S_IMODE(path.stat().st_mode) == 0o600` for both harnesses.
2. **high** — `resolve_credential_path` rejects `..` segments and a leading `/` but has no
   explicit backslash rejection. Required: reject any `credential_ref` containing `\`
   (`invalid_credential_ref`), with a test.
3. **medium** — traversal tests use the literal strings `../../etc/passwd` and `/etc/passwd`.
   Required: use neutral fabricated refs (e.g. `../outside/ref`, `/abs/outside/ref`) so no
   real system path appears in tests. No behaviour change.

## Rules

- Write each failing test first, then fix. Touch nothing outside the owned paths. No
  `PYTHONPATH=src`. Last edits: `.venv/bin/black` and `.venv/bin/ruff check --fix` on both files,
  re-run the oracle, confirm exit 0, report the test count.
