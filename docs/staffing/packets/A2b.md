# Packet A2b — Retire the superseded surrogate concurrency test

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

## Forbidden paths

- `src/lee_llm_router/staffing/ledger.py` (owned by packet A2a; do not edit)
- `src/lee_llm_router/staffing/import_evidence.py` (owned by packet A2a; do
  not edit)
- Any file not listed in Owned paths above

## Sequencing note (fact, not your work to redo)

This packet is dispatched after packet A2a has landed and its oracle
passes, so the real-import regression this packet's requirement refers to
already exists in `tests/test_staffing_import_benchmark.py` and/or
`tests/test_staffing_import_agent_orch.py`. Do not add or duplicate that
regression here; this packet only removes the now-superseded surrogate
tests from `tests/test_staffing_ledger.py`.

## Required evidence

Report the full output of the Oracle command above (all tests passing),
plus `.venv/bin/black --check` and `.venv/bin/ruff check` on
`tests/test_staffing_ledger.py`, plus a diff-visible confirmation that
`_idempotent_import_worker`, `_batch_import_worker`, and the two tests that
drive them are gone, and that
`test_transaction_excludes_other_processes_and_reenters_for_plain_append`
and other non-import lock-primitive coverage remain.

## Stop / escalation condition

Stop and report back without guessing if the named surrogate helpers or
tests do not exist under those names, if removing them would drop coverage
of `writer_transaction`/lock behavior that is not otherwise superseded, or
if A2a has not actually landed a real-import regression by the time this
packet is dispatched.
