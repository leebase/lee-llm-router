# Packet S4-review — independent review of the unrouted-legacy-groups change

- Kind: `review`; Class: `review/deterministic/none/s/python`; Owned paths: none (read-only).
- Scope: lee-llm-router working tree, uncommitted changes to exactly two files:
  `src/lee_llm_router/staffing/evidence_report.py` and
  `tests/test_staffing_evidence_report.py`. This is the cumulative result of one
  implementation attempt (`router-run-a04b0583a9bb485da6bd9e5990792fac`) plus three
  repair/escalation attempts that only fixed Black formatting
  (`router-run-015ffe8e8b9346f1b8a0e9f13f3f06fb`, `router-run-a01ec8f4f0d5444a81141cf75d5dceb3`,
  `router-run-351ed96d8f014bfa9b6590db31fea72b`). Authority: Chief of Staff, 2026-09-13
  (plan `plans/supervise-acceptance-2026-09-13.md`, the first `/supervise` acceptance case).

## Requirement under review

In `render_evidence_report` (`src/lee_llm_router/staffing/evidence_report.py`):
1. Routed groups (`route_id` not `None`) print first under the existing
   `Classes (N groups):` heading, where `N` counts only routed groups.
2. Unrouted groups print afterwards under a new heading
   `Unrouted legacy groups (M groups, no router route recorded):`, with the same
   per-group line format, unchanged.
3. `build_evidence_report`'s JSON output (`"classes"` list) is unaffected — same list,
   same order, same fields as before. No change to aggregation, `_route_changes`,
   channels, or source rows.
4. Only the two owned files changed; nothing else in the repo.

## Judge (ACCEPT/REJECT, with what you reproduced)

1. Read `git diff src/lee_llm_router/staffing/evidence_report.py` and confirm it changes
   only the text-rendering loop in `render_evidence_report`, matches points 1-2 above
   exactly (including the exact heading text and count semantics), and does not touch
   `build_evidence_report`, `_route_changes`, `_enrich_group`, `_channel_headroom_rows`,
   or any aggregation helper.
2. Read `git diff tests/test_staffing_evidence_report.py` and confirm the new/changed
   tests actually exercise: (a) a mixed report renders routed groups first with the
   correct `N`, then the unrouted heading with the correct `M`; (b) a report with zero
   unrouted groups omits the second heading entirely; (c) `build_evidence_report(...)`'s
   `classes` list/order/fields are unchanged for a fixture with both routed and
   unrouted groups.
3. Run `python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py`
   and confirm it passes with no failures.
4. Run `python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py`
   and `python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py`
   and confirm both are clean.
5. Run `git status --short` and confirm no file outside the two owned files was
   modified by this change (pre-existing unrelated untracked files in the tree are not
   in scope and are not a finding).
6. Anything that changes the JSON contract, silently reorders `classes`, mis-counts
   `N`/`M`, or leaves a forbidden file modified is contract-blocking.

End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not run the full
suite. Do not edit, commit, stash, install shims, or write any file.

## Runtime bound

10 minutes.
