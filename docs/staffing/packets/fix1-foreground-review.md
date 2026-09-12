# Review packet — P3 answer-2 fix 1 (foreground dispatch in `/supervise`)

- Kind: `review`
- Author: supervisor-authored fix (Sonnet 5 high, Claude Code), not a worker
  attempt. No worker attempt id exists for this change.
- Owned paths: `src/lee_llm_router/templates/shims/supervise.md.tmpl`,
  `tests/test_shims_parity.py`

## What changed

`docs/staffing/chief-answers-p3-2.md` ruling 1 requires the `/supervise`
template to gain, near the top, an explicit foreground-execution rule,
because a prior acceptance run backgrounded a dispatched `run` and ended its
turn "to be notified" (which a headless one-shot session never is), so the
worker died with the session.

The fix adds a new `## Foreground execution` section immediately after the
two argument-form bullets and before `## Hard command boundary` in
`src/lee_llm_router/templates/shims/supervise.md.tmpl`, containing exactly:

> Run every router command in the foreground and wait for it to return. Never
> background a `run`, a review, or a rollup; `run` has its own watchdog. Do
> not end your turn while a dispatched command is running.

`tests/test_shims_parity.py`'s `test_supervise_bodies_are_parity_checked_against_d213`
gained three new `compact` substring assertions locking in the three
sentences above, so all four rendered harness targets (Claude Code, Codex,
OMP, OpenCode) are parity-checked to carry this text identically.

## Review this diff

Run exactly:

    git -C /home/lee/projects/lee-llm-router diff -- src/lee_llm_router/templates/shims/supervise.md.tmpl tests/test_shims_parity.py

## Requirement to verify

1. The new section is genuinely near the top (before the numbered execution
   loop and before the hard command boundary is reached), not buried where a
   long-running session could miss it before it starts dispatching.
2. The added text does not weaken, contradict, or duplicate any existing
   instruction (in particular the existing step 6/9/13 language about not
   ending a turn while a worker is running, and the existing hard command
   boundary).
3. The new parity assertions actually pin the exact added sentences (not a
   paraphrase) and would fail if the template text were removed or reworded.
4. No other behavior in the template changed (diff the rest of the file
   yourself; do not trust this summary).
5. The change is confined to the two owned paths above; nothing else was
   touched.

## Oracle (run yourself; do not trust a summary)

    cd /home/lee/projects/lee-llm-router && PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_shims_parity.py
    cd /home/lee/projects/lee-llm-router && PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor shims diff --command supervise

Expect: 3 passed; `shims diff --command supervise` exits 0 (no drift, since
the fix was already installed with `shims install --command supervise --apply`).

## Required output location

Write your findings to `/tmp/staffing-p3-fix1-review/findings.md` (create the
directory if it does not exist). Classify each finding as Blocking,
Hardening, or Future, citing the violated requirement and a reproducer for
any Blocking finding. If there are no findings in a category, say so
explicitly (e.g. "Blocking: none"). End the file with a one-line verdict:
`VERDICT: PASS` or `VERDICT: FAIL`. Your chat response alone is not evidence;
the file is what the supervisor reads.

## Stop / escalation condition

If the oracle commands above do not both succeed exactly as described,
stop and report the exact failure in `findings.md`; do not guess a fix.
