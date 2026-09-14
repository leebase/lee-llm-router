# Packet M3-3 — `run --instance` pins an instance; the attempt record carries it

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`, milestone M3
("selection"), per the M3 design ruling and M3 ruling 2 at the top of that plan (2026-09-14).
M1 (catalog + schema: additive `route.channel_instance` on `attempt-record.schema.json`,
already committed — see `config/staffing/schema/attempt-record.schema.json` around
`"channel_instance"`, a nullable non-empty string, sibling of `route.provider`), M2 (per-
instance headroom), M3-1 (`EligibilityRow.instance_headrooms`, most-headroom-first, only
*enabled* instances, empty for a non-subscription channel), and M3-2 (`staff auto` exposes
`selected_instance` using exactly this rule: the first `instance_headrooms` entry whose
`eligible` is `True`) are committed. This packet is M3-1's stated next step ("the foundation
... M3-3 (run.py/doctor.py) build on") and delivers the M3 design ruling's other half: "`run
--instance <id>` pins an instance the way `--route` pins a route; without it, `run` takes the
pair `staff` chose."

## Packet fields

Kind: impl
Declared size: 4 files (all changed), approximately 250-350 changed/added lines
Owned paths: `src/lee_llm_router/staffing/run.py`, `src/lee_llm_router/doctor.py`,
`tests/test_staffing_run.py`, `tests/test_doctor.py`
Oracle: `pytest tests/test_staffing_run.py tests/test_doctor.py -q`
Review: independent review required after the oracle passes

## Objective

**1. `SelectionOutcome` (run.py, near line 428) gains an additive field
`channel_instance: str | None = None`** — the resolved instance id for the selected route's
channel, or `None` when the channel is not a subscription channel (empty `instance_headrooms`)
or no instance clears.

**2. `select_route()` (run.py, near line 577) gains a new optional keyword parameter
`instance_id: str | None = None`** (the CLI's `--instance`). Both existing branches (explicit
`--route`, and the no-`--route` cheapest-eligible fallback) already hold the chosen route's
`EligibilityRow` in a local (`row` in the explicit branch, `selected` in the fallback branch) —
that row already carries `instance_headrooms` (M3-1). Resolve `channel_instance` from it:

- **Without `--instance`** (the common supervised case: "run takes the pair staff chose"):
  `channel_instance` is the `instance_id` of the first entry in the row's `instance_headrooms`
  whose `eligible` is `True` — the *exact same rule* M3-2's `build_auto_block()` already applies
  in `block.py`, so when the supervisor dispatches with the same explicit `--route` `staff`
  chose, `run`'s default instance pick equals `staff`'s `selected_instance` without either side
  needing to pass anything extra. `None` when `instance_headrooms` is empty or no entry is
  eligible.
- **With `--instance ID`**: look up `ID` in the row's `instance_headrooms` by `instance_id`.
  - Not found at all (unknown id, or a *disabled* instance — M3-1 excludes disabled instances
    from `instance_headrooms` entirely, so an id naming a disabled instance is indistinguishable
    from an unknown one here) → `RunSelectionError` (exit 3, kind e.g. `"unknown_instance"`),
    nothing launched. Name the route id and the instance id in the message.
  - Found but `eligible` is `False` (e.g. at reserve, exhausted) → `RunSelectionError` (exit 3,
    kind e.g. `"excluded"`), citing that instance's own `reasons` — mirror how an ineligible
    explicit `--route` is refused today (same function, a few lines above).
  - The row's `instance_headrooms` is empty (non-subscription channel, or a channel the catalog
    doesn't recognize) and `--instance` was explicitly given → `RunSelectionError` (exit 3):
    this route's channel has no instance concept, so pinning one is a caller error, not a
    silent no-op.
  - Otherwise: `channel_instance = ID`.

Do not change the route-selection logic itself (which route wins) — this packet only resolves
*which instance of the already-chosen route*, exactly as M3-2 did one layer up in `staff`.

**3. `build_attempt_record()` (run.py, the `"route": {...}` dict around line 1596-1602) gains
one additive key: `"channel_instance": outcome.channel_instance` (place it after `"provider"`,
matching the schema's sibling ordering — JSON Schema itself doesn't enforce key order, but keep
it adjacent for readability). Do not touch the separate, already-dead `run_json_record()`
function (~line 2952, no callers besides its own export — grep confirms this; it predates
`build_attempt_record` and is out of scope here).

**4. CLI wiring (doctor.py):** add `run_parser.add_argument("--instance", default=None,
dest="instance", metavar="INSTANCE_ID", help=...)` next to the existing `--route` argument
(~line 2952-2963 in `doctor.py`), documenting the pin/default-pair behavior from objective 2.
Thread it into the `select_route(...)` call inside `_run_run()` (~line 1768-1783) as
`instance_id=getattr(args, "instance", None)`.

## Owned paths

- `src/lee_llm_router/staffing/run.py`
- `src/lee_llm_router/doctor.py`
- `tests/test_staffing_run.py`
- `tests/test_doctor.py`

## Forbidden paths

Every other file in the repo, including `staff.py`, `block.py`, `eligibility.py`,
`availability.py`, `catalog.py`, and any `config/staffing/**` fixture (the schema field already
exists — do not touch the schema file). Do not touch credential staging, dispatch argv
construction (`build_dispatch_command`), or anything under M4's scope (live per-run credential
isolation) — this packet only resolves and records which instance was selected; it does not
change what gets dispatched or how.

## Expected artifact

`run.py` and `doctor.py` diffs (additive `SelectionOutcome.channel_instance` field, the
`instance_id` parameter and its resolution logic in both `select_route()` branches, the one new
key in `build_attempt_record()`'s route dict, and the new `--instance` CLI argument plus its
threading) and new/extended cases in `tests/test_staffing_run.py` and `tests/test_doctor.py`
covering: (a) no `--instance`, selected route has two instances, one eligible one not (not
first in supply order) — `channel_instance` picks the eligible one; (b) no `--instance`, the
selected route's channel is non-subscription (empty `instance_headrooms`) — `channel_instance`
is `None`, no exception; (c) `--instance` naming the currently-eligible instance — accepted,
`channel_instance` equals it; (d) `--instance` naming an ineligible (at-reserve or exhausted)
instance of the selected route's channel — `RunSelectionError`, exit 3, nothing launched
(assert no dispatch/registration side effect occurred); (e) `--instance` naming an unknown or
disabled instance id — `RunSelectionError`, exit 3; (f) `--instance` given for a route whose
channel has no instance concept (empty `instance_headrooms`) — `RunSelectionError`, exit 3;
(g) `build_attempt_record()`'s output has `record["route"]["channel_instance"]` equal to
`outcome.channel_instance` in both the `None` and non-`None` cases; (h) a CLI-level test in
`test_doctor.py` (following the file's existing pattern for `--route`/`--supervisor-route`
CLI tests) proving `--instance` parses and reaches `select_route` with the right value, and that
an invalid `--instance` produces the documented exit-3 refusal at the CLI boundary. Also confirm
by inspection (and a regression test if not already covered) that a channel with **no declared
`instances`** in `channels.yaml` (the implicit single-instance case) still resolves
`channel_instance` to that implicit instance id when the channel is a subscription channel —
"nothing about a single-instance channel changes" except that it is now named on the record.

## Required evidence

```bash
cd /home/lee/projects/lee-llm-router
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_run.py tests/test_doctor.py -q
.venv/bin/black --check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
.venv/bin/ruff check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
```

All three must exit 0. Paste the full pytest summary line (pass/fail count) in your report.

## Stop/escalation condition

Stop and report (do not guess) if resolving `channel_instance` cleanly turns out to require
re-evaluating eligibility a second time, changing `evaluate_eligibility()`'s signature, or
touching `eligibility.py`/`block.py` at all — everything needed (`row.instance_headrooms`) is
already on the `EligibilityRow` objects `select_route()` computes today; if that turns out not
to be enough, that is a design gap this packet didn't anticipate, escalate rather than
improvising an alternative architecture. Runtime bound: 90 minutes. Oracle above is
deterministic.
