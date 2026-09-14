# Packet S6 — D215 as a hard tier in the ladder: prepaid headroom outranks any metered price

- Kind: `impl`; Class: `impl/deterministic/none/s/python`; Declared size: 3 files, ≤ 260 lines
- Owned paths: `src/lee_llm_router/staffing/ladder.py`, `tests/test_staffing_ladder.py`,
  `tests/test_staffing_staff.py` (assertions on the escalation chain only)
- Forbidden: everything else (`terms.yaml`, badge multipliers, `staff.py`, `block.py`, `eligibility.py`).
- Runtime bound: 25 minutes. Oracle: `python3 -m pytest -q tests/test_staffing_ladder.py tests/test_staffing_staff.py`
- Authority: D215 (Lee, 2026-09-12, verbatim: "ridiculously cheap api cost is still more
  expensive than available subscriptions that's been prepaid"); D216 (10% reserve is the only
  hard cutoff). Observed 2026-09-14: `staff --mode auto` for `impl/deterministic/none/s/python`
  produced the escalation chain Flash → Luna → **DeepSeek V4 Flash (OpenRouter, metered)** →
  GLM (metered) → V4.1 (metered) → Sol high (openai-sub) → … → OpenCode Go routes last, and
  five metered DeepSeek dispatches ran today while openai-sub was ON TRACK at 72% and both
  OpenCode Go seats had headroom. Cause: `calculate_ladder` orders rungs by expected cost
  `E`, and a subscription route's decision price is `badge multiplier × replacement list
  price` (ON TRACK 0.25, HOT 0.75, TOO FAST 1.0), which makes a pacing-but-available
  subscription "cost" more than a cheap metered row.

## Rule (implement exactly)

In `calculate_ladder` (the `order = sorted(...)` at ~line 391 and the `argmin_start` choice),
sort rungs by a **tier first**, then by the existing expected-cost/proof/marginal keys within
the tier:
- tier 0: channel `kind == "subscription"` whose headroom is above the reserve (an eligible
  row — the eligibility rows already exclude inside-reserve and exhausted channels, so every
  subscription rung that reaches the ladder is tier 0),
- tier 1: `kind == "metered"`,
- tier 2: `kind == "local"` and anything else.
Badge multipliers keep ordering *within* tier 0 (COLD before ON TRACK before HOT before TOO
FAST) through the existing expected-cost math; they never move a subscription rung below a
metered rung. `argmin_start` is the first rung of the ordered chain (same tiering). The
channel kind must be read from the catalog channel of each rung's route (the `LadderInput`
carries the route; look up `channel.kind` through whatever the caller already passes — if
`calculate_ladder` does not receive channel kinds today, add an optional
`channel_kind_by_route: Mapping[str, str] | None` parameter defaulting to None (no tiering
when absent, so existing callers and tests keep their behaviour) and have `staff.py`'s single
call site pass it; that one-line call-site change is permitted in `staff.py` only for the
argument, nothing else).

## Tests (fail first)
- A subscription rung with ON TRACK badge (decision price > 0) and a metered rung with a
  lower expected cost: subscription comes first, metered after.
- Two subscription rungs COLD vs TOO FAST: COLD first (unchanged behaviour).
- No `channel_kind_by_route` given: ordering identical to today (regression guard).
- `tests/test_staffing_staff.py`: the auto block's escalation chain for a fixture class lists
  every eligible subscription route before the first metered route.

## Required evidence
Oracle before (new tests failing) and after; black/ruff on owned files; a live
`lee-llm-router staff --mode auto --role impl --class impl/deterministic/none/s/python --json`
whose `escalation` shows no metered route ahead of any subscription route. Do not commit,
stash, or write `decisions.md`.
