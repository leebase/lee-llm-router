"""Focused P4-10 ``route show`` CLI wiring tests.

Every test invokes the real argparse parser and ``main`` in-process against
the repo's committed catalog. No provider is prompted and no real router
state is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lee_llm_router.doctor import main

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
ACTIVE_ROUTE = "codex-gpt-5-6-sol-low-openai-sub"
UNKNOWN_ROUTE = "nonexistent-route-id"


def _invoke(argv, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    return excinfo.value.code, capsys.readouterr()


def _base_argv(*extra):
    return [
        "route",
        "show",
        ACTIVE_ROUTE,
        "--catalog-dir",
        str(REPO_CONFIG_DIR),
        *extra,
    ]


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def test_route_subcommand_is_registered() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["route", "--help"])
    assert excinfo.value.code == 0


def test_route_show_subcommand_is_registered() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["route", "show", "--help"])
    assert excinfo.value.code == 0


def test_route_no_subcommand_exits_3(capsys) -> None:
    code, outerr = _invoke(["route"], capsys)
    assert code == 3
    assert "subcommand required" in outerr.err


def test_route_show_requires_route_id() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["route", "show"])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# Successful disclosure: text and JSON
# ---------------------------------------------------------------------------


def test_route_show_json_discloses_full_record(capsys) -> None:
    code, outerr = _invoke(_base_argv("--json"), capsys)
    assert code == 0
    out, err = outerr
    data = json.loads(out)
    assert data["route_id"] == ACTIVE_ROUTE
    assert data["model"] == "gpt-5.6-sol"
    assert data["effort"] == "low"
    assert data["harness"] == "codex"
    assert data["channel"] == "openai-sub"
    assert isinstance(data["dispatch_template"], str) and data["dispatch_template"]
    assert "usage_capture" in data
    assert data["status"] == "active"
    assert data["proof_status"] in ("proven", "unproven")
    assert err == ""


def test_route_show_text_output_contains_every_field(capsys) -> None:
    code, outerr = _invoke(_base_argv(), capsys)
    assert code == 0
    out, err = outerr
    for field in (
        "model:",
        "effort:",
        "harness:",
        "channel:",
        "dispatch_template:",
        "usage_capture:",
        "status:",
        "proof_status:",
    ):
        assert field in out
    assert err == ""


# ---------------------------------------------------------------------------
# Unknown route id -> exit 3
# ---------------------------------------------------------------------------


def test_unknown_route_id_exits_3(capsys) -> None:
    argv = _base_argv()
    argv[2] = UNKNOWN_ROUTE
    code, outerr = _invoke(argv, capsys)
    assert code == 3
    out, err = outerr
    assert out == ""
    assert "route show:" in err
    assert UNKNOWN_ROUTE in err


# ---------------------------------------------------------------------------
# Invalid catalog dir -> exit 3
# ---------------------------------------------------------------------------


def test_invalid_catalog_dir_exits_3(capsys, tmp_path) -> None:
    code, outerr = _invoke(
        ["route", "show", ACTIVE_ROUTE, "--catalog-dir", str(tmp_path)], capsys
    )
    assert code == 3
    out, err = outerr
    assert out == ""
    assert "route show:" in err
