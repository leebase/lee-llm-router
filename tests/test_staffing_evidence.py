"""Focused P2-1 tests for the pure D211 route/class evidence join.

The join consumes the already-committed P2-0 shapes: validated attempt
records (fixture-derived scratch shapes, no provider calls) and the
``evidence rollup`` output built from them.  Every scratch ledger write goes
through the committed state/file environment override into ``tmp_path``;
no real provider prompt or state root is ever touched.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lee_llm_router.staffing.evidence import (
    DEMAND_UNKNOWN,
    EVIDENCE_LEVELS,
    SUMMARY_KEYS,
    join_evidence,
)
from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    append_attempt,
    read_attempts,
)
from lee_llm_router.staffing.rollup import build_rollup, rollup_ledger

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / "attempt-record-router-run-unavailable.json"
)

CLASS_KEY = "impl/deterministic/none/s/python"
BENCHMARK_CLASS_KEY = "impl/deterministic/none/m/python"
LEGACY_SCHEMA = (
    Path(__file__).parent.parent
    / "config"
    / "staffing"
    / "schema"
    / "attempt-record.schema.json"
)
V6_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / "attempt-record-benchmark-v6-run.json"
)


def _record(
    *,
    attempt_id: str,
    class_key: str = CLASS_KEY,
    route_id: str = "route-a",
    record_kind: str = "router_run",
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    total_tokens: int | None = None,
    wall_clock_ms: int | None = 100,
    verdict: str = "pass",
    verified_success: bool = False,
) -> dict:
    """Make a scratch router-shaped record without launching anything."""
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parts = class_key.split("/")
    record["attempt_id"] = attempt_id
    record["record_kind"] = record_kind
    record["router_event"]["route_id"] = route_id
    record["class_record"] = {
        "class_key": class_key,
        "role": parts[0],
        "oracle_type": parts[1] if len(parts) > 1 else None,
        "domain_tags": [],
        "size_band": parts[3] if len(parts) > 3 else None,
        "language": parts[4] if len(parts) > 4 else None,
    }
    record["verdict"] = verdict
    record["oracle_cmd"] = None if verdict == "unverified" else "check"
    known = input_tokens is not None or output_tokens is not None
    record["usage"] = {
        "basis": "provider_reported" if known else "unavailable",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": total_tokens,
    }
    if known:
        record["usage"]["source"] = "codex exec --json usage"
    else:
        record["usage"]["unavailable_reason"] = "no receipt"
    record["wall_clock_ms"] = wall_clock_ms
    record["verified_success"] = verified_success
    if verified_success:
        record["supervisor_route"] = copy.deepcopy(record["route"])
        record["cost"] = {
            "basis": ["list", "marginal"],
            "usd_list": 1.0,
            "usd_marginal": 1.0,
        }
        record["failure_class"] = None
    return record


def _legacy_benchmark_record(run_id: str) -> dict:
    """Make a genuine pre-repair ``benchmark.crew-run/1`` ledger row."""
    schema = json.loads(LEGACY_SCHEMA.read_text(encoding="utf-8"))
    record = copy.deepcopy(
        next(
            example
            for example in schema["examples"]
            if example["attempt_id"] == "bench-mixed-economy-0001"
        )
    )
    record["attempt_id"] = f"benchmark:{run_id}"
    record["benchmark_run"]["attempt_id"] = record["attempt_id"]
    record["benchmark_run"]["stages"][0]["run_id"] = run_id
    record["class_record"] = {
        "class_key": BENCHMARK_CLASS_KEY,
        "role": "impl",
        "oracle_type": "deterministic",
        "domain_tags": [],
        "size_band": "m",
        "language": "python",
    }
    return record


def _benchmark_v6_record(run_id: str) -> dict:
    """Make a genuine ``benchmark.staffing-evidence/2`` correction row."""
    record = json.loads(V6_FIXTURE.read_text(encoding="utf-8"))
    record["attempt_id"] = f"benchmark:v6:{run_id}"
    record["benchmark_run"]["run_id"] = run_id
    record["benchmark_run"]["task_key"] = f"task-{run_id}"
    return record


# ---------------------------------------------------------------------------
# Ruling 1: the fixed exact-to-coarse join order
# ---------------------------------------------------------------------------


def test_exact_level_joins_attempts_passes_and_split() -> None:
    records = [
        *(
            _record(
                attempt_id=f"router-{index}",
                verified_success=index % 2 == 0,
            )
            for index in range(5)
        ),
        *(
            _record(
                attempt_id=f"bench-{index}",
                record_kind="benchmark_run",
                verified_success=False,
            )
            for index in range(2)
        ),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert joined.evidence_level == "exact"
    assert joined.level == "exact"
    assert joined.n == 7
    assert joined.k == 3
    assert joined.prior_n == 2
    assert joined.posterior_n == 5
    assert joined.estimate == pytest.approx((3 + 1) / (7 + 2))
    assert joined.low_evidence is False


def test_join_filters_route_before_dropping_language() -> None:
    records = [
        _record(
            attempt_id="go-1",
            class_key="impl/deterministic/none/s/go",
            verified_success=True,
        ),
        _record(
            attempt_id="go-2",
            class_key="impl/deterministic/none/s/rust",
        ),
        _record(
            attempt_id="other-route-exact",
            route_id="route-b",
            verified_success=True,
        ),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert joined.evidence_level == "drop_language"
    assert joined.n == 2
    assert joined.k == 1
    assert joined.estimate == pytest.approx((1 + 1) / (2 + 2))
    assert joined.low_evidence is True


def test_join_falls_back_dropping_size_band() -> None:
    records = [
        _record(
            attempt_id="xs-1",
            class_key="impl/deterministic/none/xs/go",
        ),
        _record(
            attempt_id="xl-1",
            class_key="impl/deterministic/none/xl/rust",
            verified_success=True,
        ),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert joined.evidence_level == "drop_size_band"
    assert joined.n == 2
    assert joined.k == 1


def test_join_falls_back_to_role_oracle_type() -> None:
    records = [
        _record(
            attempt_id="other-1",
            class_key="impl/deterministic/other/xl/rust",
        ),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert joined.evidence_level == "role_oracle_type"
    assert joined.n == 1
    assert joined.k == 0


def test_join_level_none_when_nothing_matches() -> None:
    records = [
        _record(
            attempt_id="elsewhere-1",
            class_key="review/judge/none/xs/markdown",
        ),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records, build_rollup(records))

    assert joined.evidence_level == "none"
    assert joined.n == 0
    assert joined.k == 0
    assert joined.prior_n == 0
    assert joined.posterior_n == 0
    assert joined.estimate == 0.5
    assert joined.low_evidence is True
    assert joined.demand == DEMAND_UNKNOWN


def test_join_without_records_is_the_bare_laplace_prior() -> None:
    joined = join_evidence("route-a", CLASS_KEY, [])

    assert joined.evidence_level == "none"
    assert joined.as_dict() == {
        "level": "none",
        "n": 0,
        "k": 0,
        "estimate": 0.5,
        "low_evidence": True,
        "prior_n": 0,
        "posterior_n": 0,
    }


def test_fixed_level_order_is_untouched() -> None:
    assert EVIDENCE_LEVELS == (
        "exact",
        "drop_language",
        "drop_size_band",
        "role_oracle_type",
        "none",
    )


# ---------------------------------------------------------------------------
# Ruling 1: prior/posterior split by record kind
# ---------------------------------------------------------------------------


def test_prior_and_posterior_split_by_record_kind() -> None:
    records = [
        _record(attempt_id="router-1", record_kind="router_run"),
        _record(attempt_id="bench-1", record_kind="benchmark_run"),
        _record(
            attempt_id="import-1",
            record_kind="agent_orch_attempt",
            verified_success=True,
        ),
        _record(attempt_id="kindless-1", record_kind=None),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    # The two contract kinds partition exactly; a record of any other kind
    # counts in n and k but in neither bucket, never in both or invented.
    assert joined.n == 4
    assert joined.k == 1
    assert joined.prior_n == 1
    assert joined.posterior_n == 1
    assert joined.estimate == pytest.approx((1 + 1) / (4 + 2))


def test_join_reuses_benchmark_supersession_for_counts() -> None:
    """A v6 correction replaces, rather than adds to, its legacy source row."""
    legacy = _legacy_benchmark_record("fixture-run-accepted")
    correction = _benchmark_v6_record("fixture-run-accepted")
    records = [legacy, correction]
    rollup = build_rollup(records)

    corrected_group = next(
        group
        for group in rollup["groups"]
        if group["route_id"] is None and group["class_key"] == BENCHMARK_CLASS_KEY
    )
    assert corrected_group["attempts"] == 1

    # The imported v6 correction explicitly has no route.  Its exact missing
    # route scope consumes the same effective row as the accepted rollup.
    joined = join_evidence(None, BENCHMARK_CLASS_KEY, records, rollup)
    assert (joined.n, joined.k, joined.prior_n, joined.posterior_n) == (1, 0, 1, 0)
    assert joined.demand["tokens"]["input_tokens"] == 101

    # Both genuine benchmark shapes have no asserted route, so without the
    # accepted supersession view raw-record counting would incorrectly return
    # n=2 for this exact route/class pair.


def test_uncorrected_legacy_benchmark_row_still_counts() -> None:
    """A legacy benchmark row without a correction remains evidence."""
    legacy = _legacy_benchmark_record("fixture-run-uncorrected")

    joined = join_evidence(
        None,
        BENCHMARK_CLASS_KEY,
        [legacy],
        build_rollup([legacy]),
    )

    assert (joined.n, joined.k, joined.prior_n, joined.posterior_n) == (1, 0, 1, 0)


# ---------------------------------------------------------------------------
# Ruling 1: low evidence and the Laplace estimate
# ---------------------------------------------------------------------------


def test_low_evidence_is_exactly_n_below_five() -> None:
    four = [_record(attempt_id=f"low-{index}") for index in range(4)]
    five = [*four, _record(attempt_id="low-4")]

    assert join_evidence("route-a", CLASS_KEY, four).low_evidence is True
    assert join_evidence("route-a", CLASS_KEY, five).low_evidence is False


def test_boundary_n_of_five_is_not_low_evidence() -> None:
    records = [
        _record(attempt_id=f"boundary-{index}", verified_success=index == 0)
        for index in range(5)
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert joined.n == 5
    assert joined.k == 1
    assert joined.estimate == pytest.approx(2 / 7)
    assert joined.low_evidence is False


def test_laplace_estimate_uses_the_joined_counts() -> None:
    records = [
        _record(attempt_id="pass-1", verified_success=True),
        _record(attempt_id="fail-1"),
        _record(attempt_id="fail-2"),
    ]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert (joined.n, joined.k) == (3, 1)
    assert joined.estimate == pytest.approx((1 + 1) / (3 + 2))


# ---------------------------------------------------------------------------
# Ruling 1: the exact summary contract
# ---------------------------------------------------------------------------


def test_summary_returns_exactly_the_contract_keys_in_order() -> None:
    records = [_record(attempt_id=f"shape-{index}") for index in range(3)]

    summary = join_evidence("route-a", CLASS_KEY, records).as_dict()

    assert list(summary) == list(SUMMARY_KEYS)
    assert list(SUMMARY_KEYS) == [
        "level",
        "n",
        "k",
        "estimate",
        "low_evidence",
        "prior_n",
        "posterior_n",
    ]
    assert isinstance(summary["estimate"], float)
    assert isinstance(summary["low_evidence"], bool)


# ---------------------------------------------------------------------------
# Ruling 2: demand medians at the same join level
# ---------------------------------------------------------------------------


def test_demand_consumes_rollup_medians_verbatim_at_exact_level() -> None:
    records = [
        _record(
            attempt_id=f"demand-{index}",
            route_id="route-a",
            input_tokens=10 + index,
            output_tokens=5 + index,
            total_tokens=15 + 2 * index,
            wall_clock_ms=100 + 10 * index,
        )
        for index in range(3)
    ]
    rollup = build_rollup(records)

    joined = join_evidence("route-a", CLASS_KEY, records, rollup)

    group = rollup["groups"][0]
    # Consumed verbatim per field; a null median field stays explicit.
    assert joined.demand == {
        "tokens": {
            **group["token_medians"],
            "cached_input_tokens": DEMAND_UNKNOWN,
            "reasoning_tokens": DEMAND_UNKNOWN,
        },
        "wall_clock_ms": group["wall_clock_median_ms"],
    }
    assert joined.demand["tokens"]["input_tokens"] == 11
    assert joined.demand["wall_clock_ms"] == 110


def test_demand_preserves_the_exact_half_integer_string_median() -> None:
    records = [
        _record(
            attempt_id=f"huge-{index}",
            input_tokens=10**401 + index,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=None,
        )
        for index in range(2)
    ]
    rollup = build_rollup(records)
    median = rollup["groups"][0]["token_medians"]["input_tokens"]
    assert isinstance(median, str) and median.endswith(".5")

    joined = join_evidence("route-a", CLASS_KEY, records, rollup)

    # The lossless decimal string is consumed verbatim, never rounded.
    assert joined.demand["tokens"]["input_tokens"] == median


def test_route_scope_is_exact_for_counts_and_demand() -> None:
    records = [
        _record(
            attempt_id="a-router",
            route_id="route-a",
            input_tokens=10,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=100,
            verified_success=True,
        ),
        _record(
            attempt_id="a-benchmark",
            route_id="route-a",
            record_kind="benchmark_run",
            input_tokens=12,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=120,
        ),
        _record(
            attempt_id="b-router",
            route_id="route-b",
            input_tokens=999,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=999,
            verified_success=True,
        ),
        _record(
            attempt_id="b-benchmark",
            route_id="route-b",
            record_kind="benchmark_run",
            input_tokens=1001,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=1001,
            verified_success=True,
        ),
    ]
    rollup = build_rollup(records)

    joined = join_evidence("route-a", CLASS_KEY, records, rollup)

    assert (joined.n, joined.k, joined.prior_n, joined.posterior_n) == (2, 1, 1, 1)
    assert joined.demand["tokens"]["input_tokens"] == 11
    assert joined.demand["wall_clock_ms"] == 110


def test_demand_unknown_when_no_usable_median() -> None:
    records = [
        _record(
            attempt_id=f"dark-{index}",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            wall_clock_ms=None,
            verdict="unverified",
        )
        for index in range(2)
    ]
    rollup = build_rollup(records)
    group = rollup["groups"][0]
    assert all(value is None for value in group["token_medians"].values())
    assert group["wall_clock_median_ms"] is None

    joined = join_evidence("route-a", CLASS_KEY, records, rollup)

    assert joined.demand == DEMAND_UNKNOWN


def test_demand_unknown_without_a_rollup() -> None:
    records = [_record(attempt_id="solo-1")]

    joined = join_evidence("route-a", CLASS_KEY, records)

    assert joined.demand == DEMAND_UNKNOWN


def test_demand_null_median_field_is_explicitly_unknown() -> None:
    records = [
        _record(
            attempt_id="partial-1",
            input_tokens=10,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=None,
        )
    ]
    rollup = build_rollup(records)

    joined = join_evidence("route-a", CLASS_KEY, records, rollup)

    assert joined.demand["tokens"]["input_tokens"] == 10
    assert joined.demand["tokens"]["total_tokens"] == DEMAND_UNKNOWN
    assert joined.demand["wall_clock_ms"] == DEMAND_UNKNOWN


def test_demand_uses_groups_at_the_used_join_level() -> None:
    records = [
        # Joins at drop_language: different language, same first four
        # components; the rollup group's medians must be consumed there.
        _record(
            attempt_id="go-1",
            class_key="impl/deterministic/none/s/go",
            input_tokens=7,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=70,
        ),
        # Matches only at drop_size_band: its medians must not leak into
        # the drop_language demand.
        _record(
            attempt_id="xs-1",
            class_key="impl/deterministic/none/xs/go",
            input_tokens=999,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=900,
        ),
        # An exact class match on another route must not enter this route's
        # coarse-level demand pool.
        _record(
            attempt_id="other-route-exact",
            route_id="route-b",
            input_tokens=9999,
            output_tokens=1,
            total_tokens=None,
            wall_clock_ms=9999,
        ),
    ]
    rollup = build_rollup(records)

    joined = join_evidence("route-a", CLASS_KEY, records, rollup)

    assert joined.evidence_level == "drop_language"
    assert joined.demand["tokens"]["input_tokens"] == 7
    assert joined.demand["wall_clock_ms"] == 70


def test_demand_ignores_nonmatching_and_unkeyed_groups() -> None:
    matching = _record(attempt_id="solo-1", input_tokens=3, output_tokens=1)
    stranger = _record(
        attempt_id="stranger-1",
        class_key="review/judge/none/xs/markdown",
        input_tokens=99,
        output_tokens=1,
        total_tokens=None,
        wall_clock_ms=999,
    )
    stranger["class_record"] = None
    stranger["router_event"]["route_id"] = "route-stranger"
    rollup = build_rollup([matching, stranger])
    # The stranger rolls up into a visibly unkeyed group: it must not join.
    assert any(group["class_key"] is None for group in rollup["groups"])

    joined = join_evidence("route-a", CLASS_KEY, [matching], rollup)

    assert joined.demand["tokens"]["input_tokens"] == 3
    assert joined.demand["wall_clock_ms"] == 100


def test_demand_ignores_malformed_group_medians() -> None:
    records = [_record(attempt_id="solo-1")]
    broken = [
        {"class_key": CLASS_KEY},  # no token_medians at all
        {
            "class_key": CLASS_KEY,
            "token_medians": "not-a-mapping",
            "wall_clock_median_ms": True,
        },
        {
            "class_key": CLASS_KEY,
            "token_medians": {"input_tokens": "abc", "output_tokens": []},
            "wall_clock_median_ms": None,
        },
    ]

    joined = join_evidence("route-a", CLASS_KEY, records, {"groups": broken})

    assert joined.demand == DEMAND_UNKNOWN


# ---------------------------------------------------------------------------
# Malformed and nonmatching record shapes
# ---------------------------------------------------------------------------


def test_malformed_record_keys_never_join() -> None:
    unkeyed = _record(attempt_id="unkeyed-1")
    unkeyed["class_record"] = None
    empty = _record(attempt_id="empty-1")
    empty["class_record"] = {"class_key": ""}
    typed = _record(attempt_id="typed-1")
    typed["class_record"] = {"class_key": 7}
    records = [unkeyed, empty, typed]

    joined = join_evidence("route-a", CLASS_KEY, records, build_rollup([]))

    assert joined.evidence_level == "none"
    assert joined.n == 0
    assert joined.demand == DEMAND_UNKNOWN


def test_short_target_keys_offer_only_the_levels_they_can_drop() -> None:
    short_key = "impl/deterministic/none"
    records = [_record(attempt_id="solo-1", class_key=short_key)]

    joined = join_evidence("route-a", short_key, records)

    assert joined.evidence_level == "exact"
    assert joined.n == 1

    orphan = join_evidence("route-a", short_key, [], [])
    assert orphan.evidence_level == "none"


def test_join_rejects_unavailable_route_and_class_keys() -> None:
    with pytest.raises(ValueError, match="route_id"):
        join_evidence("", CLASS_KEY, [])
    with pytest.raises(ValueError, match="route_id"):
        join_evidence(7, CLASS_KEY, [])
    with pytest.raises(ValueError, match="non-empty string"):
        join_evidence("route-a", None, [])
    with pytest.raises(ValueError, match="non-empty string"):
        join_evidence("route-a", "", [])
    with pytest.raises(ValueError, match="non-empty string"):
        join_evidence("route-a", 7, [])


def test_non_mapping_records_are_ignored() -> None:
    records = [_record(attempt_id="solo-1"), "not-a-record", None]  # type: ignore[list-item]

    joined = join_evidence("route-a", CLASS_KEY, records)  # type: ignore[arg-type]

    assert joined.n == 1


# ---------------------------------------------------------------------------
# Accepted ledger shapes end to end (scratch state via env override only)
# ---------------------------------------------------------------------------


def test_join_consumes_the_committed_ledger_rollup_shape(
    tmp_path: Path, monkeypatch
) -> None:
    ledger = tmp_path / "attempts.jsonl"
    for index in range(5):
        append_attempt(
            _record(
                attempt_id=f"ledger-{index}",
                verified_success=index < 2,
            ),
            ledger,
        )
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))

    rollup = rollup_ledger()

    # D211: prior/posterior and n/k come from the validated typed ledger
    # rows; the rollup is the demand aggregate and supplies no counts.
    records = read_attempts(ledger)
    joined = join_evidence("route-a", CLASS_KEY, records, rollup)
    assert joined.evidence_level == "exact"
    assert (joined.n, joined.k) == (5, 2)
    assert (joined.prior_n, joined.posterior_n) == (0, 5)
    assert joined.estimate == pytest.approx(3 / 7)
    assert joined.low_evidence is False
