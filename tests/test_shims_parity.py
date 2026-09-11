"""Tests for harness shims parity across all four targets (Sprint 4 P32, P2-8).

The generated shims are resolve-only: ``/crew auto`` and ``/crew NAME`` run
``lee-llm-router staff``, display the returned block, never dispatch or
invoke a provider, and only offer (never execute) a ``run`` command. These
tests execute the exact staff commands each rendered shim carries, for every
harness, and prove parity of the returned blocks modulo harness-irrelevant
facts, that no event is written, and that nothing is dispatched.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from lee_llm_router import shims

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "config" / "staffing"
AVAILABILITY_FILE = REPO_ROOT / "tests" / "fixtures" / "availability" / "healthy.json"
AT = "2026-10-01"
CLASS_KEY = "impl/deterministic/none/s/python"
ROLE = "impl"
CREW = "luna-sol"


def _extract_staff_lines(body: str, harness: str) -> tuple[str, str]:
    """Extract the exact auto and crew staff command lines from a shim body."""
    auto_lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip()
        == ("lee-llm-router staff --mode auto --role <role> --class <class>")
    ]
    crew_lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip() == "lee-llm-router staff --mode crew <name>"
    ]
    assert (
        len(auto_lines) == 1
    ), f"Expected exactly one auto staff line for {harness}, got {auto_lines}"
    assert (
        len(crew_lines) == 1
    ), f"Expected exactly one crew staff line for {harness}, got {crew_lines}"
    return auto_lines[0], crew_lines[0]


def _run_staff(argv: list[str], events_file: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "LEE_LLM_ROUTER_EVENTS_FILE": str(events_file),
            "LEE_LLM_ROUTER_ATTEMPTS_FILE": str(events_file.with_suffix(".attempts")),
        }
    )
    cmd = [sys.executable, "-m", "lee_llm_router.doctor", *argv]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _substitute(line: str) -> list[str]:
    """Fill the shim command placeholders the way the harness would."""
    return shlex.split(
        line.replace("<role>", ROLE)
        .replace("<class>", CLASS_KEY)
        .replace("<name>", CREW)
    )


def _staff_args(
    substituted: list[str], events_file: Path, *, json_mode: bool
) -> list[str]:
    argv = [
        *substituted[1:],
        "--at",
        AT,
        "--availability-file",
        str(AVAILABILITY_FILE),
        "--catalog-dir",
        str(CATALOG_DIR),
    ]
    if json_mode:
        argv.append("--json")
    return argv


def test_four_harness_staff_parity_subprocess(tmp_path, monkeypatch):
    """Run each shim's auto and crew staff commands; parity + no event writes."""
    tmp_home = tmp_path / "home"
    tmp_project = tmp_path / "project"
    tmp_home.mkdir(parents=True, exist_ok=True)
    tmp_project.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(shims.ENV_SHIM_HOME, str(tmp_home))

    targets = shims.get_targets(project=tmp_project, home=tmp_home)
    assert len(targets) == 4

    outputs: dict[str, dict[str, str]] = {}
    events_files: dict[str, Path] = {}

    for target in targets:
        auto_line, crew_line = _extract_staff_lines(target.body, target.harness)
        events_file = tmp_path / f"events-{target.harness}.jsonl"
        events_file.touch()

        for label, line, mode in (
            ("auto", auto_line, "json"),
            ("auto-text", auto_line, "text"),
            ("crew", crew_line, "text"),
        ):
            substituted = _substitute(line)
            assert substituted[0] == "lee-llm-router"
            assert substituted[1] == "staff"
            argv = _staff_args(substituted, events_file, json_mode=(mode == "json"))
            proc = _run_staff(argv, events_file)
            assert proc.returncode == 0, (
                f"staff command for {target.harness} ({label}) failed with exit "
                f"{proc.returncode}:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
            )
            outputs.setdefault(label, {})[target.harness] = proc.stdout

        # Nothing dispatched: no provider invocation happened and no event
        # was written for this harness's commands.
        assert (
            events_file.read_text(encoding="utf-8") == ""
        ), f"staff commands for {target.harness} wrote events"
        events_files[target.harness] = events_file

    # The four harnesses produce equivalent blocks: every output for a form
    # is byte-identical modulo harness-irrelevant facts (there are none —
    # staff commands carry no harness tag), so outputs are byte-identical.
    for label, per_harness in outputs.items():
        values = list(per_harness.values())
        assert len(values) == 4
        for i in range(1, len(values)):
            assert values[i] == values[0], (
                f"{label} output for harness {targets[i].harness} differed from "
                f"{targets[0].harness}"
            )

    # The auto JSON output is the structured staffing block: the block facts
    # match the text block modulo whitespace/harness-irrelevant facts.
    auto_payloads = {h: json.loads(out) for h, out in outputs["auto"].items()}
    for i in range(1, len(auto_payloads)):
        harness = targets[i].harness
        assert auto_payloads[harness] == auto_payloads[targets[0].harness]
    first = auto_payloads[targets[0].harness]
    assert first["mode"] == "auto"
    assert first["role"] == ROLE
    assert first["class_key"] == CLASS_KEY
    assert first["selected_route"], "auto block must name a selected route"

    # The crew text output is the saved crew block.
    crew_first = outputs["crew"][targets[0].harness]
    assert crew_first.startswith(f"staff crew {CREW} ")


def test_shims_rendered_body_offers_run_never_executes(tmp_path, monkeypatch):
    """Every rendered body: no provider command, no dispatch, run offered only."""
    tmp_home = tmp_path / "home"
    tmp_project = tmp_path / "project"
    tmp_home.mkdir(parents=True, exist_ok=True)
    tmp_project.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(shims.ENV_SHIM_HOME, str(tmp_home))

    targets = shims.get_targets(project=tmp_project, home=tmp_home)
    assert len(targets) == 4

    forbidden_substrings = (
        "lee-llm-router resolve",
        "lee-llm-router dispatch",
        "agy ",
        "codex exec",
        "claude -p",
        "opencode run",
        "omp -p",
    )
    offer_lines = (
        "lee-llm-router run --role <role> --class <class> --packet <path>",
        "lee-llm-router run --route <route-id> --role <role> --class <class> "
        "--packet <path>",
    )

    for target in targets:
        body = target.body

        for forbidden in forbidden_substrings:
            assert forbidden not in body, (
                f"Rendered body for harness {target.harness!r} contains "
                f"forbidden {forbidden!r}"
            )

        # Both run offer lines appear exactly once each.
        for offer in offer_lines:
            assert body.count(offer) == 1, (
                f"Rendered body for harness {target.harness!r} must offer "
                f"{offer!r} exactly once"
            )

        # The run commands are offered, not executed: no line instructs the
        # harness to run them (they are bare offer lines after an explicit
        # offer/do-not-execute sentence).
        assert "offer — do not execute — the dispatch command" in body

        # staff commands for both forms appear exactly once each.
        assert (
            body.count("lee-llm-router staff --mode auto --role <role> --class <class>")
            == 1
        )
        assert body.count("lee-llm-router staff --mode crew <name>") == 1
