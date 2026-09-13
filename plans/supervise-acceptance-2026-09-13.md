# Plan: evidence report — separate the unrouted legacy groups (acceptance run for /supervise)

Repo: `/home/lee/projects/lee-llm-router`. Authority: Chief of Staff, 2026-09-13, as the first
/supervise acceptance case (Lee: small real packet, bounded runtime, one repair/escalation,
deterministic oracle, independent review). The change itself is a real, reviewed
non-blocking note from the Phase 5 review (D222).

## What to build

In `src/lee_llm_router/staffing/evidence_report.py`, `render_evidence_report` prints all class
groups in one list; groups whose `route_id` is `None` (legacy imports with no router route)
dominate the top of the report and obscure the routed evidence. Change the text renderer so:

1. Routed groups (`route_id` not None) print first under the existing `Classes (N groups):`
   heading, where N counts only routed groups.
2. Unrouted groups print afterwards under a new heading
   `Unrouted legacy groups (M groups, no router route recorded):` with the same per-group
   lines, unchanged.
3. The JSON output (`--json`) is unchanged: same `classes` list, same order, same fields.
   Do not touch aggregation, `_route_changes`, channels, or source rows.

Owned files: `src/lee_llm_router/staffing/evidence_report.py` and
`tests/test_staffing_evidence_report.py` only. Forbidden: everything else, including
`doctor.py` and `tests/test_doctor_evidence_report.py`.

## Oracle (deterministic)

`python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py`
plus `python3 -m black --check` and `python3 -m ruff check` on the two owned files. Add tests:
a mixed report renders routed first and the unrouted heading with the right counts; a report
with no unrouted groups omits the second heading; `--json` byte-identical to before for a
fixture.

## Bounds

Runtime bound: 15 minutes per packet. Size: one packet (the plan is already one file pair);
do not split further. Stop if the change would require touching a forbidden file.
