"""Hand-computed tests for pure D211 ladder arithmetic."""

from __future__ import annotations

import pytest

from lee_llm_router.staffing.ladder import (
    EXPECTED_COST_AVAILABLE,
    EXPECTED_COST_UNAVAILABLE,
    LadderInput,
    calculate_ladder,
    supervisor_overhead_from_rows,
)
from lee_llm_router.staffing.proof import ProofStatus

CLASS = "impl/deterministic/none/s/python"
RUNG_KEYS = {"route", "a", "v", "s", "q", "q_prime", "E"}


def demand(input_tokens=100, output_tokens=50, **extra):
    return {
        "tokens": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            **extra,
        }
    }


def pricing(input_rate=0.005, output_rate=0.01, **extra):
    return {
        "marginal_input_usd_per_token": input_rate,
        "marginal_output_usd_per_token": output_rate,
        **extra,
    }


def evidence(n=2, k=1, level="exact"):
    return {"level": level, "n": n, "k": k, "class_key": CLASS}


def supervisor_rows(values=(0.1, 0.1, 0.1, 0.1, 0.1)):
    attestations = [
        {
            "supervisor_route": {"route_id": "supervisor"},
            "router_event": {"route_id": f"worker-{index}"},
        }
        for index, _value in enumerate(values)
    ]
    supervisor_attempts = [
        {
            "router_event": {"route_id": "supervisor"},
            "cost": {"usd_marginal": value},
        }
        for value in values
    ]
    return attestations + supervisor_attempts


def rung(route, *, a=1.0, n=2, k=1, proof=ProofStatus.UNPROVEN):
    # 100 input + 50 output tokens. Split a evenly between the two terms.
    return LadderInput(
        route=route,
        demand=demand(),
        pricing=pricing(a / 200, a / 100),
        evidence=evidence(n, k),
        proof_status=proof,
    )


def calculate(rungs, **kwargs):
    return calculate_ladder(
        rungs,
        human_escalation_cost_usd=kwargs.pop("terminal", 5.0),
        oracle_type=kwargs.pop("oracle_type", "deterministic"),
        attempt_records=kwargs.pop("attempt_records", supervisor_rows()),
        supervisor_route="supervisor",
        **kwargs,
    )


def test_one_rung_terminal_and_exact_shape():
    result = calculate([rung("r1")])

    assert result["expected_cost_status"] == EXPECTED_COST_AVAILABLE
    assert result["argmin_start"] == "r1"
    assert result["escalation"] == ["r1"]
    assert set(result["rungs"][0]) == RUNG_KEYS
    # 1.1 + .5 * (1.1 + .5 * 5) = 2.9
    row = result["rungs"][0]
    assert row["route"] == "r1"
    assert {
        key: value for key, value in row.items() if key != "route"
    } == pytest.approx(
        {"a": 1.0, "v": 0.0, "s": 0.1, "q": 0.5, "q_prime": 0.5, "E": 2.9}
    )


def test_two_rungs_are_computed_backwards_by_hand():
    result = calculate([rung("r1", a=0.1, n=2, k=0), rung("r2", a=2, n=2, k=2)])
    by_route = {row["route"]: row for row in result["rungs"]}

    # E2 = 2.1 + .25 * (2.1 + .25 * 5) = 2.9375
    assert by_route["r2"]["E"] == pytest.approx(2.9375)
    # E1 = .2 + .75 * (.2 + .75 * E2)
    assert by_route["r1"]["E"] == pytest.approx(2.00234375)
    assert result["argmin_start"] == "r1"
    assert result["escalation"] == ["r1", "r2"]


def test_three_rungs_and_argmin_can_skip_first():
    result = calculate(
        [
            rung("expensive", a=10, n=5, k=0),
            rung("middle", a=0.2, n=5, k=4),
            rung("last", a=1, n=5, k=4),
        ]
    )
    by_route = {row["route"]: row for row in result["rungs"]}

    assert by_route["last"]["E"] == pytest.approx(1.1 + (2 / 7) * (1.1 + (2 / 7) * 5))
    assert by_route["expensive"]["E"] > by_route["middle"]["E"]
    assert result["argmin_start"] == "middle"
    assert result["escalation"] == ["middle", "last"]


def repair_rows(count, passes):
    return [
        {
            "parent_attempt_id": f"parent-{index}",
            "router_event": {"route_id": "r1"},
            "class_record": {"class_key": CLASS},
            "verified_success": index < passes,
        }
        for index in range(count)
    ]


def test_q_prime_stays_q_below_repair_sample_threshold():
    rows = supervisor_rows() + repair_rows(4, 4)
    result = calculate([rung("r1", n=8, k=2)], attempt_records=rows)
    row = result["rungs"][0]
    assert row["q"] == pytest.approx(0.3)
    assert row["q_prime"] == pytest.approx(0.3)


def test_q_prime_uses_its_own_laplace_estimate_at_five_repairs():
    rows = supervisor_rows() + repair_rows(5, 4)
    row = calculate([rung("r1", n=8, k=2)], attempt_records=rows)["rungs"][0]
    assert row["q"] == pytest.approx(0.3)
    assert row["q_prime"] == pytest.approx(5 / 7)


