"""Tests for the P0-5a pure eligibility evaluation (staffing.eligibility).

Reads the committed catalog (``config/staffing``) read-only; the only
scratch state is the injected availability snapshot (parsed from dicts,
never a real file) and injectable pricing paths pointing at the committed
pinned sources. No provider call, no probability, no ladder, no ranking.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lee_llm_router.availability import parse_availability
from lee_llm_router.staffing import (
    EligibilityRow,
    StaffingEligibilityError,
    evaluate_eligibility,
)
from lee_llm_router.staffing.catalog import (
    canonical_class_key,
    load_staffing_catalog,
)

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"

FABLE_ROUTE = "claude-claude-fable-5-1-high-anthropic-sub"
MIMO_ROUTE = "opencode-opencode-go-mimo-v2-5-opencode-go"
GLM_OPENROUTER_ROUTE = "pi-z-ai-glm-5-3-flash-openrouter"
GEMINI_PRO_ROUTE = "agy-gemini-3-1-pro-gemini-sub"
SOL_LOW_ROUTE = "codex-gpt-5-6-sol-low-openai-sub"

_NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _snapshot(*subscriptions: dict):
    payload = {
        "host": "fixture",
        "observed_at": "2026-09-09T11:59:00+00:00",
        "subscriptions": list(subscriptions),
    }
    return parse_availability(payload, now=_NOW)


@pytest.fixture(scope="module")
def catalog():
    return load_staffing_catalog(REPO_CONFIG_DIR)


@pytest.fixture
def healthy_snapshot():
    """Every subscription channel observed with headroom; metered absent."""
    return _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "COLD",
            "remaining_pct": 90,
        },
        {
            "provider": "Gemini/agy",
            "bucket": "Gemini models",
            "status": "ON TRACK",
            "remaining_pct": 60,
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 50,
        },
    )


def _evaluate(catalog, snapshot, **kwargs) -> tuple[EligibilityRow, ...]:
    params = dict(
        role="impl",
        oracle_type="deterministic",
        size_band="s",
        language="python",
        domain_tags=(),
        at_date="2026-09-15",
        badge="ON TRACK",
    )
    params.update(kwargs)
    # Canonical key derived from the structured fields (record of truth).
    params.setdefault(
        "class_key",
        canonical_class_key(
            params["role"],
            params["oracle_type"],
            params["domain_tags"],
            params["size_band"],
            params["language"],
        ),
    )
    return evaluate_eligibility(catalog, availability=snapshot, **params)


def _by_route(rows: tuple[EligibilityRow, ...], route_id: str) -> EligibilityRow:
    return next(row for row in rows if row.route_id == route_id)


# ---------------------------------------------------------------------------
# Anthropic exhausted: Fable excluded with the plan-required reason string
# ---------------------------------------------------------------------------


def test_fable_reason_is_never_automatic_then_channel_exhausted(catalog) -> None:
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "HOT",
            "remaining_pct": 0,
        }
    )
    row = _by_route(_evaluate(catalog, snapshot), FABLE_ROUTE)
    assert row.eligible is False
    assert "; ".join(row.reasons) == "never_automatic; channel exhausted"
    assert row.availability_health == "exhausted"


def test_healthy_anthropic_keeps_fable_excluded_for_never_automatic_only(
    catalog, healthy_snapshot
) -> None:
    row = _by_route(_evaluate(catalog, healthy_snapshot), FABLE_ROUTE)
    assert row.eligible is False
    assert row.reasons == ("never_automatic",)


# ---------------------------------------------------------------------------
# Unknown subscription headroom vetoes; metered/local never falsely vetoed
# ---------------------------------------------------------------------------


def test_unknown_subscription_channel_vetoes_its_routes(catalog) -> None:
    # No Gemini/agy quota record at all -> gemini-sub is unknown -> veto.
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "ON TRACK",
            "remaining_pct": 80,
        }
    )
    row = _by_route(_evaluate(catalog, snapshot), GEMINI_PRO_ROUTE)
    assert row.eligible is False
    assert "channel unknown" in row.reasons
    assert row.availability_health == "unknown"


def test_metered_channel_without_quota_record_remains_evaluable(
    catalog, healthy_snapshot
) -> None:
    # openrouter is metered and the snapshot carries no quota record for it;
    # it must stay evaluable rather than being falsely vetoed.
    row = _by_route(_evaluate(catalog, healthy_snapshot), GLM_OPENROUTER_ROUTE)
    assert row.reasons == ()
    assert row.eligible is True
    assert row.availability_health == "unknown"
    assert row.availability_headroom is None
    assert row.pricing is not None
    assert row.pricing.source == "openrouter-snapshot:z-ai/glm-5.3-flash"


# ---------------------------------------------------------------------------
# Unpriced route status excludes (chief round 6 / D207)
# ---------------------------------------------------------------------------


def test_unpriced_route_excluded_with_named_reason(catalog, healthy_snapshot) -> None:
    row = _by_route(_evaluate(catalog, healthy_snapshot), MIMO_ROUTE)
    assert row.eligible is False
    assert row.status == "unpriced"
    assert row.reasons[0] == "route status unpriced"
    # Its pricing also fails closed (no invented price).
    assert "pricing unavailable" in row.reasons
    assert row.pricing is None


# ---------------------------------------------------------------------------
# D188 role scoping for Gemini 3.1 Pro (role-to-class, never a preference)
# ---------------------------------------------------------------------------


def test_gemini_pro_denied_for_coding_role_and_allowed_for_planning_review(
    catalog, healthy_snapshot
) -> None:
    impl_rows = _evaluate(catalog, healthy_snapshot, role="impl")
    denied = _by_route(impl_rows, GEMINI_PRO_ROUTE)
    assert denied.eligible is False
    assert "role_scoped: coding denied for gemini-3.1-pro" in denied.reasons

    plan_rows = _evaluate(catalog, healthy_snapshot, role="plan")
    allowed = _by_route(plan_rows, GEMINI_PRO_ROUTE)
    assert allowed.eligible is True
    assert allowed.reasons == ()


def test_role_scoped_is_the_only_class_driven_difference(catalog, healthy_snapshot):
    """All five roles agree everywhere except D188 role-scoped denials."""
    rows_by_role = {
        role: _evaluate(catalog, healthy_snapshot, role=role)
        for role in ("impl", "plan", "review", "judge", "prose")
    }
    for route_index, route in enumerate(catalog.routes.routes):
        if route.model == "gemini-3.1-pro":
            continue
        base = rows_by_role["impl"][route_index]
        assert base is not None and base.route_id == route.route_id
        for rows in rows_by_role.values():
            other = rows[route_index]
            assert (other.eligible, other.reasons) == (base.eligible, base.reasons)


# ---------------------------------------------------------------------------
# Canonical class-key validation against the classes catalog
# ---------------------------------------------------------------------------


def test_mismatched_class_key_rejected(catalog) -> None:
    with pytest.raises(StaffingEligibilityError) as excinfo:
        _evaluate(
            catalog,
            healthy_snapshot,
            class_key="impl/judge/none/s/python",
        )
    assert "class_key" in str(excinfo.value)
    assert "impl/deterministic/none/s/python" in str(excinfo.value)


def test_non_canonical_tag_order_rejected(catalog) -> None:
    # Unsorted tags: the canonical key sorts ascending by codepoint.
    with pytest.raises(StaffingEligibilityError):
        _evaluate(
            catalog,
            healthy_snapshot,
            domain_tags=("security", "persistence"),
            class_key="impl/deterministic/security+persistence/m/python",
        )


def test_value_outside_committed_set_rejected(catalog) -> None:
    with pytest.raises(StaffingEligibilityError) as excinfo:
        _evaluate(catalog, healthy_snapshot, role="sre")
    assert "'role'" in str(excinfo.value)


def test_missing_class_key_is_canonicalised(catalog, healthy_snapshot) -> None:
    # No class_key argument: the structured fields are the record of truth.
    rows = _evaluate(catalog, healthy_snapshot, class_key=None)
    assert len(rows) == len(catalog.routes.routes)


# ---------------------------------------------------------------------------
# D206: class metadata never adds eligibility or a preference
# ---------------------------------------------------------------------------


def test_class_metadata_never_changes_eligibility(catalog, healthy_snapshot):
    """A cheap-trial-denied class evaluates identically to a safe one."""
    safe = _evaluate(
        catalog, healthy_snapshot, role="impl", oracle_type="deterministic"
    )
    denied = _evaluate(
        catalog,
        healthy_snapshot,
        role="impl",
        oracle_type="human",
        size_band="l",
        domain_tags=("persistence", "security"),
        class_key="impl/human/persistence+security/l/python",
    )
    for safe_row, denied_row in zip(safe, denied):
        assert safe_row.eligible == denied_row.eligible
        assert safe_row.reasons == denied_row.reasons


# ---------------------------------------------------------------------------
# Determinism, ordering, and pricing fields
# ---------------------------------------------------------------------------


def test_rows_preserve_catalog_order_and_cover_every_route(
    catalog, healthy_snapshot
) -> None:
    rows = _evaluate(catalog, healthy_snapshot)
    assert [row.route_id for row in rows] == [
        route.route_id for route in catalog.routes.routes
    ]


def test_marginal_price_applies_badge_multiplier(catalog, healthy_snapshot) -> None:
    row = _by_route(
        _evaluate(catalog, healthy_snapshot, badge="ON TRACK"), SOL_LOW_ROUTE
    )
    assert row.pricing is not None
    assert row.pricing.multiplier == 0.25
    assert row.pricing.marginal_input_usd_per_token == pytest.approx(
        0.25 * row.pricing.replacement_input_usd_per_token
    )
    # The replacement price itself is never folded with the multiplier.
    assert row.pricing.replacement_input_usd_per_token == pytest.approx(4.00 / 1e6)


def test_unknown_badge_fails_closed_to_replacement(catalog, healthy_snapshot) -> None:
    row = _by_route(
        _evaluate(catalog, healthy_snapshot, badge="WHENEVER"), SOL_LOW_ROUTE
    )
    assert row.pricing is not None
    assert row.pricing.multiplier == 1.0


def test_harness_lock_excludes_route(catalog, healthy_snapshot) -> None:
    locked = replace(
        catalog,
        channels=replace(
            catalog.channels,
            channels=tuple(
                (
                    replace(
                        channel,
                        harness_lock=("omp",),
                    )
                    if channel.channel_id == "openrouter"
                    else channel
                )
                for channel in catalog.channels.channels
            ),
        ),
    )
    rows = _evaluate(locked, healthy_snapshot)
    row = _by_route(rows, GLM_OPENROUTER_ROUTE)
    assert row.eligible is False
    assert "harness 'pi' not in channel 'openrouter' harness_lock" in row.reasons


def test_terms_unavailable_before_first_effective_date(catalog, healthy_snapshot):
    rows = _evaluate(catalog, healthy_snapshot, at_date="2026-08-31")
    assert all(
        any("terms unavailable" in reason for reason in row.reasons) for row in rows
    )
    assert all(row.eligible is False for row in rows)


def test_non_iso_at_date_rejected(catalog, healthy_snapshot) -> None:
    with pytest.raises(StaffingEligibilityError):
        _evaluate(catalog, healthy_snapshot, at_date="not-a-date")
