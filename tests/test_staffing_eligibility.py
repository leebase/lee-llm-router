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

from lee_llm_router.availability import (
    MODEL_SCOPED_BUCKETS,
    AvailabilitySnapshot,
    parse_availability,
)
from lee_llm_router.staffing import (
    EligibilityRow,
    StaffingEligibilityError,
    evaluate_eligibility,
)
from lee_llm_router.staffing.catalog import (
    ChannelInstance,
    canonical_class_key,
    load_staffing_catalog,
)
from lee_llm_router.staffing.eligibility import (
    EligibilityInstance,
    resolve_route_family,
)

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"

FABLE_ROUTE = "claude-claude-fable-5-1-high-anthropic-sub"
OPUS_ROUTE = "claude-claude-opus-5-high-anthropic-sub"
LUNA_MAX_ROUTE = "codex-gpt-5-6-luna-max-openai-sub"
LUNA_XHIGH_CODEX_ROUTE = "codex-gpt-5-6-luna-xhigh-openai-sub"
LUNA_XHIGH_PI_ROUTE = "pi-gpt-5-6-luna-xhigh-openai-sub"
MIMO_ROUTE = "opencode-opencode-go-mimo-v2-5-opencode-go"
GLM_OPENROUTER_ROUTE = "pi-z-ai-glm-5-3-flash-openrouter"
GEMINI_PRO_ROUTE = "agy-gemini-3-1-pro-gemini-sub"
SOL_LOW_ROUTE = "codex-gpt-5-6-sol-low-openai-sub"
TERRA_HIGH_ROUTE = "codex-gpt-5-6-terra-high-openai-sub"

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
    assert (
        "; ".join(row.reasons)
        == "never_automatic; channel exhausted; reserve: 10% kept in the tank (D216)"
    )
    assert row.availability_health == "exhausted"


def test_healthy_anthropic_keeps_fable_excluded_for_never_automatic_only(
    catalog, healthy_snapshot
) -> None:
    row = _by_route(_evaluate(catalog, healthy_snapshot), FABLE_ROUTE)
    assert row.eligible is False
    assert row.reasons == ("never_automatic",)


# ---------------------------------------------------------------------------
# Luna never_automatic is narrowed to effort max (chief round 10):
# Luna Max is excluded, Luna XHigh (both harnesses) is not excluded for
# that reason, and Fable/Opus model-level rules are unchanged.
# ---------------------------------------------------------------------------


def test_luna_max_excluded_with_never_automatic_reason(
    catalog, healthy_snapshot
) -> None:
    """The effort-max Luna rule (D152/D187/D204, round 10 narrowing) still
    excludes the Luna Max route under a healthy snapshot."""
    row = _by_route(_evaluate(catalog, healthy_snapshot), LUNA_MAX_ROUTE)
    assert row.eligible is False
    assert row.reasons == ("never_automatic",)
    assert row.model == "gpt-5.6-luna"
    assert row.effort == "max"


def test_luna_xhigh_codex_not_excluded_for_never_automatic(
    catalog, healthy_snapshot
) -> None:
    """Chief round 10 makes Luna XHigh an automatic escalation rung, so the
    effort-max rule must not exclude the codex XHigh route for that reason."""
    row = _by_route(_evaluate(catalog, healthy_snapshot), LUNA_XHIGH_CODEX_ROUTE)
    assert row.model == "gpt-5.6-luna"
    assert row.effort == "xhigh"
    assert "never_automatic" not in row.reasons
    assert row.eligible is True
    assert row.reasons == ()


def test_luna_xhigh_pi_not_excluded_for_never_automatic(
    catalog, healthy_snapshot
) -> None:
    """The round-10 escalation route `gpt-5.6-luna | pi | xhigh | openai-sub`
    itself must not carry a never_automatic reason."""
    row = _by_route(_evaluate(catalog, healthy_snapshot), LUNA_XHIGH_PI_ROUTE)
    assert row.model == "gpt-5.6-luna"
    assert row.effort == "xhigh"
    assert row.harness == "pi"
    assert "never_automatic" not in row.reasons
    assert row.eligible is True
    assert row.reasons == ()


def test_fable_and_opus_model_level_rules_unchanged_by_luna_narrowing(
    catalog, healthy_snapshot
) -> None:
    """The Luna effort narrowing touches only the Luna rule: Fable 5.1 and
    Opus 5 stay model-level never-automatic exclusions."""
    rows = _evaluate(catalog, healthy_snapshot)
    for route_id in (FABLE_ROUTE, OPUS_ROUTE):
        row = _by_route(rows, route_id)
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
# D216 subscription-channel reserve: a channel at or below its reserve
# fraction excludes its routes with the reserve reason; above the reserve
# they remain eligible (all else equal).
# ---------------------------------------------------------------------------

