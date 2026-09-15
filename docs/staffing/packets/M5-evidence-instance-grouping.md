# Packet M5 — evidence report groups by route+instance

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
("channel instances — many subscriptions per provider, universally"), M5
("evidence"). Supervised via `/supervise`. Follows M1-M4 (all committed):
the attempt record's `route.channel_instance` field (additive, M1/M3-3) now
carries the chosen channel instance on every dispatch through a
multi-instance channel.

## Packet fields

Kind: impl
Owned paths: `src/lee_llm_router/staffing/evidence_report.py`, `tests/test_staffing_evidence_report.py`
Oracle: `.venv/bin/python -m pytest tests/test_staffing_evidence_report.py -q`
Review: independent review required after the oracle passes
Runtime bound: 35 minutes

## Objective

The evidence report (`lee-llm-router evidence report`) currently groups
attempts by `(route_id, class_key)` only, and its per-channel headroom
section reports one aggregate row per channel. The plan's M5 milestone
requires: (1) evidence groups additionally split by the channel instance
the attempt actually used, so cost/pass-rate/token evidence is visible per
account, not blended across accounts; (2) the channel headroom section
lists each channel's instances individually. Acceptance per the plan: "one
month later the report shows per-account cost" — this packet makes that
structurally true; it does not itself generate a month of new evidence.

## Required changes (in `src/lee_llm_router/staffing/evidence_report.py`)

1. Add a new helper `_channel_instance(record: Mapping[str, Any]) -> str |
   None`, following the exact pattern of the existing `_route_id()` helper
   just above it (same file, ~line 54): read
   `record.get("route", {}).get("channel_instance")` if `route` is a
   `Mapping`, else `None` — `channel_instance` has no `router_event`
   fallback location (unlike `route_id`), it only ever lives on
   `record["route"]["channel_instance"]` (M1's schema field, M3-3's
   writer). Use `_string_or_none` for the non-empty-string convention every
   other helper in this file already uses.

2. In `build_evidence_report()`, change the grouping key (currently `key =
   (_route_id(record), _class_key(record))`, ~line 825) to a 3-tuple
   `(_route_id(record), _class_key(record), _channel_instance(record))`.
   Update every place that consumes this key (the `grouped` dict type
   annotation, the loop that calls `_enrich_group`, and `_group_sort_key`)
   to the 3-tuple shape. `_group_sort_key` (~line 581) currently sorts
   `(route_id, class_key)` with unavailable (`None`) keys first; extend it
   the same way for `channel_instance` — unavailable last component sorts
   before any named instance, named instances sort lexically. An attempt
   with no `channel_instance` (single-instance channel, or a channel with
   no instance concept — the overwhelming majority of existing/historical
   ledger data) groups exactly as before under `channel_instance: None`;
   this must not split or change any existing single-instance-channel
   report output.

3. `_enrich_group()` (~line 533) gains a `channel_instance: str | None`
   parameter (positioned however reads best next to `route_id`/`class_key`)
   and includes it in its returned dict as `"channel_instance":
   channel_instance`. This is the only shape change to the per-group
   dict — every existing key stays exactly as-is.

4. `render_evidence_report()`'s classes section (~line 884-966): print the
   instance right after the existing `  route: ...` line, e.g. `  instance:
   {group.get('channel_instance') or '(none)'}` — always printed (not
   conditionally hidden when `None`), so the report is unambiguous about
   whether a group is instance-scoped.

5. `_channel_headroom_rows()` (~line 597): for each channel, also list its
   instances. Load the channel's declared instances the same way
   `eligibility.py` already does (`channel.effective_instances()` on the
   `catalog.py` `Channel` object already in scope here as `catalog` — one
   implicit instance named the channel id when none are declared, or the
   real declared instances otherwise; do not duplicate or reinvent this
   logic, call the existing method). For each instance, add a row to a new
   `"instances"` list on that channel's dict using
   `availability.instance_headroom(channel_id, instance_id)` (M2b, already
   implemented in `src/lee_llm_router/availability.py` — reuse it, do not
   recompute per-instance headroom by hand) for `remaining_fraction`, and
   the same reserve/inside-reserve/availability-status logic the channel
   row already uses (per-instance, using the channel's own
   `reserve_fraction`, since M3's D216 reserve is evaluated per instance
   but the fraction itself is per-channel policy — confirm this against
   `eligibility.py`'s existing per-instance reserve check rather than
   assuming). Each instance row: `{"instance_id": ..., "remaining_fraction":
   ..., "reserve_fraction": ..., "inside_reserve": ..., "availability":
   ...}` — same field names as the parent channel row, for consistency.
   Every channel gets an `"instances"` list (never omitted), even
   single-implicit-instance channels (one entry, `instance_id` equal to the
   `channel_id`) — this keeps the shape uniform and matches
   `effective_instances()`'s own "absent = one implicit instance" model
   used everywhere else in this plan.

