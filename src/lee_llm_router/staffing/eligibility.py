"""Pure route-eligibility evaluation over the staffing catalog (P0-5).

Deterministic, typed evaluation returning one :class:`EligibilityRow` per
catalog route, in catalog order (never sorted or ranked here). Applied
checks, each with a named reason string:

* route status — ``unpriced``/``retired`` routes are excluded (chief round
  6: unpriced exact ids stay in the catalog and are excluded by
  eligibility, not absent);
* channel ``harness_lock`` — a route whose harness is not in the
  channel's committed lock list is excluded; an empty lock list means no
  committed mapping, so no constraint is invented;
* policy ``never_automatic`` (D152/D187/D204) — a matched model is never
  eligible for automatic selection;
* policy ``role_scoped`` (D188) — the class role maps to a governance
  class solely for this D188 check (``impl`` -> ``coding``;
  ``plan``/``review``/``judge``/``prose`` -> ``planning_review``),
  never a preference. The committed ``policy.role_class`` rows (D189)
  govern stage-role names and are not re-derived here;
* role floors — not applied: the committed catalog carries ``role_floors``
  records (Chief round 15, D86/D87), but floors are recorded data only —
  they are not enforced in Phase 0 because the current route tiers lack
  authority (no T1-T4 tier is assigned to any current route/model). No
  floor check runs here, so no floor exclusion reason is ever emitted and
  recorded floors change no route's eligibility;
* subscription headroom veto (``availability.py``) — a subscription
  channel whose headroom is ``exhausted``, ``likely_exhausted``, or
  ``unknown`` vetoes its routes. Metered and local channels carry no
  committed quota records and are never vetoed for their absence;
* dated terms at the requested date and the badge marginal multiplier —
  each route is priced at the badge derived from its own channel's record
  in the availability snapshot (the limiting bucket's raw status badge);
  a channel with no recorded badge (missing record, metered/local, or a
  snapshot failure status) fails closed to the committed ``NO DATA``
  badge, whose configured multiplier is 1.0. A pricing failure excludes
  the route with a named reason.
* author-route independence (Chief round 15, packet D) — applied only when
  an author route id is supplied *and* the role is ``review`` or
  ``judge``: the author route itself and every candidate whose model
  family equals the author's are excluded with the reason
  ``independence``. The family is the route's ``family`` attribute when
  it carries a nonempty one, else the deterministic model-vendor-prefix
  fallback (namespaced model id: namespace before ``/``; unnamespaced:
  leading token before the first ``-``). Independence is an
  author/candidate comparison only, never a class-to-model preference
  (D206). Without an author route id no ``independence`` reason is ever
  emitted; for roles other than review/judge the check is not applicable
  and no reason is added. An unknown author route id fails closed with a
  named :class:`StaffingEligibilityError`.

D206 (verbatim, phase0-contracts.md §Class-metadata prohibition):
"Class metadata MUST NOT map directly to a preferred model or route. It
may only: 1. join production attempts to comparable benchmark evidence;
and 2. determine whether an unevidenced cheap trial is permitted."
Accordingly the structured class fields and their canonical key are
validated against the committed classes value sets, and the role maps to
a governance class solely for D188 role-scoped eligibility. The cheap-
trial rule is *not* applied here and no class ever adds eligibility.

No probability, ladder, model choice, or ranking lives in this module
(Phase 2 owns those).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from lee_llm_router.availability import (
    AvailabilitySnapshot,
    ChannelHeadroom,
    Health,
)
from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.staffing.catalog import (
    Channel,
    StaffingCatalog,
    TermsCatalog,
    TermsEntry,
    canonical_class_key,
)
from lee_llm_router.staffing.catalog import (
    Route as StaffingRoute,
)
from lee_llm_router.staffing.terms import (
    StaffingTermsError,
    badge_multiplier,
    replacement_token_prices,
)

__all__ = [
    "EligibilityPrice",
    "EligibilityRow",
    "StaffingEligibilityError",
    "evaluate_eligibility",
    "resolve_author_route",
    "resolve_route_family",
]

_SUBSCRIPTION_VETO_HEALTH: frozenset[Health] = frozenset(
    {Health.EXHAUSTED, Health.LIKELY_EXHAUSTED, Health.UNKNOWN}
)
"""Subscription-channel headroom states that veto a route (fail closed)."""

_NO_DATA_BADGE = "NO DATA"
"""Committed badge used when a route's channel records no status badge.

