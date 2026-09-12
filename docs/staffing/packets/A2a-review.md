# Review packet — A2a (concurrent import-writer control)

- Kind: `review`
- Author route: `pi-z-ai-glm-5-3-flash-openrouter` (attempt
  `router-run-abbf02182abc472ba435aa82d29886b1`)
- Owned paths (read-only for you; do not edit production code):
  `src/lee_llm_router/staffing/ledger.py`,
  `src/lee_llm_router/staffing/import_evidence.py`,
  `tests/test_staffing_import_benchmark.py`,
  `tests/test_staffing_import_agent_orch.py`

## What changed

Packet `docs/staffing/packets/A2a.md` required both real production import
entry points (`import_benchmark_evidence` and `import_agent_orch_evidence`)
to hold the shared per-ledger writer transaction across their whole
read-decide-append sequence, and required a deterministic multi-process
regression that calls one of the two real public import functions directly
(never a test-local surrogate) and proves duplicate acceptance cannot occur.

## Review this diff

Run exactly:

    git -C /home/lee/projects/lee-llm-router diff -- src/lee_llm_router/staffing/ledger.py src/lee_llm_router/staffing/import_evidence.py tests/test_staffing_import_benchmark.py tests/test_staffing_import_agent_orch.py

## Requirement to verify

1. Both `import_benchmark_evidence` and `import_agent_orch_evidence` wrap
   their entire read-decide-append body (from reading existing records
   through every `append_attempt` call) in `writer_transaction`, not just
   part of it.
2. `writer_transaction` in `ledger.py` is genuinely cross-process exclusive
   (uses an OS-level lock such as `flock`, not an in-process-only
   `threading.Lock`), re-enters safely when `append_attempt` is called
   inside an already-open transaction on the same thread, and fails closed
   (raises rather than silently proceeding unserialized) if the lock cannot
   be acquired.
3. The append-only ledger format, existing idempotency semantics (duplicate
   `attempt_id` handling), and schema validation are unchanged for
   single-writer callers.
4. The new regression test(s) in `test_staffing_import_benchmark.py` and/or
   `test_staffing_import_agent_orch.py` call the real public
   `import_benchmark_evidence`/`import_agent_orch_evidence` function from
   genuinely concurrent OS processes against one shared ledger file — not a
   reimplementation of read-decide-append against `writer_transaction`/
   `append_attempt` directly. Confirm this by reading the test body, not by
   its name.
5. The regression proves duplicate acceptance cannot occur (e.g. the final
   ledger has each attempt/row exactly once despite every process racing
   the same input).
6. The regression is deterministic (a barrier or equivalent synchronization
   forces genuine overlap; it does not rely on sleep-based timing).
7. Verify directly that the regression fails without the fix: comment out
   (or otherwise disable) the `with writer_transaction(target):` wrapping in
   one of the two real import functions, run only the new regression
   test(s), confirm they fail, then restore the file exactly
   (`git checkout -- src/lee_llm_router/staffing/import_evidence.py`) before
   finishing.
8. Nothing outside the owned paths above was touched, and
   `tests/test_staffing_ledger.py` was not edited by this candidate (that
   file is a separate packet's, A2b, forbidden here).

## Oracle (run yourself; do not trust a summary)

    cd /home/lee/projects/lee-llm-router && .venv/bin/pytest -q tests/test_staffing_ledger.py tests/test_staffing_import_benchmark.py tests/test_staffing_import_agent_orch.py
    cd /home/lee/projects/lee-llm-router && .venv/bin/black --check src/lee_llm_router/staffing/ledger.py src/lee_llm_router/staffing/import_evidence.py
    cd /home/lee/projects/lee-llm-router && .venv/bin/ruff check src/lee_llm_router/staffing/ledger.py src/lee_llm_router/staffing/import_evidence.py

Expect: all tests pass; Black reports no changes needed; Ruff reports no
findings.

## Required output location

Write your findings to `/tmp/staffing-p3-a2a-review/findings.md` (create the
directory if it does not exist). Classify each finding as Blocking,
Hardening, or Future, citing the violated requirement number above and a
reproducer for any Blocking finding. If there are no findings in a category,
say so explicitly (e.g. "Blocking: none"). End the file with a one-line
verdict: `VERDICT: PASS` or `VERDICT: FAIL`. Your chat response alone is not
evidence; the file is what the supervisor reads.

## Stop / escalation condition

If the oracle commands above do not all succeed exactly as described, or if
requirement 7's disable-and-confirm-red step cannot be performed
deterministically, stop and report the exact failure in `findings.md`; do
not guess a fix.
