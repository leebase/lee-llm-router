"""Explicit same-family review policy against the real staffing catalog."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from lee_llm_router.availability import parse_availability
from lee_llm_router.staffing import StaffingEligibilityError, evaluate_eligibility
from lee_llm_router.staffing.catalog import (
    StaffingCatalogError,
    load_staffing_catalog,
    load_staffing_document,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
AUTHOR = "claude-claude-sonnet-5-high-anthropic-sub"
SAME_FAMILY = "claude-claude-sonnet-5-medium-anthropic-sub"
NEVER_AUTOMATIC = "claude-claude-opus-5-high-anthropic-sub"


@pytest.fixture(scope="module")
def catalog():
    # Dated 2026-09-15 fixtures model then-active historical route.
    base = load_staffing_catalog(CONFIG_DIR)
    routes = tuple(
        replace(route, status="active")
        if route.route_id == "claude-claude-opus-5-high-anthropic-sub"
        else route
        for route in base.routes.routes
    )
    return replace(base, routes=replace(base.routes, routes=routes))


@pytest.fixture(scope="module")
def availability():
    return parse_availability(
        {
            "host": "fixture",
            "observed_at": "2026-09-09T11:59:00+00:00",
            "subscriptions": [
                {
                    "provider": "Anthropic/Claude",
                    "bucket": "Current session",
                    "status": "COLD",
                    "remaining_pct": 90,
                },
            ],
        },
        now=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )


def _evaluate(catalog, availability, *, role="review", author_route_id=AUTHOR):
    return evaluate_eligibility(
        catalog,
        role=role,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        author_route_id=author_route_id,
        availability=availability,
        at_date="2026-09-15",
    )


def _row(rows, route_id):
    return next(row for row in rows if row.route_id == route_id)


def _policy_with_review_preference(tmp_path, value):
    policy = yaml.safe_load((CONFIG_DIR / "policy.yaml").read_text(encoding="utf-8"))
    policy["reviewer_independence"][0]["prefer_different_family"] = value
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    return load_staffing_document("policy", path)


def test_committed_true_keeps_cross_family_exclusion(catalog, availability):
    assert catalog.policy.reviewer_independence[0].prefer_different_family is True
    rows = _evaluate(catalog, availability)
    assert _row(rows, AUTHOR).reasons == ("independence",)
    assert _row(rows, SAME_FAMILY).reasons == ("independence",)


def test_explicit_false_permits_different_route_and_discloses_limit(
    catalog, availability, tmp_path
):
    policy = _policy_with_review_preference(tmp_path, False)
    rows = _evaluate(replace(catalog, policy=policy), availability)

    author = _row(rows, AUTHOR)
    assert author.eligible is False
    assert author.reasons == ("independence",)

    reviewer = _row(rows, SAME_FAMILY)
    assert reviewer.eligible is True
    assert len(reviewer.reasons) == 1
    assert "same-family review" in reviewer.reasons[0]
    assert "limited independence" in reviewer.reasons[0]

    # The review opt-in does not waive model governance or availability.
    opus = _row(rows, NEVER_AUTOMATIC)
    assert opus.eligible is False
    assert opus.reasons[0] == "never_automatic"
    assert "same-family review" in opus.reasons[-1]

    # A different provider still needs its own availability record.
    openai = _row(rows, "codex-gpt-5-6-sol-low-openai-sub")
    assert openai.eligible is False
    assert "channel unknown" in openai.reasons


def test_opt_in_does_not_bypass_anthropic_reserve(catalog, tmp_path):
    policy = _policy_with_review_preference(tmp_path, False)
    exhausted = parse_availability(
        {
            "host": "fixture",
            "observed_at": "2026-09-09T11:59:00+00:00",
            "subscriptions": [
                {
                    "provider": "Anthropic/Claude",
                    "bucket": "Current session",
                    "status": "HOT",
                    "remaining_pct": 0,
                },
            ],
        },
        now=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )
    reviewer = _row(_evaluate(replace(catalog, policy=policy), exhausted), SAME_FAMILY)
    assert reviewer.eligible is False
    assert "channel exhausted" in reviewer.reasons
    assert "bucket 'Current session' reserve: 10% kept in the tank (D216)" in reviewer.reasons


def test_judge_stays_cross_family_with_review_opt_in(catalog, availability, tmp_path):
    policy = _policy_with_review_preference(tmp_path, False)
    rows = _evaluate(replace(catalog, policy=policy), availability, role="judge")
    assert _row(rows, AUTHOR).reasons == ("independence",)
    assert _row(rows, SAME_FAMILY).reasons == ("independence",)


def test_absent_review_rule_fails_closed_in_eligibility(catalog, availability):
    policy = replace(catalog.policy, reviewer_independence=())
    rows = _evaluate(replace(catalog, policy=policy), availability)
    assert _row(rows, SAME_FAMILY).reasons == ("independence",)


def test_no_author_route_does_not_infer_one(catalog, availability, tmp_path):
    policy = _policy_with_review_preference(tmp_path, False)
    rows = _evaluate(
        replace(catalog, policy=policy), availability, author_route_id=None
    )
    reviewer = _row(rows, SAME_FAMILY)
    assert reviewer.eligible is True
    assert reviewer.reasons == ()


def test_unknown_author_still_fails_closed(catalog, availability, tmp_path):
    policy = _policy_with_review_preference(tmp_path, False)
    with pytest.raises(StaffingEligibilityError, match="author_route_id"):
        _evaluate(
            replace(catalog, policy=policy),
            availability,
            author_route_id="unknown-route",
        )


@pytest.mark.parametrize("value", [None, "false", 0])
def test_malformed_preference_rejected_by_schema(tmp_path, value):
    with pytest.raises(StaffingCatalogError):
        _policy_with_review_preference(tmp_path, value)


def test_missing_preference_rejected_by_schema(tmp_path):
    policy = yaml.safe_load((CONFIG_DIR / "policy.yaml").read_text(encoding="utf-8"))
    del policy["reviewer_independence"][0]["prefer_different_family"]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    with pytest.raises(StaffingCatalogError):
        load_staffing_document("policy", path)