A committed terms.yaml badge whose configured multiplier is 1.0, so a
missing/unknown badge fails closed to full replacement price — no number
is invented here; the multiplier comes from the catalog.
"""

#: Class role -> governance class, solely for D188 role-scoped eligibility.
#: This is a role-to-class mapping (D188/D189 direction); it is never a
#: class-to-model or class-to-route preference (D206).
_CLASS_ROLE_TO_GOVERNANCE: dict[str, str] = {
    "impl": "coding",
    "plan": "planning_review",
    "review": "planning_review",
    "judge": "planning_review",
    "prose": "planning_review",
}

_INDEPENDENCE_ROLES: frozenset[str] = frozenset({"review", "judge"})
"""Roles for which author-route independence applies (Chief round 15).

The vocabulary mapping is review -> reviewer, judge -> evaluator; other
roles carry no independence shape, so the check is not applicable there.
"""

_INDEPENDENCE_REASON = "independence"
"""Exact exclusion reason for the author-route independence check."""

_ROUTE_FAMILY_SOURCE_ATTR = "route.family"
_MODEL_FAMILY_SOURCE_PREFIX = "model_vendor_prefix"
"""Family-resolution source labels (Chief round 15, packet D).

``route.family`` is used when the route carries a nonempty ``family``
attribute; the committed typed routes have no family field, so the
fallback source is ``model_vendor_prefix``. No schema field or vendor
lookup table is added — the fallback is derived from the model id only.
"""


class StaffingEligibilityError(LLMRouterError):
    """Raised when the eligibility evaluation arguments are invalid.

    Carries :attr:`FailureType.CONTRACT_VIOLATION`. Raised for value-set
    violations or a canonical class-key mismatch, never for a route that
    merely fails eligibility (excluded routes are rows, not errors).
    """

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(
            message, failure_type=FailureType.CONTRACT_VIOLATION, cause=cause
        )


# ---------------------------------------------------------------------------
# Typed results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EligibilityPrice:
    """Marginal and replacement per-token prices for one route, when sourced.

    ``marginal_*`` equals ``replacement_* × multiplier`` for the requested
    badge; the replacement (list/reporting) figures are carried unchanged.
    ``source`` names the exact pricing resolution (see
    :func:`lee_llm_router.staffing.terms.replacement_token_prices`).
    """

    badge: str
    multiplier: float
    replacement_input_usd_per_token: float
    replacement_output_usd_per_token: float
    marginal_input_usd_per_token: float
    marginal_output_usd_per_token: float
    source: str


@dataclass(frozen=True)
class EligibilityRow:
    """One catalog route's eligibility under one class/availability/terms set.

    ``reasons`` is an ordered tuple of named reason strings; ``eligible``
    is exactly ``not reasons``. ``availability_*`` report the snapshot's
    channel headroom (health string, limiting bucket's raw status badge,
    smallest remaining fraction) whatever the channel kind — a reported
    ``unknown`` health on a metered/local channel is informational only
    and never a veto. ``pricing`` is ``None`` exactly when the replacement
    price could not be resolved; the marginal multiplier is applied to a
    copy, never folded into the replacement figures.
    """

    route_id: str
    model: str
    effort: str | None
    harness: str
    channel: str
    status: str
    eligible: bool
    reasons: tuple[str, ...]
    availability_health: str
    availability_badge: str | None
    availability_headroom: float | None
    pricing: EligibilityPrice | None


# ---------------------------------------------------------------------------
# Argument validation (classes value sets + canonical key equality)
# ---------------------------------------------------------------------------


def _validate_class(
    catalog: StaffingCatalog,
    *,
    role: str,
    oracle_type: str,
    domain_tags: tuple[str, ...],
    size_band: str,
    language: str,
    class_key: str | None,
) -> None:
    """Validate class values against the classes value sets and key equality.

    Raises :class:`StaffingEligibilityError` naming the offending field when
    a structured value is outside the committed classes value sets, or when
    a supplied ``class_key`` does not equal the canonical rendering of the
    structured five fields (the structured fields are the record of truth;
    the string is a derived join key).
    """
    value_sets = catalog.classes.value_sets
    checks: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("role", role, value_sets.role),
        ("oracle_type", oracle_type, value_sets.oracle_type),
        ("size_band", size_band, value_sets.size_band),
        ("language", language, value_sets.language),
    )
    for field, value, allowed in checks:
        if value not in allowed:
            raise StaffingEligibilityError(
                f"class field '{field}' value {value!r} is outside the committed "
                f"value set {sorted(allowed)}"
            )
    allowed_tags = set(value_sets.domain_tags)
    for tag in domain_tags:
        if tag not in allowed_tags:
            raise StaffingEligibilityError(
                f"class field 'domain_tags' value {tag!r} is outside the "
                f"committed value set {sorted(allowed_tags)}"
            )
    if class_key is not None:
        expected = canonical_class_key(
            role, oracle_type, domain_tags, size_band, language
        )
        if class_key != expected:
            raise StaffingEligibilityError(
                f"class_key {class_key!r} does not equal the canonical key of the "
                f"structured class arguments {expected!r} (the structured fields "
                f"are the record of truth; tags sorted ascending by codepoint, "
                f"'+'-joined, empty set as 'none')"
            )


# ---------------------------------------------------------------------------
# Per-check helpers
# ---------------------------------------------------------------------------


def _channel_index(catalog: StaffingCatalog) -> dict[str, Channel]:
    return {c.channel_id: c for c in catalog.channels.channels}


def _never_automatic_reason(
    catalog: StaffingCatalog, route_model: str, route_effort: str | None
) -> str | None:
    """Return ``"never_automatic"`` when a policy rule matches the route."""
    for rule in catalog.policy.never_automatic:
        if rule.model_ref != route_model:
            continue
        if rule.effort is None or rule.effort == route_effort:
            return "never_automatic"
    return None


def _role_scoped_reason(
    catalog: StaffingCatalog, route_model: str, governance_class: str
) -> str | None:
    """Return a reason when a D188 role_scoped rule denies the role class.

    Denial only: an allowed role class adds nothing, and a model/class pair
    the rules are silent about adds nothing — class metadata never grants
    eligibility or a preference (D206).
    """
    for rule in catalog.policy.role_scoped:
        if rule.model_ref != route_model:
            continue
        if governance_class in rule.denied_role_classes:
            return f"role_scoped: {governance_class} denied for {route_model}"
    return None


def resolve_route_family(route: Any) -> tuple[str, str]:
    """Resolve one route's model family and the source that produced it.

    Prefers a nonempty ``route.family`` attribute when the route carries
    one (source ``"route.family"``). The committed typed routes have no
    family field, so the fallback is deterministic over the model id: for
    a namespaced model id the namespace before the first ``/`` (e.g.
    ``z-ai/glm-5.3-flash`` -> ``z-ai``); for an unnamespaced model id the
    leading token before the first ``-`` (e.g. ``gpt-5.6-sol`` -> ``gpt``,
    ``claude-fable-5.1`` -> ``claude``), source
    ``"model_vendor_prefix"``. The result is an author/candidate
    comparison key for the independence check only — never a preference,
    ranking, choice, or ladder input (D206). No schema field or vendor
    lookup table is added.

    Args:
        route: A route-like object with a ``model`` attribute and an
            optional ``family`` attribute.

    Returns:
        ``(family, source)`` where ``source`` is ``"route.family"`` or
        ``"model_vendor_prefix"``.
    """
    family = getattr(route, "family", None)
    if isinstance(family, str) and family.strip():
        return family, _ROUTE_FAMILY_SOURCE_ATTR
    model = route.model
    if "/" in model:
        return model.split("/", 1)[0], _MODEL_FAMILY_SOURCE_PREFIX
    return model.split("-", 1)[0], _MODEL_FAMILY_SOURCE_PREFIX


def resolve_author_route(
    catalog: StaffingCatalog, author_route_id: str
) -> StaffingRoute:
    """Look up the author route by exact ``route_id`` (fail closed).

    Args:
        catalog: The loaded staffing catalog.
        author_route_id: The ``--author-route`` route id.

    Returns:
        The catalog route whose ``route_id`` equals ``author_route_id``.

    Raises:
        StaffingEligibilityError: When no catalog route carries that id —
            independence fails closed on an unknown author route.
    """
    for route in catalog.routes.routes:
        if route.route_id == author_route_id:
            return route
    raise StaffingEligibilityError(
        f"author_route_id {author_route_id!r} does not match any route_id in "
        "the routes catalog (independence fails closed on an unknown "
        "author route)"
    )


def _availability_for(
    availability: AvailabilitySnapshot, channel_id: str
) -> ChannelHeadroom:
    return availability.headroom(channel_id)


def _availability_badge(headroom: ChannelHeadroom) -> str | None:
    """Raw status badge of the headroom-limiting bucket, when recorded."""
    if headroom.limiting_bucket is None:
        return None
    for bucket in headroom.buckets:
        if bucket.name == headroom.limiting_bucket:
            return bucket.raw_status
    return None


def _dated_terms_entry(
    terms: TermsCatalog, channel_id: str, when: date
) -> TermsEntry | None:
    """Latest TermsEntry for one channel with effective_from <= ``when``.

    Mirrors :func:`lee_llm_router.staffing.terms.terms_at` semantics for a
    single channel; two entries sharing an effective_from are ambiguous and
    yield ``None`` (fail closed), never an invented pick.
    """
    candidates = [e for e in terms.terms if e.channel_ref == channel_id]
    dated: list[tuple[date, TermsEntry]] = []
    for entry in candidates:
        try:
            effective = date.fromisoformat(entry.effective_from)
        except ValueError:
            return None
        dated.append((effective, entry))
    on_or_before = [pair for pair in dated if pair[0] <= when]
    if not on_or_before:
        return None
    dates = [d for d, _ in on_or_before]
    if len(set(dates)) != len(dates):
        return None
    return max(on_or_before, key=lambda pair: pair[0])[1]


def _dedupe(reasons: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            ordered.append(reason)
    return tuple(ordered)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_eligibility(
    catalog: StaffingCatalog,
    *,
    role: str,
    oracle_type: str,
    size_band: str,
    language: str,
    domain_tags: tuple[str, ...] | list[str] = (),
    class_key: str | None = None,
    author_route_id: str | None = None,
    availability: AvailabilitySnapshot,
    at_date: date | str,
    openrouter_snapshot_path: str | Path | None = None,
    rate_table_path: str | Path | None = None,
) -> tuple[EligibilityRow, ...]:
    """Evaluate every catalog route's eligibility, preserving catalog order.

    Args:
        catalog: The loaded staffing catalog (routes, channels, terms,
            policy, classes). The catalog is read-only here.
        role: Class role (``impl | plan | review | judge | prose``); maps to
            a governance class solely for the D188 role-scoped check.
        oracle_type: Class oracle type (validated against the classes value
            set; recorded for the canonical key only — the cheap-trial rule
            is deliberately *not* applied here).
        size_band: Class size band (validated; canonical key only).
        language: Class language (validated; canonical key only).
        domain_tags: Class domain-tag set (validated; canonical key only).
        class_key: Optional canonical class-key string; when given it must
            equal :func:`canonical_class_key` of the structured fields or
            :class:`StaffingEligibilityError` is raised.
        author_route_id: Optional author route id (Chief round 15, packet
            D). Only for the ``review``/``judge`` roles: the author route
            itself and every candidate whose model family equals the
            author's (see :func:`resolve_route_family`) are excluded with
            the reason ``independence`` — an author/candidate comparison
            only, never a class-to-model preference (D206). For other
            roles the check is not applicable and no reason is added.
            An unknown id fails closed with a named
            :class:`StaffingEligibilityError`.
        availability: An already-normalised
            :class:`~lee_llm_router.availability.AvailabilitySnapshot`.
            Subscription channels with ``exhausted``/``likely_exhausted``/
            ``unknown`` headroom are vetoed; metered and local channels are
            never vetoed for missing quota records.
        at_date: Requested date (ISO string or :class:`datetime.date`) for
            the dated-terms check.
        openrouter_snapshot_path: Injectable pinned OpenRouter snapshot path
            (defaults to the committed pinned file).
        rate_table_path: Injectable agent-orch rate-table path (defaults to
            the committed default).

    Returns:
        One :class:`EligibilityRow` per catalog route, in catalog order.
        Each route's marginal price is its replacement price times the
        configured multiplier of the badge recorded for *its own channel*
        in ``availability`` (the limiting bucket's raw status badge); a
        channel with no recorded badge — missing record, metered/local
        channel, or a snapshot failure status — fails closed to the
        committed ``NO DATA`` badge (multiplier 1.0).
        ``eligible`` is exactly ``not reasons``; no ranking, sorting,
        probability, or choice is applied.

    Raises:
        StaffingEligibilityError: When a class field is outside the
            committed value sets or ``class_key`` mismatches the structured
            arguments, when ``at_date`` is not an ISO date, or when
            ``author_route_id`` is supplied but matches no catalog
            route_id.
    """
    _validate_class(
        catalog,
        role=role,
        oracle_type=oracle_type,
        domain_tags=tuple(domain_tags),
        size_band=size_band,
        language=language,
        class_key=class_key,
    )
    if isinstance(at_date, date):
        when = at_date
    else:
        try:
            when = date.fromisoformat(at_date)
        except (TypeError, ValueError) as exc:
            raise StaffingEligibilityError(
                f"at_date: not an ISO date (YYYY-MM-DD): {at_date!r}", cause=exc
            ) from exc
    governance_class = _CLASS_ROLE_TO_GOVERNANCE[role]
    channels = _channel_index(catalog)

    independence_applies = False
    author_family: str | None = None
    if author_route_id is not None:
        author_route = resolve_author_route(catalog, author_route_id)
        if role in _INDEPENDENCE_ROLES:
            independence_applies = True
            author_family, _author_source = resolve_route_family(author_route)

    rows: list[EligibilityRow] = []
    for route in catalog.routes.routes:
        reasons: list[str] = []
        channel = channels.get(route.channel)
        if channel is None:
            reasons.append(f"channel '{route.channel}' not in channel catalog")
            availability_health = Health.UNKNOWN.value
            availability_badge = None
            availability_headroom = None
        else:
            headroom = _availability_for(availability, channel.channel_id)
            availability_health = headroom.health.value
            availability_badge = _availability_badge(headroom)
            availability_headroom = headroom.remaining_fraction

            if route.status != "active":
                reasons.append(f"route status {route.status}")
            if channel.harness_lock and route.harness not in channel.harness_lock:
                reasons.append(
                    f"harness '{route.harness}' not in channel "
                    f"'{channel.channel_id}' harness_lock"
                )
            never_automatic = _never_automatic_reason(
                catalog, route.model, route.effort
            )
            if never_automatic is not None:
                reasons.append(never_automatic)
            role_scoped = _role_scoped_reason(catalog, route.model, governance_class)
            if role_scoped is not None:
                reasons.append(role_scoped)
            if (
                channel.kind == "subscription"
                and headroom.health in _SUBSCRIPTION_VETO_HEALTH
            ):
                reasons.append(f"channel {headroom.health.value}")
            if _dated_terms_entry(catalog.terms, channel.channel_id, when) is None:
                reasons.append(
                    f"terms unavailable at {when.isoformat()} for channel "
                    f"'{channel.channel_id}'"
                )

        if independence_applies:
            candidate_family, _ = resolve_route_family(route)
            if route.route_id == author_route_id or candidate_family == author_family:
                reasons.append(_INDEPENDENCE_REASON)

        pricing: EligibilityPrice | None = None
        # Per-route pricing seam: the badge is the one derived for this
        # route's own channel from the snapshot (availability_badge above,
        # None when the channel is missing from the catalog or carries no
        # limiting-bucket status), never a report-wide constant.
        pricing_badge = (
            availability_badge if availability_badge is not None else _NO_DATA_BADGE
        )
        try:
            replacement = replacement_token_prices(
                route.model,
                route.channel,
                openrouter_snapshot_path=openrouter_snapshot_path,
                rate_table_path=rate_table_path,
            )
        except StaffingTermsError:
            reasons.append("pricing unavailable")
        else:
            multiplier = badge_multiplier(pricing_badge, catalog.terms)
            pricing = EligibilityPrice(
                badge=pricing_badge,
                multiplier=multiplier,
                replacement_input_usd_per_token=replacement.input_usd_per_token,
                replacement_output_usd_per_token=replacement.output_usd_per_token,
                marginal_input_usd_per_token=replacement.input_usd_per_token
                * multiplier,
                marginal_output_usd_per_token=replacement.output_usd_per_token
                * multiplier,
                source=replacement.source,
            )

        ordered = _dedupe(reasons)
        rows.append(
            EligibilityRow(
                route_id=route.route_id,
                model=route.model,
                effort=route.effort,
                harness=route.harness,
                channel=route.channel,
                status=route.status,
                eligible=not ordered,
                reasons=ordered,
                availability_health=availability_health,
                availability_badge=availability_badge,
                availability_headroom=availability_headroom,
                pricing=pricing,
            )
        )
    return tuple(rows)
