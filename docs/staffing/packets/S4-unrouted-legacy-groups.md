# Packet S4 — separate unrouted legacy groups in the evidence report text renderer

- Kind: `impl`
- Declared size: 2 files, at most 150 changed lines
- Owned paths: `src/lee_llm_router/staffing/evidence_report.py`, `tests/test_staffing_evidence_report.py`
- Forbidden paths: everything else, explicitly including `src/lee_llm_router/doctor.py`
  and `tests/test_doctor_evidence_report.py`.
- Oracle: `python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py`
- Domain: none

## Context

Plan `plans/supervise-acceptance-2026-09-13.md` (first `/supervise` acceptance
case). Authority: Chief of Staff, 2026-09-13.

## Objective

In `src/lee_llm_router/staffing/evidence_report.py`, change `render_evidence_report`
so routed groups (`route_id` is not `None`) print first under the existing
`Classes (N groups):` heading, where `N` counts only routed groups, and unrouted
groups (`route_id is None`, legacy imports with no router route) print afterwards
under a new heading `Unrouted legacy groups (M groups, no router route recorded):`
using the same per-group line format, unchanged. Do not change the JSON output
(`build_evidence_report`): same `classes` list, same order, same fields. Do not
touch aggregation, `_route_changes`, channels, or source rows — this is a text
rendering change only.

## Expected artifact

An updated `render_evidence_report` in `src/lee_llm_router/staffing/evidence_report.py`
plus new/updated tests in `tests/test_staffing_evidence_report.py` covering:

1. A mixed report (some routed, some unrouted groups) renders routed groups first
   under `Classes (N groups):` (N = routed count only), then the unrouted groups
   under `Unrouted legacy groups (M groups, no router route recorded):` (M =
   unrouted count), with per-group line content unchanged.
2. A report with zero unrouted groups omits the second heading entirely.
3. `build_evidence_report(...)["classes"]` (the JSON/dict path) is unaffected —
   same list, same order, same fields as before this change, for a fixture with
   both routed and unrouted groups.

## Required evidence

Run and report the exact output of, from the repo root:

```
python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py
python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
```

All three must pass (pytest: 0 failures; black/ruff: clean) before reporting done.

## Stop / escalation condition

Stop and report back without guessing if:
- The change would require editing `doctor.py` or `tests/test_doctor_evidence_report.py`.
- The existing `classes` JSON field order/content would need to change to make the
  text split work (it must not — group them for text rendering only, in Python,
  without reordering or filtering the underlying `report["classes"]` list).
- Any of the three oracle commands cannot be made to pass without touching a
  forbidden file or the JSON contract.

## Runtime bound

15 minutes.
