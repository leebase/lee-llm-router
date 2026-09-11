"""Pure D211 route/class evidence joins over validated staffing evidence.

This module implements D211 rulings 1 and 2 of
``docs/staffing/phase2-contracts.md`` as pure functions over already
validated evidence.  It is a consumer, not a producer: it reads the exact
placements committed by the attempt-record v2 schema and by the P2-0
``evidence rollup`` output and never rewrites, derives, or duplicates them.

The evidence join (ruling 1) is scoped to the caller-supplied exact
``(route_id, class_key)`` pair.  It filters the observed route first, then
walks the fixed exact-to-coarse class-key order: the exact
``class_record.class_key`` first, then the key with ``language`` dropped,
then with ``size_band`` also dropped, then ``role/oracle_type`` only, and
finally ``none``.  The first level at which at least one attempt matches is
the used level, exposed both as the result's ``level`` field and as the
:class:`EvidenceJoin` ``evidence_level`` attribute.  ``n`` is the joined
attempts, ``k`` their verified passes (the ``verified_success`` equivalence
the rollup counts as ``verified_pass``), ``prior_n`` counts the benchmark
rows (``record_kind == "benchmark_run"``), and ``posterior_n`` counts the
production rows (``record_kind == "router_run"``).  The Laplace estimate is
exactly ``(k + 1) / (n + 2)`` and ``low_evidence`` is exactly ``n < 5``
(:data:`lee_llm_router.staffing.rollup.MINIMUM_SAMPLE_SIZE`).  A record
whose ``record_kind`` is neither value counts in ``n`` and ``k`` but in
neither split — the contract partitions prior/posterior by those two exact
kinds and invents no third bucket.  The summary returned by
:meth:`EvidenceJoin.as_dict` carries exactly the seven contract keys, so the
estimate is never shown without ``k``/``n`` and the level.

The class key is an evidence key only (D205/D206): it joins comparable
evidence and gates cheap trials.  The caller supplies route scope explicitly;
this module never maps a class to a model or route and never guesses a route
identifier.

Demand (ruling 2) is taken from the P2-0 rollup's ``token_medians`` and
``wall_clock_median_ms`` at the same join level — never recomputed from
sums, means, or the raw attempts.  Only groups with the exact requested
``route_id`` whose ``class_key`` matches at the used level contribute their
medians; when several class groups match within that route, their medians
are pooled and the exact median of the pool is emitted.  Unavailable medians
stay JSON ``null`` in the rollup and are emitted as the explicit string
``"unknown"`` here; when no median is usable at all, the whole demand is the
literal string ``"unknown"`` and no expected-cost figure exists.  Exact
half-integer medians remain the lossless ``"<whole>.5"`` decimal strings the
rollup emits (see :mod:`lee_llm_router.staffing.rollup`): when a single usable
median is consumed it is emitted verbatim, preserving its exact type.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Iterable, Mapping

from lee_llm_router.staffing.json_int import int_to_decimal
from lee_llm_router.staffing.rollup import (
    MINIMUM_SAMPLE_SIZE,
    TOKEN_FIELDS,
    _route_id,
    _without_superseded_benchmark_lines,
)

__all__ = [
    "DEMAND_UNKNOWN",
    "EVIDENCE_LEVELS",
    "EVIDENCE_LEVEL_DROP_LANGUAGE",
    "EVIDENCE_LEVEL_DROP_SIZE_BAND",
    "EVIDENCE_LEVEL_EXACT",
    "EVIDENCE_LEVEL_NONE",
    "EVIDENCE_LEVEL_ROLE_ORACLE_TYPE",
    "EvidenceJoin",
    "join_evidence",
]

DEMAND_UNKNOWN = "unknown"
"""The explicit demand value when no median is usable (D211 ruling 2)."""

EVIDENCE_LEVEL_EXACT = "exact"
"""The join level of the exact ``class_record.class_key``."""

EVIDENCE_LEVEL_DROP_LANGUAGE = "drop_language"
"""The join level after dropping the trailing ``language`` component."""

EVIDENCE_LEVEL_DROP_SIZE_BAND = "drop_size_band"
"""The join level after additionally dropping the ``size_band`` component."""

EVIDENCE_LEVEL_ROLE_ORACLE_TYPE = "role_oracle_type"
"""The join level reduced to the ``role/oracle_type`` prefix."""

EVIDENCE_LEVEL_NONE = "none"
"""The join level with no comparable evidence at all."""

EVIDENCE_LEVELS: tuple[str, ...] = (
    EVIDENCE_LEVEL_EXACT,
    EVIDENCE_LEVEL_DROP_LANGUAGE,
    EVIDENCE_LEVEL_DROP_SIZE_BAND,
    EVIDENCE_LEVEL_ROLE_ORACLE_TYPE,
    EVIDENCE_LEVEL_NONE,
)
"""The fixed exact-to-coarse join order of D211 ruling 1."""

SUMMARY_KEYS: tuple[str, ...] = (
    "level",
    "n",
    "k",
    "estimate",
    "low_evidence",
    "prior_n",
    "posterior_n",
)
"""The exact key set and order of the D211 ruling 1 evidence-join summary."""

BENCHMARK_RECORD_KIND = "benchmark_run"
"""The attempt-record kind counted in ``prior_n`` (D211 ruling 1)."""

ROUTER_RECORD_KIND = "router_run"
"""The attempt-record kind counted in ``posterior_n`` (D211 ruling 1)."""

#: Widths of the coarser join levels against the locked five-component
#: class-key grammar ``role/oracle_type/surface/size_band/language``.
_DROP_LANGUAGE_WIDTH = 4
_DROP_SIZE_BAND_WIDTH = 3
_ROLE_ORACLE_TYPE_WIDTH = 2


def _string_or_none(value: object) -> str | None:
    """Return a non-empty string, or the explicit unavailable value ``None``."""
    return value if isinstance(value, str) and value else None


def _record_class_key(record: Mapping[str, Any]) -> str | None:
    """Read the canonical class key at its committed placement.

    The v2 schema keeps the class key in ``class_record.class_key``; the
    plain ``class_key`` lookup is a compatibility convenience for callers
    passing already-normalised mappings, mirroring the rollup reader.
    """
    class_record = record.get("class_record")
    if isinstance(class_record, Mapping):
        class_key = _string_or_none(class_record.get("class_key"))
        if class_key is not None:
            return class_key
    return _string_or_none(record.get("class_key"))


def _record_kind(record: Mapping[str, Any]) -> str | None:
    """Read the attempt-record kind at its committed v2 placement."""
    return _string_or_none(record.get("record_kind"))


def _target_route_id(route_id: object) -> str | None:
    """Validate the exact route scope, retaining explicit missing-route scope."""
    if route_id is None:
        return None
    if isinstance(route_id, str) and route_id:
        return route_id
    raise ValueError(
        "route_id must be a non-empty string or None; the join never guesses "
        "or rewrites a route"
    )


def _group_matches_route(group: Mapping[str, Any], route_id: str | None) -> bool:
    """Match only an explicitly emitted rollup route field, without guessing."""
    return "route_id" in group and group.get("route_id") == route_id


def _target_components(class_key: object) -> list[str]:
    """Split the target class key, refusing unavailable or empty keys."""
    key = _string_or_none(class_key)
    if key is None:
        raise ValueError(
            "class_key must be a non-empty string; the join never guesses a key"
        )
    return key.split("/")


def _level_widths(target: list[str]) -> list[tuple[str, int]]:
    """Return the offered join levels with their match widths, in order.

    The exact level always matches the whole target.  A coarser level is
    offered only when the target actually carries the component it drops —
    a key without a ``language`` component cannot drop one, so ``exact`` is
    then already its coarsest comparable level before ``none``.  The locked
    grammar is five components, for which the widths are 5, 4, 3, 2.
    """
    widths: list[tuple[str, int]] = [(EVIDENCE_LEVEL_EXACT, len(target))]
    if len(target) > _DROP_LANGUAGE_WIDTH:
        widths.append((EVIDENCE_LEVEL_DROP_LANGUAGE, _DROP_LANGUAGE_WIDTH))
    if len(target) > _DROP_SIZE_BAND_WIDTH:
        widths.append((EVIDENCE_LEVEL_DROP_SIZE_BAND, _DROP_SIZE_BAND_WIDTH))
    if len(target) > _ROLE_ORACLE_TYPE_WIDTH:
        widths.append((EVIDENCE_LEVEL_ROLE_ORACLE_TYPE, _ROLE_ORACLE_TYPE_WIDTH))
    return widths


def _matches_at_width(
    record_key: str, target: list[str], width: int, *, exact: bool
) -> bool:
    """Whether one record class key matches the target at a join level.

    The exact level requires full component equality.  A coarse level joins
    every record sharing the target's leading ``width`` components, which is
    precisely the key with the dropped components removed.
    """
    components = record_key.split("/")
    if len(components) < width:
        return False
    if exact:
        return components == target
    return components[:width] == target[:width]


def _rollup_groups(rollup: object) -> list[Mapping[str, Any]]:
    """Extract the groups of an accepted P2-0 ``evidence rollup`` shape.

    Accepts either the rollup object ``{"groups": [...]}`` or a bare
    iterable of groups.  Anything else is treated as an empty rollup: a
    malformed input can never contribute a demand median.
    """
    if isinstance(rollup, Mapping):
        groups = rollup.get("groups")
        if isinstance(groups, list):
            return [group for group in groups if isinstance(group, Mapping)]
        return []
    if isinstance(rollup, Iterable) and not isinstance(rollup, (str, bytes)):
        return [group for group in rollup if isinstance(group, Mapping)]
    return []


def _group_class_key(group: Mapping[str, Any]) -> str | None:
    """Read a rollup group's class key; an unkeyed group matches nothing."""
    return _string_or_none(group.get("class_key"))


