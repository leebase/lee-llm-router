"""Focused P1-6 tests for deterministic staffing evidence rollups."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lee_llm_router.staffing.import_evidence import (
    BENCHMARK_SCHEMA_VERSION,
    benchmark_source_run_id,
    is_benchmark_v6_record,
)
from lee_llm_router.staffing.json_int import int_from_decimal, int_to_decimal
from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    AttemptLedgerError,
    append_attempt,
    validate_attempt,
)
from lee_llm_router.staffing.rollup import (
    build_rollup,
    render_rollup,
    rollup_ledger,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / ("attempt-record-router-run-unavailable.json")
)
AGENT_ORCH_ATTEMPT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / ("attempt-record-agent-orch-raw-attempt.json")
)


def _record(
    *,
    attempt_id: str,
    route_id: str,
    class_key: str = "impl/deterministic/none/s/python",
    oracle_type: str = "deterministic",
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    cached_input_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    total_tokens: int | None = None,
    wall_clock_ms: int | None = 100,
    verdict: str = "pass",
    verified_success: bool = False,
) -> dict:
    """Make a schema-valid scratch router record without launching anything."""
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record["attempt_id"] = attempt_id
    record["router_event"]["route_id"] = route_id
    record["class_record"] = {
        "class_key": class_key,
        "role": class_key.split("/", 1)[0],
        "oracle_type": oracle_type,
        "domain_tags": [],
        "size_band": class_key.split("/")[3],
        "language": class_key.split("/")[4],
    }
    record["verdict"] = verdict
    record["oracle_cmd"] = None if verdict == "unverified" else "check"
    record["usage"] = {
        "basis": (
            "provider_reported"
            if input_tokens is not None or output_tokens is not None
            else "unavailable"
        ),
        "source": (
            "codex exec --json usage"
            if input_tokens is not None or output_tokens is not None
            else None
        ),
        "unavailable_reason": (
            "no receipt" if input_tokens is None and output_tokens is None else None
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
    }
    if record["usage"]["basis"] == "unavailable":
        record["usage"].pop("source")
    else:
        record["usage"].pop("unavailable_reason")
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


def test_fixture_ledger_rolls_up_multiple_groups_and_medians(tmp_path: Path) -> None:
    """Known counters use even-sample medians; unavailable usage is excluded."""
    first_group = [
        _record(
            attempt_id=f"a-{index}",
            route_id="route-a",
            input_tokens=value,
            output_tokens=value + 1,
            cached_input_tokens=value * 10 if index % 2 == 0 else None,
            total_tokens=value + value + 1,
            wall_clock_ms=value * 100,
            verified_success=index == 0,
        )
        for index, value in enumerate((1, 3, 5, 7))
    ]
    second_group = _record(
        attempt_id="b-1",
        route_id="route-b",
        class_key="review/judge/none/xs/markdown",
        oracle_type="judge",
        input_tokens=None,
        output_tokens=None,
        wall_clock_ms=None,
        verdict="unverified",
    )
    ledger = tmp_path / "attempts.jsonl"
    for record in [*first_group, second_group]:
        append_attempt(record, ledger)

    result = rollup_ledger(ledger)

    assert result == {
        "groups": [
            {
                "route_id": "route-a",
                "class_key": "impl/deterministic/none/s/python",
                "attempts": 4,
                "verified_pass": 1,
                "pass_by_oracle_type": {"deterministic": 4},
                "token_sums": {
                    "input_tokens": 16,
                    "output_tokens": 20,
                    "cached_input_tokens": 60,
                    "reasoning_tokens": None,
                    "total_tokens": 36,
                },
                # Exact integer medians: every even sample here has an even
                # two-middle sum, so the mean is emitted as an exact int
                # instead of statistics.median's float.
                "token_medians": {
                    "input_tokens": 4,
                    "output_tokens": 5,
                    "cached_input_tokens": 30,
                    "reasoning_tokens": None,
                    "total_tokens": 9,
                },
                "wall_clock_median_ms": 400,
                "usage_known": 4,
                "comparison_eligible": False,
            },
            {
                "route_id": "route-b",
                "class_key": "review/judge/none/xs/markdown",
                "attempts": 1,
                "verified_pass": 0,
                "pass_by_oracle_type": {},
                "token_sums": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "cached_input_tokens": None,
                    "reasoning_tokens": None,
                    "total_tokens": None,
                },
                "token_medians": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "cached_input_tokens": None,
                    "reasoning_tokens": None,
                    "total_tokens": None,
                },
                "wall_clock_median_ms": None,
                "usage_known": 0,
                "comparison_eligible": False,
            },
        ]
    }


def test_comparison_gate_changes_only_at_five_attempts() -> None:
    records = [
        _record(attempt_id=f"a-{index}", route_id="route-a") for index in range(5)
    ]
    assert build_rollup(records[:4])["groups"][0]["comparison_eligible"] is False
    assert build_rollup(records)["groups"][0]["comparison_eligible"] is True


def test_missing_ledger_is_a_valid_empty_rollup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(ATTEMPTS_STATE_ROOT_ENV_VAR, str(tmp_path / "state"))
    monkeypatch.delenv(ATTEMPTS_FILE_ENV_VAR, raising=False)

    assert rollup_ledger() == {"groups": []}


def test_cli_path_uses_state_root_override_and_committed_validation(
    tmp_path: Path, monkeypatch
) -> None:
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(_record(attempt_id="a-1", route_id="route-a"), ledger)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("{malformed\n")

    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    with pytest.raises(AttemptLedgerError, match=r":2: line is not valid JSON"):
        rollup_ledger()


# ---------------------------------------------------------------------------
# Exact medians for every validated counter (Astra final-gate blocker 2)
# ---------------------------------------------------------------------------


def _huge_group(members: list[dict]) -> dict:
    """Roll up one route group and return it, validating every member first."""
    for member in members:
        validate_attempt(member)
    return build_rollup(members)["groups"][0]


def test_odd_huge_sample_median_is_the_exact_middle_counter() -> None:
    """An odd sample of validated 10**400-scale counters stays exact."""
    members = [
        _record(
            attempt_id=f"huge-odd-{index}",
            route_id="route-huge-odd",
            input_tokens=value,
            output_tokens=value,
            total_tokens=value,
            wall_clock_ms=None,
        )
        for index, value in enumerate((10**400, 10**401, 10**402))
    ]

    group = _huge_group(members)

    assert group["token_medians"]["input_tokens"] == 10**401
    assert isinstance(group["token_medians"]["input_tokens"], int)
    assert group["token_sums"]["input_tokens"] == 10**400 + 10**401 + 10**402


def test_even_huge_sample_median_is_the_exact_integer_mean() -> None:
    """The reproducer pair: two 10**400 counters aggregate without overflow."""
    equal = [
        _record(
            attempt_id=f"huge-equal-{index}",
            route_id="route-huge-equal",
            input_tokens=10**400,
            output_tokens=10**400,
            total_tokens=10**400,
            wall_clock_ms=None,
        )
        for index in range(2)
    ]
    # Same parity, unequal middles whose sum is even: still an exact int.
    spread = [
        _record(
            attempt_id="huge-spread-0",
            route_id="route-huge-spread",
            input_tokens=10**400,
            output_tokens=10**400,
            total_tokens=10**400,
            wall_clock_ms=None,
        ),
        _record(
            attempt_id="huge-spread-1",
            route_id="route-huge-spread",
            input_tokens=10**400 + 2,
            output_tokens=10**400 + 2,
            total_tokens=10**400 + 2,
            wall_clock_ms=None,
        ),
    ]

    equal_group = _huge_group(equal)
    spread_group = _huge_group(spread)

    assert equal_group["token_medians"]["input_tokens"] == 10**400
    assert spread_group["token_medians"]["input_tokens"] == 10**400 + 1
    assert isinstance(spread_group["token_medians"]["input_tokens"], int)


def test_even_huge_odd_sum_median_is_the_exact_decimal_string() -> None:
    """A half-integer above float range stays exact; nothing is invented."""
    members = [
        _record(
            attempt_id=f"huge-half-{index}",
            route_id="route-huge-half",
            input_tokens=10**400 + index,
            output_tokens=10**400 + index,
            total_tokens=10**400 + index,
            wall_clock_ms=None,
        )
        for index in range(2)
    ]

    group = _huge_group(members)

    expected = f"{10**400}.5"
    assert group["token_medians"]["input_tokens"] == expected
    assert isinstance(group["token_medians"]["input_tokens"], str)
    # The exact decimal string must survive the rendered JSON round trip.
    rendered = json.loads(render_rollup({"groups": [group]}))
    assert rendered["groups"][0]["token_medians"]["input_tokens"] == expected


def test_boundary_rollup_preserves_exact_sum_integer_median_and_round_trip() -> None:
    """Two valid 4300-digit counters aggregate past Python's default limit."""
    counter = 9 * 10**4299
    members = [
        _record(
            attempt_id=f"boundary-equal-{index}",
            route_id="route-boundary",
            input_tokens=counter,
            output_tokens=0,
            total_tokens=None,
            wall_clock_ms=None,
        )
        for index in range(2)
    ]

    group = _huge_group(members)
    assert group["token_sums"]["input_tokens"] == 2 * counter
    assert group["token_medians"]["input_tokens"] == counter
    assert isinstance(group["token_medians"]["input_tokens"], int)

    rollup = build_rollup(members)
    rendered = render_rollup(rollup)
    assert int_to_decimal(2 * counter) in rendered
    assert json.loads(rendered, parse_int=int_from_decimal) == rollup


