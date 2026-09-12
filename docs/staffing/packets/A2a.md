# Packet A2a — Concurrent import-writer control (production paths + real regression)

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

## Forbidden paths

- `tests/test_staffing_ledger.py` (owned by packet A2b; do not edit)
- Any file not listed in Owned paths above

## Inherited state (fact, not your work to redo)

The working tree already contains an uncommitted candidate from a prior
rejected attempt:

- `src/lee_llm_router/staffing/ledger.py` already defines `writer_transaction`
  (a re-entrant, cross-process-exclusive `flock`-backed context manager) and
  `append_attempt` already re-enters it when called inside an open
  transaction.
- `src/lee_llm_router/staffing/import_evidence.py` already wraps the entire
  read-decide-append body of both `import_benchmark_evidence` and
  `import_agent_orch_evidence` in `with writer_transaction(target):`.

Review this inherited code for correctness as part of this packet (it is in
your owned paths), but do not treat it as unproven — check it, don't assume
it. The prior attempt was rejected specifically because its multi-process
regression test called a test-local surrogate (`_idempotent_import_worker`
/ `_batch_import_worker` in `tests/test_staffing_ledger.py`) that
reimplemented read-decide-append directly against
`writer_transaction`/`append_attempt`, instead of calling a real import
function. That regression proved the locking primitive correct but never
proved the two production import functions actually use it — a regression
that would stay green even if `writer_transaction` were deleted from
`import_benchmark_evidence` or `import_agent_orch_evidence`. Do not reuse or
adapt that surrogate; do not edit `tests/test_staffing_ledger.py` at all —
it is forbidden here and a separate packet (A2b) retires the surrogate
tests there.

## Regression requirement, precisely

Add the multi-process regression to `tests/test_staffing_import_benchmark.py`
or `tests/test_staffing_import_agent_orch.py` (your choice of one or both).
It must:

- Invoke at least one of `import_benchmark_evidence` or
  `import_agent_orch_evidence` directly (the real public function, not a
  reimplementation of its internals) from concurrent OS processes against
  one shared ledger file.
- Prove that duplicate acceptance cannot occur under that concurrency (for
  example: import overlapping/duplicate rows across processes and assert
  the final ledger has each attempt exactly once, or an equivalent
  deterministic proof).
- Fail (turn red) if `writer_transaction` is removed from either real
  import function. Verify this directly before finishing: temporarily
  comment out the `with writer_transaction(target):` wrapping (dedenting
  the body) in one of the two functions, run only your new test, confirm it
  fails, then restore the code and confirm it passes again. Do not leave
  that temporary modification in your final diff.
- Be deterministic — no reliance on sleep-based timing races to prove
  exclusion; use a barrier or equivalent synchronization so processes
  genuinely overlap.

## Required evidence

Report the full output of the Oracle command above (all tests passing), plus
`.venv/bin/black --check` and `.venv/bin/ruff check` on any production files
you changed.

## Stop / escalation condition

Stop and report back without guessing if: the real import functions'
read-decide-append boundaries are ambiguous, the inherited
`writer_transaction` implementation appears unsound in a way you cannot
safely fix within owned paths, or proving the "fails if writer_transaction is
removed" requirement deterministically is not possible without flaking.
