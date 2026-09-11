"""Deterministic rollups of validated staffing attempt evidence.

The rollup is deliberately descriptive only.  It groups validated attempt
records by the observed ``(route_id, class_key)`` pair and reports counts and
aggregates; it does not calculate probabilities, scores, routing rules, or
ladders.

Token components are independent observations.  A non-null counter contributes
to that component's sum and median; a component with no observed counters is
rendered as ``null``, never as a fabricated zero.  Thus a nullable optional
counter remains visibly unavailable, while a partially observed component is
explicitly an aggregate of the observed values only.

The append-only ledger can describe one benchmark source run twice: the
pre-repair legacy crew-run line and the deterministic ``benchmark:v6:<run_id>``
correction a governed re-import appends for it.  History is never rewritten,
but the correction supersedes its legacy source attempt in the aggregation, so
every distinct source run is counted exactly once.  Runs without a correction,
and all non-benchmark records, pass through unchanged.

Medians are exact and every validated ledger integer is accepted: an odd
sample reports its middle counter, and an even sample reports the exact
arithmetic mean of its two middle counters — an ``int`` when that mean is an
integer, a ``float`` when the half-integer is exactly representable in binary
floating point, and otherwise the exact ``"<whole>.5"`` decimal string,
because neither exact Python numeric type can carry the value: an ``int`` is
never fractional and a ``float`` would round the half away above 53
significand bits, while JSON itself can carry the exact digits and the lossless
``str`` preserves them.  Pass counting follows each record's own verdict
shape: canonical v2 records carry the verdict string ``pass`` and break down by
class oracle type, while agent-orch imports (chief answer 3) carry the verdict
object ``{"tier": "engine_validation"}`` whose pass fact is exactly the
schema's ``verified_success`` equivalence (``worker_exit_code == 0`` and
``validation_passed == true``); those passes count under the
``engine_validation`` key.  Every record contributes to at most one breakdown
key, so no pass is ever counted twice.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from lee_llm_router.staffing.import_evidence import (
    BENCHMARK_CORRECTION_PREFIX,
    benchmark_source_run_id,
    is_benchmark_v6_record,
)
from lee_llm_router.staffing.json_int import dump_json, int_to_decimal
from lee_llm_router.staffing.ledger import read_attempts, resolve_attempts_path

MINIMUM_SAMPLE_SIZE = 5
"""The sample size at which a route/class group is comparison eligible."""

TOKEN_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "total_tokens",
)
"""Token counter fields in the committed attempt-record v2 usage object."""

__all__ = [
    "MINIMUM_SAMPLE_SIZE",
    "TOKEN_FIELDS",
    "build_rollup",
    "render_rollup",
    "rollup_attempts",
    "rollup_ledger",
    "summarize_attempts",
]


def _string_or_none(value: object) -> str | None:
    """Return a non-empty string, or the explicit unavailable value ``None``."""
    return value if isinstance(value, str) and value else None


def _route_id(record: Mapping[str, Any]) -> str | None:
    """Read the route id from the v2 router-event evidence.

    ``route_id`` is not duplicated into the v2 ``route`` identity object: the
    committed schema places it in ``router_event``.  The other two lookups are
    compatibility conveniences for callers of the pure aggregation function;
    records read from the committed ledger use the first lookup.
    """
    event = record.get("router_event")
    if isinstance(event, Mapping):
        route_id = _string_or_none(event.get("route_id"))
        if route_id is not None:
            return route_id

    # These fallbacks do not affect schema-valid v2 records.  They make the
    # pure function useful with already-normalised test mappings without
    # changing the ledger's source-of-truth placement.
    route_id = _string_or_none(record.get("route_id"))
    if route_id is not None:
        return route_id
    route = record.get("route")
    if isinstance(route, Mapping):
        return _string_or_none(route.get("route_id"))
    return None


def _class_key(record: Mapping[str, Any]) -> str | None:
    """Read the canonical class key without deriving or rewriting it."""
    class_record = record.get("class_record")
    if isinstance(class_record, Mapping):
        class_key = _string_or_none(class_record.get("class_key"))
        if class_key is not None:
            return class_key
    return _string_or_none(record.get("class_key"))


def _oracle_type(record: Mapping[str, Any]) -> str | None:
    """Read the class oracle type used for the pass-count breakdown."""
    class_record = record.get("class_record")
    if isinstance(class_record, Mapping):
        oracle_type = _string_or_none(class_record.get("oracle_type"))
        if oracle_type is not None:
            return oracle_type
    return _string_or_none(record.get("oracle_type"))


def _usage(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the usage object when the record carries one."""
    value = record.get("usage")
    return value if isinstance(value, Mapping) else None


