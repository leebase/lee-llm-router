"""Auto staffing with a policy-permitted same-provider reviewer."""

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
from lee_llm_router.staffing.eligibility import resolve_route_family
from lee_llm_router.staffing.staff import staff

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
AUTHOR = "claude-claude-sonnet-5-high-anthropic-sub"
SAME_FAMILY = "claude-claude-sonnet-5-medium-anthropic-sub"
OTHER_FAMILY_AUTHOR = "pi-z-ai-glm-5-3-flash-openrouter"


@pytest.fixture(scope="module")
def catalog():
    return load_staffing_catalog(CONFIG_DIR)


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


@pytest.fixture
def opt_in_catalog(catalog, tmp_path):
    policy = yaml.safe_load((CONFIG_DIR / "policy.yaml").read_text(encoding="utf-8"))
    policy["reviewer_independence"][0]["prefer_different_family"] = False
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    return replace(catalog, policy=load_staffing_document("policy", path))


def _auto(catalog, availability, *, author_route_id=None):
    return staff(
        catalog,
        availability,
        mode="auto",
        role="impl",
        class_key="impl/deterministic/none/s/python",
        at_date="2026-09-15",
        author_route_id=author_route_id,
        attempt_records=[
            {
                "record_kind": "router_run",
                "router_event": {"route_id": AUTHOR},
                "class_record": {
                    "class_key": "impl/deterministic/none/s/python"
                },
                "usage": {"basis": "observed"},
                "verified_success": False,
            }
        ],
        rollup={"groups": []},
    )


@pytest.mark.parametrize("author_route_id", [None, AUTHOR])
def test_auto_selects_same_family_reviewer_with_limited_disclosure(
    opt_in_catalog, availability, author_route_id
):
    result = _auto(
        opt_in_catalog, availability, author_route_id=author_route_id
    )
    review = result.payload["review"]

    assert result.payload["selected_route"] == AUTHOR
    assert review["route_id"] == SAME_FAMILY
    assert review["eligible"] is True
    assert review["independence_evaluated"] is True
    assert review["independence_reference"] == AUTHOR
    assert "same-family review" in review["reason"]
    assert "limited independence" in review["reason"]
    assert f"distinct from {AUTHOR}" in result.text
    assert "limited independence" in result.text
    assert f"independent of {AUTHOR}" not in result.text


def test_auto_discloses_selected_worker_family_with_different_explicit_author(
    opt_in_catalog, availability
):
    result = _auto(
        opt_in_catalog,
        availability,
        author_route_id=OTHER_FAMILY_AUTHOR,
    )
    review = result.payload["review"]

    assert result.payload["selected_route"] == AUTHOR
    assert review["route_id"] == SAME_FAMILY
    assert review["eligible"] is True
    assert review["independence_reference"] == OTHER_FAMILY_AUTHOR
    assert "same model family as selected worker" in review["reason"]
    assert "same model family as author" not in review["reason"]
    assert "limited independence" in review["reason"]
    assert f"distinct from author {OTHER_FAMILY_AUTHOR}" in result.text
    assert f"distinct from selected {AUTHOR}" in result.text
    assert "independent of author" not in result.text


def test_auto_default_remains_strict(catalog, availability):
    result = _auto(catalog, availability)
    review = result.payload["review"]
    routes = {route.route_id: route for route in catalog.routes.routes}

    assert result.payload["selected_route"] == AUTHOR
    assert review["route_id"] is not None
    assert review["route_id"] not in (AUTHOR, SAME_FAMILY)
    reviewer_family, _ = resolve_route_family(routes[review["route_id"]])
    author_family, _ = resolve_route_family(routes[AUTHOR])
    assert reviewer_family != author_family
    assert "limited independence" not in (review["reason"] or "")


def test_auto_opt_in_rejects_exact_explicit_author_and_selected_worker(
    opt_in_catalog, availability
):
    result = _auto(opt_in_catalog, availability, author_route_id=SAME_FAMILY)
    review = result.payload["review"]

    assert result.payload["selected_route"] == AUTHOR
    assert review["independence_evaluated"] is True
    assert review["independence_reference"] == SAME_FAMILY
    assert review["route_id"] is not None
    assert review["route_id"] not in (SAME_FAMILY, AUTHOR)
    assert f"independent of author {SAME_FAMILY}" in result.text
    assert f"selected {AUTHOR} also excluded" in result.text
