# Packet M3-1 — per-instance D216 reserve/health check in eligibility.py

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`, milestone M3
("selection"), per the M3 design ruling at the top of that plan (2026-09-14). M1 (catalog +
schema: `ChannelInstance`, `Channel.effective_instances()`, additive `route.channel_instance`)
and M2 (per-instance headroom: `AvailabilitySnapshot.instance_headroom(channel, instance)`,
`to_dict()["instances"]`) are committed. This packet is the foundation M3-2 (staff.py/block.py)
and M3-3 (run.py/doctor.py) build on — do not start those until this one is verified.

## Packet fields

Kind: impl
Declared size: 2 files (both changed), approximately 200 changed/added lines
Owned paths: `src/lee_llm_router/staffing/eligibility.py`, `tests/test_staffing_eligibility.py`
Oracle: `pytest tests/test_staffing_eligibility.py -q`
Review: independent review required after the oracle passes

## Objective

Today `evaluate_eligibility()` in `src/lee_llm_router/staffing/eligibility.py` vetoes a
subscription-channel route using exactly one channel-wide headroom read
(`availability.headroom(channel.channel_id)`, lines ~541 and ~561-577): a health veto
(`_SUBSCRIPTION_VETO_HEALTH`) and the D216 reserve check
(`catalog.policy.reserve_fraction.fraction_for(channel_id)` vs.
`headroom.remaining_fraction`). Make both checks **per instance**: for every channel, walk
`channel.effective_instances()` (M1; for a channel with no declared `instances`, this already
returns one implicit instance whose `instance_id` equals the channel id — the exact case that
must reduce to today's behavior, unchanged), skip disabled instances, and read each enabled
instance's headroom via `availability.instance_headroom(channel.channel_id, instance.instance_id)`
(M2) instead of the channel-wide aggregate for the veto/reserve decision.

**Route-level eligibility:** the route is *not* vetoed by health/reserve as long as at least one
enabled instance clears both checks (health not in `_SUBSCRIPTION_VETO_HEALTH`, and
`remaining_fraction` — when not `None` — strictly above `reserve_fraction.fraction_for(channel_id)`).
Only when *every* enabled instance is vetoed does the route gain a `reasons` entry (this is the
"an instance at reserve is excluded like an exhausted channel; only when a route has no instance
left does selection move to the next route" ruling — applied here at the eligibility layer, one
route at a time). When there are no enabled instances at all, add a reason
(e.g. `"no enabled instance for channel '<channel_id>'"`).

**New per-instance data on `EligibilityRow`:** add a field (e.g. `instance_headrooms:
tuple[EligibilityInstance, ...]`, new frozen dataclass alongside `EligibilityPrice`) listing every
*enabled* instance for the route's channel, each carrying at least: `instance_id`, `eligible: bool`,
`reasons: tuple[str, ...]` (that instance's own health/reserve reasons, empty when clear),
`remaining_fraction: float | None`, `health: str`, `badge: str | None`. Order the tuple by
descending `remaining_fraction` (most headroom first; `None` sorts last) — this order **is** the
same-route instance fallback order M3-2/M3-3 will consume (first eligible entry = the instance
`staff`/`run` should pick). For a non-subscription channel (`channel.kind != "subscription"`), or
a channel the catalog doesn't recognize, this field is an empty tuple — no behavior change there.
Do **not** change the existing `availability_health` / `availability_badge` / `availability_headroom`
fields on `EligibilityRow` — they keep reporting the channel-wide aggregate exactly as today,
purely additive change.

Harness-lock (`channel.harness_lock`) and never-automatic/role-scoped checks stay channel/model
-level, evaluated exactly as today, unaffected by instance selection — do not touch those lines.

## Owned paths

- `src/lee_llm_router/staffing/eligibility.py`
- `tests/test_staffing_eligibility.py`

## Forbidden paths

Every other file in the repo, including `staff.py`, `run.py`, `block.py`, `doctor.py`,
`availability.py`, `catalog.py`, and any `config/staffing/**` fixture. If a fixture change looks
necessary to prove this packet's behavior, add a test-local fixture instead, or stop and report —
do not edit shared fixtures.

## Expected artifact

`src/lee_llm_router/staffing/eligibility.py` diff (additive dataclass + per-instance loop
replacing the channel-wide veto/reserve block) and new/extended cases in
`tests/test_staffing_eligibility.py` covering: (a) a channel with no declared instances behaves
byte-identically to before (same `reasons`, same `eligible`); (b) the existing `opencode-go`
fixture (`config/staffing/channels.yaml`, instances `a`/`b`) — one instance at/under reserve and
one above it still leaves the route eligible, with `instance_headrooms` showing the vetoed one
ineligible and the clear one first/eligible; (c) both `opencode-go` instances at/under reserve
makes the route ineligible with a reason; (d) a disabled instance never appears as eligible and
is excluded from `instance_headrooms` entirely (or explicitly marked ineligible with a `disabled`
reason — pick one and test it, document the choice in the dataclass docstring).

## Required evidence

```bash
cd /home/lee/projects/lee-llm-router
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_eligibility.py -q
.venv/bin/black --check src/lee_llm_router/staffing/eligibility.py tests/test_staffing_eligibility.py
.venv/bin/ruff check src/lee_llm_router/staffing/eligibility.py tests/test_staffing_eligibility.py
```

All three must exit 0. Paste the full pytest summary line (pass/fail count) in your report.

## Stop/escalation condition

Stop and report (do not guess) if `catalog.policy.reserve_fraction.fraction_for()` or
`_availability_badge()` need a signature change to support per-instance reads — they should not;
if they do, that's a design gap this packet didn't anticipate, escalate rather than improvising an
alternative architecture. Runtime bound: 45 minutes. Oracle above is deterministic.
