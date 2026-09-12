"""Focused P5-1 ``evidence report`` CLI wiring tests.

Every test invokes the real argparse parser and ``main`` in-process against
scratch ledger files. No provider is prompted and no real router state is
touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lee_llm_router.doctor import main

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"


def _invoke(argv, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    return excinfo.value.code, capsys.readouterr()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def test_evidence_report_subcommand_is_registered() -> None:
    """Running ``evidence report --help`` exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        main(["evidence", "report", "--help"])
    assert excinfo.value.code == 0


def test_evidence_report_requires_month() -> None:
    """Missing --month exits 2 with argparse error."""
    with pytest.raises(SystemExit) as excinfo:
        main(["evidence", "report", "--json"])
    assert excinfo.value.code == 2


def test_evidence_report_with_empty_ledger_text(capsys) -> None:
    """Running with no ledger prints valid text report and exits 0."""
    code, outerr = _invoke(
        [
            "evidence",
            "report",
            "--month",
            "2030-01",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
        ],
        capsys,
    )
    assert code == 0
    out = outerr.out
    assert "Evidence report" in out
    assert "2030-01" in out
    assert "Recommended route changes: none" in out


def test_evidence_report_with_empty_ledger_json(capsys) -> None:
    """Running with no ledger and --json prints valid JSON and exits 0."""
    code, outerr = _invoke(
        [
            "evidence",
            "report",
            "--month",
            "2030-01",
            "--json",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
        ],
        capsys,
    )
    assert code == 0
    out = outerr.out
    data = json.loads(out)
    assert data["report_for"] == "2030-01"
    assert isinstance(data["classes"], list)
    assert isinstance(data["channels"], list)
    assert isinstance(data["route_changes"], list)
    assert isinstance(data["route_changes_not_recommended"], list)


def test_evidence_report_with_availability_file(capsys, tmp_path) -> None:
    """--availability-file is accepted and forwards to the report builder."""
    avail_file = tmp_path / "avail.json"
    avail_file.write_text(
        json.dumps(
            {
                "host": "test",
                "observed_at": "2026-09-15T12:00:00+00:00",
                "subscriptions": [],
            }
        ),
        encoding="utf-8",
    )
    code, outerr = _invoke(
        [
            "evidence",
            "report",
            "--month",
            "2030-01",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
            "--availability-file",
            str(avail_file),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    data = json.loads(outerr.out)
    assert data["report_for"] == "2030-01"


def test_evidence_report_invalid_month(capsys) -> None:
    """A badly formatted month exits 3 with an error message."""
    code, outerr = _invoke(
        [
            "evidence",
            "report",
            "--month",
            "not-a-month",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
        ],
        capsys,
    )
    assert code == 3
    assert "evidence report:" in outerr.err


def test_evidence_report_nonexistent_catalog(capsys, tmp_path) -> None:
    """A nonexistent catalog directory exits 3."""
    code, outerr = _invoke(
        [
            "evidence",
            "report",
            "--month",
            "2030-01",
            "--catalog-dir",
            str(tmp_path / "nonexistent"),
        ],
        capsys,
    )
    assert code == 3
    assert "evidence report:" in outerr.err