def test_supervisor_overhead_requires_five_eligible_attested_rows():
    four = supervisor_rows((0.1,) * 4)
    assert supervisor_overhead_from_rows(four, supervisor_route="supervisor") == (
        None,
        4,
    )
    result = calculate([rung("r1")], attempt_records=four)
    assert result["rungs"][0]["s"] == EXPECTED_COST_UNAVAILABLE
    assert result["rungs"][0]["E"] == EXPECTED_COST_UNAVAILABLE
    assert "need 5" in result["unavailable_reasons"][-1]

    rows = supervisor_rows((0.1, 0.2, 0.3, 0.4, 0.5))
    assert supervisor_overhead_from_rows(rows, supervisor_route="supervisor") == (
        0.3,
        5,
    )


def test_rows_without_supervisor_route_or_explicitly_ineligible_are_excluded():
    rows = supervisor_rows((0.2,) * 5)
    rows.extend(
        [
            {
                "router_event": {"route_id": "unattested-supervisor"},
                "cost": {"usd_marginal": 99},
            },
            {
                "supervisor_route": {"route_id": "supervisor"},
                "router_event": {"route_id": "supervisor"},
                "cost": {"usd_marginal": 99},
                "eligible": False,
            },
        ]
    )
    assert supervisor_overhead_from_rows(rows, supervisor_route="supervisor") == (
        0.2,
        5,
    )


def test_judge_v_is_explicit_selected_independent_reviewer_expected_cost():
    result = calculate(
        [rung("r1")], oracle_type="judge", reviewer_expected_cost_usd=0.4
    )
    row = result["rungs"][0]
    assert row["v"] == pytest.approx(0.4)
    assert row["E"] == pytest.approx(1.5 + 0.5 * (1.5 + 0.5 * 5))


def test_unknown_judge_cost_makes_expected_cost_unavailable():
    result = calculate([rung("r1")], oracle_type="judge")
    assert result["expected_cost_status"] == EXPECTED_COST_UNAVAILABLE
    assert result["rungs"][0]["v"] == EXPECTED_COST_UNAVAILABLE


@pytest.mark.parametrize(
    ("changed", "field"),
    [
        ({"demand": "unknown"}, "a"),
        ({"demand": demand(input_tokens="unknown")}, "a"),
        ({"pricing": None}, "a"),
        ({"evidence": evidence(level="none", n=0, k=0)}, "q"),
        ({"evidence": None}, "q"),
    ],
)
def test_unknown_demand_pricing_or_evidence_is_explicit(changed, field):
    base = {
        "route": "r1",
        "demand": demand(),
        "pricing": pricing(),
        "evidence": evidence(),
    }
    base.update(changed)
    result = calculate([base])
    row = result["rungs"][0]
    assert row[field] == EXPECTED_COST_UNAVAILABLE
    assert row["E"] == EXPECTED_COST_UNAVAILABLE
    assert result["expected_cost_status"] == EXPECTED_COST_UNAVAILABLE


def test_attempt_cost_uses_only_input_output_medians_and_marginal_prices():
    item = {
        "route": "r1",
        "demand": demand(
            input_tokens=2,
            output_tokens=3,
            total_tokens=10_000_000,
            cached_input_tokens=9_000_000,
        ),
        "pricing": pricing(
            input_rate=0.1,
            output_rate=0.2,
            replacement_input_usd_per_token=999,
            replacement_output_usd_per_token=999,
        ),
        "evidence": evidence(),
    }
    row = calculate([item])["rungs"][0]
    assert row["a"] == pytest.approx(0.8)


def test_unavailable_arithmetic_fallback_is_proof_then_price_and_stable():
    rungs = [
        LadderInput("cheap-unproven", "unknown", pricing(0.01, 0.01), evidence()),
        LadderInput(
            "proven-tie-a",
            "unknown",
            pricing(0.02, 0.03),
            evidence(),
            ProofStatus.PROVEN,
        ),
        LadderInput(
            "proven-cheap",
            "unknown",
            pricing(0.01, 0.02),
            evidence(),
            ProofStatus.PROVEN,
        ),
        LadderInput(
            "proven-tie-b",
            "unknown",
            pricing(0.02, 0.03),
            evidence(),
            ProofStatus.PROVEN,
        ),
    ]
    result = calculate(rungs)

    assert result["expected_cost_status"] == EXPECTED_COST_UNAVAILABLE
    assert result["argmin_start"] == "proven-cheap"
    assert result["escalation"] == [
        "proven-cheap",
        "proven-tie-a",
        "proven-tie-b",
        "cheap-unproven",
    ]
    assert [row["route"] for row in result["rungs"]] == result["escalation"]


def test_empty_ladder_is_explicitly_unavailable():
    result = calculate([])
    assert result["argmin_start"] is None
    assert result["escalation"] == []
    assert result["unavailable_reasons"] == ["no eligible routes"]
