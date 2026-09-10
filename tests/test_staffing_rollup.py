"""Focused P1-6 tests for deterministic staffing evidence rollups."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    AttemptLedgerError,
    append_attempt,
)
from lee_llm_router.staffing.rollup import build_rollup, rollup_ledger

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / ("attempt-record-router-run-unavailable.json")
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
                "token_medians": {
                    "input_tokens": 4.0,
                    "output_tokens": 5.0,
                    "cached_input_tokens": 30,
                    "reasoning_tokens": None,
                    "total_tokens": 9.0,
                },
                "wall_clock_median_ms": 400.0,
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