def test_boundary_half_integer_median_is_an_exact_decimal_string() -> None:
    """A huge odd middle sum stays exact without a rounded float."""
    counter = 9 * 10**4299
    members = [
        _record(
            attempt_id=f"boundary-half-{index}",
            route_id="route-boundary-half",
            input_tokens=counter + index,
            output_tokens=0,
            total_tokens=None,
            wall_clock_ms=None,
        )
        for index in range(2)
    ]

    group = _huge_group(members)
    assert group["token_sums"]["input_tokens"] == 2 * counter + 1
    assert group["token_medians"]["input_tokens"] == (f"{int_to_decimal(counter)}.5")
    assert isinstance(group["token_medians"]["input_tokens"], str)
    assert (
        json.loads(render_rollup({"groups": [group]}), parse_int=int_from_decimal)[
            "groups"
        ][0]["token_medians"]["input_tokens"]
        == f"{int_to_decimal(counter)}.5"
    )


def test_normal_medians_keep_exact_values_and_representations() -> None:
    """Normal samples stay statistics.median-faithful: ints and exact floats."""
    odd = [
        _record(
            attempt_id=f"normal-odd-{index}",
            route_id="route-normal-odd",
            input_tokens=value,
            output_tokens=value,
            wall_clock_ms=value * 100,
        )
        for index, value in enumerate((1, 2, 9))
    ]
    even_odd_sum = [
        _record(
            attempt_id="normal-half-0",
            route_id="route-normal-half",
            input_tokens=4,
            output_tokens=4,
            wall_clock_ms=300,
        ),
        _record(
            attempt_id="normal-half-1",
            route_id="route-normal-half",
            input_tokens=5,
            output_tokens=5,
            wall_clock_ms=500,
        ),
    ]

    odd_group = _huge_group(odd)
    half_group = _huge_group(even_odd_sum)

    assert odd_group["token_medians"]["input_tokens"] == 2
    assert isinstance(odd_group["token_medians"]["input_tokens"], int)
    assert odd_group["wall_clock_median_ms"] == 200
    assert half_group["token_medians"]["input_tokens"] == 4.5
    assert isinstance(half_group["token_medians"]["input_tokens"], float)
    # An integral even-sample mean is the exact int, not a rounded float.
    assert half_group["wall_clock_median_ms"] == 400
    assert isinstance(half_group["wall_clock_median_ms"], int)