_SONNET_HIGH_ROUTE = "claude-claude-sonnet-5-high-anthropic-sub"
"""A never-automatic-free route on anthropic-sub for reserve tests."""


def test_reserve_at_or_below_excludes_with_reserve_reason(catalog) -> None:
    """Anthropic at exactly 10%% remaining (at reserve): the Sonnet route is
    excluded with the reserve: 10%% kept in the tank (D216) reason."""
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "ON TRACK",
            "remaining_pct": 10,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), _SONNET_HIGH_ROUTE)
    assert row.eligible is False
    assert "reserve: 10% kept in the tank (D216)" in row.reasons


def test_reserve_above_remains_eligible(catalog) -> None:
    """Anthropic at 11%% remaining (above reserve): the Sonnet route is
    eligible, no reserve reason."""
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "ON TRACK",
            "remaining_pct": 11,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), _SONNET_HIGH_ROUTE)
    assert row.eligible is True
    assert not any(r.startswith("reserve:") for r in row.reasons)


def test_reserve_and_health_both_exclude_independently(catalog) -> None:
    """Both the reserve check and the health-based veto run and can each
    independently exclude a route. At 0%% remaining (at or below reserve AND
    exhausted), the row carries both reasons.
    """
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "HOT",
            "remaining_pct": 0,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), _SONNET_HIGH_ROUTE)
    assert "reserve: 10% kept in the tank (D216)" in row.reasons
    assert "channel exhausted" in row.reasons


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


# ---------------------------------------------------------------------------
# Per-channel marginal pricing: each route is priced at the badge derived
# from its own channel's availability record (committed multipliers only).
# ---------------------------------------------------------------------------


def test_on_track_channel_prices_at_0_25(catalog, healthy_snapshot) -> None:
    row = _by_route(_evaluate(catalog, healthy_snapshot), SOL_LOW_ROUTE)
    assert row.availability_badge == "ON TRACK"
    assert row.pricing is not None
    assert row.pricing.badge == "ON TRACK"
    assert row.pricing.multiplier == 0.25
    assert row.pricing.marginal_input_usd_per_token == pytest.approx(
        0.25 * row.pricing.replacement_input_usd_per_token
    )
    # The replacement price itself is never folded with the multiplier.
    assert row.pricing.replacement_input_usd_per_token == pytest.approx(4.00 / 1e6)


def test_hot_channel_prices_at_0_75(catalog) -> None:
    # HOT with headroom is degraded (not vetoed): still priced, at 0.75x.
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "HOT",
            "remaining_pct": 80,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), SOL_LOW_ROUTE)
    assert row.availability_badge == "HOT"
    assert row.pricing is not None
    assert row.pricing.badge == "HOT"
    assert row.pricing.multiplier == 0.75
    assert row.pricing.marginal_input_usd_per_token == pytest.approx(
        0.75 * row.pricing.replacement_input_usd_per_token
    )
    assert row.pricing.marginal_output_usd_per_token == pytest.approx(
        0.75 * row.pricing.replacement_output_usd_per_token
    )


def test_cold_channel_prices_at_zero(catalog) -> None:
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "COLD",
            "remaining_pct": 90,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), FABLE_ROUTE)
    assert row.availability_badge == "COLD"
    assert row.pricing is not None
    assert row.pricing.badge == "COLD"
    assert row.pricing.multiplier == 0.0
    assert row.pricing.marginal_input_usd_per_token == 0.0
    assert row.pricing.marginal_output_usd_per_token == 0.0
    # Replacement price is preserved even at a zero multiplier.
    assert row.pricing.replacement_input_usd_per_token > 0.0


def test_use_it_channel_prices_at_zero(catalog) -> None:
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "USE IT",
            "remaining_pct": 80,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), SOL_LOW_ROUTE)
    assert row.availability_badge == "USE IT"
    assert row.pricing is not None
    assert row.pricing.badge == "USE IT"
    assert row.pricing.multiplier == 0.0
    assert row.pricing.marginal_input_usd_per_token == 0.0


def test_channel_without_record_fails_closed_to_no_data_multiplier(catalog) -> None:
    # The openrouter channel is metered: no quota record, no badge — it
    # must price at the committed NO DATA multiplier (1.0), never at a
    # neighbour channel's badge.
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENROUTER_ROUTE)
    assert row.availability_badge is None
    assert row.pricing is not None
    assert row.pricing.badge == "NO DATA"
    assert row.pricing.multiplier == 1.0
    assert row.pricing.marginal_input_usd_per_token == pytest.approx(
        row.pricing.replacement_input_usd_per_token
    )