def _usable_median_fraction(value: object) -> Fraction | None:
    """Convert one rollup median into an exact fraction, else ``None``.

    Accepts exactly the median shapes the rollup emits: a nonnegative
    ``int``, a ``float`` (consumed at its exact binary value), and the
    lossless ``"<whole>.5"`` decimal string.  Booleans, nulls, and anything
    unparseable are unusable and are excluded from the demand pool.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(value)
    if isinstance(value, str) and value.endswith(".5"):
        try:
            whole = int(value[:-2])
        except ValueError:
            return None
        return Fraction(whole) + Fraction(1, 2)
    return None


def _emit_exact(value: Fraction) -> int | float | str:
    """Emit an exact pooled median in the rollup's JSON-safe conventions.

    Medians of half-integer medians stay integers or half-integers.  An
    integer is emitted as ``int``; a half-integer as ``float`` when exactly
    representable (53 significand bits, identical to the rollup rule) and
    otherwise as the lossless ``"<whole>.5"`` decimal string rendered
    through the bounded converter.  The final float branch is reachable only
    from non-half floats the committed rollup never emits.
    """
    if value.denominator == 1:
        return int(value)
    if value.denominator == 2 and value.numerator >= 0:
        numerator = value.numerator
        if numerator.bit_length() <= 53:
            return float(value)
        return f"{int_to_decimal(numerator // 2)}.5"
    return float(value)


def _pooled_median(values: list[object]) -> int | float | str | None:
    """Pool the usable medians of matching groups into one demand value.

    With no usable value the field is unavailable (``None``).  When every
    usable value is equal the first is emitted verbatim, preserving the
    rollup's exact type (``int``, ``float``, or the exact decimal string).
    Otherwise the exact median over the pooled values is emitted: with an
    odd pool its middle value, with an even pool the exact mean of the two
    middle values, both computed on exact rationals without rounding.
    """
    usable = [
        (value, fraction)
        for value, fraction in (
            (value, _usable_median_fraction(value)) for value in values
        )
        if fraction is not None
    ]
    if not usable:
        return None
    if len(usable) == len(values) and all(
        fraction == usable[0][1] for _, fraction in usable[1:]
    ):
        return usable[0][0]
    ordered = sorted(fraction for _, fraction in usable)
    count = len(ordered)
    if count % 2 == 1:
        return _emit_exact(ordered[count // 2])
    return _emit_exact((ordered[count // 2 - 1] + ordered[count // 2]) / 2)


def _demand_at_level(
    groups: list[Mapping[str, Any]],
    target: list[str],
    width: int,
    *,
    exact: bool,
) -> dict[str, Any] | str:
    """Build the D211 ruling 2 demand from rollup medians at one level.

    Only groups whose ``class_key`` matches at the used join level
    contribute.  Each token component and the wall-clock median pool the
    matching groups' non-null medians; a field with no usable median is the
    explicit string ``"unknown"``.  When no median at all is usable the
    whole demand is the literal string ``"unknown"`` and no expected-cost
    figure exists.
    """
    matching = [
        group
        for group in groups
        if (key := _group_class_key(group)) is not None
        and _matches_at_width(key, target, width, exact=exact)
    ]
    tokens: dict[str, int | float | str | None] = {}
    for field in TOKEN_FIELDS:
        values: list[object] = []
        for group in matching:
            medians = group.get("token_medians")
            if not isinstance(medians, Mapping):
                continue
            if medians.get(field) is not None:
                values.append(medians[field])
        tokens[field] = _pooled_median(values)
    wall_values: list[object] = []
    for group in matching:
        median = group.get("wall_clock_median_ms")
        if median is not None:
            wall_values.append(median)
    wall_clock_ms = _pooled_median(wall_values)

    if all(value is None for value in (*tokens.values(), wall_clock_ms)):
        return DEMAND_UNKNOWN
    return {
        "tokens": {
            field: (DEMAND_UNKNOWN if tokens[field] is None else tokens[field])
            for field in TOKEN_FIELDS
        },
        "wall_clock_ms": (DEMAND_UNKNOWN if wall_clock_ms is None else wall_clock_ms),
    }


class EvidenceJoin:
    """The D211 ruling 1 evidence join for one exact route/class pair.

    Attributes:
        n: Joined attempts at the used level.
        k: Verified passes (``verified_success is True``) among them.
        prior_n: Joined ``benchmark_run`` rows (the benchmark prior).
        posterior_n: Joined ``router_run`` rows (the production posterior).

    The join object never maps the class to a model or route and carries
    no selection, ranking, or expected-cost figure (D205/D206).
    """

    def __init__(
        self,
        *,
        level: str,
        n: int,
        k: int,
        prior_n: int,
        posterior_n: int,
        demand: dict[str, Any] | str,
    ) -> None:
        self._level = level
        self.n = n
        self.k = k
        self.prior_n = prior_n
        self.posterior_n = posterior_n
        self._demand = demand

    @property
    def evidence_level(self) -> str:
        """The used join level, exposed under its D211 ruling 1 name."""
        return self._level

    @property
    def level(self) -> str:
        """The used join level, under the summary's ``level`` key name."""
        return self._level

    @property
    def estimate(self) -> float:
        """The Laplace estimate ``(k + 1) / (n + 2)`` (D211 ruling 1)."""
        return (self.k + 1) / (self.n + 2)

    @property
    def low_evidence(self) -> bool:
        """Exactly ``n < 5`` (D211 ruling 1)."""
        return self.n < MINIMUM_SAMPLE_SIZE

    @property
    def demand(self) -> dict[str, Any] | str:
        """Demand medians at the used join level (D211 ruling 2).

        Either the literal string ``"unknown"`` when no median is usable,
        or a mapping with one explicit entry per rollup token component and
        the ``wall_clock_ms`` median, each unavailable field the string
        ``"unknown"``.
        """
        return self._demand

    def as_dict(self) -> dict[str, Any]:
        """Return exactly the seven D211 ruling 1 summary keys.

        Returns:
            A fresh dict with exactly ``level``, ``n``, ``k``, ``estimate``,
            ``low_evidence``, ``prior_n``, and ``posterior_n``, in the
            contract's order.  The estimate is never shown without ``k``,
            ``n``, and the level.
        """
        return {
            "level": self._level,
            "n": self.n,
            "k": self.k,
            "estimate": self.estimate,
            "low_evidence": self.low_evidence,
            "prior_n": self.prior_n,
            "posterior_n": self.posterior_n,
        }

    def __repr__(self) -> str:
        return (
            f"EvidenceJoin(level={self._level!r}, n={self.n}, k={self.k}, "
            f"prior_n={self.prior_n}, posterior_n={self.posterior_n})"
        )


