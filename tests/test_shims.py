"""Tests for harness shims generation and management (Sprint 4 C3)."""

from __future__ import annotations

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


def test_rendered_bodies_differ_only_in_marker_hash(shim_env):
    """Rendered bodies carry no harness placeholder, so they differ only in
    the marker hash (frontmatter still differs per harness)."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)
    assert len(targets) == 5

    bodies = [t.body.replace(t.marker_hash, "HASH") for t in targets]
    for i in range(1, len(bodies)):
        assert (
            bodies[i] == bodies[0]
        ), f"Body for {targets[i].harness} differed from {targets[0].harness}"


STAFF_AUTO_LINE = "lee-llm-router staff --mode auto --role <role> --class <class>"
STAFF_CREW_LINE = "lee-llm-router staff --mode crew <name>"
RUN_OFFER_LINE = "lee-llm-router run --role <role> --class <class> --packet <path>"
RUN_OFFER_ROUTE_LINE = (
    "lee-llm-router run --route <route-id> --role <role> --class <class> "
    "--packet <path>"
)


def test_rendered_body_has_staff_lines_and_run_offer(shim_env):
    """Each rendered body carries the exact staff commands and run offer lines."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    for t in targets:
        stripped = [line.strip() for line in t.body.splitlines()]
        assert STAFF_AUTO_LINE in stripped
        assert STAFF_CREW_LINE in stripped
        assert RUN_OFFER_LINE in stripped
        assert RUN_OFFER_ROUTE_LINE in stripped


