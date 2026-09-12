"""Focused P1-7 benchmark-v6 evidence import tests.

All state is redirected through the app-specific attempt-ledger environment
override.  Fixtures are static CSV/JSON only; no provider boundary exists in
this test module.  One regression starts real OS processes (``fork``) that
call the real public import function against one shared ledger; every other
test runs in-process.

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
import multiprocessing as mp
import sys
from collections import Counter
from pathlib import Path

import pytest

from lee_llm_router.doctor import main
from lee_llm_router.staffing.import_evidence import (
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_USAGE_SOURCE,
    ImportIssue,
    import_benchmark_evidence,
)
from lee_llm_router.staffing.ledger import (
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    append_attempt,
    read_attempts,
)
from lee_llm_router.staffing.rollup import build_rollup

FIXTURES = Path(__file__).parent / "fixtures" / "staffing"
SIDECAR = FIXTURES / "benchmark-v6-sidecar.fixture"
REAL_V6_SIDECAR = Path(
    "/home/lee/projects/ai-workforce-benchmark/exports/"
    "staffing-evidence-v6-20260909.json"
)
EMPTY_EFFORT_RUN_IDS = (
    "deepseek-flash-01",
    "glm-flash-01",
    "monthly-deepseek-flash-01",
    "monthly-glm-flash-01",
)


@pytest.fixture(autouse=True)
def isolated_attempt_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use only the named scratch override, never a user state directory."""
    ledger = tmp_path / "state" / "benchmark-attempts.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    monkeypatch.delenv(ATTEMPTS_STATE_ROOT_ENV_VAR, raising=False)
    return ledger


def _sidecar_sha256() -> str:
    return hashlib.sha256(SIDECAR.read_bytes()).hexdigest()