# ---------------------------------------------------------------------------
# Engine-validation pass breakdown (Astra final-gate blocker 3)
# ---------------------------------------------------------------------------


def _agent_orch_record(attempt_id: str, *, passed: bool) -> dict:
    """A schema-valid agent-orch attempt copied from the reviewed fixture."""
    record = json.loads(AGENT_ORCH_ATTEMPT_FIXTURE.read_text(encoding="utf-8"))
    record["attempt_id"] = attempt_id
    if not passed:
        record["verified_success"] = False
        payload = record["agent_orch_attempt"]
        payload["worker_exit_code"] = 1
        payload["validation_passed"] = False
        payload["policy_decision"] = "FAIL"
        payload["failure_classification"] = "validation_failed"
    validate_attempt(record)
    return record


def test_engine_validation_passes_count_under_their_tier() -> None:
    """Real agent-orch shape: verified passes break down as engine_validation."""
    members = [
        _agent_orch_record(f"agent-pass-{index}", passed=True) for index in range(2)
    ] + [_agent_orch_record("agent-fail-1", passed=False)]

    group = build_rollup(members)["groups"][0]

    assert group["route_id"] is None
    assert group["class_key"] is None
    assert group["attempts"] == 3
    assert group["verified_pass"] == 2
    assert group["pass_by_oracle_type"] == {"engine_validation": 2}
    # The breakdown covers exactly the verified passes: no double count.
    assert sum(group["pass_by_oracle_type"].values()) == group["verified_pass"]


