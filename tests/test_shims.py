"""Tests for harness shims generation and management (Sprint 4 C3)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from lee_llm_router import shims
from lee_llm_router.doctor import main


@pytest.fixture
def shim_env(tmp_path, monkeypatch):
    """Set up temporary home and project directories for shim tests."""
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "project"
    home_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(shims.ENV_SHIM_HOME, str(home_dir))
    return home_dir, project_dir


def test_rendered_bodies_differ_only_in_harness_tag_and_marker_hash(shim_env):
    """Rendered bodies differ only in the harness tag and the marker hash."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)
    assert len(targets) == 4

    normalized_bodies = []
    for t in targets:
        b = t.body
        # Replace the harness tag using word boundaries
        b = re.sub(rf"\b{re.escape(t.harness)}\b", "TAG", b)
        # Replace the marker hash
        b = b.replace(t.marker_hash, "HASH")
        normalized_bodies.append(b)

    for i in range(1, len(normalized_bodies)):
        assert (
            normalized_bodies[i] == normalized_bodies[0]
        ), f"Body for {targets[i].harness} differed from {targets[0].harness}"


def test_rendered_body_contains_exact_resolve_and_dispatch_lines(shim_env):
    """Each rendered body contains the exact resolve command and dispatch line."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    for t in targets:
        expected_resolve_line = f"lee-llm-router resolve $ARGUMENTS --mode flex --harness {t.harness} --json"
        assert expected_resolve_line in t.body.splitlines()

        expected_dispatch_line = (
            f"lee-llm-router dispatch --crew <crew> --role <role> --mode flex "
            f"--harness {t.harness} --prompt-file <path>"
        )
        assert expected_dispatch_line in t.body

        # No provider binary name as a command
        for forbidden in ("agy", "codex exec", "claude -p", "opencode run", "omp -p"):
            assert forbidden not in t.body


def test_shims_install_dry_run(shim_env, capsys):
    """Dry-run prints four paths and four full bodies and creates nothing."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--dry-run", "--project", str(project)])
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    stdout = captured.out

    for t in targets:
        assert str(t.path) in stdout
        assert "action: create" in stdout
        assert t.body in stdout
        assert not t.path.exists()
        assert not t.path.parent.exists()


def test_shims_install_apply_creates_files_and_parents(shim_env, capsys):
    """Apply creates all four with parent directories."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--apply", "--project", str(project)])
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    for t in targets:
        assert f"create: {t.path}" in captured.out
        assert t.path.exists()
        assert t.path.read_text(encoding="utf-8") == t.content


def test_shims_install_apply_second_run_reports_unchanged(shim_env, capsys):
    """A second apply reports unchanged."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    # First apply
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--apply", "--project", str(project)])
    assert excinfo.value.code == 0
    capsys.readouterr()

    # Second apply
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--apply", "--project", str(project)])
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    for t in targets:
        assert f"unchanged: {t.path}" in captured.out


def test_shims_hand_edited_target_refused_without_force_and_overwritten_with_force(
    shim_env, capsys
):
    """Hand-edited target is refused without --force (exit 1, others still written) and overwritten with --force."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    # Install first
    with pytest.raises(SystemExit):
        main(["shims", "install", "--apply", "--project", str(project)])
    capsys.readouterr()

    # Delete other 3 targets so we can confirm they are still written on refusal
    for t in targets[1:]:
        t.path.unlink()
        assert not t.path.exists()

    # Hand edit the first target
    tampered_target = targets[0]
    tampered_target.path.write_text(
        tampered_target.path.read_text(encoding="utf-8") + "\n# user hand edit\n",
        encoding="utf-8",
    )

    # Apply without force: exit 1, tampered refused, other 3 written
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--apply", "--project", str(project)])
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert (
        f"refuse: not generated by lee-llm-router: {tampered_target.path}"
        in captured.err
    )

    # The other three are still written
    for t in targets[1:]:
        assert t.path.exists()
        assert t.path.read_text(encoding="utf-8") == t.content

    # Now apply with --force: exit 0, tampered target overwritten
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--apply", "--project", str(project), "--force"])
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert f"update: {tampered_target.path}" in captured.out
    assert tampered_target.path.read_text(encoding="utf-8") == tampered_target.content


def test_shims_target_with_no_marker_line_is_refused(shim_env, capsys):
    """A target with no marker line is refused."""
    home, project = shim_env
    target = shims.get_targets(project=project, home=home)[0]
    target.path.parent.mkdir(parents=True, exist_ok=True)
    target.path.write_text(
        "custom content without any router marker\n", encoding="utf-8"
    )

    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--apply", "--project", str(project)])
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert f"refuse: not generated by lee-llm-router: {target.path}" in captured.err


def test_shims_diff_lifecycle(shim_env, capsys):
    """diff exits 0 on clean install, 1 with unified diff after hand edit, and reports missing for removed file."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    # Clean install
    with pytest.raises(SystemExit):
        main(["shims", "install", "--apply", "--project", str(project)])
    capsys.readouterr()

    # Diff clean: exit 0, empty output
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "diff", "--project", str(project)])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""

    # Hand edit one target
    edit_target = targets[0]
    edit_target.path.write_text(
        edit_target.path.read_text(encoding="utf-8") + "\n# hand edit line\n",
        encoding="utf-8",
    )

    # Diff after hand edit: exit 1, unified diff
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "diff", "--project", str(project)])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert f"--- {edit_target.path}" in captured.out
    assert f"+++ {edit_target.path} (rendered)" in captured.out
    assert "+# hand edit line" in captured.out or "-# hand edit line" in captured.out

    # Re-apply cleanly
    with pytest.raises(SystemExit):
        main(["shims", "install", "--apply", "--project", str(project), "--force"])
    capsys.readouterr()

    # Remove one file
    remove_target = targets[2]
    remove_target.path.unlink()

    # Diff with missing file: exit 1, reports missing
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "diff", "--project", str(project)])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert f"missing: {remove_target.path}" in captured.out