def test_unknown_badge_fails_closed_to_replacement(catalog) -> None:
    # "UNAVAILABLE" is a snapshot failure status, not a pricing badge: the
    # catalog has no configured multiplier for it, so pricing fails closed
    # to full replacement (1.0) while the row still records the raw badge.
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "UNAVAILABLE",
            "remaining_pct": 80,
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), SOL_LOW_ROUTE)
    assert row.availability_badge == "UNAVAILABLE"
    assert row.pricing is not None
    assert row.pricing.badge == "UNAVAILABLE"
    assert row.pricing.multiplier == 1.0
    assert row.pricing.marginal_input_usd_per_token == pytest.approx(
        row.pricing.replacement_input_usd_per_token
    )


def test_channels_in_one_evaluation_price_at_their_own_badges(catalog) -> None:
    # One call, two channels, two different committed multipliers: codex is
    # ON TRACK (0.25) while anthropic is HOT (0.75). Replacement prices are
    # untouched and exclusion reasons are unaffected by the pricing seam.
    snapshot = _snapshot(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "HOT",
            "remaining_pct": 80,
        },
    )
    rows = _evaluate(catalog, snapshot)
    on_track = _by_route(rows, SOL_LOW_ROUTE)
    hot = _by_route(rows, FABLE_ROUTE)
    assert on_track.pricing is not None and hot.pricing is not None
    assert on_track.pricing.badge == "ON TRACK"
    assert on_track.pricing.multiplier == 0.25
    assert hot.pricing.badge == "HOT"
    assert hot.pricing.multiplier == 0.75
    # Exclusion reasons are preserved verbatim alongside per-route pricing.
    assert hot.reasons == ("never_automatic",)
    assert on_track.reasons == ()


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


# ---------------------------------------------------------------------------
# Chief round 15 packet D: author-route independence (review/judge only)
# ---------------------------------------------------------------------------

SONNET_HIGH_ROUTE = "claude-claude-sonnet-5-high-anthropic-sub"
DEEPSEEK_FLASH_ROUTE = "pi-deepseek-deepseek-v4-flash-openrouter"
GLM_OPENCODE_ROUTE = "pi-glm-5-3-flash-opencode-go"


def _catalog_route(catalog, route_id: str):
    return next(r for r in catalog.routes.routes if r.route_id == route_id)


def test_resolve_route_family_prefers_nonempty_route_family_attribute() -> None:
    """A route carrying a nonempty ``family`` attribute resolves from it."""
    from types import SimpleNamespace

    route = SimpleNamespace(route_id="x", model="gpt-5.6-sol", family="openai")
    assert resolve_route_family(route) == ("openai", "route.family")


def test_resolve_route_family_falls_back_to_model_id_deterministically(
    catalog,
) -> None:
    """Typed routes have no family: namespaced ids use the namespace before
    '/', unnamespaced ids use the leading token before the first '-'."""
    by_id = {r.route_id: r for r in catalog.routes.routes}
    assert resolve_route_family(by_id[GLM_OPENROUTER_ROUTE]) == (
        "z-ai",
        "model_vendor_prefix",
    )
    assert resolve_route_family(by_id[SOL_LOW_ROUTE]) == (
        "gpt",
        "model_vendor_prefix",
    )
    assert resolve_route_family(by_id[FABLE_ROUTE]) == (
        "claude",
        "model_vendor_prefix",
    )
    assert resolve_route_family(by_id[GEMINI_PRO_ROUTE]) == (
        "gemini",
        "model_vendor_prefix",
    )
    assert resolve_route_family(by_id[DEEPSEEK_FLASH_ROUTE]) == (
        "deepseek",
        "model_vendor_prefix",
    )
    # An empty family attribute is ignored (nonempty required).
    from types import SimpleNamespace

    empty = SimpleNamespace(route_id="x", model="gpt-5.6-sol", family="  ")
    assert resolve_route_family(empty) == ("gpt", "model_vendor_prefix")


def test_no_author_route_never_emits_independence(catalog, healthy_snapshot) -> None:
    """Without --author-route no route carries the independence reason."""
    for role in ("impl", "plan", "review", "judge", "prose"):
        rows = _evaluate(catalog, healthy_snapshot, role=role)
        assert all("independence" not in row.reasons for row in rows)


def test_same_author_route_excluded_with_independence_reason(
    catalog, healthy_snapshot
) -> None:
    """Review with the author route supplied: the author route itself is
    excluded with 'independence', preserving existing reason order."""
    rows = _evaluate(
        catalog,
        healthy_snapshot,
        role="review",
        author_route_id=SOL_LOW_ROUTE,
    )
    sol = _by_route(rows, SOL_LOW_ROUTE)
    assert sol.eligible is False
    assert sol.reasons == ("independence",)
    # Same-family candidates (gpt leading token) are excluded too.
    assert _by_route(rows, LUNA_XHIGH_PI_ROUTE).reasons == ("independence",)
    # Different-family routes are untouched.
    glm = _by_route(rows, GLM_OPENROUTER_ROUTE)
    assert glm.eligible is True
    assert glm.reasons == ()
    # Pricing is preserved alongside the added reason.
    assert sol.pricing is not None
    assert sol.pricing.multiplier == 0.25


