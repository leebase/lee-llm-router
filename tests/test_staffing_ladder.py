"""Hand-computed tests for pure D211 ladder arithmetic.

Finding 4 semantics: attempt-record v2 has no attributable supervision-cost
field or record kind, so supervisor overhead is always unavailable — the
supervisor route's own worker attempt costs are never repurposed as ``s``.
Every ladder that would need ``s`` therefore fails closed, and the tests
assert the proof-first, marginal-price fallback ordering instead of argmin
arithmetic.
"""

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


def assert_s_fail_closed(result):
    """Every rung's s and E are unavailable with the fail-closed reason."""
    reason = " ".join(result["unavailable_reasons"])
    assert "supervisor overhead unavailable" in reason
    assert "attributable supervision-cost" in reason
    assert "need 5" in reason
    assert result["expected_cost_status"] == EXPECTED_COST_UNAVAILABLE
    for row in result["rungs"]:
        assert row["s"] == EXPECTED_COST_UNAVAILABLE
        assert row["E"] == EXPECTED_COST_UNAVAILABLE


def test_supervisor_overhead_fails_closed_without_attributable_cost():
    """Even five attested rows plus five same-route marginal costs never
    produce s: those costs price the worker attempts, not the supervision."""
    rows = supervisor_rows((0.1, 0.2, 0.3, 0.4, 0.5))
    assert supervisor_overhead_from_rows(rows, supervisor_route="supervisor") == (
        None,
        5,
    )
    assert supervisor_overhead_from_rows(rows) == (None, 5)


def test_worker_costs_of_the_supervisor_route_are_never_repurposed():
    result = calculate([rung("r1")])
    assert_s_fail_closed(result)


def test_fewer_than_five_attestations_still_fail_closed():
    four = supervisor_rows((0.1,) * 4)
    assert supervisor_overhead_from_rows(four, supervisor_route="supervisor") == (
        None,
        4,
    )
    result = calculate([rung("r1")], attempt_records=four)
    assert_s_fail_closed(result)
    assert result["rungs"][0]["a"] == pytest.approx(1.0)


def test_one_rung_shape_with_fail_closed_s():
    result = calculate([rung("r1")])

    assert result["argmin_start"] == "r1"
    assert result["escalation"] == ["r1"]
    assert set(result["rungs"][0]) == RUNG_KEYS
    row = result["rungs"][0]
    assert row["route"] == "r1"
    assert {
        key: value for key, value in row.items() if key not in ("route", "s", "E")
    } == pytest.approx({"a": 1.0, "v": 0.0, "q": 0.5, "q_prime": 0.5})
    assert_s_fail_closed(result)


def test_each_known_term_is_still_computed_while_s_is_unavailable():
    result = calculate([rung("r1", a=0.1, n=2, k=0), rung("r2", a=2, n=2, k=2)])
    by_route = {row["route"]: row for row in result["rungs"]}

    assert by_route["r1"]["a"] == pytest.approx(0.1)
    assert by_route["r2"]["a"] == pytest.approx(2.0)
    assert_s_fail_closed(result)
    # The fallback orders by current marginal price, so the cheap rung leads.
    assert result["argmin_start"] == "r1"
    assert result["escalation"] == ["r1", "r2"]


def test_fallback_orders_three_rungs_by_marginal_price():
    result = calculate(
        [
            rung("expensive", a=10, n=5, k=0),
            rung("middle", a=0.2, n=5, k=4),
            rung("last", a=1, n=5, k=4),
        ]
    )

    assert_s_fail_closed(result)
    assert result["argmin_start"] == "middle"
    assert result["escalation"] == ["middle", "last", "expensive"]


def test_subscription_headroom_outranks_cheaper_metered_route(monkeypatch):
    monkeypatch.setattr(
        "lee_llm_router.staffing.ladder.supervisor_overhead_from_rows",
        lambda *_args, **_kwargs: (0.0, 5),
    )
    result = calculate(
        [rung("metered", a=0.01), rung("subscription-on-track", a=0.25)],
        channel_kind_by_route={
            "metered": "metered",
            "subscription-on-track": "subscription",
        },
    )

    by_route = {row["route"]: row for row in result["rungs"]}
    assert result["expected_cost_status"] == EXPECTED_COST_AVAILABLE
    assert by_route["metered"]["E"] < by_route["subscription-on-track"]["E"]
    assert by_route["subscription-on-track"]["a"] > 0
    assert result["argmin_start"] == "subscription-on-track"
    assert result["escalation"] == ["subscription-on-track", "metered"]


def test_badge_price_still_orders_subscription_routes_within_their_tier():
    result = calculate(
        [rung("too-fast", a=1.0), rung("cold", a=0.0)],
        channel_kind_by_route={"too-fast": "subscription", "cold": "subscription"},
    )

    assert result["escalation"] == ["cold", "too-fast"]


def test_omitted_channel_kinds_preserve_existing_price_ordering():
    result = calculate([rung("subscription-on-track", a=0.25), rung("metered", a=0.01)])

    assert result["argmin_start"] == "metered"
    assert result["escalation"] == ["metered", "subscription-on-track"]


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
    assert_s_fail_closed(result)


def test_q_prime_uses_its_own_laplace_estimate_at_five_repairs():
    rows = supervisor_rows() + repair_rows(5, 4)
    row = calculate([rung("r1", n=8, k=2)], attempt_records=rows)["rungs"][0]
    assert row["q"] == pytest.approx(0.3)
    assert row["q_prime"] == pytest.approx(5 / 7)


def test_rows_without_supervisor_route_or_explicitly_ineligible_do_not_attest():
    rows = supervisor_rows()
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
    # Only the five eligible attesting rows count toward the disclosure;
    # the unattested and explicitly ineligible rows add nothing.
    assert supervisor_overhead_from_rows(rows, supervisor_route="supervisor") == (
        None,
        5,
    )


def test_judge_v_is_explicit_selected_independent_reviewer_expected_cost():
    result = calculate(
        [rung("r1")], oracle_type="judge", reviewer_expected_cost_usd=0.4
    )
    row = result["rungs"][0]
    assert row["v"] == pytest.approx(0.4)
    assert row["a"] == pytest.approx(1.0)
    assert row["q"] == pytest.approx(0.5)
    assert_s_fail_closed(result)


def test_unknown_judge_cost_makes_expected_cost_unavailable():
    result = calculate([rung("r1")], oracle_type="judge")
    assert result["expected_cost_status"] == EXPECTED_COST_UNAVAILABLE
    assert result["rungs"][0]["v"] == EXPECTED_COST_UNAVAILABLE
    assert_s_fail_closed(result)


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
    assert row["s"] == EXPECTED_COST_UNAVAILABLE
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


def test_proven_rung_leads_the_fallback_even_when_more_expensive():
    rungs = [
        LadderInput("cheap-unproven", "unknown", pricing(0.01, 0.01), evidence()),
        LadderInput(
            "proven-cheap",
            "unknown",
            pricing(0.01, 0.02),
            evidence(),
            ProofStatus.PROVEN,
        ),
        LadderInput(
            "proven-tie-a",
            "unknown",
            pricing(0.02, 0.03),
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
