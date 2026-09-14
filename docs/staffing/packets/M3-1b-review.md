# Packet M3-1b-review — independent review of the combined M3-1 + S8 eligibility diff

- Kind: `review`; Class: `review/judge/none/s/python`; Owned paths: none (read-only; write nothing).
- Runtime bound: 20 minutes.
- Scope: the **uncommitted** diff in `/home/lee/projects/lee-llm-router` limited to
  `src/lee_llm_router/staffing/eligibility.py` and `tests/test_staffing_eligibility.py` (`git diff -- <those>`).
  Ignore every other file. Prior reviews of M3-1 alone (`docs/staffing/packets/M3-1-review.md`,
  attempts on Luna xHigh and Sol high) rejected on one regression: declared instances with an
  untagged channel record read `unknown` and vetoed the route. S8 (`docs/staffing/packets/S8-instance-inherits-channel-record.md`)
  adds inheritance of the channel-level record per the plan's M3 ruling 2.
- Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md` (M3, rulings 1 and 2).

## Judge (ACCEPT/REJECT each, with what you reproduced)
1. Per-instance veto and reserve; a route is eligible when any enabled instance is clear;
   disabled instances excluded; explicit tagged records authoritative; no leakage of one
   instance's tagged record into another.
2. Inheritance: an instance with no tagged record inherits the untagged channel record for
   headroom, badge, health and reserve; `unknown` only when the channel has no record; the reason
   text says `inherited channel record`.
3. The previously failing `tests/test_staffing_staff.py::test_auto_explicit_author_review_never_picks_the_selected_worker`
   passes unchanged. Run `python3 -m pytest -q tests/test_staffing_eligibility.py tests/test_staffing_staff.py`.
4. Live: `lee-llm-router catalog explain --role impl --class impl/deterministic/none/s/python`
   shows the OpenCode Go routes eligible with the inheritance reason against the live snapshot.
5. Nothing in `availability.py`, `staff.py`, `ladder.py`, the catalog or the schema is touched by this
   diff; never-automatic, harness-lock and role-scoped checks unchanged.
End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not run the full suite. Do not edit,
commit, stash, or write.