@pytest.mark.parametrize(
    "forbidden_line",
    [
        "lee-llm-router resolve ",
        "lee-llm-router dispatch ",
        "lee-llm-router run --route pi-gpt-5-6-luna-xhigh-openai-sub",
        "agy ",
        "codex exec",
        "claude -p",
        "opencode run",
        "omp -p",
    ],
)
def test_rendered_body_never_dispatches_or_invokes_providers(shim_env, forbidden_line):
    """No resolve/dispatch line, no executed run command, no provider binary."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    for t in targets:
        assert (
            forbidden_line not in t.body
        ), f"Rendered body for {t.harness} contains forbidden {forbidden_line!r}"


def test_rendered_body_run_offer_is_offered_not_executed(shim_env):
    """The run command appears only as an offer: each occurrence sits in a
    sentence that says offer/do not execute, and no line tells the harness
    to run it."""
    home, project = shim_env
    targets = shims.get_targets(project=project, home=home)

    for t in targets:
        assert "offer — do not execute — the dispatch command" in t.body
        # The only lines starting with the run command are the two offer lines
        run_lines = [
            line
            for line in t.body.splitlines()
            if line.startswith("lee-llm-router run")
        ]
        assert sorted(run_lines) == sorted([RUN_OFFER_LINE, RUN_OFFER_ROUTE_LINE])


def test_crew_default_selection_is_byte_identical_to_explicit_crew(shim_env, capsys):
    """The omitted command remains exactly the legacy ``crew`` command."""
    home, project = shim_env
    default_targets = shims.get_targets(project=project, home=home)
    crew_targets = shims.get_targets(
        project=project, home=home, command=shims.CREW_COMMAND
    )

    assert default_targets == crew_targets
    for default, explicit in zip(default_targets, crew_targets):
        assert default.content == explicit.content
        assert default.body == explicit.body
        assert default.path == explicit.path

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--dry-run",
                "--project",
                str(project),
            ]
        )
    assert excinfo.value.code == 0
    default_output = capsys.readouterr().out

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--dry-run",
                "--command",
                "crew",
                "--project",
                str(project),
            ]
        )
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == default_output


def test_shims_supervise_cli_lifecycle_all_targets(shim_env, capsys):
    """Exercise the supervise command selector through its full lifecycle."""
    home, project = shim_env
    targets = shims.get_targets(
        project=project, home=home, command=shims.SUPERVISE_COMMAND
    )

    # The dry-run must select supervise targets and must not create anything.
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--dry-run",
                "--command",
                "supervise",
                "--project",
                str(project),
            ]
        )
    assert excinfo.value.code == 0
    dry_run_output = capsys.readouterr().out
    for target in targets:
        assert f"target: {target.path}" in dry_run_output
        assert "action: create" in dry_run_output
        assert target.body in dry_run_output
        assert not target.path.exists()
        assert not target.path.parent.exists()

    # Apply creates only the selected command's four targets.
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--apply",
                "--command",
                "supervise",
                "--project",
                str(project),
            ]
        )
    assert excinfo.value.code == 0
    apply_output = capsys.readouterr().out
    for target in targets:
        assert f"create: {target.path}" in apply_output
        assert target.path.read_text(encoding="utf-8") == target.content
        assert not target.path.with_name("crew.md").exists()

    # A second apply is a no-op for every target.
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--apply",
                "--command",
                "supervise",
                "--project",
                str(project),
            ]
        )
    assert excinfo.value.code == 0
    unchanged_output = capsys.readouterr().out
    for target in targets:
        assert f"unchanged: {target.path}" in unchanged_output

    # Clean diff is empty.  Drift is checked independently for all four
    # harness targets, proving --command reaches both the renderer and diff.
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "diff",
                "--command",
                "supervise",
                "--project",
                str(project),
            ]
        )
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == ""

    for target in targets:
        target.path.write_text(
            target.path.read_text(encoding="utf-8") + "\n# drift\n",
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "shims",
                    "diff",
                    "--command",
                    "supervise",
                    "--harness",
                    target.harness,
                    "--project",
                    str(project),
                ]
            )
        assert excinfo.value.code == 1
        drift_output = capsys.readouterr().out
        assert f"--- {target.path}" in drift_output
        assert f"+++ {target.path} (rendered)" in drift_output
        assert "# drift" in drift_output

        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "shims",
                    "install",
                    "--apply",
                    "--force",
                    "--command",
                    "supervise",
                    "--harness",
                    target.harness,
                    "--project",
                    str(project),
                ]
            )
        assert excinfo.value.code == 0
        capsys.readouterr()
        assert target.path.read_text(encoding="utf-8") == target.content


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
    """Refuse a hand edit without force; overwrite it with force."""
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
    """Diff reports clean, edited, and missing target states."""
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
    assert not targets[4].path.exists()

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


def test_pi_target_path_and_frontmatter(tmp_path):
    """Pi targets resolve to ~/.pi/agent/prompts/<cmd>.md with expected frontmatter."""
    home = tmp_path / "home"

    # crew target
    crew_target = shims.render_target("pi", home=home, command=shims.CREW_COMMAND)
    expected_crew_path = home / ".pi" / "agent" / "prompts" / "crew.md"
    assert crew_target.path == expected_crew_path
    assert crew_target.form == "Pi prompt template"
    assert "argument-hint: auto|NAME" in crew_target.frontmatter
    assert "description: Compute one staffing decision" in crew_target.frontmatter

    # supervise target
    supervise_target = shims.render_target(
        "pi", home=home, command=shims.SUPERVISE_COMMAND
    )
    expected_supervise_path = home / ".pi" / "agent" / "prompts" / "supervise.md"
    assert supervise_target.path == expected_supervise_path
    assert supervise_target.form == "Pi prompt template"
    assert (
        "argument-hint: <plan-path> [crew NAME | auto]" in supervise_target.frontmatter
    )
    assert "description: Supervise one plan" in supervise_target.frontmatter


def test_pi_marker_round_trip(tmp_path):
    """Pi shim marker round-trips through create, unchanged, update, and refuse."""
    import hashlib

    home = tmp_path / "home"
    target = shims.render_target("pi", home=home, command=shims.CREW_COMMAND)

    # Initial state -> create
    assert shims.inspect_target(target) == "create"

    # Install cleanly -> unchanged
    target.path.parent.mkdir(parents=True, exist_ok=True)
    target.path.write_text(target.content, encoding="utf-8")
    assert shims.inspect_target(target) == "unchanged"

    # Modify with a valid hash from an older version -> update
    old_body = "\nOlder version of pi shim body\n"
    old_hash = hashlib.sha256(old_body.encode("utf-8")).hexdigest()
    old_marker = f"<!-- lee-llm-router shim v1 sha256={old_hash} -->"
    old_content = f"---\ndescription: test\n---\n{old_marker}\n{old_body}"
    target.path.write_text(old_content, encoding="utf-8")
    assert shims.inspect_target(target) == "update"

    # Tampered body -> refuse
    target.path.write_text(old_content + "\ntampered line\n", encoding="utf-8")
    assert shims.inspect_target(target) == "refuse: not generated by lee-llm-router"


def test_shims_diff_clean_after_install_temp_home(shim_env, capsys):
    """shims diff reports clean (exit 0, empty) after install into a temp home
    across all five targets.
    """
    home, project = shim_env

    for cmd in (shims.CREW_COMMAND, shims.SUPERVISE_COMMAND):
        # Install with --apply
        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "shims",
                    "install",
                    "--apply",
                    "--command",
                    cmd,
                    "--project",
                    str(project),
                ]
            )
        assert excinfo.value.code == 0
        capsys.readouterr()

        # Diff must be clean across all five harnesses
        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "shims",
                    "diff",
                    "--command",
                    cmd,
                    "--project",
                    str(project),
                ]
            )
        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        assert captured.out == ""
