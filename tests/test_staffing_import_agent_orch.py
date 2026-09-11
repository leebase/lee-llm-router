"""Focused P1-7 Agent-Orch raw-attempt import tests.

The fixture builder writes only the three authorized source artifacts: a run
manifest, sibling route-selection.json, and usage.json when present. No
provider, subprocess, or real prompt is used.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lee_llm_router.doctor import main
from lee_llm_router.staffing.import_evidence import (
    EvidenceImportError,
    import_agent_orch_evidence,
)
from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    read_attempts,
)

NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _add_run(
    root: Path,
    *,
    run_id: str,
    timestamp: str,
    attempts: list[dict],
) -> None:
    run_dir = root / run_id
    step_id = "step_fixture"
    step_attempts = []
    for item in attempts:
        number = item["attempt_number"]
        attempt_dir = run_dir / "steps" / step_id / f"attempt-{number}"
        route = item.get(
            "route",
            {"harness": "codex_cli", "model": "gpt-5.6-sol", "effort": "low"},
        )
        _write_json(attempt_dir / "route-selection.json", {"selected_route": route})
        if "usage" in item:
            _write_json(attempt_dir / "usage.json", item["usage"])
        step_attempts.append(
            {
                "attempt_number": number,
                "failure_classification": item.get("failure_classification"),
                "policy_decision": item.get("policy_decision", "PASS"),
                "run_dir": str(attempt_dir),
                "validation_passed": item.get("validation_passed", True),
                "worker_exit_code": item.get("worker_exit_code", 0),
            }
        )
        for timestamp_name in ("started_at", "ended_at"):
            if timestamp_name in item:
                step_attempts[-1][timestamp_name] = item[timestamp_name]
    _write_json(
        run_dir / "run.json",
        {
            "run_id": run_id,
            "last_updated_at": timestamp,
            "step_results": [{"step_id": step_id, "attempts": step_attempts}],
        },
    )


def _measured_usage() -> dict:
    return {
        "accounting_schema_version": 1,
        "accounting_status": "measured",
        "cached_read_tokens": 2,
        "cost_usd": 0.5,
        "input_tokens": 10,
        "model": "gpt-5.6-sol",
        "output_tokens": 4,
        "raw_usage": {"reasoning_output_tokens": 1},
        "total_tokens": 14,
        "usage_scope": "single",
    }


@pytest.fixture(autouse=True)
def isolated_attempt_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every append in the app-specific scratch-state override."""
    ledger = tmp_path / "state" / "agent-orch-attempts.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    monkeypatch.delenv(ATTEMPTS_STATE_ROOT_ENV_VAR, raising=False)
    return ledger


@pytest.fixture
def agent_orch_fixture(tmp_path: Path) -> Path:
    """Create measured, unavailable, missing-receipt, cutoff, and malformed rows."""
    root = tmp_path / "fixture-agent-orch-runs"
    _add_run(
        root,
        run_id="measured-run",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[
            {
                "attempt_number": 1,
                "started_at": "2026-09-10T11:58:00Z",
                "ended_at": "2026-09-10T12:00:00Z",
                "usage": _measured_usage(),
            }
        ],
    )
    _add_run(
        root,
        run_id="unaccounted-run",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[
            {
                "attempt_number": 1,
                "usage": {
                    "accounting_schema_version": 1,
                    "accounting_status": "unaccounted",
                    "reason": "provider receipt missing",
                },
                "worker_exit_code": 1,
                "validation_passed": False,
            }
        ],
    )
    _add_run(
        root,
        run_id="missing-receipt-run",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[{"attempt_number": 1}],
    )
    _add_run(
        root,
        run_id="not-applicable-run",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[
            {
                "attempt_number": 1,
                "usage": {
                    "accounting_schema_version": 1,
                    "accounting_status": "not_applicable",
                    "reason": "subscription adapter",
                },
            }
        ],
    )
    _add_run(
        root,
        run_id="cutoff-run",
        timestamp="2026-08-01T12:00:00Z",
        attempts=[{"attempt_number": 1, "usage": _measured_usage()}],
    )
    _add_run(
        root,
        run_id="malformed-route-run",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[
            {
                "attempt_number": 1,
                "route": {"harness": "codex_cli"},
                "usage": _measured_usage(),
            }
        ],
    )
    return root