def test_same_family_excluded_with_independence_reason(
    catalog, healthy_snapshot
) -> None:
    """Author Fable (claude family): the eligible same-family Sonnet route is
    excluded by 'independence' alone; the author route keeps its existing
    never_automatic reason first."""
    rows = _evaluate(
        catalog,
        healthy_snapshot,
        role="review",
        author_route_id=FABLE_ROUTE,
    )
    assert _by_route(rows, FABLE_ROUTE).reasons == (
        "never_automatic",
        "independence",
    )
    sonnet = _by_route(rows, SONNET_HIGH_ROUTE)
    assert sonnet.eligible is False
    assert sonnet.reasons == ("independence",)


def test_different_family_not_excluded(catalog, healthy_snapshot) -> None:
    """A different-family candidate stays eligible under a review author."""
    rows = _evaluate(
        catalog,
        healthy_snapshot,
        role="review",
        author_route_id=GLM_OPENROUTER_ROUTE,
    )
    glm = _by_route(rows, GLM_OPENROUTER_ROUTE)
    assert glm.eligible is False
    assert glm.reasons == ("independence",)
    # glm-5.3-flash (unnamespaced) is family 'glm', not 'z-ai': untouched.
    opencode_glm = _by_route(rows, GLM_OPENCODE_ROUTE)
    assert opencode_glm.eligible is True
    assert opencode_glm.reasons == ("inherited channel record",)
    # deepseek-v4-pro (leading token 'deepseek') differs from z-ai: untouched.
    deepseek_pro = _by_route(rows, "pi-deepseek-v4-pro-opencode-go")
    assert deepseek_pro.eligible is True
    assert deepseek_pro.reasons == ("inherited channel record",)


def test_judge_role_applies_independence(catalog, healthy_snapshot) -> None:
    """Judge with an author route behaves like review: same route and family
    excluded with the exact 'independence' reason."""
    rows = _evaluate(
        catalog, healthy_snapshot, role="judge", author_route_id=SOL_LOW_ROUTE
    )
    sol = _by_route(rows, SOL_LOW_ROUTE)
    assert sol.reasons == ("independence",)
    assert _by_route(rows, TERRA_HIGH_ROUTE).reasons == ("independence",)


def test_impl_role_author_route_is_not_applicable(catalog, healthy_snapshot) -> None:
    """For impl the check is not applicable: rows are identical to the
    baseline evaluation and the author route gains no independence reason."""
    baseline = _evaluate(catalog, healthy_snapshot, role="impl")
    rows = _evaluate(
        catalog,
        healthy_snapshot,
        role="impl",
        author_route_id=SOL_LOW_ROUTE,
    )
    assert rows == baseline
    assert all("independence" not in row.reasons for row in rows)


def test_unknown_author_route_fails_closed(catalog, healthy_snapshot) -> None:
    """An author route id matching no catalog route raises a named error."""
    with pytest.raises(StaffingEligibilityError) as excinfo:
        _evaluate(
            catalog,
            healthy_snapshot,
            role="review",
            author_route_id="no-such-route",
        )
    assert "no-such-route" in str(excinfo.value)
    assert "author_route_id" in str(excinfo.value)


def test_prose_role_author_route_is_not_applicable(catalog, healthy_snapshot) -> None:
    """Only review/judge carry the independence shape; prose does not."""
    rows = _evaluate(
        catalog,
        healthy_snapshot,
        role="prose",
        author_route_id=FABLE_ROUTE,
    )
    assert all("independence" not in row.reasons for row in rows)


# ---------------------------------------------------------------------------
# Packet M3-1: per-instance D216 reserve and health check
# ---------------------------------------------------------------------------