def _counter(value: object) -> int | None:
    """Return a truthful nonnegative integer counter, otherwise ``None``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _known_usage(record: Mapping[str, Any]) -> bool:
    """Whether the record has a non-unavailable usage basis.

    The basis is the source's statement about usage availability.  Individual
    nullable counters are handled independently by :func:`_token_values` and
    do not turn a provider-reported usage record into an unavailable record.
    """
    usage = _usage(record)
    return usage is not None and usage.get("basis") in {
        "observed",
        "provider_reported",
        "calculated",
    }


def _token_values(members: Iterable[Mapping[str, Any]], field: str) -> list[int]:
    """Collect only known values for one token component."""
    values: list[int] = []
    for record in members:
        usage = _usage(record)
        if usage is None:
            continue
        value = _counter(usage.get(field))
        if value is not None:
            values.append(value)
    return values


def _exact_median(values: list[int]) -> int | float | str:
    """Return the exact median of integer counters as a JSON-safe value.

    ``statistics.median`` divides the sum of the two middle values in
    floating point, which raises :class:`OverflowError` for validated
    counters such as ``10**400`` on an even sample and silently rounds any
    total above 53 significand bits.  This helper keeps every emitted median
    exact.  An odd sample returns its middle counter (an ``int``).  An even
    sample returns the exact arithmetic mean of its two middle counters:
    an ``int`` when the sum is even, a ``float`` when the half-integer is
    exactly representable in binary floating point (sum ``bit_length <= 53``,
    identical to what ``statistics.median`` returns there), and otherwise
    the exact ``"<whole>.5"`` decimal string — neither exact Python numeric
    type can carry the value (an ``int`` is never fractional and a ``float``
    would round above 53 significand bits), so the lossless decimal string
    is the truthful representation; rounding is never substituted for it.
    """
    ordered = sorted(values)
    count = len(ordered)
    if count % 2 == 1:
        return ordered[count // 2]
    total = ordered[count // 2 - 1] + ordered[count // 2]
    if total % 2 == 0:
        return total // 2
    if total.bit_length() <= 53:
        return total / 2
    # The whole part can exceed the interpreter's default int-to-decimal
    # ceiling (e.g. an odd sum of aggregates near ``9 * 10**4299``), so its
    # exact digits are rendered through the bounded converter.
    return f"{int_to_decimal(total // 2)}.5"


def _token_aggregates(
    members: list[Mapping[str, Any]],
) -> tuple[dict[str, int | float | str | None], dict[str, int | float | str | None]]:
    """Build component-wise sums and exact median values.

    The grouping/counting approach follows the aggregation in
    ``/home/lee/projects/auto-orch/src/auto_orch/performance.py``
    (``summarize_observations``): collect members, count facts with ``sum``,
    and sort emitted groups deterministically.  :func:`_exact_median` keeps
    the ``statistics.median`` sample semantics (odd samples return the
    middle value, even samples the arithmetic mean of the two middle values)
    without its float-division overflow or rounding.  No missing component
    is passed to ``sum`` as zero.
    """
    sums: dict[str, int | float | str | None] = {}
    medians: dict[str, int | float | str | None] = {}
    for field in TOKEN_FIELDS:
        values = _token_values(members, field)
        sums[field] = sum(values) if values else None
        medians[field] = _exact_median(values) if values else None
    return sums, medians


def _group_sort_key(key: tuple[str | None, str | None]) -> tuple[int, str, int, str]:
    """Sort known string keys lexically, with unavailable keys first."""
    route_id, class_key = key
    return (
        0 if route_id is None else 1,
        route_id or "",
        0 if class_key is None else 1,
        class_key or "",
    )


def _pass_oracle_type(record: Mapping[str, Any]) -> str | None:
    """Return the breakdown key when the record counts as a pass.

    Canonical v2 records pass when their verdict string is ``pass`` and are
    broken down by the class oracle type chosen for the attempt.  Agent-Orch
    imports (chief answer 3) instead carry the verdict object
    ``{"tier": "engine_validation"}`` for every attempt: the tier names
    agent-orch's own worker-exit/validation gate, never an oracle chosen by
    this repository, and its pass fact is exactly the schema's
    ``verified_success`` equivalence (``worker_exit_code == 0`` and
    ``validation_passed == true``).  Those verified passes count under the
    ``engine_validation`` key so the breakdown totals stay truthful.  A
    record has exactly one verdict shape, so it can contribute to at most
    one key and no pass is ever double counted.
    """
    verdict = record.get("verdict")
    if isinstance(verdict, Mapping):
        if (
            verdict.get("tier") == "engine_validation"
            and record.get("verified_success") is True
        ):
            return "engine_validation"
        return None
    if verdict == "pass":
        return _oracle_type(record)
    return None


def _group_record(
    route_id: str | None,
    class_key: str | None,
    members: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Render one route/class group in the stable field order."""
    pass_by_oracle_type: dict[str, int] = {}
    for record in members:
        oracle_type = _pass_oracle_type(record)
        if oracle_type is not None:
            pass_by_oracle_type[oracle_type] = (
                pass_by_oracle_type.get(oracle_type, 0) + 1
            )

    token_sums, token_medians = _token_aggregates(members)
    wall_clocks = [
        value
        for value in (_counter(record.get("wall_clock_ms")) for record in members)
        if value is not None
    ]
    wall_clock_median = _exact_median(wall_clocks) if wall_clocks else None
    return {
        "route_id": route_id,
        "class_key": class_key,
        "attempts": len(members),
        "verified_pass": sum(
            1 for record in members if record.get("verified_success") is True
        ),
        "pass_by_oracle_type": {
            key: pass_by_oracle_type[key] for key in sorted(pass_by_oracle_type)
        },
        "token_sums": token_sums,
        "token_medians": token_medians,
        "wall_clock_median_ms": wall_clock_median,
        "usage_known": sum(1 for record in members if _known_usage(record)),
        "comparison_eligible": len(members) >= MINIMUM_SAMPLE_SIZE,
    }


