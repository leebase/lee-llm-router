"""Focused P2-2 tests for D211 route proof status."""

from __future__ import annotations

from pathlib import Path

import pytest

from lee_llm_router.staffing.proof import (
    PROVEN_USAGE_BASES,
    ProofStatus,
    is_route_proven,
    proof_status_by_route,
    proof_status_ledger,
    record_proves_route,
    route_proof_status,
    router_route_id,
)

ROUTE_A = "route-a"
ROUTE_B = "route-b"
ROUTE_C = "route-c"


def router_run(
    route_id: str = ROUTE_A,
    *,
    basis: object = "unavailable",
    verified_success: object = False,
) -> dict[str, object]:
    """Build the minimum equivalent mapping needed by the pure proof logic."""
    return {
        "record_kind": "router_run",
        "router_event": {"route_id": route_id},
        "usage": {"basis": basis},
        "verified_success": verified_success,
    }


def test_d211_proven_usage_bases_are_exact() -> None:
    assert PROVEN_USAGE_BASES == frozenset({"observed", "provider_reported"})


@pytest.mark.parametrize(
    "record_kind", ["agent_orch", "agent_orch_attempt", "benchmark_run"]
)
def test_imports_never_prove_even_with_router_evidence(
    record_kind: str,
) -> None:
    record = router_run(basis="provider_reported", verified_success=True)
    record["record_kind"] = record_kind

    assert record_proves_route(record) is None
    assert proof_status_by_route([record]) == {}


@pytest.mark.parametrize("basis", ["calculated", "unavailable"])
def test_calculated_and_unavailable_only_are_unproven(basis: str) -> None:
    record = router_run(basis=basis)

    assert record_proves_route(record) is None
    assert proof_status_by_route([record]) == {
        ROUTE_A: ProofStatus.UNPROVEN,
    }
    assert route_proof_status([record], ROUTE_A) is ProofStatus.UNPROVEN
    assert not is_route_proven([record], ROUTE_A)


@pytest.mark.parametrize("basis", [None, [], {}, 1])
def test_malformed_usage_basis_fails_closed(basis: object) -> None:
    record = router_run(basis=basis)

    assert proof_status_by_route([record]) == {
        ROUTE_A: ProofStatus.UNPROVEN,
    }


def test_failed_provider_reported_router_run_is_proven() -> None:
    record = router_run(basis="provider_reported", verified_success=False)

    assert record_proves_route(record) == ROUTE_A
    assert proof_status_by_route([record]) == {
        ROUTE_A: ProofStatus.PROVEN,
    }


def test_verified_success_proves_with_unavailable_usage() -> None:
    record = router_run(basis="unavailable", verified_success=True)

    assert record_proves_route(record) == ROUTE_A
    assert route_proof_status([record], ROUTE_A) is ProofStatus.PROVEN
    assert is_route_proven([record], ROUTE_A)


@pytest.mark.parametrize("verified_success", [1, "true", "yes", []])
def test_verified_success_must_be_the_boolean_true(verified_success: object) -> None:
    record = router_run(basis="unavailable", verified_success=verified_success)

    assert proof_status_by_route([record]) == {
        ROUTE_A: ProofStatus.UNPROVEN,
    }


@pytest.mark.parametrize("record_kind", [None, "", "router_run ", 1, []])
def test_missing_or_malformed_record_kind_fails_closed(
    record_kind: object,
) -> None:
    record = router_run(basis="provider_reported", verified_success=True)
    if record_kind is None:
        del record["record_kind"]
    else:
        record["record_kind"] = record_kind

    assert record_proves_route(record) is None
    assert proof_status_by_route([record]) == {}


@pytest.mark.parametrize(
    "router_event",
    [
        None,
        [],
        {},
        {"route_id": None},
        {"route_id": 0},
        {"route_id": []},
        {"route_id": {}},
        {"route_id": ""},
        {"route_id": "   "},
    ],
)
def test_missing_or_malformed_route_ids_fail_closed(
    router_event: object,
) -> None:
    record = router_run(basis="provider_reported", verified_success=True)
    record["router_event"] = router_event
    record["route_id"] = ROUTE_A
    record["route"] = {"route_id": ROUTE_A}

    assert router_route_id(record) is None
    assert record_proves_route(record) is None
    assert proof_status_by_route([record]) == {}


@pytest.mark.parametrize("record", [None, [], "not a record", 42])
def test_non_mapping_rows_fail_closed(record: object) -> None:
    assert router_route_id(record) is None
    assert record_proves_route(record) is None
    assert proof_status_by_route([record]) == {}


def test_proof_is_isolated_to_each_route() -> None:
    records = [
        router_run(ROUTE_A, basis="unavailable"),
        router_run(ROUTE_B, basis="provider_reported"),
        router_run(ROUTE_A, basis="calculated"),
    ]

    assert proof_status_by_route(records) == {
        ROUTE_A: ProofStatus.UNPROVEN,
        ROUTE_B: ProofStatus.PROVEN,
    }
    assert route_proof_status(records, ROUTE_C) is ProofStatus.UNPROVEN


def test_results_are_deterministically_sorted_and_repeatable() -> None:
    records = [
        router_run(ROUTE_C, basis="unavailable"),
        router_run(ROUTE_A, basis="provider_reported"),
        router_run(ROUTE_B, basis="calculated"),
        router_run(ROUTE_C, basis="observed"),
    ]

    first = proof_status_by_route(records)
    second = proof_status_by_route(list(reversed(records)))

    assert list(first) == [ROUTE_A, ROUTE_B, ROUTE_C]
    assert (
        first
        == second
        == {
            ROUTE_A: ProofStatus.PROVEN,
            ROUTE_B: ProofStatus.UNPROVEN,
            ROUTE_C: ProofStatus.PROVEN,
        }
    )


def test_empty_ledger_has_no_route_status(tmp_path: Path) -> None:
    ledger = tmp_path / "attempts.jsonl"
    ledger.touch()

    assert proof_status_by_route([]) == {}
    assert proof_status_ledger(ledger) == {}
    assert proof_status_ledger(tmp_path / "missing.jsonl") == {}
