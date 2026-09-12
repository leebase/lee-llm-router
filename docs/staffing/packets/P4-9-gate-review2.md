# Gate Re-Review Packet — Phase 4 (Staffing Migration), D215 ruling 5

Independent, read-only re-review. Your first review round (round 1) issued
`REVIEW VERDICT: REJECT` with 4 contract-blocking findings against Phase 4. All four have
since been fixed and committed; confirm each fix independently rather than trusting this
description.

## The four findings and what changed

1. **Judge prompt contradicted its enforced schema.** `build_judge_packet`
   (`agent-orch/src/agent_orch/semantic.py`) now explicitly instructs the judge to include
   `rejection_kind` (one of `capability_rejected`/`spec_rejected`/`content_defect`) whenever
   `passed` is `false`, matching `SEMANTIC_VERDICT_SCHEMA`'s `if`/`then` requirement. New test
   `test_judge_packet_instructs_rejection_kind_on_a_false_verdict`.

2. **P4-7's `derive_task_type` never obtained a task type from the real CLI.**
   `auto-orch/src/auto_orch/auto_crew.py`'s `derive_task_type` now reads `class_key` from the
   payload's top level first (falling back to `class_derivation.class.class_key`), matching
   `resolve_role_route`'s own precedence — not the never-populated
   `class_derivation.class_key` it read before. New test `test_derive_task_type_with_real_cli`
   (no catch-and-skip on any failure once the binary is confirmed present, same discipline as
   P4-8's `test_resolve_role_route_with_real_cli`).

3. **`ESCALATE` could record a transition that never executes.** `agent-orch/src/agent_orch/
   engine.py`'s escalation eligibility check now requires `attempt_number < last_attempt` in
   addition to the existing ladder/verdict checks — a `capability_rejected` verdict on a
   step's own final allowed attempt now correctly falls through to `HALT`/`FAILED` instead of
   recording an `ESCALATE` decision the enclosing `for attempt_number in range(first_attempt,
   last_attempt + 1)` loop can never act on. New boundary test
   `test_escalate_on_final_attempt_halts_instead_of_a_phantom_transition` (`max_attempts=1`).

4. **Sealed playbooks lost `escalation` on resume.** `EscalationIntent.to_payload()` added
   (`agent-orch/src/agent_orch/models.py`, mirroring `RoutingPreference`/
   `TokenExhaustionFallbackIntent`); `_snapshot_step_payload` (`engine.py`) now serializes
   `step.escalation` when present. The load side (`playbook.py`'s `_parse_escalation`) was
   already correct from the P4-8 fix (`7296c38`) — only the seal side was missing. New
   round-trip test `test_playbook_snapshot_round_trips_step_escalation`.

Commits: `agent-orch` `88ce8ac`; `auto-orch` `e345126`.

## What to check

1. Read each diff (`git -C /home/lee/projects/agent-orch show 88ce8ac`;
   `git -C /home/lee/projects/auto-orch show e345126`). Confirm each fix actually addresses
   the finding you raised, not just something plausible-looking.
2. Reproduce at least the class_key finding (#2) and the escalation-snapshot finding (#4)
   yourself directly against the real CLI / a small Python snippet — don't just re-read code.
3. Re-run the four new/changed tests directly, then the full suites:
   - `agent-orch`: `.venv/bin/python -m pytest -q` — expect 1940 passed, 9 skipped, 3 failed
     (the same pre-existing `tests/test_codex_usage.py` failures from round 1, unchanged by
     this diff).
   - `auto-orch`: `.venv/bin/python -m pytest -q` — expect 1514 passed, 2 skipped, 1 failed
     (the same pre-existing `test_end_to_end_failed_run_increments_and_third_fire_halts`,
     unchanged by this diff).
   - `lee-llm-router`: unchanged since round 1 — 1717 passed, 1 skipped, 0 failed.
   If your sandbox's counts differ from these (round 1's sandbox reported 104 agent-orch
   failures against a 3-failure baseline, attributed to Chromium/socket/read-only-fixture
   restrictions specific to that sandbox, not to any Phase 4 change) — say so explicitly and
   explain the discrepancy rather than silently reporting a different number as if it
   contradicts this packet.
4. Confirm no new regression was introduced by these four fixes (compare against your own
   round-1 findings — nothing here should touch anything you didn't flag).

Everything else from round 1 (D216 reserve, never-invent-usage, route/authority discipline,
the two recorded needs-lee items, gate (a)/(b) live evidence) already passed your review and
does not need re-verification unless this diff plausibly affects it (it doesn't).

## Report

Classify any remaining findings as Contract-blocking / Non-blocking hardening / Future
concern (D209). End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`.
