# Review packet — A2b (retire superseded surrogate concurrency test)

- Kind: `review`
- Author route: `pi-z-ai-glm-5-3-flash-openrouter` (attempt
  `router-run-4df1da2d422e48d9a95175c38ada3075`)
- Owned paths (read-only for you; do not edit): `tests/test_staffing_ledger.py`

## What changed

Packet `docs/staffing/packets/A2b.md` required removing the now-superseded
test-local surrogate multi-process tests (`_idempotent_import_worker`,
`_batch_import_worker`, and the two tests that drove them) from
`tests/test_staffing_ledger.py`, because packet A2a (already committed as
`1aa64cd`) added a real-import multi-process regression that supersedes
them. `test_transaction_excludes_other_processes_and_reenters_for_plain_append`
(and any other coverage of `writer_transaction`/lock behavior itself,
independent of import semantics) must be kept. All other tests in the file
must be unchanged.

## Review this diff

Run exactly:

    git -C /home/lee/projects/lee-llm-router diff HEAD~1 -- tests/test_staffing_ledger.py

(HEAD is the A2b commit if already committed by the time you run this; if
not yet committed, use `git -C /home/lee/projects/lee-llm-router diff --
tests/test_staffing_ledger.py` instead — check which applies.)

## Requirement to verify

1. `_idempotent_import_worker`, `_batch_import_worker`, and the two tests
   that invoke them via `multiprocessing`/`fork` are actually gone (grep the
   full file; do not trust a summary).
2. `test_transaction_excludes_other_processes_and_reenters_for_plain_append`
   is present and still genuinely exercises cross-process exclusion and
   re-entrancy of `writer_transaction`/`append_attempt` — not weakened into
   a no-op or single-process-only test.
3. No other existing test in the file was removed, renamed, or had its
   assertions weakened. (Two structural tests — the "exactly one
   `os.open` call site" test and the "no network/subprocess/provider
   imports" test — were already updated by inherited prior work to account
   for the new lock-file descriptor and `fcntl`/`contextlib`/`threading`/
   `time` imports; confirm those updates are accurate to the current
   `ledger.py`, not that they're unchanged.)
4. Nothing outside `tests/test_staffing_ledger.py` was touched by this
   candidate.
5. Removing the surrogate tests does not drop any coverage of
   `writer_transaction`/lock primitive behavior that isn't already covered
   by the retained test or by A2a's real-import regressions.

## Oracle (run yourself; do not trust a summary)

    cd /home/lee/projects/lee-llm-router && .venv/bin/pytest -q tests/test_staffing_ledger.py
    cd /home/lee/projects/lee-llm-router && .venv/bin/black --check tests/test_staffing_ledger.py
    cd /home/lee/projects/lee-llm-router && .venv/bin/ruff check tests/test_staffing_ledger.py

Expect: all tests pass; Black reports no changes needed; Ruff reports no
findings.

## Required output location

Write your findings to `/tmp/staffing-p3-a2b-review/findings.md` (create the
directory if it does not exist). Classify each finding as Blocking,
Hardening, or Future, citing the violated requirement number above and a
reproducer for any Blocking finding. If there are no findings in a category,
say so explicitly (e.g. "Blocking: none"). End the file with a one-line
verdict: `VERDICT: PASS` or `VERDICT: FAIL`. Your chat response alone is not
evidence; the file is what the supervisor reads.

## Stop / escalation condition

If the oracle commands above do not all succeed exactly as described, stop
and report the exact failure in `findings.md`; do not guess a fix.
