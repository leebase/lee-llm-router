# Review packet — P4-5b (`/supervise` dispatch pattern for auto-backgrounding harnesses)

- Kind: `review`
- Author route (excluded from this review for independence): `agy-gemini-3-8-flash-high-gemini-sub`
- Diff to review: `git -C /home/lee/projects/lee-llm-router diff -- src/lee_llm_router/templates/shims/supervise.md.tmpl tests/test_shims_parity.py`

## What changed

`templates/shims/supervise.md.tmpl`'s `## Foreground execution` section was replaced by a new
`## Dispatch pattern` section instructing the detached-and-poll mechanic for every `run`
dispatch (worker or reviewer): start `lee-llm-router run ...` detached via
`setsid nohup bash -c "cd <repo> && lee-llm-router run ... > <log> 2>&1; echo done=$? >> <log>" < /dev/null &`;
poll in bounded foreground calls of at most 90 s each via
`timeout 90 bash -c "until grep -q '^done=' <log>; do sleep 10; done"`, repeating until it
succeeds, never a single call over 90 s, never a background tool, never ending the turn while
the log lacks `done=`; then read the attempt record before deciding. Same pattern applies to
review dispatches. `tests/test_shims_parity.py`'s
`test_supervise_bodies_are_parity_checked_against_d213` assertions were updated to match the
new section's exact text across all four rendered harness targets (Claude Code, Codex, OMP,
OpenCode). The rendered shims were reinstalled (`shims install --command supervise --apply`)
for the home targets and both the `lee-llm-router` and `chief-of-staff` project `.omp` targets;
`shims diff --command supervise` confirms zero drift in both projects.

## Requirements to verify

1. The old "Run every router command in the foreground..." instruction is completely gone —
   no lingering foreground-only wording that contradicts the new pattern.
2. The new section states the detached-start command, the bounded 90 s poll command, the
   "read the attempt record before deciding" step, and explicitly extends the same pattern to
   review dispatches.
3. The `## Hard command boundary` section and its six permitted router commands are unchanged
   and unviolated by the new section's prose (no new command is implied that isn't one of
   `staff`, `run`, `classify-failure`, `next-action`, `census`, `evidence`).
4. No provider binary (`claude`, `codex`, `agy`, `opencode`, `omp`, `pi`) is invoked directly
   anywhere in the template.
5. Scope confinement: only the two owned paths
   (`src/lee_llm_router/templates/shims/supervise.md.tmpl`, `tests/test_shims_parity.py`) are
   modified in the diff above — flag anything else as a Blocking finding.
6. The updated test assertions actually match the new template text verbatim (a drifted
   assertion that happens to still pass because it checks a substring that exists elsewhere
   would be a Hardening/Blocking finding depending on severity).

## Oracle (run yourself; do not trust a summary)

    cd /home/lee/projects/lee-llm-router && env PYTHONPATH=src .venv/bin/python -m pytest tests/test_shims_parity.py tests/test_shims.py -q

Expect: all tests pass.

## Required output

End your response with a final line exactly `REVIEW VERDICT: ACCEPT` or
`REVIEW VERDICT: REJECT`, plus a classification of any findings as Blocking, Hardening, or
Future (say "none" for empty categories).
