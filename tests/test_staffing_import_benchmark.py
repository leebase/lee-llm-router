"""Focused P1-7 benchmark-v6 evidence import tests.

All state is redirected through the app-specific attempt-ledger environment
override.  Fixtures are static CSV/JSON only; no subprocess or provider
boundary exists in this test module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lee_llm_router.doctor import main
from lee_llm_router.staffing.import_evidence import (
    BENCHMARK_USAGE_SOURCE,
    import_benchmark_evidence,
)
from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    read_attempts,
)

FIXTURES = Path(__file__).parent / "fixtures" / "staffing"
SIDECAR = FIXTURES / "benchmark-v6-sidecar.fixture"


@pytest.fixture(autouse=True)
def isolated_attempt_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use only the named scratch override, never a user state directory."""
    ledger = tmp_path / "state" / "benchmark-attempts.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    monkeypatch.delenv(ATTEMPTS_STATE_ROOT_ENV_VAR, raising=False)
    return ledger


def test_benchmark_rows_map_tokens_class_acceptance_and_provenance(
    isolated_attempt_state: Path,
) -> None:
    summary = import_benchmark_evidence(SIDECAR)

    assert summary.imported == 2
    assert summary.skipped == 1
    assert summary.ledger_path == isolated_attempt_state
    assert summary.issues[0].run_id == "fixture-run-malformed"
    assert summary.issues[0].reason == "usage_input_tokens is unavailable"

    records = read_attempts(isolated_attempt_state)
    assert [record["attempt_id"] for record in records] == [
        "benchmark:fixture-run-accepted",
        "benchmark:fixture-run-rejected",
    ]
    accepted, rejected = records
    assert accepted["captured_at"] == "2026-09-09T12:05:00Z"
    assert accepted["verdict"] == "pass"
    assert rejected["verdict"] == "fail"
    assert accepted["verified_success"] is False
    assert accepted["class_record"] == {
        "class_key": "impl/deterministic/none/m/python",
        "role": "impl",
        "oracle_type": "deterministic",
        "domain_tags": [],
        "size_band": "m",
        "language": "python",
    }
    assert rejected["class_record"]["class_key"] == (
        "review/judge/data-schema/m/python"
    )
    assert accepted["usage"] == {
        "basis": "provider_reported",
        "source": BENCHMARK_USAGE_SOURCE,
        "input_tokens": 101,
        "output_tokens": 202,
        "cached_input_tokens": 33,
        "reasoning_tokens": None,
        "total_tokens": 303,
    }
    assert rejected["usage"]["reasoning_tokens"] == 11
    assert accepted["cost"] == {"basis": ["unavailable"]}
    assert "route" not in accepted
    assert "supervisor_route" not in accepted
    assert accepted["provenance"]["source"] == "benchmark"
    assert accepted["benchmark_run"]["stages"][0]["worker"] == {
        "model": "gpt-5.6-luna",
        "harness": "pi",
        "effort": "xhigh",
        "model_family": "luna",
    }
    assert accepted["benchmark_run"]["final_acceptance"] == "accepted"
    assert accepted["wall_clock_ms"] == 290000


def test_second_import_has_deterministic_ids_and_adds_zero(
    isolated_attempt_state: Path,
) -> None:
    first = import_benchmark_evidence(SIDECAR)
    before = isolated_attempt_state.read_bytes()

    second = import_benchmark_evidence(SIDECAR)

    assert first.imported == 2
    assert second.imported == 0
    assert second.skipped == 3
    assert isolated_attempt_state.read_bytes() == before
    duplicate_ids = {
        issue.run_id
        for issue in second.issues
        if issue.reason == "attempt_id already present"
    }
    assert duplicate_ids == {"fixture-run-accepted", "fixture-run-rejected"}


def test_cli_prints_counts_and_explicit_malformed_row(
    isolated_attempt_state: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["evidence", "import", "--benchmark", str(SIDECAR)])

    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == "imported=2 skipped=1\n"
    assert "skipped row 4 run_id=fixture-run-malformed" in captured.err
    assert "usage_input_tokens is unavailable" in captured.err
    assert len(read_attempts(isolated_attempt_state)) == 2
