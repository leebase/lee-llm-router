# Review packet — M5 + M5-fix1 (evidence report grouped by route + instance)

You are the independent reviewer. Author routes: `agy-gemini-3-8-flash-high-gemini-sub` (M5) and
`pi-gpt-5-6-luna-xhigh-openai-sub` (M5-fix1). Read `docs/staffing/packets/M5-evidence-instance-grouping.md`,
`docs/staffing/packets/M5-fix1-route-level-aggregation.md`, the prior review
`docs/staffing/packets/M5-review.md` (REJECT: 1 medium, 2 low), and the current uncommitted diff
(`git diff -- src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py`).
Owned paths are read-only for you — do not edit anything.

Verify, citing exact lines:
1. `_route_changes()` now works on route-level aggregates collapsed by `(class_key, route_id)`;
   two instances of one route can no longer produce a recommendation naming that same route, and
   there is a test proving it.
2. The per-instance headroom test exercises the D216 inside-reserve branch (an instance ≤ 0.10).
3. A test runs `build_evidence_report()` then `render_evidence_report()` on the same
   instance-bearing report and asserts `channel_instance` / instance grouping survive.
4. The classes/grouping section still reports per-instance rows; legacy untagged records still
   group correctly; nothing else in the report regressed.

If you can run commands, run `.venv/bin/python -m pytest tests/test_staffing_evidence_report.py -q`
and quote the exit code; otherwise say you reviewed statically only.

Output exactly one JSON object: {"verdict": "PASS" | "REJECT", "findings": [{"severity", "location",
"finding"}], "verification": {...}}.
