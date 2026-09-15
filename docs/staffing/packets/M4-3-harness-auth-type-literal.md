# Packet M4-3 — per-harness auth `type` literal in credential staging

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md` (M4 addendum, 23:45Z,
and status 00:30Z). M4-1/M4-2 are committed (`dca7f70`, `01e2722`); this closes the last M4 gap.

Owned paths: `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_credentials.py -q`
Runtime bound: 15 minutes
Review: independent review required after the oracle passes

## Fact (verified from the real auth files on this host, keys redacted)

- opencode `~/.local/share/opencode/auth.json`: the `opencode-go` entry is `{"type": "api", "key": …}`.
- pi `~/.pi/agent/auth.json`: the `opencode-go` entry is `{"type": "api_key", "key": …}`.

Today `_stage_harness_home` writes `{provider_key: {"type": <stored type>, "key": <stored key>}}`
with the stored credential's `type` passed through unchanged, so a pi-staged home carries `"api"`
where pi expects `"api_key"`.

## Required change

1. `_HARNESS_AUTH_LAYOUTS` carries the harness's own `type` literal alongside the auth path and
   env variables: opencode → `"api"`, pi → `"api_key"`. Keep the existing tuple/dataclass style;
   a small dataclass is acceptable if it stays inside `credentials.py`.
2. The staged entry uses the harness literal, not the stored `type`. The stored file must still
   have a string `key` (malformed otherwise); its `type`, if present, is ignored for the staged
   entry. Do not change any other behaviour (traversal checks, OSError wrapping, 0600, cleanup).
3. Tests: one assertion per harness that the staged JSON's `provider_key` entry has exactly the
   harness literal (`api` for opencode, `api_key` for pi) and the stored key; write the pi one
   first and watch it fail before fixing.

## Rules

- Do not touch files outside the owned paths. No `PYTHONPATH=src` prefixes.
- Last edits: `.venv/bin/black` and `.venv/bin/ruff check --fix` on both owned files; re-run the
  oracle; confirm exit 0; report the test count.