def test_channel_with_no_declared_instances_behaves_byte_identically(
    catalog,
) -> None:
    """(a) Anthropic has no declared instances: reduces to one implicit instance
    and behaves byte-identically to before for eligible, at-reserve, and exhausted."""
    # 1. Healthy / above reserve
    healthy = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "ON TRACK",
            "remaining_pct": 80,
        }
    )
    row_healthy = _by_route(_evaluate(catalog, healthy), _SONNET_HIGH_ROUTE)
    assert row_healthy.eligible is True
    assert row_healthy.reasons == ()
    assert len(row_healthy.instance_headrooms) == 1
    inst = row_healthy.instance_headrooms[0]
    assert isinstance(inst, EligibilityInstance)
    assert inst.instance_id == "anthropic-sub"
    assert inst.eligible is True
    assert inst.reasons == ()
    assert inst.remaining_fraction == pytest.approx(0.80)
    assert inst.health == "healthy"
    assert inst.badge == "ON TRACK"

    # 2. At reserve (10%)
    at_reserve = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "ON TRACK",
            "remaining_pct": 10,
        }
    )
    row_reserve = _by_route(_evaluate(catalog, at_reserve), _SONNET_HIGH_ROUTE)
    assert row_reserve.eligible is False
    assert row_reserve.reasons == ("reserve: 10% kept in the tank (D216)",)
    assert len(row_reserve.instance_headrooms) == 1
    inst_res = row_reserve.instance_headrooms[0]
    assert inst_res.instance_id == "anthropic-sub"
    assert inst_res.eligible is False
    assert inst_res.reasons == ("reserve: 10% kept in the tank (D216)",)
    assert inst_res.remaining_fraction == pytest.approx(0.10)

    # 3. Exhausted (0%)
    exhausted = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "HOT",
            "remaining_pct": 0,
        }
    )
    row_ex = _by_route(_evaluate(catalog, exhausted), _SONNET_HIGH_ROUTE)
    assert row_ex.eligible is False
    assert row_ex.reasons == (
        "channel exhausted",
        "reserve: 10% kept in the tank (D216)",
    )
    assert len(row_ex.instance_headrooms) == 1
    inst_ex = row_ex.instance_headrooms[0]
    assert inst_ex.instance_id == "anthropic-sub"
    assert inst_ex.eligible is False
    assert inst_ex.reasons == (
        "channel exhausted",
        "reserve: 10% kept in the tank (D216)",
    )
    assert inst_ex.remaining_fraction == pytest.approx(0.0)
    assert inst_ex.health == "exhausted"
    assert inst_ex.badge == "HOT"


def test_opencode_go_one_instance_at_reserve_one_above_route_eligible(
    catalog,
) -> None:
    """(b) opencode-go has instances a/b: instance a at reserve, instance b above.
    Route remains eligible with instance b ordered first in instance_headrooms."""
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 10,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 60,
            "instance": "b",
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is True
    assert row.reasons == ()
    assert len(row.instance_headrooms) == 2

    # b is clear (60%) and sorts first (descending remaining_fraction)
    first = row.instance_headrooms[0]
    assert first.instance_id == "b"
    assert first.eligible is True
    assert first.reasons == ()
    assert first.remaining_fraction == pytest.approx(0.60)
    assert first.health == "healthy"
    assert first.badge == "ON TRACK"

    # a is at reserve (10%) and sorts second, marked ineligible
    second = row.instance_headrooms[1]
    assert second.instance_id == "a"
    assert second.eligible is False
    assert second.reasons == ("reserve: 10% kept in the tank (D216)",)
    assert second.remaining_fraction == pytest.approx(0.10)
    assert second.health == "degraded"
    assert second.badge == "ON TRACK"


def test_opencode_go_one_instance_exhausted_one_clear_route_eligible(
    catalog,
) -> None:
    """(b symmetric) instance a is clear (75%), instance b is exhausted (0%).
    Route remains eligible with instance a ordered first in instance_headrooms."""
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "COLD",
            "remaining_pct": 75,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "HOT",
            "remaining_pct": 0,
            "instance": "b",
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is True
    assert row.reasons == ()
    assert len(row.instance_headrooms) == 2

    first = row.instance_headrooms[0]
    assert first.instance_id == "a"
    assert first.eligible is True
    assert first.reasons == ()
    assert first.remaining_fraction == pytest.approx(0.75)
    assert first.badge == "COLD"

    second = row.instance_headrooms[1]
    assert second.instance_id == "b"
    assert second.eligible is False
    assert second.reasons == (
        "channel exhausted",
        "reserve: 10% kept in the tank (D216)",
    )
    assert second.remaining_fraction == pytest.approx(0.0)
    assert second.health == "exhausted"


def test_opencode_go_both_instances_at_or_under_reserve_vetoes_route(
    catalog,
) -> None:
    """(c) Both opencode-go instances at/under reserve makes the route ineligible."""
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 10,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 10,
            "instance": "b",
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is False
    assert row.reasons == ("reserve: 10% kept in the tank (D216)",)
    assert len(row.instance_headrooms) == 2
    for inst in row.instance_headrooms:
        assert inst.eligible is False
        assert inst.reasons == ("reserve: 10% kept in the tank (D216)",)
        assert inst.remaining_fraction == pytest.approx(0.10)


