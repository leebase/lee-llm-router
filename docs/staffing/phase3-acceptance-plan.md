# Phase 3 acceptance plan

Execute both packets through the installed `/supervise` protocol with crew
`sol-low-glm-pi`. Each accepted packet must be its own reviewed commit.

## A1 — Text explain tier-kind parity

- Kind: `impl`
- Declared size: 2 files, at most 80 changed lines
- Owned paths: `src/lee_llm_router/doctor.py`,
  `tests/test_staffing_catalog_explain.py`
- Requirement: the human-readable `catalog explain` terms disclosure includes
  each effective channel tier's `kind`, matching the already-authoritative JSON
  terms view. Preserve all existing JSON fields and selection behavior.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_catalog_explain.py`
- Review: independent review required after the oracle passes.
- Commit: `feat(staffing P3): expose tier kind in text explain`

## A2 — Concurrent import-writer control

- Kind: `impl`
- Declared size: 2 files, at most 180 changed lines
- Owned paths: `src/lee_llm_router/staffing/ledger.py`,
  `tests/test_staffing_ledger.py`
- Requirement: concurrent processes importing attempts into the same per-host
  ledger cannot interleave, lose, or duplicate accepted records. Preserve the
  append-only format, existing idempotency semantics, schema validation, and
  serialized-writer behavior. Add a deterministic multi-process regression.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_ledger.py`
- Review: independent review required after the oracle passes.
- Commit: `feat(staffing P3): serialize concurrent import writers`