def _legacy_record(run_id: str = "fixture-run-accepted") -> dict:
    """A pre-repair legacy crew-run-shaped record for one source run.

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
    record["attempt_id"] = f"benchmark:{run_id}"
    record["benchmark_run"]["attempt_id"] = f"benchmark:{run_id}"
    record["benchmark_run"]["stages"][0]["run_id"] = run_id
    record["captured_at"] = "2026-09-09T12:05:00Z"
    return record


def _empty_effort_sources(tmp_path: Path) -> Path:
    """A v6 sidecar/CSV pair in the real shape with empty-string effort.

    The authoritative export records some adapters' worker effort as the
    empty string: one measured row and one unknown-usage row mirror that
    exactly.
    """
    csv_path = tmp_path / "empty-effort-runs.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "run_id,task_key,model,harness,effort,acceptance,captured_at,"
        "usage_status,usage_input_tokens,usage_output_tokens,"
        "usage_cached_input_tokens,usage_reasoning_tokens,usage_total_tokens\n"
        "empty-effort-measured,router-change@v1,scratch-deepseek,opencode,,"
        "accepted,2026-09-09T12:05:00Z,known,10,20,0,,30\n"
        "empty-effort-unknown,router-change@v1,scratch-deepseek,opencode,,"
        "accepted,2026-09-09T13:05:00Z,unknown,11,22,0,,33\n",
        encoding="utf-8",
    )
    sidecar = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "generated_at": "2026-09-09T15:00:00Z",
        "source_csv": {
            "path": str(csv_path),
            "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        },
        "rows": [
            {
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
                    "model": "scratch-deepseek",
                    "model_family": "scratch-family",
                    "harness": "opencode",
                    "effort": "",
                },
                "run_ids": ["empty-effort-measured", "empty-effort-unknown"],
                "run_usage": [
                    {
                        "run_id": "empty-effort-measured",
                        "usage_input_tokens": 10,
                        "usage_output_tokens": 20,
                        "usage_cached_input_tokens": 0,
                        "usage_reasoning_tokens": None,
                        "usage_total_tokens": 30,
                    },
                    {
                        "run_id": "empty-effort-unknown",
                        "usage_input_tokens": 11,
                        "usage_output_tokens": 22,
                        "usage_cached_input_tokens": 0,
                        "usage_reasoning_tokens": None,
                        "usage_total_tokens": 33,
                    },
                ],
            }
        ],
    }
    sidecar_path = tmp_path / "empty-effort-sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    return sidecar_path


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
            "sha256": (  # noqa: E501
                "7d8201137cfb98c02f8fa43151633376eede0044d589e5ed307ec4ca91a97227"
            ),
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


def test_sidecar_empty_effort_is_preserved_as_canonical_null(
    isolated_attempt_state: Path,
) -> None:
    """Real-shape blocker: measured rows with source effort "" import truthfully.

    The authoritative v6 sidecar and CSV record some adapters' worker effort
    as the empty string. The canonical crewWorker schema admits only a
    non-empty string or null, so the empty source effort is preserved as
    null and the exact raw representation is disclosed in provenance — the
    row is neither rejected nor given a substituted value.
    """
    sidecar = _empty_effort_sources(Path(isolated_attempt_state).parent)
    summary = import_benchmark_evidence(sidecar)

    assert summary.imported == 1
    assert summary.issues == (
        ImportIssue(
            3,
            "empty-effort-unknown",
            "usage_status 'unknown' is not provider-reported usage",
        ),
    )
    (record,) = read_attempts(isolated_attempt_state)
    assert record["attempt_id"] == "benchmark:empty-effort-measured"
    assert record["benchmark_run"]["worker"] == {
        "model": "scratch-deepseek",
        "harness": "opencode",
        "effort": None,
        "model_family": "scratch-family",
    }
    assert record["usage"]["input_tokens"] == 10
    notes = record["provenance"]["notes"]
    assert any(
        "Source worker effort is the empty string in the v6 sidecar and " "CSV" in note
        for note in notes
    )


def test_empty_effort_legacy_row_is_corrected_and_idempotent(
    isolated_attempt_state: Path,
) -> None:
    """The empty-effort correction is deterministic and appended once."""
    run_id = "empty-effort-measured"
    append_attempt(_legacy_record(run_id), isolated_attempt_state)
    before = isolated_attempt_state.read_bytes()

    summary = import_benchmark_evidence(
        _empty_effort_sources(Path(isolated_attempt_state).parent)
    )

    assert summary.imported == 1
    lines = isolated_attempt_state.read_bytes().splitlines(keepends=True)
    assert lines[0] == before  # legacy line retained byte for byte
    assert len(lines) == 2
    legacy, correction = read_attempts(isolated_attempt_state)
    assert legacy["attempt_id"] == f"benchmark:{run_id}"
    assert correction["attempt_id"] == f"benchmark:v6:{run_id}"
    assert correction["benchmark_run"]["worker"]["effort"] is None

    after_first = isolated_attempt_state.read_bytes()
    second = import_benchmark_evidence(
        _empty_effort_sources(Path(isolated_attempt_state).parent)
    )
    assert second.imported == 0
    assert [issue.reason for issue in second.issues if issue.run_id == run_id] == [
        "correction already present"
    ]
    assert isolated_attempt_state.read_bytes() == after_first


def test_rollup_after_correction_counts_each_source_run_once(
    isolated_attempt_state: Path,
) -> None:
    """Mixed ledger: the correction supersedes its legacy attempt in rollup."""
    append_attempt(_legacy_record(), isolated_attempt_state)
    import_benchmark_evidence(SIDECAR)

    records = read_attempts(isolated_attempt_state)
    assert [record["attempt_id"] for record in records] == [
        "benchmark:fixture-run-accepted",
        "benchmark:v6:fixture-run-accepted",
        "benchmark:fixture-run-rejected",
    ]
    groups = {group["class_key"]: group for group in build_rollup(records)["groups"]}
    accepted = groups["impl/deterministic/none/m/python"]
    rejected = groups["review/judge/data-schema/m/python"]
    # 182-style double counting would report attempts=2 for the accepted run.
    assert accepted["attempts"] == 1
    assert accepted["token_sums"]["input_tokens"] == 101
    assert rejected["attempts"] == 1
    assert rejected["token_sums"]["input_tokens"] == 44


@pytest.mark.skipif(
    not REAL_V6_SIDECAR.is_file(),
    reason="authoritative v6 staffing-evidence export not present",
)
def test_real_v6_sidecar_imports_all_93_measured_rows_idempotently(
    isolated_attempt_state: Path,
) -> None:
    """Real-shape closure: all 93 measured rows correct; 9 unknowns skip.

    Four of the measured rows carry source effort "" and must receive
    truthful corrections with canonical null effort, joining the other 89
    corrections; the second import appends nothing.
    """
    first = import_benchmark_evidence(REAL_V6_SIDECAR)

    assert first.imported == 93
    assert Counter(issue.reason for issue in first.issues) == {
        "usage_status 'unknown' is not provider-reported usage": 9
    }
    records = read_attempts(isolated_attempt_state)
    assert len(records) == 93
    by_id = {record["attempt_id"]: record for record in records}
    for run_id in EMPTY_EFFORT_RUN_IDS:
        record = by_id[f"benchmark:{run_id}"]
        assert record["benchmark_run"]["worker"]["effort"] is None
        assert any(
            "Source worker effort is the empty string" in note
            for note in record["provenance"]["notes"]
        )
    for record in records:
        assert record["usage"]["basis"] == "provider_reported"
        assert record["benchmark_run"]["schema_version"] == BENCHMARK_SCHEMA_VERSION

    before = isolated_attempt_state.read_bytes()
    second = import_benchmark_evidence(REAL_V6_SIDECAR)
    assert second.imported == 0
    assert Counter(issue.reason for issue in second.issues) == {
        "attempt_id already present": 93,
        "usage_status 'unknown' is not provider-reported usage": 9,
    }
    assert isolated_attempt_state.read_bytes() == before


@pytest.mark.skipif(
    not REAL_V6_SIDECAR.is_file(),
    reason="authoritative v6 staffing-evidence export not present on this machine",
)
def test_real_mixed_ledger_rollup_reports_93_distinct_source_runs(
    isolated_attempt_state: Path,
) -> None:
    """Legacy rows plus all 93 corrections roll up to 93 source runs once."""
    for run_id in EMPTY_EFFORT_RUN_IDS:
        append_attempt(_legacy_record(run_id), isolated_attempt_state)

    summary = import_benchmark_evidence(REAL_V6_SIDECAR)

    assert summary.imported == 93  # 89 fresh + 4 empty-effort corrections
    records = read_attempts(isolated_attempt_state)
    assert len(records) == 97  # 93 corrections + 4 retained legacy lines
    groups = build_rollup(records)["groups"]
    assert {group["class_key"]: group["attempts"] for group in groups} == {
        "impl/deterministic/authority/m/python": 8,
        "impl/deterministic/data-schema/m/python": 1,
        "impl/deterministic/persistence/m/python": 28,
        "plan/judge/authority/l/python": 11,
        "plan/judge/persistence/m/python": 15,
        "review/judge/data-schema/m/python": 13,
        "review/judge/persistence/m/python": 17,
    }
    assert sum(group["attempts"] for group in groups) == 93


# ---------------------------------------------------------------------------
# Multi-process writer-transaction regression (P3)
# ---------------------------------------------------------------------------


def _concurrent_sources(tmp_path: Path, run_ids: list[str]) -> Path:
    """A v6 sidecar/CSV pair with one valid measured row per run id."""
    csv_path = tmp_path / "conc-runs.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "run_id,task_key,model,harness,effort,acceptance,captured_at,"
        "usage_status,usage_input_tokens,usage_output_tokens,"
        "usage_cached_input_tokens,usage_reasoning_tokens,usage_total_tokens\n"
    ]
    usage = []
    for number, run_id in enumerate(run_ids):
        lines.append(
            f"{run_id},router-change@v1,scratch-worker,opencode,xhigh,"
            f"accepted,2026-09-09T12:{number:02d}:00Z,known,10,20,0,,30\n"
        )
        usage.append(
            {
                "run_id": run_id,
                "usage_input_tokens": 10,
                "usage_output_tokens": 20,
                "usage_cached_input_tokens": 0,
                "usage_reasoning_tokens": None,
                "usage_total_tokens": 30,
            }
        )
    csv_path.write_text("".join(lines), encoding="utf-8")
    sidecar = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "generated_at": "2026-09-09T15:00:00Z",
        "source_csv": {
            "path": str(csv_path),
            "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        },
        "rows": [
            {
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
                    "model": "scratch-worker",
                    "model_family": "scratch-family",
                    "harness": "opencode",
                    "effort": "xhigh",
                },
                "run_ids": list(run_ids),
                "run_usage": usage,
            }
        ],
    }
    sidecar_path = tmp_path / "conc-sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    return sidecar_path


def _benchmark_import_worker(conn, sidecar: str, ledger: str, barrier) -> None:
    """Child body: one real import_benchmark_evidence against a shared ledger."""
    try:
        barrier.wait(timeout=30)
        summary = import_benchmark_evidence(sidecar, ledger_path=ledger)
        conn.send(
            ("ok", summary.imported, [issue.reason for issue in summary.issues])
        )
    except Exception as exc:  # pragma: no cover - reported to the parent
        conn.send(("error", repr(exc)))
    finally:
        conn.close()


def test_concurrent_processes_import_benchmark_rows_exactly_once(
    tmp_path: Path,
) -> None:
    """Four OS processes race one real import against one shared ledger.

    This is the production concurrency regression (P3): every child calls the
    real public ``import_benchmark_evidence`` — no surrogate reimplements the
    read-decide-append sequence — released together by a fork barrier so the
    whole sequences genuinely overlap.  Each import must hold the per-ledger
    writer transaction across its entire read-decide-append body: the first
    process's accepted ids are then seen by every later process, so each row
    lands exactly once.  Without that transaction every process reads the
    still-empty ledger and appends every row, so this test turns red.
    """
    if sys.platform == "win32":
        pytest.skip("POSIX fork for multi-process regression")
    fork_ctx = mp.get_context("fork")
    run_ids = [f"conc-run-{index}" for index in range(4)]
    sidecar = _concurrent_sources(tmp_path, run_ids)
    ledger = tmp_path / "shared-attempts.jsonl"

    barrier = fork_ctx.Barrier(4)
    processes = []
    receivers = []
    for _ in range(4):
        parent_conn, child_conn = fork_ctx.Pipe()
        proc = fork_ctx.Process(
            target=_benchmark_import_worker,
            args=(child_conn, str(sidecar), str(ledger), barrier),
        )
        proc.start()
        child_conn.close()
        processes.append(proc)
        receivers.append(parent_conn)
    results = [conn.recv() for conn in receivers]
    for proc in processes:
        proc.join(timeout=60)
    for conn in receivers:
        conn.close()
    for proc in processes:
        assert proc.exitcode == 0, results

    statuses = [result[0] for result in results]
    assert statuses == ["ok"] * 4, results
    imported = [result[1] for result in results]
    assert sum(imported) == 4, results
    assert imported.count(0) == 3, results  # losers see every id already present
    for result in results:
        if result[0] == "ok":
            assert set(result[2]) <= {"attempt_id already present"}, results

    records = read_attempts(ledger)
    assert [record["attempt_id"] for record in records] == [
        f"benchmark:{run_id}" for run_id in run_ids
    ]
