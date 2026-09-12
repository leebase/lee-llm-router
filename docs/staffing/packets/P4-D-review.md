# Group D Review Packet — Phase 4.1 follow-ups (D219 rulings 1-3, P4-14)

Independent, read-only review. You did not author any of this. Read every diff yourself
and reproduce claims directly — do not accept this description on faith.

Authority: `chief-of-staff/decisions.md` D219 (Phase 4.1/"Group D" follow-ups before
Phase 5) on the D215/D211/D209 baseline. Four commits across three repos, one packet group
(all four are in scope for this single review):

1. `lee-llm-router` `44d7d2b` — P4-10: `route show <route_id> [--json]`, a new CLI
   subcommand disclosing the catalog's full route record (model, effort, harness, channel,
   dispatch_template, usage_capture, status, status_reason, proof_status) for one route id.
   Command: `git -C /home/lee/projects/lee-llm-router show 44d7d2b`
2. `auto-orch` `8f40e2b` — P4-11 + P4-13: `resolve_role_route` now resolves harness/model/
   effort from `route show` instead of the naming-convention-harness + `price`-based-model
   workaround (naming convention kept only as a fail-closed cross-check); and the `auto`
   crew now resolves `reviewer`/`judge` with `--author-route <primary's route>` so a governed
   review is never staffed from the same route/family as the work it reviews (D211 ruling 5).
   Command: `git -C /home/lee/projects/auto-orch show 8f40e2b`
3. `agent-orch` `0b2f7d6` — P4-12: the user-simulation gate's `user_journeys_execution_verified`
   validator now re-executes a claimed bare `python`/`python3` command against the target
   workspace's own `.venv/bin/python` when present (else `python3`), and records the resolved
   `interpreter_path` in the gate's evidence. Note in the commit message: this working tree
   carries another lane's uncommitted WIP in the same two files (structured-stdin support);
   the commit was built with a hand-crafted patch (`git apply --cached`) to stage only the
   P4-12 hunks. Verify the commit's diff is clean and self-contained on its own terms; you do
   not need to inspect the other lane's unstaged WIP.
   Command: `git -C /home/lee/projects/agent-orch show 0b2f7d6`
4. `lee-llm-router` `097039f` — closeout docs from one live `auto-orch run-cycle
   staffing-proof` (cycle `20260912T124316Z`, run `003dd9f505b8`) run under the P4-11/P4-12/
   P4-13 fixes above: `WHERE_AM_I.md`/`context.md`/`result-review.md`/`sprint-plan.md` updates
   plus review/smoke evidence files the governed run itself produced. No production source
   changed in this commit — verify that claim by reading the diff.
   Command: `git -C /home/lee/projects/lee-llm-router show 097039f`

## Time-boxing (read this first)

Do not launch the full pytest suites in any repo yourself — each takes minutes and your own
prior attempt at this packet returned prematurely ("launched ... and am waiting") without ever
reporting a verdict, after starting exactly those full-suite commands. The supervisor has
already run every full suite directly and will not re-trust a claim you did not personally
observe complete, so instead: run only the small, fast, targeted commands named below (each
takes at most a few seconds), read the four diffs directly with `git show`, and reason from
those plus the JSON evidence files named below. Finish and print your verdict in a single pass
— do not defer any command to "wait for it to finish" and end your turn before reporting.

## What to check

1. **P4-10 correctness.** Does `route show` disclose exactly the documented fields, no more
   (i.e. it must not leak selection/ranking logic — this is disclosure, not eligibility) and
   no less? Does an unknown route id fail closed (exit 3)? Reproduce:
   `cd /home/lee/projects/lee-llm-router && PYTHONPATH=src .venv/bin/python -m
   lee_llm_router.doctor route show codex-gpt-5-6-sol-low-openai-sub --json` and
   `... route show nonexistent-route-id --json` (expect exit 3) yourself.
