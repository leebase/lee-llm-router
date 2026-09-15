# Packet M5-fix1 — route-level aggregation for `_route_changes`; two test gaps

Parent: `M5-evidence-instance-grouping.md` (impl on the tree, uncommitted, oracle green).
Reason: independent review (`M5-review.md`, Luna xHigh) REJECTED with one MEDIUM and two LOW
findings. This is the single authorized repair for M5.

Owned paths: `src/lee_llm_router/staffing/evidence_report.py`, `tests/test_staffing_evidence_report.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_evidence_report.py -q`
Runtime bound: 25 minutes
Review: independent review required after the oracle passes

## Findings to close (all three)

1. **MEDIUM — `_route_changes()` treats per-instance rows as distinct routes**
   (`evidence_report.py` ~725-815, 878-916). Two instances of one route can satisfy the
   two-route checks, select the cheaper instance, and emit a recommendation whose
   `recommended_route_id` equals the current route; the `others` filter (~801) also removes the
   sibling instance. Required: `_route_changes()` must operate on route-level aggregates —
   collapse rows by `(class_key, route_id)` (sum counts, combine verdicts/costs the same way the
   pre-M5 code did for a single row per route) before the two-route logic, while the classes /
   grouping section keeps its per-instance rows. A recommendation must never name the current
   route as the recommended route.
2. **LOW — per-instance headroom test never exercises the inside-reserve branch**
   (`tests/…:1276-1384`). Add an instance at or below 0.10 and assert it renders as inside
   reserve while its sibling instance renders outside.
3. **LOW — no build→render round-trip on an instance-bearing report**
   (`tests/…:1174-1230, 1257-1273, 1387-1451`). Add one test that calls
   `build_evidence_report()` on instance-tagged records and then `render_evidence_report()` on
   that same output, asserting the instance grouping and `channel_instance` survive.

## Rules

- Write a failing test for finding 1 first (two instances of one route must not yield a
  recommendation naming that route), then fix. Do not touch files outside the owned paths.
- Do not prefix commands with `PYTHONPATH=src`; the venv has the package installed editable.
- As your last edits run `.venv/bin/black` and `.venv/bin/ruff check --fix` on the two owned
  files, then re-run the oracle and confirm exit 0. Report what you changed and the test count.
