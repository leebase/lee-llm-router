# Review packet M5 — evidence report groups by route+instance

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M5 ("evidence"). Independent review of the uncommitted worktree changes made
by `docs/staffing/packets/M5-evidence-instance-grouping.md` (impl attempt
`router-run-78b9fc486cd548bc8c74e00fb895c03c`, author route
`agy-gemini-3-8-flash-high-gemini-sub`, excluded from this review for
independence).

Owned paths under review (read-only for you — do not edit): `src/lee_llm_router/staffing/evidence_report.py`, `tests/test_staffing_evidence_report.py`

## Context

M1–M4 (all committed) added a `route.channel_instance` field to the attempt
record so a dispatch through a multi-instance subscription channel (e.g. two
OpenCode Go accounts) records which account it actually used. M5 makes the
evidence report (`lee-llm-router evidence report`) group its per-class rows
additionally by that instance, and list each channel's instances
individually in the headroom section, so cost/pass-rate is visible per
account instead of blended across accounts. The impl is currently
**uncommitted** on the worktree; the supervisor has already personally
verified (not taking the worker's word for it):

```
.venv/bin/python -m pytest tests/test_staffing_evidence_report.py -q   # 33 passed
.venv/bin/python -m pytest -q                                           # 1918 passed, 6 skipped (pre-packet baseline: 1913 passed, 6 skipped)
.venv/bin/black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py   # unchanged, exit 0
.venv/bin/ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py       # exit 0
```

Verify these yourself if you have a command-execution tool; if not, say so
explicitly and review statically only.

## What to check

1. **Grouping key correctness:** `build_evidence_report()`'s group key is
   now the 3-tuple `(route_id, class_key, channel_instance)`. Confirm every
   consumer of that key (`grouped` dict typing, the `_enrich_group()` call
   site, `_group_sort_key`) was updated consistently — no stale 2-tuple
   assumption left anywhere that could silently merge or drop rows.
2. **Backward compatibility is provable, not assumed:** a ledger record with
   no `route.channel_instance` key (the overwhelming majority of
   real/historical data) must group exactly as it did before this packet.
   Confirm a pre-existing test that asserts specific `classes` group content
   still passes unmodified (not just "still exists" — check it wasn't
   quietly loosened to accommodate the new shape).
3. **`_channel_instance()` helper:** confirm it reads only
   `record["route"]["channel_instance"]` (no incorrect `router_event`
   fallback — unlike `_route_id()`, this field has no legacy fallback
   location per the plan), returns `None` for a missing/non-mapping `route`,
   and uses the same `_string_or_none` non-empty-string convention as the
   file's other helpers.
4. **`_channel_headroom_rows()` per-instance data is real, not invented:**
   confirm each channel's `"instances"` list is built from
   `channel.effective_instances()` (not reimplemented) and each row's
   headroom numbers come from `availability.instance_headroom(channel_id,
   instance_id)` (not recomputed by hand), and that the reserve/
   inside_reserve/availability-status logic per instance matches what
   `eligibility.py` actually does for per-instance D216 reserve (trace it,
   don't assume it's the channel-level `reserve_fraction` carried over
   unchanged — the packet's stop condition required escalating if this
   didn't hold).
5. **Uniform shape:** every channel — including a single-instance channel
   with no declared `instances` — has a non-empty `"instances"` list (one
   entry, `instance_id` equal to the channel id, matching the channel-level
   aggregate exactly). Confirm this with the actual test, not just the
   packet's claim.
6. **Rendering:** `render_evidence_report()` prints an `  instance: ...` line
   for every class group (always, even when `None` → `(none)`) and one
   `    instance <id>: ...` line per channel instance. Confirm both are
   exercised by a test that inspects rendered output text, not just the
   underlying dict.
7. **Scope discipline:** confirm `_route_changes()` was not modified (the
   packet was explicitly forbidden from touching it unless it broke) and
   that `git diff --stat` touches only the two owned paths — no edits to
   `rollup.py`, `catalog.py`, `availability.py`, `eligibility.py`, or the
   baton docs (`context.md`, `sprint-plan.md`, `result-review.md`).
8. Any other correctness or test-quality defect you find, including whether
   the new tests actually exercise the described behavior end-to-end
   (e.g. via `build_evidence_report()` + `render_evidence_report()` on a
   realistic fixture) rather than merely asserting on isolated internals in
   a way that could pass even if the grouping were subtly wrong.

## Verdict

State PASS/ACCEPT or REJECT with concrete findings, each citing the exact
line(s) and why it is a defect (not a style preference). If you ran the
commands above, quote their exit codes/output in your verdict.
