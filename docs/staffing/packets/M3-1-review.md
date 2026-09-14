# Packet M3-1-review — independent review of the uncommitted per-instance eligibility diff

Kind: review
Declared size: 2 files, approximately 500 changed/added lines
Owned paths: src/lee_llm_router/staffing/eligibility.py, tests/test_staffing_eligibility.py
Oracle: none (judge review; verdict is the deliverable)
Review: n/a (this is the review)

The owned paths above are registered for conflict-freedom only — this is a
read-only review; write nothing.

Runtime bound: 20 minutes.

Scope: the **uncommitted** working-tree diff in `/home/lee/projects/lee-llm-router`
limited to `src/lee_llm_router/staffing/eligibility.py` and
`tests/test_staffing_eligibility.py` (`git diff -- <those two>`). Ignore every
other file, including untracked files elsewhere in the repo. Packet under
review: `docs/staffing/packets/M3-1-eligibility-instances.md`; plan:
`/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
(milestone M3, per the M3 design ruling at the top of that plan, 2026-09-14).
M1 (`ChannelInstance`, `Channel.effective_instances()`) and M2
(`AvailabilitySnapshot.instance_headroom()`) are already committed and must
not appear changed in this diff.

## Judge (ACCEPT/REJECT, with what you reproduced)

1. `evaluate_eligibility()`'s subscription health veto and D216 reserve check
   are now evaluated **per enabled instance** (via
   `channel.effective_instances()` and `availability.instance_headroom()`),
   not against the channel-wide aggregate. Confirm the channel-wide
   `availability_health` / `availability_badge` / `availability_headroom`
   fields on `EligibilityRow` are unchanged in meaning and still report the
   channel-wide aggregate (purely additive change, nothing repurposed).
2. A route is vetoed by health/reserve only when **every** enabled instance
   is vetoed (or there are no enabled instances at all, which adds a
   `"no enabled instance for channel '<id>'"` reason). Confirm a route with
   at least one clear enabled instance is NOT vetoed even when another
   enabled instance of the same channel is at/under reserve or exhausted.
3. New `EligibilityInstance` frozen dataclass and `EligibilityRow.instance_headrooms:
   tuple[EligibilityInstance, ...]` field (default `()`). Confirm it lists
   every *enabled* instance for the route's channel (disabled instances
   excluded entirely — not present, not marked ineligible, simply absent),
   each carrying `instance_id`, `eligible`, `reasons`, `remaining_fraction`,
   `health`, `badge`.
4. Order of `instance_headrooms`: descending `remaining_fraction` (most
   headroom first), entries with `remaining_fraction is None` sorted last.
   Reproduce this against the new
   `test_instance_headrooms_none_remaining_fraction_sorts_last` case yourself,
   not just by reading the sort key.
5. Non-subscription channels, and channels the catalog doesn't recognize,
   carry an empty `instance_headrooms` tuple — confirm via
   `test_non_subscription_channel_carries_empty_instance_headrooms`.
6. A channel with no declared `instances` in `channels.yaml` (the implicit
   single-instance case) behaves byte-identically to the pre-diff eligibility
   result for that route — same `reasons`, same `eligible`. Confirm via
   `test_channel_with_no_declared_instances_behaves_byte_identically` and by
   inspecting that the implicit instance id equals the channel id (M1
   convention).
7. Harness-lock (`channel.harness_lock`) and never-automatic/role-scoped
   checks are untouched by this diff — confirm the diff does not touch those
   lines or their tests.
8. Run the oracle yourself: `pytest tests/test_staffing_eligibility.py -q`
   (from the repo root) and confirm it passes; also run `pytest -q` (full
   suite) and confirm no new failures elsewhere.
9. `black --check` and `ruff check` on the two owned Python files pass.
10. Nothing outside the two owned files is touched by this diff (`git status
    --short` / `git diff --stat`) — anything that changes `staff.py`,
    `block.py`, `run.py`, `doctor.py`, `availability.py`, `catalog.py`, or any
    `config/staffing/**` fixture is contract-blocking and out of scope for
    this packet (that is M3-2/M3-3, not started yet).

End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not edit,
commit, stash, or write anything.