2. **P4-11 fail-closed cross-check.** Confirm `resolve_role_route` actually raises
   `RouteUnavailable` when `route show`'s harness disagrees with the naming-convention
   prefix, not merely trusts one source. Read the test
   `test_resolve_role_route_unmapped_harness` and its route-show-consistent fixture wiring.
3. **P4-13 independence.** Confirm the `auto` crew resolves `reviewer`/`judge` with
   `--author-route` set to the primary's route id (not to `None`, not to a hardcoded
   constant), and that the `auto-crew-mandate.json` artifact records `author_route`/
   `independence_reason` per role. Reproduce the real-CLI test yourself:
   `cd /home/lee/projects/auto-orch && .venv/bin/python -m pytest -q
   tests/test_auto_orch_auto_crew.py -k real_cli`.
4. **P4-12 interpreter resolution and evidence.** Confirm `_apply_gate_interpreter` only
   rewrites a bare `python`/`python3` argv[0] (never other executables), resolves
   `.venv/bin/python` correctly relative to the *workspace* being validated (not the
   orchestrator's own environment), and that the chosen interpreter path lands in the
   per-command evidence entry. Reproduce:
   `cd /home/lee/projects/agent-orch && .venv/bin/python -m pytest -q tests/test_validators.py
   -k "gate_interpreter or execution_verified"`.
5. **Live-cycle evidence is real, not narrated.** Open
   `/home/lee/projects/lee-llm-router-agent-orch-runs/003dd9f505b8/steps/step_08b_user_simulation_gate/attempt-1/validation.json`
   yourself and confirm the `user_journeys_execution_verified` outcome's `passed` is `true`
   with `interpreter_path` set to `/home/lee/projects/lee-llm-router/.venv/bin/python` on
   every command entry, and that
   `/home/lee/projects/auto-orch/missions/staffing-proof/cycle-reports/20260912T124316Z.yaml`
   really does say `cycle_outcome: success` and `run_passed: true`.
6. **Suite health (targeted only — do not run a full suite).** The supervisor personally ran
   every full suite and reports: router 1725 passed/1 skipped/0 failed (was 1717/1/0 before
   P4-10's 8 new tests); agent-orch 1949 passed/9 skipped/3 failed (was 1940/9/3 before P4-12's
   5 new tests, same 3 pre-existing `test_codex_usage.py` failures, unchanged); auto-orch 1515
   passed/2 skipped/1 failed (was 1514/2/1 before P4-11/P4-13's 1 net new test, same 1
   pre-existing failure, unchanged). Spot-check this claim with only the fast targeted commands
   in items 2-4 above, not a full run.
7. **P4-14 (bisection claim).** This session bisected the three pre-existing
   `test_codex_usage.py` failures to agent-orch commit `4270736` ("fix: bound worker
   validation and recover timeout usage", 2026-09-11, NOT a Phase 4 commit) via a
   `git worktree` per commit — confirmed the P0 baseline `d166e4d` passes 15/15, and that
   `4270736` is the first commit in the range where the same 3 tests fail. No Phase 4 commit
   (`af5dea5`, `39a0457`, `7751a07`, `7296c38`, `88ce8ac`) introduced or touched this
   regression. Spot-check this claim: reproduce at least one bisection point yourself (e.g.
   worktree `d166e4d` should pass, worktree `4270736` should fail the same 3 tests) rather
   than accepting the narrative.

## Boundaries

- Read-only. Do not edit, commit, or `git add` anything in any of the three repos.
- Do not touch `missions/staffing-proof/` beyond reading it, and do not touch any other
  uncommitted working-tree changes you notice in any of the three repos (multiple lanes have
  in-progress WIP; that is expected and out of scope for this review).

## Response contract

End with a line `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. If REJECT, list every
contract-blocking finding with the exact file/line/command that reproduces it. Findings that
are stylistic/hardening-only should be listed separately and must not block ACCEPT.
