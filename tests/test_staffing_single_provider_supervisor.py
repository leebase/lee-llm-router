"""Supervisor identity during explicit, policy-permitted same-family review."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from lee_llm_router.availability import parse_availability
from lee_llm_router.staffing.catalog import (
    load_staffing_catalog,
    load_staffing_document,
)
from lee_llm_router.staffing.run import RunSelectionError, select_route

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
AUTHOR = "claude-claude-sonnet-5-high-anthropic-sub"
REVIEWER = "claude-claude-sonnet-5-medium-anthropic-sub"
SUPERVISOR = "claude-claude-opus-5-high-anthropic-sub"
REVIEW_CLASS = "review/judge/none/s/python"


@pytest.fixture(scope="module")
def catalog():
    # Dated 2026-09-15 fixtures model then-active historical route.
    base = load_staffing_catalog(CONFIG_DIR)
    routes = tuple(
        replace(route, status="active")
        if route.route_id == SUPERVISOR
        else route
        for route in base.routes.routes
    )
    return replace(base, routes=replace(base.routes, routes=routes))


@pytest.fixture
def opt_in_catalog(catalog, tmp_path):
    policy = yaml.safe_load((CONFIG_DIR / "policy.yaml").read_text(encoding="utf-8"))
    policy["reviewer_independence"][0]["prefer_different_family"] = False
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    return replace(catalog, policy=load_staffing_document("policy", path))


def _availability(status: str = "COLD", remaining_pct: int = 90):
    return parse_availability(
        {
            "host": "fixture",
            "observed_at": "2026-09-09T11:59:00+00:00",
            "subscriptions": [
                {
                    "provider": "Anthropic/Claude",
                    "bucket": "Current session",
                    "status": status,
                    "remaining_pct": remaining_pct,
                }
            ],
        },
        now=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )


def _select(catalog, availability, route_id: str, *, rate_table_path=None):
    return select_route(
        catalog,
        availability,
        role="review",
        oracle_type="judge",
        size_band="s",
        language="python",
        class_key=REVIEW_CLASS,
        at_date="2026-09-15",
        route_id=route_id,
        author_route_id=AUTHOR,
        supervisor_route_id=SUPERVISOR,
        rate_table_path=rate_table_path,
    )


def test_opt_in_review_selects_reviewer_and_attests_same_family_supervisor(
    opt_in_catalog,
):
    outcome = _select(opt_in_catalog, _availability(), REVIEWER)
    supervisor = next(
        route for route in opt_in_catalog.routes.routes if route.route_id == SUPERVISOR
    )

    assert outcome.route.route_id == REVIEWER
    assert outcome.supervisor_route == {
        "model": supervisor.model,
        "effort": supervisor.effort,
        "harness": supervisor.harness,
        "channel": supervisor.channel,
        "provider": "claude_code_cli",
    }


def test_default_policy_still_excludes_same_family_reviewer(catalog):
    with pytest.raises(RunSelectionError, match="independence") as excinfo:
        _select(catalog, _availability(), REVIEWER)
    assert "explicit route" in str(excinfo.value)


def test_opt_in_still_excludes_exact_author(opt_in_catalog):
    with pytest.raises(RunSelectionError, match="independence") as excinfo:
        _select(opt_in_catalog, _availability(), AUTHOR)
    assert "explicit route" in str(excinfo.value)


def test_informational_disclosure_does_not_hide_headroom_veto(opt_in_catalog):
    with pytest.raises(RunSelectionError, match="channel exhausted") as excinfo:
        _select(opt_in_catalog, _availability("HOT", 0), REVIEWER)
    assert f"--supervisor-route {SUPERVISOR!r}" in str(excinfo.value)
    assert "currently usable route identity" in str(excinfo.value)


def test_informational_disclosure_does_not_hide_pricing_veto(opt_in_catalog, tmp_path):
    with pytest.raises(RunSelectionError, match="pricing unavailable") as excinfo:
        _select(
            opt_in_catalog,
            _availability(),
            REVIEWER,
            rate_table_path=tmp_path / "missing-rate-table.json",
        )
    assert f"--supervisor-route {SUPERVISOR!r}" in str(excinfo.value)


@pytest.mark.parametrize(
    ("governed_change", "reason"),
    [
        ("retired", "is not active"),
        ("harness_lock", "harness_lock"),
        ("missing_channel", "not in channel catalog"),
    ],
)
def test_other_identity_vetoes_still_refuse_supervisor(
    opt_in_catalog, governed_change, reason
):
    if governed_change == "retired":
        routes = tuple(
            replace(route, status="retired") if route.route_id == SUPERVISOR else route
            for route in opt_in_catalog.routes.routes
        )
        catalog = replace(
            opt_in_catalog, routes=replace(opt_in_catalog.routes, routes=routes)
        )
    else:
        channels = tuple(
            (
                replace(channel, harness_lock=("codex",))
                if channel.channel_id == "anthropic-sub"
                and governed_change == "harness_lock"
                else channel
            )
            for channel in opt_in_catalog.channels.channels
            if channel.channel_id != "anthropic-sub"
            or governed_change != "missing_channel"
        )
        catalog = replace(
            opt_in_catalog,
            channels=replace(opt_in_catalog.channels, channels=channels),
        )

    with pytest.raises(RunSelectionError, match=reason) as excinfo:
        _select(catalog, _availability(), REVIEWER)
    assert f"--supervisor-route {SUPERVISOR!r}" in str(excinfo.value)
