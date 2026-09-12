"""Tests for scripts/harvest_failed_packets.py (Phase 5 Packet P5-3)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lee_llm_router.staffing.ledger import append_attempt
from scripts.harvest_failed_packets import (
    extract_oracle_line,
    extract_owned_paths_lines,
    is_production_failure,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "staffing"
BASE_ROUTER_RUN = json.loads(
    (FIXTURE_DIR / "attempt-record-router-run-unavailable.json").read_text(
        encoding="utf-8"
    )
)
BENCHMARK_RUN = json.loads(
    (FIXTURE_DIR / "attempt-record-benchmark-run.json").read_text(encoding="utf-8")
)

DEFAULT_PACKET_ID = (
    "sha256:0000000000000000000000000000000000000000000000000000000000000001"
)


def _make_router_run(
    *,
    attempt_id: str = "run-001",
    packet_id: str = DEFAULT_PACKET_ID,
    captured_at: str = "2026-09-12T10:00:00Z",
    verdict: str = "fail",
    failure_class: str | None = "spec_rejected",
    route_id: str = "test-route-a",
    oracle_cmd: str | None = "python3 -m unittest -q",
    class_key: str = "impl/deterministic/none/s/python",
    role: str = "impl",
    oracle_type: str = "deterministic",
    domain_tags: list[str] | None = None,
    size_band: str = "s",
    language: str = "python",
) -> dict:
    rec = json.loads(json.dumps(BASE_ROUTER_RUN))
    rec["attempt_id"] = attempt_id
    rec["packet_id"] = packet_id
    rec["captured_at"] = captured_at
    rec["verdict"] = verdict
    rec["failure_class"] = failure_class
    rec["oracle_cmd"] = oracle_cmd
    rec["class_record"] = {
        "class_key": class_key,
        "role": role,
        "oracle_type": oracle_type,
        "domain_tags": domain_tags or [],
        "size_band": size_band,
        "language": language,
    }
    rec["router_event"]["route_id"] = route_id
    rec["router_event"]["ts"] = captured_at
    return rec


@pytest.fixture
def sample_packet(tmp_path: Path) -> tuple[Path, str, str]:
    content = (
        "# Packet Sample-1 — test packet\n\n"
        "- Kind: `impl`\n"
        "- Owned paths: `src/sample.py`, `tests/test_sample.py`\n"
        "- Oracle: `python3 -m unittest tests/test_sample.py`\n"
    )
    packet_file = tmp_path / "packets" / "Sample-1.md"
    packet_file.parent.mkdir(parents=True, exist_ok=True)
    packet_file.write_text(content, encoding="utf-8")
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return packet_file, sha, content


def test_is_production_failure_unit() -> None:
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)

    # Exclude non-router_run
    bench = dict(BENCHMARK_RUN)
    assert not is_production_failure(bench, cutoff, now)

    agent_orch = {
        "record_kind": "agent_orch_attempt",
        "captured_at": "2026-09-10T00:00:00Z",
        "verdict": "fail",
    }
    assert not is_production_failure(agent_orch, cutoff, now)

    # Outside window
    old_run = {
        "record_kind": "router_run",
        "captured_at": "2026-08-01T00:00:00Z",
        "verdict": "fail",
    }
    assert not is_production_failure(old_run, cutoff, now)

    # Inside window, fail verdict string
    valid_fail = {
        "record_kind": "router_run",
        "captured_at": "2026-09-10T00:00:00Z",
        "verdict": "fail",
    }
    assert is_production_failure(valid_fail, cutoff, now)

    # Inside window, fail verdict dict shape
    dict_fail = {
        "record_kind": "router_run",
        "captured_at": "2026-09-10T00:00:00Z",
        "verdict": {"status": "fail"},
    }
    assert is_production_failure(dict_fail, cutoff, now)

    # Inside window, capability_rejected failure_class even if verdict is unverified
    cap_rejected = {
        "record_kind": "router_run",
        "captured_at": "2026-09-10T00:00:00Z",
        "verdict": "unverified",
        "failure_class": "capability_rejected",
    }
    assert is_production_failure(cap_rejected, cutoff, now)

    # Success pass is not a failure
    pass_run = {
        "record_kind": "router_run",
        "captured_at": "2026-09-10T00:00:00Z",
        "verdict": "pass",
        "failure_class": None,
    }
    assert not is_production_failure(pass_run, cutoff, now)


def test_extraction_helpers() -> None:
    text = (
        "# Packet P\n\n"
        "- Kind: `impl`\n"
        "- Owned paths: `file1.py` (new),\n"
        "  `file2.py` (new)\n"
        "- Oracle: `pytest -q tests/test.py`\n"
    )
    owned = extract_owned_paths_lines(text)
    assert owned == ["- Owned paths: `file1.py` (new),", "  `file2.py` (new)"]
    oracle = extract_oracle_line(text)
    assert oracle == "- Oracle: `pytest -q tests/test.py`"

    # Test ## Oracle format
    text2 = "## Oracle\n\npytest -q tests/test.py\n"
    assert extract_oracle_line(text2) == "pytest -q tests/test.py"


def test_production_filtering_and_time_window(
    tmp_path: Path, sample_packet: tuple[Path, str, str]
) -> None:
    packet_file, sha, _ = sample_packet
    ledger_path = tmp_path / "attempts.jsonl"

    # 1. Valid router run inside window
    r1 = _make_router_run(
        attempt_id="r1",
        packet_id=f"sha256:{sha}",
        captured_at="2026-09-10T10:00:00Z",
        verdict="fail",
    )
    # 2. Router run older than 30 days
    r_old = _make_router_run(
        attempt_id="r_old",
        packet_id=f"sha256:{sha}",
        captured_at="2026-07-01T10:00:00Z",
        verdict="fail",
    )
    # 3. Router run with capability_rejected (verdict unverified, so oracle_cmd is None)
    r_cap = _make_router_run(
        attempt_id="r_cap",
        packet_id=f"sha256:{sha}",
        captured_at="2026-09-11T10:00:00Z",
        verdict="unverified",
        failure_class="capability_rejected",
        oracle_cmd=None,
    )
    # 4. Benchmark run (should be excluded)
    b_run = json.loads(json.dumps(BENCHMARK_RUN))

    for rec in [r1, r_old, r_cap, b_run]:
        append_attempt(rec, path=ledger_path)

    packet_dir = str(packet_file.parent)

    # Run harvest with --now 2026-09-12 and --days 30
    res = subprocess.run(
        [
            "python3",
            "scripts/harvest_failed_packets.py",
            "--ledger",
            str(ledger_path),
            "--packet-dirs",
            packet_dir,
            "--now",
            "2026-09-12",
            "--days",
            "30",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    groups = json.loads(res.stdout)
    assert len(groups) == 1
    g = groups[0]
    assert g["packet_id"] == f"sha256:{sha}"
    assert g["attempt_count"] == 2  # r1 and r_cap only
    assert "r1" in g["attempt_ids"]
    assert "spec_rejected" in g["failure_classes"]
    assert "capability_rejected" in g["failure_classes"]


def test_hash_resolution_and_unresolved(
    tmp_path: Path, sample_packet: tuple[Path, str, str]
) -> None:
    packet_file, sha, _ = sample_packet
    ledger_path = tmp_path / "attempts.jsonl"

    # Resolved attempt
    r1 = _make_router_run(
        attempt_id="r1",
        packet_id=f"sha256:{sha}",
        captured_at="2026-09-10T10:00:00Z",
    )
    # Unresolved attempt
    unresolved_sha = "f" * 64
    r2 = _make_router_run(
        attempt_id="r2",
        packet_id=f"sha256:{unresolved_sha}",
        captured_at="2026-09-10T11:00:00Z",
    )

    append_attempt(r1, path=ledger_path)
    append_attempt(r2, path=ledger_path)

    res = subprocess.run(
        [
            "python3",
            "scripts/harvest_failed_packets.py",
            "--ledger",
            str(ledger_path),
            "--packet-dirs",
            str(packet_file.parent),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = res.stdout
    assert str(packet_file) in stdout
    unresolved_msg = (
        "briefing: unresolved (no file under --packet-dirs hashes to this id)"
    )
    assert unresolved_msg in stdout


def test_skeleton_emission(
    tmp_path: Path, sample_packet: tuple[Path, str, str]
) -> None:
    packet_file, sha, _content = sample_packet
    ledger_path = tmp_path / "attempts.jsonl"

    r1 = _make_router_run(
        attempt_id="r1",
        packet_id=f"sha256:{sha}",
        captured_at="2026-09-10T10:00:00Z",
        route_id="route-test-1",
        failure_class="spec_rejected",
        oracle_cmd="python3 -m unittest tests/test_sample.py",
        class_key="impl/deterministic/none/s/python",
        role="impl",
    )
    append_attempt(r1, path=ledger_path)

    emit_dir = tmp_path / "harvested"
    subprocess.run(
        [
            "python3",
            "scripts/harvest_failed_packets.py",
            "--ledger",
            str(ledger_path),
            "--packet-dirs",
            str(packet_file.parent),
            "--emit",
            str(emit_dir),
        ],
        check=True,
    )

    harvest_id = f"h-{sha[:12]}-impl-deterministic-none-s-python"
    v1_dir = emit_dir / harvest_id / "v1"
    assert v1_dir.is_dir()

    # Verify briefing.md is byte-for-byte identical
    briefing_file = v1_dir / "briefing.md"
    assert briefing_file.read_bytes() == packet_file.read_bytes()

    # Verify oracle.txt is non-empty and equals oracle_cmd
    oracle_file = v1_dir / "oracle.txt"
    expected_oracle = "python3 -m unittest tests/test_sample.py"
    assert oracle_file.read_text(encoding="utf-8").strip() == expected_oracle

    # Verify manifest.json
    manifest = json.loads((v1_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "pilot-packet/1"
    assert manifest["task_id"] == harvest_id
    assert manifest["task_version"] == "v1"
    assert manifest["role"] == "implementation"
    assert manifest["difficulty_intent"] == "production-failure"
    assert manifest["design_target_minutes"] is None
    assert manifest["origin_kind"] == "harvested-production-failure"
    assert manifest["origin_ref"] == f"lee-llm-router attempt ledger sha256:{sha}"
    assert manifest["origin"]["repository_label"] == "lee-llm-router"
    assert manifest["origin"]["observed_files"] == [
        "- Owned paths: `src/sample.py`, `tests/test_sample.py`"
    ]
    assert manifest["visible_inputs"] == [{"path": "briefing.md", "sha256": sha}]
    assert (
        manifest["output_contract"]["required"]
        == "- Oracle: `python3 -m unittest tests/test_sample.py`"
    )
    assert manifest["output_contract"]["verification"] == expected_oracle
    assert manifest["output_contract"]["evaluation_schema"] == "pilot-evaluation/1"
    assert manifest["output_contract"]["acceptance_is_not_model_ranking"] is True
    assert manifest["class"]["class_key"] == "impl/deterministic/none/s/python"
    assert manifest["harvest"]["packet_id"] == f"sha256:{sha}"
    assert manifest["harvest"]["attempt_ids"] == ["r1"]
    assert manifest["harvest"]["routes"] == ["route-test-1"]
    assert manifest["harvest"]["failure_classes"] == ["spec_rejected"]


def test_missing_or_unreadable_ledger_exits_2(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.jsonl"
    res = subprocess.run(
        [
            "python3",
            "scripts/harvest_failed_packets.py",
            "--ledger",
            str(non_existent),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2
    assert "cannot read ledger" in res.stderr
