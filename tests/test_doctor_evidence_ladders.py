"""Focused P5-2 CLI wiring tests for ``evidence ladders --derive``.

Every test invokes the real argparse parser and ``main`` in-process against
scratch data. No real router state or provider is touched.
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


def test_evidence_ladders_subcommand_is_registered() -> None:
    """Running ``evidence ladders --help`` exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        main(["evidence", "ladders", "--help"])
    assert excinfo.value.code == 0


def test_evidence_ladders_requires_derive() -> None:
    """Running ``evidence ladders`` without --derive exits 2 (argparse)."""
    with pytest.raises(SystemExit) as excinfo:
        main(["evidence", "ladders"])
    assert excinfo.value.code == 2


def test_evidence_ladders_derive_with_empty_ledger_text(capsys) -> None:
    """Running with an empty ledger produces valid text output and exits 0."""
    code, outerr = _invoke(
        [
            "evidence",
            "ladders",
            "--derive",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
        ],
        capsys,
    )
    assert code == 0
    out = outerr.out
    assert "Evidence ladders derived and written to" in out
    assert "Diff against benchmark" in out


def test_evidence_ladders_derive_with_empty_ledger_json(capsys) -> None:
    """Running with an empty ledger and --json produces valid JSON output."""
    code, outerr = _invoke(
        [
            "evidence",
            "ladders",
            "--derive",
            "--json",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
        ],
        capsys,
    )
    assert code == 0
    data = json.loads(outerr.out)
    assert "derived_ladders" in data
    assert "written_to" in data
    assert "benchmark_diffs" in data
    assert "crews_diffs" in data
    assert data["derived_ladders"]["schema_version"] == "derived-ladder/1"


def test_evidence_ladders_derive_with_output_dir(capsys, tmp_path) -> None:
    """--output-dir is accepted and files land in the specified directory."""
    out_dir = tmp_path / "ladders"
    code, outerr = _invoke(
        [
            "evidence",
            "ladders",
            "--derive",
            "--json",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
            "--output-dir",
            str(out_dir),
        ],
        capsys,
    )
    assert code == 0
    data = json.loads(outerr.out)
    written_path = data["written_to"]
    assert str(out_dir) in written_path
    # Verify the written file is valid JSON
    written_file = Path(written_path)
    assert written_file.exists()
    contents = json.loads(written_file.read_text(encoding="utf-8"))
    assert contents["schema_version"] == "derived-ladder/1"


def test_evidence_ladders_derive_with_invalid_catalog(capsys, tmp_path) -> None:
    """A nonexistent catalog directory exits 3."""
    code, outerr = _invoke(
        [
            "evidence",
            "ladders",
            "--derive",
            "--catalog-dir",
            str(tmp_path / "nonexistent"),
        ],
        capsys,
    )
    assert code == 3
    assert "evidence ladders:" in outerr.err


def test_evidence_ladders_derive_with_nonexistent_output_dir(capsys, tmp_path) -> None:
    """A nonexistent output directory is created."""
    out_dir = tmp_path / "does-not-exist-yet" / "nested"
    code, outerr = _invoke(
        [
            "evidence",
            "ladders",
            "--derive",
            "--json",
            "--catalog-dir",
            str(REPO_CONFIG_DIR),
            "--output-dir",
            str(out_dir),
        ],
        capsys,
    )
    assert code == 0
    data = json.loads(outerr.out)
    written_path = data["written_to"]
    written_file = Path(written_path)
    assert written_file.exists()
