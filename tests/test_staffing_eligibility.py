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
from lee_llm_router.staffing.eligibility import resolve_route_family

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
    assert "; ".join(row.reasons) == "never_automatic; channel exhausted"
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
    assert opencode_glm.reasons == ()
    # deepseek-v4-pro (leading token 'deepseek') differs from z-ai: untouched.
    deepseek_pro = _by_route(rows, "pi-deepseek-v4-pro-opencode-go")
    assert deepseek_pro.eligible is True
    assert deepseek_pro.reasons == ()


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
