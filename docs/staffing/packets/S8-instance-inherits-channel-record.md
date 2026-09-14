# Packet S8 — instances inherit the channel-level availability record (M3 ruling 2)

- Kind: `impl`; Class: `impl/deterministic/none/s/python`; Declared size: 3 files, ≤ 200 lines
- Owned paths: `src/lee_llm_router/staffing/eligibility.py`, `tests/test_staffing_eligibility.py`,
  `tests/test_staffing_staff.py` (fixture additions only)
- Forbidden: everything else (`availability.py`, `staff.py`, `ladder.py`, catalog, schema).
- Runtime bound: 25 minutes. Oracle (fails first): `python3 -m pytest -q tests/test_staffing_eligibility.py tests/test_staffing_staff.py`
- Context: the uncommitted M3-1 diff in `eligibility.py` (per-instance veto/reserve, any-clear-instance
  route eligibility) was reviewed twice: correct on its own terms, REJECT on one regression —
  with instances `a`/`b` declared and an availability snapshot carrying only the untagged
  `OpenCode/Go` record (filed under the implicit instance `opencode-go`), both instances read
  `unknown` and the route is vetoed. The live snapshot is exactly that shape today, so this is a
  production regression, not a fixture problem. Plan ruling (Chief, 2026-09-14): an instance with
  no instance-qualified record **inherits the channel-level record** for headroom, badge and
  reserve; `unknown` only when the channel itself has none.

## Change
In the per-instance lookup added by M3-1, when `availability.instance_headroom(channel, instance)`
yields no record, fall back to the channel-level record (the implicit instance named after the
channel, or the channel aggregate M2b left byte-identical) and use it for that instance; mark the
row's reason with `inherited channel record` so `explain` shows it. Behaviour with tagged records is
unchanged. Do not touch `availability.py`.

## Tests (fail first)
- Declared instances `a`,`b`; snapshot with one untagged Go record at 80% ON TRACK → both instances
  eligible, reason notes inheritance; the route is eligible (this is the reviewers' failing case:
  `test_auto_explicit_author_review_never_picks_the_selected_worker` must pass again unchanged).
- Untagged record at 8% (inside reserve) → both instances vetoed by reserve.
- Tagged `a` at 80%, no record for `b`, untagged channel record at 8% → `a` eligible, `b` vetoed.
- No channel record at all → unknown, vetoed (existing behaviour).
- Fixture additions in `test_staffing_staff.py` for a tagged-instance snapshot are welcome but the
  existing untagged fixtures stay as they are.

## Required evidence
Oracle before/after; full suite `python3 -m pytest -q` count; black/ruff on the three files;
`lee-llm-router catalog explain --role impl --class impl/deterministic/none/s/python | grep opencode-go`
showing the Go routes eligible again against the live snapshot. Do not commit, stash, or write
`decisions.md`.