def join_evidence(
    route_id: object,
    class_key: object,
    records: Iterable[Mapping[str, Any]],
    rollup: object = None,
) -> EvidenceJoin:
    """Join comparable evidence for one exact route/class pair.

    Args:
        route_id: The exact route scope.  A non-empty string is compared
            byte-for-byte; ``None`` explicitly selects records and rollup
            groups whose route is unavailable.  No route alias is inferred.
        class_key: The target ``class_record.class_key``.  Must be a
            non-empty string; the join never guesses or rewrites a key.
        records: Attempt records already validated by
            :func:`lee_llm_router.staffing.ledger.read_attempts` (or
            equivalent); they are consumed truthfully after applying the
            accepted rollup supersession view.
        rollup: Optional accepted P2-0 ``evidence rollup`` shape — the
            ``{"groups": [...]}`` object or a bare iterable of groups —
            normally :func:`lee_llm_router.staffing.rollup.build_rollup`
            output over the same records.  It supplies the demand medians;
            without it every demand field is explicitly ``"unknown"``.

    Returns:
        An :class:`EvidenceJoin` whose :meth:`~EvidenceJoin.as_dict` carries
        exactly ``{level, n, k, estimate, low_evidence, prior_n,
        posterior_n}`` and whose ``evidence_level`` is the used level.  The
        used level is the first level in the fixed exact-to-coarse order at
        which at least one record matches; ``none`` (with ``n = 0`` and the
        bare Laplace prior ``0.5``) when nothing matches.  A record whose
        ``record_kind`` is neither ``benchmark_run`` nor ``router_run``
        counts in ``n`` and ``k`` but in neither split.

    Raises:
        ValueError: If ``route_id`` is neither ``None`` nor a non-empty
            string, or if ``class_key`` is not a non-empty string.
    """
    target_route_id = _target_route_id(route_id)
    target = _target_components(class_key)
    levels = _level_widths(target)
    raw_records = [record for record in records if isinstance(record, Mapping)]
    # Reuse the accepted Phase-1/rollup supersession view.  This must happen
    # before route/class filtering so n, k, prior_n, and posterior_n describe
    # the same effective rows as build_rollup, even when the correction has a
    # different (or unavailable) route shape from its legacy source row.
    materialized = _without_superseded_benchmark_lines(raw_records)
    route_records = [
        record for record in materialized if _route_id(record) == target_route_id
    ]

    joined: list[Mapping[str, Any]] = []
    used = EVIDENCE_LEVEL_NONE
    used_width = 0
    for level, width in levels:
        joined = [
            record
            for record in route_records
            if (key := _record_class_key(record)) is not None
            and _matches_at_width(
                key, target, width, exact=level == EVIDENCE_LEVEL_EXACT
            )
        ]
        if joined:
            used = level
            used_width = width
            break

    prior_n = sum(
        1 for record in joined if _record_kind(record) == BENCHMARK_RECORD_KIND
    )
    posterior_n = sum(
        1 for record in joined if _record_kind(record) == ROUTER_RECORD_KIND
    )
    if used == EVIDENCE_LEVEL_NONE:
        # No comparable evidence exists at any level, so no rollup group can
        # match either: the demand is the explicit unknown, never a guess.
        demand: dict[str, Any] | str = DEMAND_UNKNOWN
    else:
        route_groups = [
            group
            for group in _rollup_groups(rollup)
            if _group_matches_route(group, target_route_id)
        ]
        demand = _demand_at_level(
            route_groups,
            target,
            used_width,
            exact=used == EVIDENCE_LEVEL_EXACT,
        )
    return EvidenceJoin(
        level=used,
        n=len(joined),
        k=sum(1 for record in joined if record.get("verified_success") is True),
        prior_n=prior_n,
        posterior_n=posterior_n,
        demand=demand,
    )
