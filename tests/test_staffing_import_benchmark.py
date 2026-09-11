"""Focused P1-7 benchmark-v6 evidence import tests.

All state is redirected through the app-specific attempt-ledger environment
override.  Fixtures are static CSV/JSON only; no subprocess or provider
boundary exists in this test module.

The import writes only the raw ``benchmarkV6Run`` payload: facts copied from
the verified v6 sidecar and its SHA-256-pinned source CSV.  The v6 sidecar
provides neither a crew name nor a crews-file identity, so no fabricated
``crew_name``/``crews_file_sha256`` field may appear anywhere in a record
(D209).  Pre-repair legacy crew-run rows stay valid and readable; re-running
the import appends deterministic ``benchmark:v6:<run_id>`` correction records
instead of rewriting the append-only ledger.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from lee_llm_router.doctor import main
from lee_llm_router.staffing.import_evidence import (
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_USAGE_SOURCE,
    import_benchmark_evidence,
)
from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    append_attempt,
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


def _sidecar_sha256() -> str:
    return hashlib.sha256(SIDECAR.read_bytes()).hexdigest()


def _legacy_record() -> dict:
    """A pre-repair legacy crew-run-shaped record for the accepted fixture run.

    Built from the schema's legacy benchmark example (scratch data only) with
    the deterministic import id; it validates under the retained legacy
    crew-run payload branch, exactly like the committed ledger lines.
    """
    schema = json.loads(
        (FIXTURES.parent.parent.parent / "config/staffing/schema")
        .joinpath("attempt-record.schema.json")
        .read_text()
    )
    record = next(
        ex
        for ex in schema["examples"]
        if ex["attempt_id"] == "bench-mixed-economy-0001"
    )
    record = copy.deepcopy(record)
    record["attempt_id"] = "benchmark:fixture-run-accepted"
    record["benchmark_run"]["attempt_id"] = "benchmark:fixture-run-accepted"
    record["benchmark_run"]["stages"][0]["run_id"] = "fixture-run-accepted"
    record["captured_at"] = "2026-09-09T12:05:00Z"
    return record


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
    assert accepted["wall_clock_ms"] == 290000


def test_benchmark_payload_records_only_verified_v6_source_facts(
    isolated_attempt_state: Path,
) -> None:
    """Astra reproducer at the import layer: no fabricated machine facts."""
    import_benchmark_evidence(SIDECAR)
    accepted, rejected = read_attempts(isolated_attempt_state)

    payload = accepted["benchmark_run"]
    assert payload == {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "sidecar_sha256": _sidecar_sha256(),
        "source_csv": {
            "path": "benchmark-v6-runs.csv",
            "sha256": "7d8201137cfb98c02f8fa43151633376eede0044d589e5ed307ec4ca91a97227",
        },
        "generated_at": "2026-09-09T15:00:00Z",
        "run_id": "fixture-run-accepted",
        "task_key": "router-change@v1",
        "class": {
            "class_key": "impl/deterministic/none/m/python",
            "role": "impl",
            "oracle_type": "deterministic",
            "domain_tags": [],
            "size_band": "m",
            "language": "python",
        },
        "worker": {
            "model": "gpt-5.6-luna",
            "harness": "pi",
            "effort": "xhigh",
            "model_family": "luna",
        },
        "usage": {
            "usage_status": "known",
            "usage_input_tokens": 101,
            "usage_output_tokens": 202,
            "usage_cached_input_tokens": 33,
            "usage_reasoning_tokens": None,
            "usage_total_tokens": 303,
        },
        "acceptance": "accepted",
        "elapsed_ms": 290000,
        "source_timestamps": {
            "run_created_at": "2026-09-09T12:00:00Z",
            "started_at": "2026-09-09T12:00:05Z",
            "finished_at": "2026-09-09T12:04:55Z",
            "captured_at": "2026-09-09T12:05:00Z",
        },
    }
    assert rejected["benchmark_run"]["acceptance"] == "not_accepted"
    assert rejected["benchmark_run"]["run_id"] == "fixture-run-rejected"


def test_no_record_contains_fabricated_crew_or_crews_file_facts(
    isolated_attempt_state: Path,
) -> None:
    """The v6 sidecar provides no crew name and no crews-file identity.

    Fabricated fields are machine-readable facts, not prose: the whole record
    must not contain ``crew_name``, ``crews_file_sha256``, the invented crew
    name, or a role-derived stage/role-composition structure.
    """

    def walk(value: object) -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                found.append(str(key))
                found.extend(walk(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(walk(item))
        elif isinstance(value, str):
            found.append(value)
        return found

    summary = import_benchmark_evidence(SIDECAR)
    assert summary.imported == 2
    for record in read_attempts(isolated_attempt_state):
        keys_and_values = json.dumps(record)
        walk_keys = walk(record)
        assert "crew_name" not in walk_keys
        assert "crews_file_sha256" not in walk_keys
        assert "stages" not in walk_keys
        assert "role_composition" not in walk_keys
        assert "mixed-economy" not in keys_and_values
        assert "benchmark.crew-run/1" not in keys_and_values
        notes = " ".join(record["provenance"]["notes"])
        assert "mixed-economy" not in notes
        assert "crews_file_sha256" not in notes


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


def test_legacy_crew_run_row_is_corrected_not_rewritten(
    isolated_attempt_state: Path,
) -> None:
    """Governed reconciliation: append a truthful correction, keep history."""
    append_attempt(_legacy_record(), isolated_attempt_state)
    before = isolated_attempt_state.read_bytes()

    summary = import_benchmark_evidence(SIDECAR)

    # fixture-run-accepted gains its correction; fixture-run-rejected is a
    # fresh raw import; the malformed row is still skipped explicitly.
    assert summary.imported == 2
    assert summary.skipped == 1
    lines = isolated_attempt_state.read_bytes().splitlines(keepends=True)
    # The legacy line is retained byte for byte; nothing was rewritten.
    assert lines[0] == before
    assert len(lines) == 3

    records = read_attempts(isolated_attempt_state)
    legacy, correction, fresh = records
    assert legacy["attempt_id"] == "benchmark:fixture-run-accepted"
    assert legacy["benchmark_run"]["schema_version"] == "benchmark.crew-run/1"
    assert correction["attempt_id"] == "benchmark:v6:fixture-run-accepted"
    assert correction["benchmark_run"]["schema_version"] == BENCHMARK_SCHEMA_VERSION
    assert correction["benchmark_run"]["run_id"] == "fixture-run-accepted"
    assert correction["benchmark_run"]["sidecar_sha256"] == _sidecar_sha256()
    assert fresh["attempt_id"] == "benchmark:fixture-run-rejected"
    assert fresh["benchmark_run"]["sidecar_sha256"] == _sidecar_sha256()
    correction_notes = " ".join(correction["provenance"]["notes"])
    assert "Truthful correction of legacy record benchmark:fixture-run-accepted" in (
        correction_notes
    )
    # The correction itself carries no fabricated machine facts either: the
    # only occurrence of those names is the prose note naming what it corrects.
    assert "crew_name" not in json.dumps(correction["benchmark_run"])
    assert "crews_file_sha256" not in json.dumps(correction["benchmark_run"])


def test_correction_is_idempotent_and_legacy_row_stays_unique(
    isolated_attempt_state: Path,
) -> None:
    append_attempt(_legacy_record(), isolated_attempt_state)
    first = import_benchmark_evidence(SIDECAR)
    assert first.imported == 2
    before = isolated_attempt_state.read_bytes()

    second = import_benchmark_evidence(SIDECAR)

    assert second.imported == 0
    assert second.skipped == 3
    reasons = {issue.run_id: issue.reason for issue in second.issues}
    assert reasons["fixture-run-accepted"] == "correction already present"
    assert reasons["fixture-run-rejected"] == "attempt_id already present"
    assert isolated_attempt_state.read_bytes() == before


def test_unrelated_existing_record_is_not_corrected(
    isolated_attempt_state: Path,
) -> None:
    """A duplicate id that is not the legacy shape of this run is skipped."""
    legacy = _legacy_record()
    legacy["attempt_id"] = "benchmark:unrelated-run-9"
    legacy["benchmark_run"]["attempt_id"] = "benchmark:unrelated-run-9"
    legacy["benchmark_run"]["stages"][0]["run_id"] = "unrelated-run-9"
    append_attempt(legacy, isolated_attempt_state)

    summary = import_benchmark_evidence(SIDECAR)

    # The unrelated legacy row's recovered run id matches no CSV run, so it is
    # neither corrected nor re-imported; both valid rows import fresh.
    assert summary.imported == 2
    assert summary.skipped == 1
    ids = [r["attempt_id"] for r in read_attempts(isolated_attempt_state)]
    assert ids == [
        "benchmark:unrelated-run-9",
        "benchmark:fixture-run-accepted",
        "benchmark:fixture-run-rejected",
    ]


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
