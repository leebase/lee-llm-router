# Packet M3-2 — `staff auto` exposes the selected instance and per-instance headroom

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`, milestone M3
("selection"), per the M3 design ruling and M3 ruling 2 at the top of that plan
(2026-09-14). M1 (catalog + schema: `route.channel_instance`), M2 (per-instance headroom),
and M3-1 (`src/lee_llm_router/staffing/eligibility.py`: `EligibilityRow.instance_headrooms`,
a tuple of `EligibilityInstance` — `instance_id`, `eligible`, `reasons`, `remaining_fraction`,
`health`, `badge` — ordered descending by `remaining_fraction`, most headroom first, for every
*enabled* instance of the row's channel; empty for a non-subscription channel) are committed.
This packet is M3-1's stated next step ("the foundation M3-2 (staff.py/block.py)... build
on"). Investigation for this packet already confirmed `build_auto_block` in
`src/lee_llm_router/staffing/block.py` receives the full `EligibilityRow` objects via its
`eligibility_rows` parameter and builds one `WorkerFacts` per row — so this packet is
achievable inside `block.py` alone; `staff.py`'s own selection algorithm
(`_select_auto_route`, `_staff_auto`) picks *which route* and does not need to change, since
instance selection happens only after a route is already selected.

## Packet fields

Kind: impl
Declared size: 2 files (both changed), approximately 120-180 changed/added lines
Owned paths: `src/lee_llm_router/staffing/block.py`, `tests/test_staffing_block.py`
Oracle: `pytest tests/test_staffing_block.py -q`
Review: independent review required after the oracle passes

## Objective

The M3 design ruling: "Selection returns a *pair* — the chosen route and the chosen instance
of that route's channel — and the attempt record carries the instance in
`route.channel_instance`... `staff --json` exposes `selected_instance` and, per candidate row,
the per-instance headroom it read from the availability snapshot (M2b's `instances`)." This
packet delivers that for `staff auto`'s JSON/text output only (worker selection; the
independent reviewer's own instance choice is explicitly out of scope — see Stop/escalation
condition).

**1. `WorkerFacts` gains the per-instance data, additively.** Add a field (e.g.
`instance_headrooms: tuple[dict[str, Any], ...] = ()`) carrying, for every entry in the
eligibility row's `instance_headrooms` (read via the existing `_field()` helper so both a real
`EligibilityRow`/`EligibilityInstance` and a test double/mapping work), a JSON-safe dict with
exactly: `instance_id`, `eligible`, `reasons` (list), `remaining_fraction`, `health`, `badge`
— same field names and order as `EligibilityInstance`, same order as supplied (already
most-headroom-first from M3-1, do not re-sort). Empty tuple when the row carries none (a
non-subscription channel, or a caller that supplies none — must not raise). Include it in
`WorkerFacts.as_dict()`. `_worker_facts()` is the one place that currently builds a
`WorkerFacts` from a row; extend it there.

**2. `StaffingBlock` gains `selected_instance: str | None`, additively.** In
`build_auto_block()`, after `selection` (the already-chosen route id) is finalized, resolve
`selected_instance`: `None` when `selection` is `None`; otherwise look up that route's
`WorkerFacts` (the existing `by_route` mapping already built in that function) and take the
`instance_id` of the *first* entry in its `instance_headrooms` whose `eligible` is `True`
(there must always be at least one, since `selection` is only ever an eligible route and M3-1
made a route eligible exactly when some enabled instance clears — but fail closed to `None`
without raising if none is found rather than asserting an invariant this packet doesn't own).
For a non-subscription-channel selected route (empty `instance_headrooms`), `selected_instance`
is `None` — this is the "nothing about a single-instance channel changes" case from the plan's
Outcome section extended to "no-instance-concept" channels; only *subscription* channels ever
populate `instance_headrooms` per M3-1, including the implicit single-instance case (instance
id equal to the channel id).

**3. Surface `selected_instance` in the stable outputs.** Add `"selected_instance"` to
`StaffingBlock.as_dict()`'s returned mapping (place it immediately after `"selected_route"`)
and to the `STAFFING_BLOCK_JSON_KEYS` tuple in the same position — `render_json()` filters
through that tuple, so both must change together or the key is silently dropped. Add one
deterministic text-rendering line that appears in `render_text()`'s output whenever
`selected_instance` is not `None` (exact wording is your call — e.g. append `, instance
<id>` to the existing "Reason:" line, or add it to the expected-cost line — pick one, keep it
deterministic, and cover it with a text-rendering test); when `selected_instance` is `None`,
add no such fragment (do not print a literal "instance: unknown" or similar — the field is
simply absent from the rendered facts, matching how the module treats other absent-but-legal
facts elsewhere in this file).

## Owned paths

- `src/lee_llm_router/staffing/block.py`
- `tests/test_staffing_block.py`

## Forbidden paths

Every other file in the repo, including `staff.py`, `run.py`, `doctor.py`, `eligibility.py`,
`availability.py`, `catalog.py`, and any `config/staffing/**` fixture. Do not touch
`_select_auto_route` or any other route-selection arithmetic in `staff.py` — this packet only
renders a fact that is already fully determined once `selection` exists.

## Expected artifact

`src/lee_llm_router/staffing/block.py` diff (additive `WorkerFacts.instance_headrooms` field
plus its `as_dict()` entry, additive `StaffingBlock.selected_instance` field plus its
`as_dict()`/`STAFFING_BLOCK_JSON_KEYS` entries, the resolution logic in `build_auto_block()`,
and one text-rendering line) and new/extended cases in `tests/test_staffing_block.py` covering:
(a) a selected route with two instance rows, one eligible one not (reserve/health excluded) —
`selected_instance` picks the eligible one even when it is not first in supply order, and both
instance dicts appear verbatim on the worker's `instance_headrooms`; (b) a selected route whose
only supplied instance is ineligible — `selected_instance` is `None`, no exception; (c) a
selected route with an empty `instance_headrooms` (non-subscription channel) — `selected_instance`
is `None`, `as_dict()` still includes the key with value `None`; (d) `selection is None` (no
eligible worker at all) — `selected_instance` is `None`; (e) `render_json()`'s key list
includes `"selected_instance"` in the documented position (extend the existing
`STAFFING_BLOCK_JSON_KEYS`-order assertion at the bottom of the test file rather than adding a
new one); (f) `render_text()` contains the new deterministic fragment exactly when
`selected_instance` is not `None`, and does not contain it when `selected_instance` is `None`.

## Required evidence

```bash
cd /home/lee/projects/lee-llm-router
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_block.py -q
.venv/bin/black --check src/lee_llm_router/staffing/block.py tests/test_staffing_block.py
.venv/bin/ruff check src/lee_llm_router/staffing/block.py tests/test_staffing_block.py
```

All three must exit 0. Paste the full pytest summary line (pass/fail count) in your report.

## Stop/escalation condition

Stop and report (do not guess) if delivering this cleanly inside `build_auto_block()` turns out
to require reading `staff.py`'s route-selection state beyond what `eligibility_rows` and the
existing `by_route`/`selection` locals already carry, or if the independent reviewer's own
instance choice turns out to be required to make this packet's tests pass — reviewer-instance
selection is explicitly out of scope for M3-2 and belongs to a later packet; do not invent it
here. Runtime bound: 60 minutes. Oracle above is deterministic.
