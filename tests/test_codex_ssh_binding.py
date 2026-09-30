"""Governed Codex binding under interactive and SSH daemon PATHs."""

from __future__ import annotations

from pathlib import Path

import pytest

import lee_llm_router.staffing.run as run
from lee_llm_router.staffing.catalog import Route
from lee_llm_router.staffing.run import RunDispatchError, build_dispatch_command


@pytest.fixture
def route():
    return Route(
        route_id="exact-sol61",
        model="gpt-6.1-sol",
        effort="medium",
        harness="codex",
        channel="openai-sub",
        dispatch_template="codex exec {prompt}",
        usage_capture="codex_jsonl",
        status="active",
    )


@pytest.fixture
def installed(tmp_path, monkeypatch):
    monkeypatch.delenv("LEE_LLM_ROUTER_CODEX_BINARY", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    p = tmp_path / ".local/bin/codex"
    p.parent.mkdir(parents=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o755)
    return p


def test_normal_path_keeps_bare_command(route, installed, monkeypatch):
    monkeypatch.setattr(run.shutil, "which", lambda binary: "/usr/local/bin/codex")
    assert build_dispatch_command(route)[0] == "codex"


def test_daemon_path_uses_actual_user_install(route, installed, monkeypatch):
    monkeypatch.setattr(run.shutil, "which", lambda binary: None)
    argv = build_dispatch_command(route)
    assert argv[0] == str(installed)
    assert argv[1:5] == ["exec", "--json", "-s", "workspace-write"]
    assert argv[argv.index("--model") + 1] == "gpt-6.1-sol"
    assert "model_reasoning_effort=medium" in argv
    assert not any("bypass" in arg for arg in argv)


@pytest.mark.parametrize(
    "mode", ["missing", "non-executable", "directory", "broken-symlink"]
)
def test_missing_real_cli_fails_clearly(route, installed, monkeypatch, mode):
    monkeypatch.setattr(run.shutil, "which", lambda binary: None)
    if mode == "non-executable":
        installed.chmod(0o644)
    else:
        installed.unlink()
        if mode == "directory":
            installed.mkdir()
        if mode == "broken-symlink":
            installed.symlink_to(installed.parent / "absent")
    with pytest.raises(RunDispatchError, match="Codex CLI binary not found"):
        build_dispatch_command(route)


def test_existing_explicit_override_wins(route, installed, monkeypatch):
    monkeypatch.setenv("LEE_LLM_ROUTER_CODEX_BINARY", "/opt/exact/codex")
    monkeypatch.setattr(run.shutil, "which", lambda binary: "/usr/bin/codex")
    assert build_dispatch_command(route)[0] == "/opt/exact/codex"


def test_user_symlink_resolves_real_package_for_adjacent_helper(
    route, installed, monkeypatch, tmp_path
):
    monkeypatch.setattr(run.shutil, "which", lambda binary: None)
    real = tmp_path / "package" / "bin" / "codex"
    real.parent.mkdir(parents=True)
    installed.rename(real)
    installed.symlink_to(real)
    assert build_dispatch_command(route)[0] == str(real)