def test_opencode_go_both_instances_exhausted_vetoes_route_with_reasons(
    catalog,
) -> None:
    """(c) Both opencode-go instances exhausted vetoes route with health
    and reserve reasons."""
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "HOT",
            "remaining_pct": 0,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "HOT",
            "remaining_pct": 0,
            "instance": "b",
        },
    )
    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is False
    assert "channel exhausted" in row.reasons
    assert "reserve: 10% kept in the tank (D216)" in row.reasons


def test_disabled_instance_excluded_from_instance_headrooms(catalog) -> None:
    """(d) A disabled instance never appears as eligible and is excluded from
    instance_headrooms entirely. Uses a test-local catalog with instance b disabled."""
    test_catalog = replace(
        catalog,
        channels=replace(
            catalog.channels,
            channels=tuple(
                (
                    replace(
                        channel,
                        instances=(
                            ChannelInstance("a", "opencode-go/a", enabled=True),
                            ChannelInstance("b", "opencode-go/b", enabled=False),
                        ),
                    )
                    if channel.channel_id == "opencode-go"
                    else channel
                )
                for channel in catalog.channels.channels
            ),
        ),
    )
    # Both instances have headroom in snapshot, but b is disabled in catalog
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 95,
            "instance": "b",
        },
    )
    row = _by_route(_evaluate(test_catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is True
    assert row.reasons == ()
    # Only enabled instance a appears; disabled instance b is excluded entirely
    assert len(row.instance_headrooms) == 1
    assert row.instance_headrooms[0].instance_id == "a"
    assert row.instance_headrooms[0].eligible is True
    assert all(inst.instance_id != "b" for inst in row.instance_headrooms)


def test_disabled_instance_does_not_rescue_route(catalog) -> None:
    """(d) When the only enabled instance is at reserve, a disabled instance
    with ample headroom does not rescue the route."""
    test_catalog = replace(
        catalog,
        channels=replace(
            catalog.channels,
            channels=tuple(
                (
                    replace(
                        channel,
                        instances=(
                            ChannelInstance("a", "opencode-go/a", enabled=True),
                            ChannelInstance("b", "opencode-go/b", enabled=False),
                        ),
                    )
                    if channel.channel_id == "opencode-go"
                    else channel
                )
                for channel in catalog.channels.channels
            ),
        ),
    )
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 5,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 95,
            "instance": "b",
        },
    )
    row = _by_route(_evaluate(test_catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is False
    assert "reserve: 10% kept in the tank (D216)" in row.reasons
    assert len(row.instance_headrooms) == 1
    assert row.instance_headrooms[0].instance_id == "a"
    assert row.instance_headrooms[0].eligible is False


def test_all_instances_disabled_emits_no_enabled_instance_reason(catalog) -> None:
    """When all instances of a channel are disabled, a dedicated reason is added."""
    test_catalog = replace(
        catalog,
        channels=replace(
            catalog.channels,
            channels=tuple(
                (
                    replace(
                        channel,
                        instances=(
                            ChannelInstance("a", "opencode-go/a", enabled=False),
                            ChannelInstance("b", "opencode-go/b", enabled=False),
                        ),
                    )
                    if channel.channel_id == "opencode-go"
                    else channel
                )
                for channel in catalog.channels.channels
            ),
        ),
    )
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80,
            "instance": "a",
        },
    )
    row = _by_route(_evaluate(test_catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is False
    assert "no enabled instance for channel 'opencode-go'" in row.reasons
    assert row.instance_headrooms == ()


def test_non_subscription_channel_carries_empty_instance_headrooms(
    catalog, healthy_snapshot
) -> None:
    """Non-subscription channels carry instance_headrooms=() by contract."""
    row = _by_route(_evaluate(catalog, healthy_snapshot), GLM_OPENROUTER_ROUTE)
    assert row.channel == "openrouter"
    assert row.instance_headrooms == ()


def test_instance_headrooms_none_remaining_fraction_sorts_last(catalog) -> None:
    """When an instance has None remaining_fraction, it sorts last in
    instance_headrooms."""
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 50,
            "instance": "a",
        },
        # instance b has no bucket recorded -> unknown -> remaining_fraction is None
    )
    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)
    assert row.eligible is True  # a is healthy and clears
    assert len(row.instance_headrooms) == 2
    assert row.instance_headrooms[0].instance_id == "a"
    assert row.instance_headrooms[0].remaining_fraction == pytest.approx(0.50)
    assert row.instance_headrooms[1].instance_id == "b"
    assert row.instance_headrooms[1].remaining_fraction is None
    assert row.instance_headrooms[1].health == "unknown"


