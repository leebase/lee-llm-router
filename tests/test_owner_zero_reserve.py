"""Owner regression: configured reserve opt-out is not an availability waiver."""

from __future__ import annotations

from dataclasses import replace

import pytest

from lee_llm_router.availability import parse_availability
from lee_llm_router.staffing.catalog import (
    ReserveFractionOverride,
    load_staffing_catalog,
)
from lee_llm_router.staffing.eligibility import _reserve_finding

from .test_staffing_eligibility import (
    _NOW,
    REPO_CONFIG_DIR,
    SOL_LOW_ROUTE,
    _by_route,
    _evaluate,
    _snapshot,
)


@pytest.mark.parametrize(
    "remaining,hours,window", [(0.25, 87.5, 168.0), (0.10, None, None)]
)
def test_zero_reserve_honors_available_capacity(remaining, hours, window):
    assert not _reserve_finding(remaining, hours, window, 0.0).reserved
    assert _reserve_finding(remaining, hours, window, 0.10).reserved


def test_zero_reserve_does_not_unlock_empty_capacity():
    assert _reserve_finding(0.0, 87.5, 168.0, 0.0).reserved


@pytest.mark.parametrize(
    "remaining,status,expected",
    [
        (25, "TOO FAST", True),
        (0, "HOT", False),
        (2, "HOT", False),
        (None, "NO DATA", False),
    ],
)
def test_zero_reserve_keeps_channel_health_veto(remaining, status, expected):
    catalog = load_staffing_catalog(REPO_CONFIG_DIR)
    reserve = replace(
        catalog.policy.reserve_fraction,
        overrides=(
            *catalog.policy.reserve_fraction.overrides,
            ReserveFractionOverride(channel_id="openai-sub", reserve_fraction=0.0),
        ),
    )
    catalog = replace(catalog, policy=replace(catalog.policy, reserve_fraction=reserve))
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "remaining_pct": remaining,
            "status": status,
            "resets_in_hours": 87.5,
            "window_hours": 168.0,
        }
    )
    row = _by_route(_evaluate(catalog, snapshot), SOL_LOW_ROUTE)
    assert row.eligible is expected
    stale_snapshot = parse_availability(
        {
            "host": "fixture",
            "observed_at": "2026-09-08T00:00:00Z",
            "subscriptions": [
                {
                    "provider": "OpenAI/Codex",
                    "bucket": "Weekly limit",
                    "remaining_pct": remaining,
                    "status": status,
                    "resets_in_hours": 87.5,
                    "window_hours": 168.0,
                }
            ],
        },
        now=_NOW,
    )
    assert stale_snapshot.stale
    assert not _by_route(_evaluate(catalog, stale_snapshot), SOL_LOW_ROUTE).eligible


def test_zero_reserve_does_not_change_anthropic_default():
    catalog = load_staffing_catalog(REPO_CONFIG_DIR)
    reserve = replace(
        catalog.policy.reserve_fraction,
        overrides=(
            *catalog.policy.reserve_fraction.overrides,
            ReserveFractionOverride(channel_id="openai-sub", reserve_fraction=0.0),
        ),
    )
    catalog = replace(catalog, policy=replace(catalog.policy, reserve_fraction=reserve))
    assert catalog.policy.reserve_fraction.fraction_for("anthropic-sub") == 0.10
    assert _reserve_finding(0.25, 87.5, 168.0, 0.10).reserved