def test_shims_harness_filter(shim_env, capsys):
    """--harness filter limits targets in install and diff."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    # Install only codex
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--apply",
                "--project",
                str(project),
                "--harness",
                "codex",
            ]
        )
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert f"create: {targets[1].path}" in captured.out
    assert targets[1].path.exists()
    assert not targets[0].path.exists()
    assert not targets[2].path.exists()
    assert not targets[3].path.exists()

    # Diff with --harness codex: exit 0
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "diff", "--project", str(project), "--harness", "codex"])
    assert excinfo.value.code == 0

    # Diff with --harness omp: exit 1 (missing)
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "diff", "--project", str(project), "--harness", "omp"])
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert f"missing: {targets[2].path}" in captured.out


def test_shims_usage_errors(shim_env, capsys):
    """Usage errors exit 3."""
    home, project = shim_env

    # No subcommand
    with pytest.raises(SystemExit) as excinfo:
        main(["shims"])
    assert excinfo.value.code == 3
    captured = capsys.readouterr()
    assert "subcommand required" in captured.err

    # Neither --dry-run nor --apply
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--project", str(project)])
    assert excinfo.value.code == 3
    captured = capsys.readouterr()
    assert "exactly one of --dry-run or --apply is required" in captured.err

    # Both --dry-run and --apply
    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "install", "--dry-run", "--apply", "--project", str(project)])
    assert excinfo.value.code == 3
    captured = capsys.readouterr()
    assert "exactly one of --dry-run or --apply is required" in captured.err

    # Unknown harness tag
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--dry-run",
                "--project",
                str(project),
                "--harness",
                "badtag",
            ]
        )
    assert excinfo.value.code == 3
    captured = capsys.readouterr()
    assert "unknown harness 'badtag'" in captured.err

    with pytest.raises(SystemExit) as excinfo:
        main(["shims", "diff", "--project", str(project), "--harness", "badtag"])
    assert excinfo.value.code == 3
    captured = capsys.readouterr()
    assert "unknown harness 'badtag'" in captured.err


def test_shims_inspect_target_actions(tmp_path):
    """inspect_target returns correct action for create, unchanged, update, refuse."""
    import hashlib

    home = tmp_path / "home"
    project = tmp_path / "project"
    targets = shims.get_targets(project=project, home=home)
    t = targets[0]

    # Target does not exist -> create
    assert shims.inspect_target(t) == "create"

    # Write target content -> unchanged
    t.path.parent.mkdir(parents=True, exist_ok=True)
    t.path.write_text(t.content, encoding="utf-8")
    assert shims.inspect_target(t) == "unchanged"

    # Write older version with valid hash -> update
    old_body = "\nOlder version body\n"
    old_hash = hashlib.sha256(old_body.encode("utf-8")).hexdigest()
    old_marker = f"<!-- lee-llm-router shim v1 sha256={old_hash} -->"
    old_file = f"---\ndescription: test\n---\n{old_marker}\n{old_body}"
    t.path.write_text(old_file, encoding="utf-8")
    assert shims.inspect_target(t) == "update"

    # Tampered body -> refuse
    t.path.write_text(old_file + "tampered", encoding="utf-8")
    assert shims.inspect_target(t) == "refuse: not generated by lee-llm-router"

    # Missing marker -> refuse
    t.path.write_text("just some random text without marker", encoding="utf-8")
    assert shims.inspect_target(t) == "refuse: not generated by lee-llm-router"