def test_engine_validation_failures_are_never_passes() -> None:
    """A nonzero worker exit or failed validation is not a pass anywhere."""
    failed_exit = _agent_orch_record("agent-fail-exit", passed=False)
    failed_exit["agent_orch_attempt"]["worker_exit_code"] = 1
    failed_validation = _agent_orch_record("agent-fail-validation", passed=False)
    failed_validation["agent_orch_attempt"]["worker_exit_code"] = 0
    failed_validation["agent_orch_attempt"]["validation_passed"] = False

    group = build_rollup([failed_exit, failed_validation])["groups"][0]

    assert group["attempts"] == 2
    assert group["verified_pass"] == 0
    assert group["pass_by_oracle_type"] == {}


def test_mixed_oracle_types_and_engine_validation_break_down_without_overlap() -> None:
    """String-verdict passes use their oracle type; tier passes their tier."""
    deterministic = [
        _record(
            attempt_id=f"mixed-det-{index}",
            route_id="route-a",
            verdict="pass",
        )
        for index in range(2)
    ]
    judge = _record(
        attempt_id="mixed-judge-1",
        route_id="route-b",
        class_key="review/judge/none/xs/markdown",
        oracle_type="judge",
        verdict="pass",
    )
    unverified = _record(
        attempt_id="mixed-unverified-1",
        route_id="route-a",
        verdict="unverified",
    )
    engine = _agent_orch_record("mixed-engine-pass-1", passed=True)
    for record in [*deterministic, judge, unverified]:
        validate_attempt(record)

    groups = {
        (group["route_id"], group["class_key"]): group
        for group in build_rollup([*deterministic, judge, unverified, engine])["groups"]
    }

    oracle_group = groups[("route-a", "impl/deterministic/none/s/python")]
    assert oracle_group["attempts"] == 3
    assert oracle_group["pass_by_oracle_type"] == {"deterministic": 2}
    # The unverified record counts no pass; the judge pass keeps its own
    # oracle type in its own group.
    assert groups[("route-b", "review/judge/none/xs/markdown")][
        "pass_by_oracle_type"
    ] == {"judge": 1}
    # The engine-validation record lives in its own unkeyed group under its
    # tier, never inside an oracle-type key: no overlap, no double count.
    engine_group = groups[(None, None)]
    assert engine_group["attempts"] == 1
    assert engine_group["pass_by_oracle_type"] == {"engine_validation": 1}


def test_engine_validation_rows_coexist_with_superseded_benchmark_lines() -> None:
    """Supersession still counts a corrected run once beside agent-orch rows."""
    legacy = _legacy_benchmark_record("run-9")
    correction = _benchmark_v6_record("run-9")
    engine_pass = _agent_orch_record("agent-coexist-pass", passed=True)
    engine_fail = _agent_orch_record("agent-coexist-fail", passed=False)

    groups = {
        group["class_key"]: group
        for group in build_rollup([legacy, correction, engine_pass, engine_fail])[
            "groups"
        ]
    }
    benchmark_group = groups["impl/deterministic/none/m/python"]
    assert benchmark_group["attempts"] == 1
    assert benchmark_group["pass_by_oracle_type"] == {"deterministic": 1}
    # Pre-existing semantics are untouched: canonical verdict-pass records
    # fill the breakdown while verified_pass keeps its own stricter count.
    assert benchmark_group["verified_pass"] == 0
    engine_group = groups[None]
    assert engine_group["attempts"] == 2
    assert engine_group["verified_pass"] == 1
    assert engine_group["pass_by_oracle_type"] == {"engine_validation": 1}
    assert sum(engine_group["pass_by_oracle_type"].values()) == (
        engine_group["verified_pass"]
    )


# ---------------------------------------------------------------------------
# Benchmark correction supersession (Astra re-review blocker 4)
# ---------------------------------------------------------------------------

BENCH_CLASS = {
    "class_key": "impl/deterministic/none/m/python",
    "role": "impl",
    "oracle_type": "deterministic",
    "domain_tags": [],
    "size_band": "m",
    "language": "python",
}
V6_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / "attempt-record-benchmark-v6-run.json"
)
LEGACY_EXAMPLE_SCHEMA = (
    Path(__file__).parent.parent
    / "config"
    / "staffing"
    / "schema"
    / "attempt-record.schema.json"
)