def test_agent_orch_accounting_provenance_cutoff_and_raw_shape(
    agent_orch_fixture: Path, isolated_attempt_state: Path
) -> None:
    summary = import_agent_orch_evidence(agent_orch_fixture, now=NOW)

    assert summary.imported == 4
    assert summary.skipped == 1
    assert summary.ledger_path == isolated_attempt_state
    assert summary.issues[0].run_id == "malformed-route-run"
    assert summary.issues[0].reason == "selected route model is missing"
    records = read_attempts(isolated_attempt_state)
    by_run = {record["agent_orch_attempt"]["run_id"]: record for record in records}

    measured = by_run["measured-run"]
    assert measured["attempt_id"] == (
        "fb7701dadda0c9f252501e6c36c64c939ba6b25b6e890267e247c65b30fdb9ed"
    )
    assert measured["record_kind"] == "agent_orch_attempt"
    assert measured["class_source"] == "none"
    assert "class_record" not in measured and "class_key" not in measured
    assert measured["usage"] == {
        "basis": "provider_reported",
        "source": "agent-orch usage.json",
        "input_tokens": 10,
        "output_tokens": 4,
        "cached_input_tokens": 2,
        "reasoning_tokens": 1,
        "total_tokens": 14,
    }
    assert measured["cost"] == {"basis": "list", "usd_list": 0.5}
    measured_dir = (
        agent_orch_fixture / "measured-run" / "steps" / "step_fixture" / "attempt-1"
    ).resolve()
    measured_paths = [
        str((agent_orch_fixture / "measured-run" / "run.json").resolve()),
        str(measured_dir / "route-selection.json"),
        str(measured_dir / "usage.json"),
    ]
    assert measured["agent_orch_attempt"] == {
        "run_id": "measured-run",
        "step_id": "step_fixture",
        "attempt_number": 1,
        "route": {
            "harness": "codex_cli",
            "model": "gpt-5.6-sol",
            "effort": "low",
        },
        "worker_exit_code": 0,
        "validation_passed": True,
        "policy_decision": "PASS",
        "failure_classification": None,
        "accounting_status": "measured",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 4,
            "cached_read_tokens": 2,
            "reasoning_output_tokens": 1,
            "total_tokens": 14,
        },
        "cost_usd": 0.5,
        "started_at": "2026-09-10T11:58:00Z",
        "ended_at": "2026-09-10T12:00:00Z",
        "source_paths": measured_paths,
    }
    assert measured["verified_success"] is True
    assert measured["verdict"] == {"tier": "engine_validation"}
    assert measured["provenance"]["source"] == "agent-orch-runs"
    assert measured["provenance"]["recorded_by"] == ("lee-llm-router evidence import")
    assert measured["provenance"]["source_refs"] == [
        "docs/staffing/chief-answers-p1-3.md",
        *measured_paths,
    ]

    unaccounted = by_run["unaccounted-run"]
    assert unaccounted["usage"] == {
        "basis": "unavailable",
        "unavailable_reason": "provider receipt missing",
    }
    assert unaccounted["cost"] == {"basis": "unavailable"}
    assert unaccounted["agent_orch_attempt"]["accounting_status"] == "unaccounted"
    assert unaccounted["agent_orch_attempt"]["source_paths"][-1].endswith("/usage.json")

    missing = by_run["missing-receipt-run"]
    assert missing["usage"] == {
        "basis": "unavailable",
        "unavailable_reason": "missing usage receipt",
    }
    assert missing["cost"] == {"basis": "unavailable"}
    assert missing["agent_orch_attempt"]["accounting_status"] is None
    assert len(missing["agent_orch_attempt"]["source_paths"]) == 2
    assert all(
        not path.endswith("/usage.json")
        for path in missing["agent_orch_attempt"]["source_paths"]
    )

    not_applicable = by_run["not-applicable-run"]
    assert not_applicable["usage"] == {
        "basis": "unavailable",
        "unavailable_reason": "non-metered adapter",
    }
    assert not_applicable["cost"] == {"basis": "unavailable"}
    assert not_applicable["agent_orch_attempt"]["accounting_status"] == (
        "not_applicable"
    )

    assert {record["usage"]["basis"] for record in records} == {
        "provider_reported",
        "unavailable",
    }
    for record in records:
        assert record["class_source"] == "none"
        for absent in (
            "class_key",
            "class_record",
            "route",
            "supervisor_route",
            "oracle_cmd",
            "selection",
        ):
            assert absent not in record


def test_agent_orch_verified_success_is_exact_exit_validation_equivalence(
    tmp_path: Path, isolated_attempt_state: Path
) -> None:
    root = tmp_path / "success-agent-orch-runs"
    outcomes = [(0, True), (0, False), (9, True), (9, False)]
    _add_run(
        root,
        run_id="success-matrix",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[
            {
                "attempt_number": number,
                "worker_exit_code": exit_code,
                "validation_passed": validation_passed,
                "usage": {
                    "accounting_status": "not_applicable",
                },
            }
            for number, (exit_code, validation_passed) in enumerate(outcomes, start=1)
        ],
    )

    summary = import_agent_orch_evidence(root, now=NOW)

    assert summary.imported == 4
    records = read_attempts(isolated_attempt_state)
    assert [record["verified_success"] for record in records] == [
        True,
        False,
        False,
        False,
    ]
    assert all(record["verdict"] == {"tier": "engine_validation"} for record in records)