# ---------------------------------------------------------------------------
# Packet S8: declared instances inherit channel-level availability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("remaining_pct", "eligible"),
    ((80, True), (8, False)),
)
def test_declared_instances_inherit_untagged_channel_record(
    catalog, remaining_pct: int, eligible: bool
) -> None:
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": remaining_pct,
        }
    )

    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)

    assert row.eligible is eligible
    assert {instance.instance_id for instance in row.instance_headrooms} == {"a", "b"}
    for instance in row.instance_headrooms:
        assert instance.eligible is eligible
        assert "inherited channel record" in instance.reasons
        assert instance.remaining_fraction == pytest.approx(remaining_pct / 100)
        assert instance.badge == "ON TRACK"
    if eligible:
        assert "inherited channel record" in row.reasons
    else:
        assert all(
            "reserve: 10% kept in the tank (D216)" in instance.reasons
            for instance in row.instance_headrooms
        )


def test_tagged_instance_wins_while_missing_instance_inherits_channel_record(
    catalog,
) -> None:
    snapshot = _snapshot(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 8,
        },
    )

    row = _by_route(_evaluate(catalog, snapshot), GLM_OPENCODE_ROUTE)
    instances = {instance.instance_id: instance for instance in row.instance_headrooms}

    assert row.eligible is True
    assert instances["a"].eligible is True
    assert instances["a"].remaining_fraction == pytest.approx(0.80)
    assert "inherited channel record" not in instances["a"].reasons
    assert instances["b"].eligible is False
    assert instances["b"].remaining_fraction == pytest.approx(0.08)
    assert "inherited channel record" in instances["b"].reasons
    assert "reserve: 10% kept in the tank (D216)" in instances["b"].reasons


def test_missing_instance_and_channel_record_remains_unknown(catalog) -> None:
    row = _by_route(_evaluate(catalog, _snapshot()), GLM_OPENCODE_ROUTE)

    assert row.eligible is False
    assert {instance.health for instance in row.instance_headrooms} == {"unknown"}
    assert all(not instance.eligible for instance in row.instance_headrooms)
    assert all(
        "inherited channel record" not in instance.reasons
        for instance in row.instance_headrooms
    )


# ---------------------------------------------------------------------------
# Packet P2: a model sub-limit gates only its own model family
# ---------------------------------------------------------------------------

FABLE_BUCKET = "Claude Fable — weekly"
"""The one ``ai-subs`` bucket the reader knows is a model sub-limit (P2)."""

FABLE_HEALTH_REASON = f"model bucket {FABLE_BUCKET!r} exhausted"
FABLE_RESERVE_REASON = (
    f"model bucket {FABLE_BUCKET!r} reserve: 10% kept in the tank (D216)"
)


def _anthropic_2026_09_16(*, fable_pct: float | None = 0.0) -> AvailabilitySnapshot:
    """The observed 2026-09-16 Anthropic shape: session 97%, all-models 14%, Fable 0%.

    The observed snapshot itself is evidence and is never read or edited here;
    this rebuilds its shape. ``fable_pct=None`` drops the sub-limit entirely,
    which is the scope-free control every other route must match.
    """
    entries: list[dict] = [
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "COLD",
            "remaining_pct": 97,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "All models — weekly",
            "status": "ON TRACK",
            "remaining_pct": 14,
        },
    ]
    if fable_pct is not None:
        entries.append(
            {
                "provider": "Anthropic/Claude",
                "bucket": FABLE_BUCKET,
                "status": "ON TRACK",
                "remaining_pct": fable_pct,
            }
        )
    return _snapshot(*entries)


def test_exhausted_model_sub_limit_stops_gating_its_siblings(catalog) -> None:
    """Fable at 0% must not exclude Sonnet or Opus while the channel holds 14%."""
    rows = _evaluate(catalog, _anthropic_2026_09_16())

    sonnet = _by_route(rows, _SONNET_HIGH_ROUTE)
    assert sonnet.eligible is True
    assert sonnet.reasons == ()
    assert sonnet.availability_health == "degraded"
    assert sonnet.availability_headroom == pytest.approx(0.14)
    assert sonnet.pricing is not None and sonnet.pricing.badge == "ON TRACK"

    # Opus carries its own model-level rule and picks up nothing from Fable.
    assert _by_route(rows, OPUS_ROUTE).reasons == ("never_automatic",)


def test_exhausted_model_sub_limit_still_gates_its_own_model(catalog) -> None:
    """Fable at 0% must still exclude Fable, citing its own bucket — not the channel."""
    rows = _evaluate(catalog, _anthropic_2026_09_16())
    fable = _by_route(rows, FABLE_ROUTE)

    assert fable.eligible is False
    assert fable.reasons == (
        "never_automatic",
        FABLE_HEALTH_REASON,
        FABLE_RESERVE_REASON,
    )
    # The exclusion names the sub-limit that actually ran out. The channel did
    # not: it still held 14%, and reading it as exhausted was the defect.
    assert FABLE_HEALTH_REASON in fable.reasons
    assert "channel exhausted" not in fable.reasons
    assert fable.availability_health == "degraded"