def _without_superseded_benchmark_lines(
    records: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Drop legacy benchmark lines superseded by their truthful correction.

    A governed benchmark re-import appends one deterministic
    ``benchmark:v6:<run_id>`` correction per pre-repair legacy crew-run line
    and never rewrites the append-only ledger.  Aggregation must still count
    each distinct source run exactly once, so when a raw v6 record describes
    a run, every legacy-shaped line describing that same run is superseded
    and excluded here.  Lines stay in the ledger; only this rollup view
    changes.  Runs without a correction, records whose source run id cannot
    be read, and all non-benchmark records pass through unchanged.  Should
    multiple raw v6 records ever describe one run, the correction-prefixed
    attempt id wins deterministically and otherwise the first committed
    record.
    """
    raw_v6_by_run: dict[str, Mapping[str, Any]] = {}
    for record in records:
        run_id = benchmark_source_run_id(record)
        if run_id is None or not is_benchmark_v6_record(record):
            continue
        current = raw_v6_by_run.get(run_id)
        if current is None or (
            not current["attempt_id"].startswith(BENCHMARK_CORRECTION_PREFIX)
            and record["attempt_id"].startswith(BENCHMARK_CORRECTION_PREFIX)
        ):
            raw_v6_by_run[run_id] = record
    kept: list[Mapping[str, Any]] = []
    for record in records:
        run_id = benchmark_source_run_id(record)
        if (
            run_id is not None
            and not is_benchmark_v6_record(record)
            and run_id in raw_v6_by_run
        ):
            continue
        kept.append(record)
    return kept


def build_rollup(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate attempt records by their exact route/class pair.

    Args:
        records: Attempt records already validated by :func:`read_attempts`.

    Returns:
        A JSON-serialisable object containing deterministically ordered
        ``groups``.  Missing route or class metadata is retained as JSON
        ``null`` rather than silently dropped; such a group is visibly
        unkeyed and is never converted into a guessed identifier.

        A benchmark source run described by both a pre-repair legacy crew-run
        line and its raw v6 correction is aggregated once — the correction
        supersedes the legacy line, which remains in the ledger but is
        excluded from the counts, tokens, and pass statistics here.
    """
    materialized = _without_superseded_benchmark_lines(list(records))
    grouped: dict[tuple[str | None, str | None], list[Mapping[str, Any]]] = {}
    for record in materialized:
        key = (_route_id(record), _class_key(record))
        grouped.setdefault(key, []).append(record)

    return {
        "groups": [
            _group_record(route_id, class_key, grouped[(route_id, class_key)])
            for route_id, class_key in sorted(grouped, key=_group_sort_key)
        ]
    }


# These names make the pure aggregation entry point discoverable without
# creating a second implementation or a second set of semantics.
rollup_attempts = build_rollup
summarize_attempts = build_rollup


def rollup_ledger(path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Read and roll up the configured validated attempt ledger.

    Args:
        path: Optional explicit ledger path.  The CLI passes no path, so the
            committed file/state-root environment overrides are resolved by
            :func:`resolve_attempts_path`.

    Returns:
        The same JSON-serialisable object as :func:`build_rollup`.  A missing
        ledger is treated as an empty ledger, which makes first-use evidence
        output valid without creating state.

    Raises:
        AttemptLedgerError: If a present line is malformed or schema-invalid.
        OSError: If the ledger cannot otherwise be read.
    """
    ledger_path = resolve_attempts_path(path)
    try:
        records = read_attempts(ledger_path)
    except FileNotFoundError:
        records = []
    return build_rollup(records)


def render_rollup(rollup: Mapping[str, Any]) -> str:
    """Encode a rollup as stable compact JSON followed by no newline.

    Aggregates of validated counters stay exact arbitrary-precision JSON
    integers at any magnitude: the bounded serializer
    :func:`lee_llm_router.staffing.json_int.dump_json` emits every digit
    without tripping CPython's default int-to-decimal conversion ceiling (the
    stock ``json.dumps`` raises :class:`ValueError` once an aggregate passes
    it, e.g. ``2 * 9 * 10**4299``), without mutating that process-wide
    setting, and without rounding or stringifying a counter. Half-integer
    medians that Python's exact numeric types cannot carry remain the exact
    ``"<whole>.5"`` decimal strings described in the module docstring.
    """
    return dump_json(dict(rollup), sort_keys=True)