def _benchmark_v6_record(run_id: str) -> dict:
    """A schema-valid raw benchmarkV6Run record for one source run."""
    record = json.loads(V6_FIXTURE.read_text(encoding="utf-8"))
    record["attempt_id"] = f"benchmark:v6:{run_id}"
    payload = record["benchmark_run"]
    payload["run_id"] = run_id
    payload["task_key"] = f"task-{run_id}"
    return record


def _legacy_benchmark_record(run_id: str) -> dict:
    """A schema-valid pre-repair legacy crew-run record for the same run.

    Its token counters deliberately differ from the correction's so the
    tests can prove the superseded line's numbers are excluded.
    """
    schema = json.loads(LEGACY_EXAMPLE_SCHEMA.read_text(encoding="utf-8"))
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
    record["class_record"] = dict(BENCH_CLASS)
    record["usage"] = {
        "basis": "provider_reported",
        "source": "benchmark v6 CSV usage_*_tokens",
        "input_tokens": 999,
        "output_tokens": 888,
        "cached_input_tokens": 77,
        "reasoning_tokens": None,
        "total_tokens": 1964,
    }
    return record


def test_correction_supersedes_its_legacy_source_attempt_in_rollup() -> None:
    """Legacy line + correction = one attempt with the correction's facts."""
    legacy = _legacy_benchmark_record("run-1")
    correction = _benchmark_v6_record("run-1")
    unrelated = _record(attempt_id="router-1", route_id="route-a")

    groups = {
        group["class_key"]: group
        for group in build_rollup([legacy, correction, unrelated])["groups"]
    }

    benchmark_group = groups["impl/deterministic/none/m/python"]
    assert benchmark_group["attempts"] == 1
    assert benchmark_group["token_sums"]["input_tokens"] == 101
    assert benchmark_group["token_sums"]["output_tokens"] == 202
    assert benchmark_group["pass_by_oracle_type"] == {"deterministic": 1}
    # The generic unrelated attempt is untouched.
    assert groups["impl/deterministic/none/s/python"]["attempts"] == 1
    assert (
        groups["impl/deterministic/none/s/python"]["token_sums"]["input_tokens"] == 10
    )


def test_legacy_benchmark_line_without_correction_still_counts() -> None:
    """Supersession requires an actual raw v6 correction for the run."""
    legacy = _legacy_benchmark_record("run-2")

    group = build_rollup([legacy])["groups"][0]

    assert group["attempts"] == 1
    assert group["token_sums"]["input_tokens"] == 999
    assert group["pass_by_oracle_type"] == {"deterministic": 1}


def test_benchmark_supersession_is_order_independent() -> None:
    """Ledger order must not change which record the rollup selects."""
    legacy = _legacy_benchmark_record("run-3")
    correction = _benchmark_v6_record("run-3")
    unrelated = _record(attempt_id="router-2", route_id="route-b")

    forward = build_rollup([legacy, correction, unrelated])
    backward = build_rollup([correction, unrelated, legacy])

    assert render_rollup(forward) == render_rollup(backward)
    assert render_rollup(forward) == render_rollup(
        build_rollup([correction, unrelated])
    )


def test_comparison_gate_counts_distinct_benchmark_source_runs() -> None:
    """Legacy+correction pairs count once: eligibility needs 5 distinct runs."""
    run_ids = [f"run-{index}" for index in range(1, 6)]
    paired = [
        record
        for run_id in run_ids
        for record in (_legacy_benchmark_record(run_id), _benchmark_v6_record(run_id))
    ]

    five_runs = build_rollup(paired)["groups"][0]
    assert five_runs["attempts"] == 5
    assert five_runs["comparison_eligible"] is True
    assert five_runs["token_sums"]["input_tokens"] == 5 * 101

    four_runs = build_rollup(paired[:-2])["groups"][0]
    assert four_runs["attempts"] == 4
    assert four_runs["comparison_eligible"] is False


def test_benchmark_source_run_id_helpers_cover_both_payload_shapes() -> None:
    """Run-id recovery works for raw v6 and legacy shapes; others are None."""
    correction = _benchmark_v6_record("run-4")
    legacy = _legacy_benchmark_record("run-4")
    unrelated = _record(attempt_id="router-3", route_id="route-a")

    assert benchmark_source_run_id(correction) == "run-4"
    assert benchmark_source_run_id(legacy) == "run-4"
    assert benchmark_source_run_id(unrelated) is None
    assert is_benchmark_v6_record(correction) is True
    assert is_benchmark_v6_record(legacy) is False
    assert correction["benchmark_run"]["schema_version"] == BENCHMARK_SCHEMA_VERSION