def test_healthy_model_sub_limit_adds_no_reason(catalog) -> None:
    """A sub-limit with headroom contributes nothing to its own route either."""
    rows = _evaluate(catalog, _anthropic_2026_09_16(fable_pct=56))
    fable = _by_route(rows, FABLE_ROUTE)
    assert fable.reasons == ("never_automatic",)
    assert not any("model bucket" in reason for reason in fable.reasons)


def test_model_sub_limit_reserve_veto_is_isolated(catalog) -> None:
    """Exactly at the reserve only the reserve veto fires, and it names the bucket."""
    rows = _evaluate(catalog, _anthropic_2026_09_16(fable_pct=10))
    fable = _by_route(rows, FABLE_ROUTE)
    assert fable.reasons == ("never_automatic", FABLE_RESERVE_REASON)
    assert FABLE_HEALTH_REASON not in fable.reasons
    # Sonnet is untouched by its sibling's reserve floor.
    assert _by_route(rows, _SONNET_HIGH_ROUTE).eligible is True


def test_model_sub_limit_health_veto_covers_unknown(catalog) -> None:
    """The health veto is the subscription veto set, ``unknown`` included."""
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "COLD",
            "remaining_pct": 97,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "All models — weekly",
            "status": "ON TRACK",
            "remaining_pct": 66,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": FABLE_BUCKET,
            "status": "NO DATA",
            "remaining_pct": 90,
        },
    )
    rows = _evaluate(catalog, snapshot)
    fable = _by_route(rows, FABLE_ROUTE)
    assert fable.reasons == (
        "never_automatic",
        f"model bucket {FABLE_BUCKET!r} unknown",
    )
    assert _by_route(rows, _SONNET_HIGH_ROUTE).eligible is True


def test_sub_limit_presence_changes_no_other_route(catalog) -> None:
    """Byte-identical rows: only Fable's own row differs from the scope-free run."""
    with_sub_limit = _evaluate(catalog, _anthropic_2026_09_16(fable_pct=0))
    without = _evaluate(catalog, _anthropic_2026_09_16(fable_pct=None))

    for scoped, plain in zip(with_sub_limit, without):
        assert scoped.route_id == plain.route_id
        if scoped.route_id == FABLE_ROUTE:
            assert scoped != plain
            continue
        assert scoped == plain


def test_second_table_row_needs_no_other_change(catalog, monkeypatch) -> None:
    """Extending the reader's table by one row scopes a further family."""
    monkeypatch.setitem(MODEL_SCOPED_BUCKETS, "Claude Opus — weekly", "claude-opus")
    snapshot = _snapshot(
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "COLD",
            "remaining_pct": 97,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "All models — weekly",
            "status": "ON TRACK",
            "remaining_pct": 66,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "Claude Opus — weekly",
            "status": "ON TRACK",
            "remaining_pct": 0,
        },
    )
    rows = _evaluate(catalog, snapshot)

    opus = _by_route(rows, OPUS_ROUTE)
    assert "model bucket 'Claude Opus — weekly' exhausted" in opus.reasons
    # Sonnet is a different family: untouched, and the channel is not exhausted.
    sonnet = _by_route(rows, _SONNET_HIGH_ROUTE)
    assert sonnet.eligible is True
    assert sonnet.reasons == ()
    assert sonnet.availability_health == "healthy"


def test_reserve_is_waived_when_the_window_is_about_to_reset():
    """D216's reserve preserves capacity for later work inside the window.

    Quota that expires before that work could happen cannot serve it, so
    holding it back is waste. Lee, 2026-09-17, with 53 minutes left on the
    weekly window and 10% unspent: "we are close to roll over so it's use it
    or lose it."
    """
    from lee_llm_router.staffing.eligibility import (
        RESERVE_WAIVER_HORIZON_HOURS,
        _reserve_waived,
    )

    # Inside the horizon: the window is ending, so the floor stops applying.
    assert _reserve_waived(0.0) is True
    assert _reserve_waived(0.88) is True
    assert _reserve_waived(RESERVE_WAIVER_HORIZON_HOURS - 0.01) is True

    # At or beyond the horizon the reserve holds normally.
    assert _reserve_waived(RESERVE_WAIVER_HORIZON_HOURS) is False
    assert _reserve_waived(12.0) is False
    assert _reserve_waived(168.0) is False


def test_reserve_holds_when_the_reset_horizon_is_unknown_or_nonsense():
    """Fail closed: an unreported or non-finite horizon never waives."""
    from lee_llm_router.staffing.eligibility import _reserve_waived

    assert _reserve_waived(None) is False
    assert _reserve_waived(float("nan")) is False
    assert _reserve_waived(float("inf")) is False
    assert _reserve_waived(-1.0) is False
