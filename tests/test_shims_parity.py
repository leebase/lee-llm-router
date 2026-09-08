"""Tests for harness shims parity across all four targets (Sprint 4 P32)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from lee_llm_router import shims


def test_four_harness_parity_resolve_subprocess(tmp_path, monkeypatch):
    """Render all four shims, extract resolve line, run as subprocess, assert parity."""
    tmp_home = tmp_path / "home"
    tmp_project = tmp_path / "project"
    tmp_home.mkdir(parents=True, exist_ok=True)
    tmp_project.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(shims.ENV_SHIM_HOME, str(tmp_home))

    repo_root = Path(__file__).resolve().parent.parent
    crews_file = repo_root / "tests" / "fixtures" / "crews.yaml"
    availability_file = (
        repo_root / "tests" / "fixtures" / "availability" / "healthy.json"
    )
    events_file = tmp_path / "events.jsonl"

    targets = shims.get_targets(project=tmp_project, home=tmp_home)
    assert len(targets) == 4

    crew = "test-flex"
    role = "envision"

    outputs: list[str] = []
    target_harnesses: list[str] = []

    for target in targets:
        target_harnesses.append(target.harness)

        # Extract the exact line matching:
        # 'lee-llm-router resolve $ARGUMENTS --mode flex --harness <tag> --json'
        matching_lines = [
            line.strip()
            for line in target.body.splitlines()
            if line.strip()
            == (
                f"lee-llm-router resolve $ARGUMENTS --mode flex "
                f"--harness {target.harness} --json"
            )
        ]
        assert len(matching_lines) == 1, (
            f"Expected exactly one resolve line in body for {target.harness}, "
            f"found: {matching_lines}"
        )
        resolve_line = matching_lines[0]

        # Substitute $ARGUMENTS with <crew> <role> the way the harness would
        substituted_line = resolve_line.replace("$ARGUMENTS", f"{crew} {role}")

        # Split into tokens and ensure command begins with lee-llm-router
        cmd_tokens = shlex.split(substituted_line)
        assert cmd_tokens[0] == "lee-llm-router"
        assert cmd_tokens[1] == "resolve"

        # Build subprocess command running python -m lee_llm_router.doctor
        # with fixture and tmp ledger appended
        sub_cmd = [
            sys.executable,
            "-m",
            "lee_llm_router.doctor",
            *cmd_tokens[1:],
            "--crews-file",
            str(crews_file),
            "--availability-file",
            str(availability_file),
            "--events-file",
            str(events_file),
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "src")

        proc = subprocess.run(
            sub_cmd,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, (
            f"Command {sub_cmd} for harness {target.harness} failed with exit code "
            f"{proc.returncode}:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        outputs.append(proc.stdout)

    assert len(outputs) == 4

    # The four JSON outputs are byte-identical after deleting ts, harness, event_path
    cleaned_dicts = []
    for out in outputs:
        data = json.loads(out)
        data.pop("ts", None)
        data.pop("harness", None)
        data.pop("event_path", None)
        cleaned_dicts.append(data)

    for i in range(1, len(cleaned_dicts)):
        assert (
            cleaned_dicts[i] == cleaned_dicts[0]
        ), f"Cleaned JSON for {targets[i].harness} differed from {targets[0].harness}"

    cleaned_bytes = [
        json.dumps(d, indent=2, sort_keys=True).encode("utf-8") for d in cleaned_dicts
    ]
    for i in range(1, len(cleaned_bytes)):
        assert cleaned_bytes[i] == cleaned_bytes[0], (
            f"Byte-serialized JSON for {targets[i].harness} differed from "
            f"{targets[0].harness}"
        )

    # The events file holds exactly four lines whose harness values are
    # exactly {'claude-code', 'codex', 'omp', 'opencode'} and whose route_id
    # values are all equal
    assert events_file.exists(), f"Events file {events_file} does not exist"
    event_lines = [
        line.strip()
        for line in events_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert (
        len(event_lines) == 4
    ), f"Expected exactly four event records, found {len(event_lines)}"

    records = [json.loads(line) for line in event_lines]
    recorded_harnesses = {rec["harness"] for rec in records}
    assert recorded_harnesses == {"claude-code", "codex", "omp", "opencode"}

    route_ids = [rec["route_id"] for rec in records]
    assert (
        len(set(route_ids)) == 1
    ), f"Expected all route_id values to be equal, got {route_ids}"
    assert route_ids[0], "route_id must not be empty"


def test_shims_rendered_body_recommends_never_runs(tmp_path, monkeypatch):
    """Assert every rendered body contains no provider command and offers dispatch."""
    tmp_home = tmp_path / "home"
    tmp_project = tmp_path / "project"
    tmp_home.mkdir(parents=True, exist_ok=True)
    tmp_project.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(shims.ENV_SHIM_HOME, str(tmp_home))

    targets = shims.get_targets(project=tmp_project, home=tmp_home)
    assert len(targets) == 4

    forbidden_commands = ("agy", "codex exec", "claude -p", "opencode run", "omp -p")

    for target in targets:
        body = target.body

        # Provider binary names must not appear as commands in the rendered body
        for forbidden in forbidden_commands:
            assert forbidden not in body, (
                f"Rendered body for harness {target.harness!r} contains forbidden "
                f"command {forbidden!r}"
            )

        # Body contains the dispatch offer line
        expected_dispatch_line = (
            f"lee-llm-router dispatch --crew <crew> --role <role> --mode flex "
            f"--harness {target.harness} --prompt-file <path>"
        )
        assert (
            expected_dispatch_line in body
        ), f"Rendered body for harness {target.harness!r} missing dispatch offer line"
