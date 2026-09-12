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

## A2a — Concurrent import-writer control (production paths + real regression)

- Kind: `impl`
- Declared size: 4 files, at most 250 changed lines
- Owned paths: `src/lee_llm_router/staffing/ledger.py`,
  `src/lee_llm_router/staffing/import_evidence.py`,
  `tests/test_staffing_import_benchmark.py`,
  `tests/test_staffing_import_agent_orch.py`
- Requirement: both real production import entry points
  (`import_benchmark_evidence` and `import_agent_orch_evidence`) hold the
  shared per-ledger writer transaction for their whole read-decide-append
  sequence, so concurrent processes importing attempts into the same
  per-host ledger cannot interleave, lose, or duplicate accepted records.
  Preserve the append-only format, existing idempotency semantics, schema
  validation, and serialized-writer behavior. Add a deterministic
  multi-process regression that invokes at least one of the two real public
  import functions directly against a shared ledger from concurrent
  processes — never a test-local surrogate that reimplements
  read-decide-append inline instead of calling the real function — and
  proves duplicate acceptance cannot occur. The regression must fail (turn
  red) if `writer_transaction` is removed from either real import function.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_ledger.py tests/test_staffing_import_benchmark.py tests/test_staffing_import_agent_orch.py`
- Review: independent review required after the oracle passes.
- Commit: `feat(staffing P3): serialize concurrent import writers`

## A2b — Retire the superseded surrogate concurrency test

- Kind: `impl`
- Declared size: 1 file, at most 100 changed lines
- Owned paths: `tests/test_staffing_ledger.py`
- Requirement: A2a's real-import regression supersedes the test-local
  surrogate multi-process tests in this file that reimplement
  read-decide-append directly against `writer_transaction`/`append_attempt`
  instead of calling a real import function (they proved the primitive
  lock correct but not that the real import paths use it, which is exactly
  the P3-6 acceptance finding). Remove or replace the superseded surrogate
  import-simulation tests (`_idempotent_import_worker`,
  `_batch_import_worker`, and the two tests that drive them). Keep
  `test_transaction_excludes_other_processes_and_reenters_for_plain_append`
  (and any other coverage of `writer_transaction`/lock behavior itself,
  independent of import semantics) — it is still valid, non-superseded
  coverage of the locking primitive. Leave the file's other tests
  unchanged.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_ledger.py`
- Review: independent review required after the oracle passes.
- Commit: `feat(staffing P3): retire superseded import concurrency surrogate`