6. `render_evidence_report()`'s channels section (~line 968-986): after each
   channel's existing summary line(s), print one indented line per
   instance, e.g. `    instance {instance_id}: remaining=..., reserve=...,
   status=...` (reuse the existing `N/A`-when-`None` number formatting
   convention already used for the channel-level line).

7. Do not change `_route_changes()` or anything about route-change
   recommendation logic — confirm it still works unchanged with the new
   group shape (it reads specific keys off each group dict, not the whole
   dict), but do not touch that function unless you find it actually
   breaks, in which case stop and report exactly what broke rather than
   silently redesigning recommendation logic.

## Tests (required, extend `tests/test_staffing_evidence_report.py`)

- Two ledger records with the same `route_id` and `class_key` but different
  `route.channel_instance` values (e.g. `"a"` and `"b"`) produce **two**
  separate groups in `build_evidence_report()["classes"]`, each with its
  own `attempts`/`verified_pass`/cost numbers scoped to only that
  instance's records, and each carrying the correct `"channel_instance"`
  value.
- A ledger record with no `route.channel_instance` key (the existing,
  overwhelmingly common shape in historical/test fixture data) groups
  exactly as it did before this packet — confirm an existing pre-packet
  test (pick one that already asserts specific `classes` group content)
  still passes unmodified, proving no regression for the ungrouped-by-
  instance case.
- `render_evidence_report()` output contains an `  instance: ...` line for
  a grouped record, showing the correct instance id (or `(none)`).
- `_channel_headroom_rows()` (or `build_evidence_report()["channels"]`) for
  a catalog fixture with a channel that declares `instances` (reuse or
  extend an existing multi-instance fixture pattern from the M1/M3 test
  suites — do not invent a new fixture shape if a suitable one exists)
  returns an `"instances"` list with one row per declared instance, correct
  `instance_id`s, and per-instance `remaining_fraction` sourced from
  `availability.instance_headroom()` (not the channel aggregate).
- A single-instance (no declared `instances`) channel's `"instances"` list
  has exactly one entry whose `instance_id` equals the channel id, and its
  values match the channel-level aggregate exactly (proving the implicit-
  instance case is consistent, not a second independent computation).
- `render_evidence_report()` prints one `    instance ...:` line per entry
  in a channel's `instances` list.

## Forbidden

Every other file, in particular:
- `src/lee_llm_router/staffing/rollup.py`, `src/lee_llm_router/staffing/catalog.py`,
  `src/lee_llm_router/availability.py`, `src/lee_llm_router/staffing/eligibility.py`
  (all already implement what this packet reuses — call into them, do not
  modify them)
- `context.md`, `sprint-plan.md`, `result-review.md` (the supervisor updates
  these after the packet is verified)

## Before you finish

Run `.venv/bin/black src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py` (no `--check`) and `.venv/bin/ruff check --fix src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py` as your own last edits, then re-run the oracle and the full suite and confirm both exit 0, before you report done.

## Oracle (deterministic, required)

```bash
.venv/bin/python -m pytest tests/test_staffing_evidence_report.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
.venv/bin/ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
```

Do not prefix any command with `PYTHONPATH=src`. All four commands must
exit 0. Full suite must show strictly more passed tests than the pre-packet
baseline (1913 passed, 6 skipped) and zero new failures.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the two owned paths.
- One paragraph confirming a single-instance-channel report (the
  overwhelming majority of today's real ledger data) is provably byte-
  identical in its `classes` numbers to before this packet — only the new
  `channel_instance`/`instances` keys are additive.

## Stop / escalation condition

If `_channel_headroom_rows()` cannot determine the correct reserve fraction
to apply per instance (i.e. if per-instance reserve evaluation in
`eligibility.py` turns out to use something other than the channel-level
`reserve_fraction.fraction_for(channel_id)` this function already reads),
stop and report exactly what `eligibility.py` does instead, rather than
guessing or inventing a different per-instance reserve rule.