def test_agent_orch_cutoff_is_inclusive_and_future_runs_are_excluded(
    tmp_path: Path, isolated_attempt_state: Path
) -> None:
    root = tmp_path / "cutoff-agent-orch-runs"
    cutoff = NOW - timedelta(days=30)
    cases = {
        "at-cutoff": cutoff,
        "before-cutoff": cutoff - timedelta(microseconds=1),
        "at-now": NOW,
        "after-now": NOW + timedelta(microseconds=1),
    }
    for run_id, timestamp in cases.items():
        _add_run(
            root,
            run_id=run_id,
            timestamp=timestamp.isoformat().replace("+00:00", "Z"),
            attempts=[{"attempt_number": 1, "usage": _measured_usage()}],
        )

    summary = import_agent_orch_evidence(root, now=NOW)

    assert summary.imported == 2
    assert summary.skipped == 0
    assert {
        record["agent_orch_attempt"]["run_id"]
        for record in read_attempts(isolated_attempt_state)
    } == {"at-cutoff", "at-now"}


def test_agent_orch_malformed_artifacts_are_skipped_with_reasons(
    tmp_path: Path,
) -> None:
    root = tmp_path / "malformed-agent-orch-runs"
    _add_run(
        root,
        run_id="bad-route",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[{"attempt_number": 1, "route": {}, "usage": _measured_usage()}],
    )
    bad_usage = _measured_usage()
    bad_usage["cost_usd"] = -1
    _add_run(
        root,
        run_id="bad-usage",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[{"attempt_number": 1, "usage": bad_usage}],
    )
    _add_run(
        root,
        run_id="bad-attempt",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[{"attempt_number": 1, "validation_passed": "yes"}],
    )
    malformed_run = root / "bad-run" / "run.json"
    malformed_run.parent.mkdir(parents=True)
    malformed_run.write_text("{not json\n", encoding="utf-8")

    summary = import_agent_orch_evidence(root, now=NOW)

    assert summary.imported == 0
    assert summary.skipped == 4
    reasons = {issue.reason for issue in summary.issues}
    assert "selected route harness is missing" in reasons
    assert "usage.json cost_usd is not a nonnegative finite number" in reasons
    assert "validation_passed is not a boolean" in reasons
    assert any("is not valid UTF-8 JSON" in reason for reason in reasons)


def test_agent_orch_latest_pointer_is_not_a_duplicate_source(
    tmp_path: Path, isolated_attempt_state: Path
) -> None:
    root = tmp_path / "latest-agent-orch-runs"
    _add_run(
        root,
        run_id="retained-run",
        timestamp="2026-09-10T12:00:00Z",
        attempts=[{"attempt_number": 1, "usage": _measured_usage()}],
    )
    (root / "latest").symlink_to("retained-run", target_is_directory=True)

    summary = import_agent_orch_evidence(root, now=NOW)

    assert summary.imported == 1
    assert summary.skipped == 0
    assert len(read_attempts(isolated_attempt_state)) == 1


def test_agent_orch_rejects_bad_source_and_naive_cutoff(tmp_path: Path) -> None:
    with pytest.raises(EvidenceImportError, match="source directory not found"):
        import_agent_orch_evidence(tmp_path / "missing", now=NOW)
    empty_root = tmp_path / "empty-agent-orch-runs"
    empty_root.mkdir()
    with pytest.raises(EvidenceImportError, match="timezone-aware"):
        import_agent_orch_evidence(
            empty_root,
            now=datetime(2026, 9, 11, 12),
        )


def test_agent_orch_reimport_adds_zero_and_cli_reports_counts(
    agent_orch_fixture: Path,
    tmp_path: Path,
    isolated_attempt_state: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = import_agent_orch_evidence(agent_orch_fixture, now=NOW)
    before = isolated_attempt_state.read_bytes()
    second = import_agent_orch_evidence(agent_orch_fixture, now=NOW)

    assert first.imported == 4
    assert second.imported == 0
    assert second.skipped == 5
    assert isolated_attempt_state.read_bytes() == before

    cli_root = tmp_path / "cli-agent-orch-runs"
    _add_run(
        cli_root,
        run_id="cli-run",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        attempts=[{"attempt_number": 1, "usage": _measured_usage()}],
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["evidence", "import", "--agent-orch", str(cli_root)])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == "imported=1 skipped=0\n"
    # Four prior IDs remain, while the CLI source contributes one new attempt.
    assert len(read_attempts(isolated_attempt_state)) == 5


def test_agent_orch_cli_rejects_benchmark_csv_override(
    agent_orch_fixture: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "evidence",
                "import",
                "--agent-orch",
                str(agent_orch_fixture),
                "--csv",
                str(tmp_path / "unused.csv"),
            ]
        )

    assert excinfo.value.code == 3
    assert capsys.readouterr().err == "evidence import: --csv requires --benchmark\n"
