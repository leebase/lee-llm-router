"""Doctor CLI tests (Sprint 4 + Sprint 6 export workflow)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from lee_llm_router.doctor import (
    MANIFEST_NAME,
    check_config,
    export_source,
    get_template,
)
from lee_llm_router.staffing import DOCUMENT_ORDER
from tests.test_staffing_catalog import _DOC_BUILDERS, write_docs

FIXTURES = Path(__file__).parent / "fixtures"
PI_HARNESS = FIXTURES / "pi_harness.py"


def test_doctor_shims_command_selector_forwards_supervise(
    tmp_path, monkeypatch, capsys
):
    """The doctor CLI accepts and forwards the managed shim command."""
    from lee_llm_router import shims
    from lee_llm_router.doctor import main

    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv(shims.ENV_SHIM_HOME, str(home))

    target = shims.target_path_for_harness(
        "opencode", project=project, home=home, command="supervise"
    )
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "shims",
                "install",
                "--dry-run",
                "--command",
                "supervise",
                "--harness",
                "opencode",
                "--project",
                str(project),
            ]
        )

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert f"target: {target}" in output
    assert "description: Supervise one plan" in output
    assert not target.exists()


def test_doctor_valid_config_exit_0():
    """Mock-only config has no env var or binary requirements - zero errors."""
    errors, warnings = check_config(str(FIXTURES / "llm_test.yaml"))
    assert errors == [], f"Unexpected errors: {errors}"


def test_doctor_allows_openai_http_alias(tmp_path, monkeypatch):
    """Configs using type: openai_http must pass when env + base_url provided."""
    monkeypatch.setenv("OPENAI_ALIAS_KEY", "token")

    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        """\
llm:
  default_role: planner
  providers:
    openrouter:
      type: openai_http
      base_url: https://api.openai.com/v1
      api_key_env: OPENAI_ALIAS_KEY
  roles:
    planner:
      provider: openrouter
      model: gpt-4o-mini
""",
        encoding="utf-8",
    )
    errors, warnings = check_config(str(config_file))
    assert errors == []
    assert warnings == []


def test_doctor_allows_openai_codex_subscription_alias_with_env(tmp_path, monkeypatch):
    """Configs using type: openai_codex_http pass when access_token_env is set."""
    monkeypatch.setenv("OPENAI_CODEX_TOKEN", "token")

    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        """\
llm:
  default_role: planner
  providers:
    codex_sub:
      type: openai_codex_http
      base_url: https://chatgpt.com/backend-api/codex
      access_token_env: OPENAI_CODEX_TOKEN
  roles:
    planner:
      provider: codex_sub
      model: gpt-5.3-codex
""",
        encoding="utf-8",
    )
    errors, warnings = check_config(str(config_file))
    assert errors == []
    assert warnings == []


def test_doctor_allows_gemini_cli_alias(tmp_path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        f"""\
llm:
  default_role: local
  providers:
    gemini:
      type: gemini
      command: {sys.executable}
      args:
        - {PI_HARNESS}
        - success_json
      response_format: json
  roles:
    local:
      provider: gemini
      model: gemini-2.5-pro
""",
        encoding="utf-8",
    )
    errors, warnings = check_config(str(config_file))

    assert errors == []
    assert warnings == []


def test_doctor_missing_env_var_reports_error(tmp_path, monkeypatch):
    """HTTP provider whose api_key_env is unset produces an error."""
    monkeypatch.delenv("MISSING_API_KEY_XYZ", raising=False)

    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        """\
llm:
  default_role: http_role
  providers:
    openrouter:
      type: openrouter_http
      base_url: https://openrouter.ai/api/v1
      api_key_env: MISSING_API_KEY_XYZ
  roles:
    http_role:
      provider: openrouter
      model: gpt-4o
""",
        encoding="utf-8",
    )
    errors, _ = check_config(str(config_file))
    assert any("MISSING_API_KEY_XYZ" in error for error in errors), f"Errors: {errors}"


def test_doctor_missing_binary_reports_error(tmp_path):
    """CLI provider whose command binary does not exist produces an error."""
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        """\
llm:
  default_role: local
  providers:
    codex:
      type: codex_cli
      command: definitely_not_a_real_binary_xyzzy999
  roles:
    local:
      provider: codex
""",
        encoding="utf-8",
    )
    errors, _ = check_config(str(config_file))
    assert any(
        "definitely_not_a_real_binary_xyzzy999" in error for error in errors
    ), f"Expected binary-not-found error, got: {errors}"


def test_doctor_accepts_pi_harness_cli_config(tmp_path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        f"""\
llm:
  default_role: local
  providers:
    pi_harness:
      type: codex_cli
      command: {sys.executable}
      args:
        - {PI_HARNESS}
        - success_json
      response_format: json
  roles:
    local:
      provider: pi_harness
      model: o3
""",
        encoding="utf-8",
    )

    errors, warnings = check_config(str(config_file))

    assert errors == []
    assert warnings == []


def test_doctor_accepts_pi_harness_with_disabled_default_flags(tmp_path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        f"""\
llm:
  default_role: local
  providers:
    pi_harness:
      type: codex_cli
      command: {sys.executable}
      args:
        - {PI_HARNESS}
        - strict_success_json
      model_flag: null
      output_flag: null
      response_format: json
  roles:
    local:
      provider: pi_harness
      model: o3
""",
        encoding="utf-8",
    )

    errors, warnings = check_config(str(config_file))

    assert errors == []
    assert warnings == []


def test_doctor_rejects_invalid_codex_cli_response_format(tmp_path):
    config_file = tmp_path / "llm.yaml"
    config_file.write_text(
        """\
llm:
  default_role: local
  providers:
    pi_harness:
      type: codex_cli
      command: python3
      response_format: yaml
  roles:
    local:
      provider: pi_harness
      model: o3
""",
        encoding="utf-8",
    )

    errors, _ = check_config(str(config_file))

    assert any("response_format" in error for error in errors)


def test_template_command_outputs_yaml():
    output = get_template()
    assert "llm:" in output
    assert "providers:" in output
    assert "roles:" in output
    assert "api_key_env" in output


def test_doctor_invalid_config_returns_error(tmp_path):
    """Malformed YAML config returns config-level error, not an exception."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("not_llm_key: value\n", encoding="utf-8")
    errors, _ = check_config(str(config_file))
    assert len(errors) == 1
    assert "Config invalid" in errors[0] or "Config" in errors[0]


def test_export_source_writes_package_tree_and_manifest(tmp_path):
    destination = tmp_path / "vendor" / "lee_llm_router"

    result = export_source(destination)

    assert destination.exists()
    assert (destination / "__init__.py").exists()
    assert (destination / "providers" / "registry.py").exists()
    manifest_path = destination / MANIFEST_NAME
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["package"] == "lee_llm_router"
    assert manifest["version"] == result["version"]
    assert manifest["source_subdir"] == "src/lee_llm_router"
    assert "exported_at_utc" in manifest


def test_export_source_allows_existing_empty_destination(tmp_path):
    destination = tmp_path / "vendor" / "lee_llm_router"
    destination.mkdir(parents=True)

    result = export_source(destination)

    assert (destination / "__init__.py").exists()
    assert (destination / MANIFEST_NAME).exists()
    assert result["destination"] == str(destination)


def test_export_source_refuses_non_empty_destination_without_force(tmp_path):
    destination = tmp_path / "vendor" / "lee_llm_router"
    destination.mkdir(parents=True)
    (destination / "sentinel.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Destination is not empty"):
        export_source(destination)


def test_export_source_force_overwrites_existing_destination(tmp_path):
    destination = tmp_path / "vendor" / "lee_llm_router"
    destination.mkdir(parents=True)
    (destination / "sentinel.txt").write_text("stale", encoding="utf-8")

    export_source(destination, force=True)

    assert not (destination / "sentinel.txt").exists()
    assert (destination / MANIFEST_NAME).exists()


def test_doctor_cli_main_exit_0():
    """main() with valid mock config exits 0 without raising SystemExit(1)."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--config", str(FIXTURES / "llm_test.yaml")])
    assert exc_info.value.code == 0


def test_doctor_cli_template_prints_yaml(capsys):
    """main() template subcommand prints the example YAML."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["template"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "llm:" in captured.out


def test_removed_legacy_public_exports_are_absent():
    """The deleted router layer is not resurrected by package lazy exports."""
    import lee_llm_router

    for name in (
        "LLMRouter",
        "LLMClient",
        "load_config",
        "LLMConfig",
        "RoutingPolicy",
        "SimpleRoutingPolicy",
        "ProviderChoice",
        "TraceStore",
        "LocalFileTraceStore",
        "EventSink",
        "RouterEvent",
    ):
        assert name not in lee_llm_router.__all__
        with pytest.raises(AttributeError):
            getattr(lee_llm_router, name)


@pytest.mark.parametrize("removed_command", ["resolve", "dispatch"])
def test_removed_legacy_cli_commands_are_rejected(capsys, removed_command):
    """The old selection and dispatch command paths are no longer registered."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main([removed_command, "--help"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert f"invalid choice: '{removed_command}'" in captured.err


def test_export_source_cli_main_prints_summary(tmp_path, capsys):
    """main() export-source subcommand writes files and prints a summary."""
    from lee_llm_router.doctor import main

    destination = tmp_path / "vendor" / "lee_llm_router"

    with pytest.raises(SystemExit) as exc_info:
        main(["export-source", "--dest", str(destination)])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "Lee LLM Router Source Export" in captured.out
    assert str(destination) in captured.out
    assert (destination / MANIFEST_NAME).exists()


CREWS_FIXTURE = FIXTURES / "crews.yaml"
LIVE_CREWS_FILE = Path("/home/lee/projects/auto-orch/config/crews.yaml")

BAD_CREWS_YAML = """
workers:
  legacy_worker:
    command: "run-sol {stage} {prompt_path} {response_path}"
crews:
  broken:
    description: Worker command has no stage-worker env vars.
    stages:
      envision: legacy_worker
    governed:
      primary: {harness: codex_cli}
"""


def test_crews_list_plain_output(capsys):
    """main() crews list renders each crew, its stages, and governed routes."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["crews", "list", "--crews-file", str(CREWS_FIXTURE)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "test-flagship" in out
    assert "envision: codex_sol_high (codex_cli gpt-5.6-sol/high)" in out
    assert "ideate: claude_opus5_high (claude_code_cli claude-opus-5/high)" in out
    assert "governed: primary=claude_code/claude-opus-5" in out


def test_crews_list_json_output(capsys):
    """main() crews list --json emits a JSON array of crew summaries."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["crews", "list", "--crews-file", str(CREWS_FIXTURE), "--json"])
    assert exc_info.value.code == 0

    payload = json.loads(capsys.readouterr().out)
    assert [entry["name"] for entry in payload] == ["test-flagship", "test-flex"]
    envision = payload[1]["stages"]["envision"]
    assert envision["worker_id"] == "codex_luna_max"
    assert envision["provider"] == "codex_cli"
    assert envision["model"] == "gpt-5.6-luna"
    assert envision["effort"] == "max"
    assert envision["eligible"][1] == "antigravity_gemini38_flash_high"


def test_doctor_crews_without_config_exits_0(capsys):
    """doctor --crews works without --config and reports resolved workers."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(CREWS_FIXTURE)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "OK crews: 2 crews, 4/4 workers resolved, 0 role-scoped warning(s)" in out


def test_doctor_crews_bad_file_exits_1(tmp_path, capsys):
    """doctor --crews exits 1 when a worker cannot be resolved."""
    from lee_llm_router.doctor import main

    bad = tmp_path / "crews.yaml"
    bad.write_text(BAD_CREWS_YAML, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(bad)])
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "legacy_worker" in err


def test_doctor_without_config_or_crews_exits_1(capsys):
    """doctor with neither --config nor --crews is a usage error."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor"])
    assert exc_info.value.code == 1
    assert "--config" in capsys.readouterr().err


@pytest.mark.skipif(
    not LIVE_CREWS_FILE.is_file(), reason="live Auto-Orch crews file not present"
)
def test_doctor_crews_against_live_file_exits_0(capsys):
    """doctor --crews resolves every worker in the live Auto-Orch crews file."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(LIVE_CREWS_FILE)])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "OK crews:" in out
    # P0-2c: the live count must be derived from the live crews file, not a
    # literal, so additive workers never stale this assertion.
    from lee_llm_router.crews import load_crews

    live_workers = len(load_crews(LIVE_CREWS_FILE).workers)
    assert f"{live_workers}/{live_workers} workers resolved" in out
    assert "0 role-scoped warning(s)" in out


UNREFERENCED_BAD_WORKER_YAML = """
workers:
  codex_sol_high:
    command: "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/x/bin/codex \
CODEX_STAGE_WORKER_MODEL=gpt-5.6-sol python3 /x/w.py {stage}"
  orphan_worker:
    command: "run-something {stage} {prompt_path} {response_path}"
crews:
  only-crew:
    description: No stage references orphan_worker.
    stages:
      envision: codex_sol_high
    governed:
      primary: {harness: codex_cli}
"""

ROLE_SCOPED_CODING_WORKER_YAML = """
workers:
  antigravity_gemini31_pro:
    command: "/usr/bin/env ANTIGRAVITY_STAGE_WORKER_BINARY=/x/bin/agy \
ANTIGRAVITY_STAGE_WORKER_MODEL=gemini-3.1-pro python3 /x/w.py {stage}"
crews:
  gemini-pro-crew:
    description: Uses the role-scoped model in a coding role.
    stages:
      author: antigravity_gemini31_pro
    governed:
      primary: {harness: antigravity_cli}
"""

ROLE_SCOPED_PLANNING_WORKER_YAML = """
workers:
  antigravity_gemini31_pro:
    command: "/usr/bin/env ANTIGRAVITY_STAGE_WORKER_BINARY=/x/bin/agy \
ANTIGRAVITY_STAGE_WORKER_MODEL=gemini-3.1-pro python3 /x/w.py {stage}"
crews:
  gemini-pro-crew:
    description: Uses the role-scoped model in a planning role.
    stages:
      envision: antigravity_gemini31_pro
    governed:
      primary: {harness: antigravity_cli}
"""


def test_doctor_crews_unreferenced_bad_worker_exits_1(tmp_path, capsys):
    """A malformed top-level worker no crew references is still an error."""
    from lee_llm_router.doctor import main

    bad = tmp_path / "crews.yaml"
    bad.write_text(UNREFERENCED_BAD_WORKER_YAML, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(bad)])
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "orphan_worker" in err


def test_doctor_crews_role_scoped_model_warns_in_coding_stage(tmp_path, capsys):
    """A gemini-3.1-pro worker in a coding stage warns and keeps exit 0."""
    from lee_llm_router.doctor import main

    crews_file = tmp_path / "crews.yaml"
    crews_file.write_text(ROLE_SCOPED_CODING_WORKER_YAML, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(crews_file)])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "  !  " in captured.out
    assert (
        "Crew 'gemini-pro-crew' stage 'author' uses role-scoped model "
        "'gemini-3.1-pro' in a coding role; staffing will never auto-select it "
        "there (decisions.md D188)" in captured.out
    )
    assert "1/1 workers resolved, 1 role-scoped warning(s)" in captured.out
    assert captured.err == ""


def test_doctor_crews_role_scoped_model_no_warning_in_planning_stage(tmp_path, capsys):
    """A gemini-3.1-pro worker in a planning stage emits no warning and exits 0."""
    from lee_llm_router.doctor import main

    crews_file = tmp_path / "crews.yaml"
    crews_file.write_text(ROLE_SCOPED_PLANNING_WORKER_YAML, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(crews_file)])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "  !  " not in captured.out
    assert "1/1 workers resolved, 0 role-scoped warning(s)" in captured.out
    assert captured.err == ""


PI_GOVERNED_YAML = """
workers:
  pi_worker:
    command: "/usr/bin/env PI_STAGE_WORKER_BINARY=/x/bin/pi \
PI_STAGE_WORKER_PROVIDER=openai-codex PI_STAGE_WORKER_MODEL=gpt-5.6-sol \
python3 /x/w.py {stage}"
crews:
  pi-crew:
    description: Governed run whose harnesses are pi_cli.
    stages:
      author: pi_worker
    governed:
      primary: {harness: pi_cli}
      reviewer: {harness: pi_cli}
"""

UNKNOWN_GOVERNED_HARNESS_YAML = """
workers:
  pi_worker:
    command: "/usr/bin/env PI_STAGE_WORKER_BINARY=/x/bin/pi \
PI_STAGE_WORKER_MODEL=gpt-5.6-sol python3 /x/w.py {stage}"
crews:
  pi-crew:
    description: Governed run naming an unregistered harness.
    stages:
      author: pi_worker
    governed:
      primary: {harness: warp_cli}
"""


def test_doctor_crews_governed_pi_cli_routes_accepted(tmp_path, capsys):
    """Governed primary and reviewer routes naming pi_cli validate cleanly."""
    from lee_llm_router.doctor import main

    crews_file = tmp_path / "crews.yaml"
    crews_file.write_text(PI_GOVERNED_YAML, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(crews_file)])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "  x  " not in captured.err
    assert "OK crews: 1 crews, 1/1 workers resolved" in captured.out
    assert captured.err == ""


def test_doctor_crews_unknown_governed_harness_fails(tmp_path, capsys):
    """A governed route naming an unknown harness errors with the known set."""
    from lee_llm_router.doctor import main

    crews_file = tmp_path / "crews.yaml"
    crews_file.write_text(UNKNOWN_GOVERNED_HARNESS_YAML, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--crews", "--crews-file", str(crews_file)])
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "unknown harness 'warp_cli'" in err
    assert "known: " in err
    assert "omp_cli" in err
    assert "pi_cli" in err


def test_doctor_crews_unmapped_stage_warns(monkeypatch):
    """A crew stage with no role class emits a warning citing D188."""
    from lee_llm_router.crews import Crew, CrewsConfig, Stage, Worker
    from lee_llm_router.doctor import check_crews

    worker = Worker(
        id="w1",
        command=(
            "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/x/bin/codex "
            "CODEX_STAGE_WORKER_MODEL=gpt-5.6-sol python3 /x/w.py {stage}"
        ),
    )
    crew = Crew(
        name="test-crew",
        description="test",
        stages={"unknown_stage": Stage(name="unknown_stage", workers=("w1",))},
        governed={},
    )
    config = CrewsConfig(
        workers={"w1": worker}, crews={"test-crew": crew}, path=Path("/x/crews.yaml")
    )

    monkeypatch.setattr("lee_llm_router.crews.load_crews", lambda _p=None: config)
    errors, warnings, crew_count, resolved_count, total = check_crews()
    assert not errors
    assert any(
        "stage 'unknown_stage' has no role class (decisions.md D188)" in w
        for w in warnings
    )


AVAILABILITY_SUBSCRIPTIONS = [
    {
        "provider": "OpenAI/Codex",
        "bucket": "Weekly limit",
        "status": "HOT",
        "remaining_pct": 48.0,
    },
    {
        "provider": "Anthropic/Claude",
        "bucket": "Current session",
        "status": "COLD",
        "remaining_pct": 73.0,
    },
]


_SAME_AGE = object()
"""Sentinel: ``observed_at`` ages exactly like ``written_at`` unless told otherwise."""


def _write_snapshot(
    tmp_path,
    age_minutes: float | None = 5.0,
    observed_age_minutes=_SAME_AGE,
    now=None,
    **overrides,
):
    """Write an availability snapshot whose timestamps are ``age_minutes`` old.

    Both ``observed_at`` and ``written_at`` are stamped relative to ``now``
    (default: the current UTC time), never to a hardcoded absolute date:
    staleness is governed by the *older* of the two, so a frozen ``observed_at``
    would quietly drift past the 90-minute ceiling as wall-clock time passes and
    turn every "fresh snapshot" case into a stale one.

    Args:
        tmp_path: Directory to write ``A8Max.json`` into.
        age_minutes: How many minutes old ``written_at`` is; a negative value
            stamps it in the future, and ``None`` omits the key entirely.
        observed_age_minutes: Same for ``observed_at``; defaults to
            ``age_minutes`` so a "fresh" snapshot is fresh on both timestamps.
        now: Reference time the ages are measured back from. Pin it and pass the
            same value to the reader when a test asserts an exact age.
        **overrides: Raw body keys written last, for malformed-input cases.

    Returns:
        The path of the snapshot written.
    """
    from datetime import datetime, timedelta, timezone

    moment = now or datetime.now(timezone.utc)
    if observed_age_minutes is _SAME_AGE:
        observed_age_minutes = age_minutes

    def stamp(minutes: float) -> str:
        return (moment - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "source": "live CLI integration",
        "subscriptions": AVAILABILITY_SUBSCRIPTIONS,
        "host": "A8Max",
    }
    if observed_age_minutes is not None:
        body["observed_at"] = stamp(observed_age_minutes)
    if age_minutes is not None:
        body["written_at"] = stamp(age_minutes)
    body.update(overrides)
    path = tmp_path / "A8Max.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _pinned_now():
    """A single reference instant shared by a snapshot and the reader under test."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_check_availability_fresh_snapshot_is_clean(tmp_path):
    from lee_llm_router.doctor import check_availability

    now = _pinned_now()
    path = _write_snapshot(tmp_path, now=now)

    errors, warnings, details = check_availability(path, now=now)

    assert errors == []
    assert warnings == []
    assert details["bucket_count"] == 2
    assert details["age_minutes"] is not None
    assert 0 < details["age_minutes"] < 90


def test_check_availability_falls_back_to_observed_at(tmp_path):
    from lee_llm_router.doctor import check_availability

    now = _pinned_now()
    path = _write_snapshot(
        tmp_path, age_minutes=None, observed_age_minutes=3.0, now=now
    )

    errors, warnings, details = check_availability(path, now=now)

    assert errors == []
    assert warnings == []
    assert details["written_at"] is None
    assert details["age_minutes"] < 90


def test_check_availability_ages_from_the_older_timestamp(tmp_path):
    """A fresh ``written_at`` never rescues an observation past the ceiling."""
    from lee_llm_router.doctor import check_availability

    now = _pinned_now()
    path = _write_snapshot(
        tmp_path, age_minutes=1.0, observed_age_minutes=200.0, now=now
    )

    errors, warnings, details = check_availability(path, now=now)

    assert errors == []
    assert len(warnings) == 1
    assert "observed_at is older than 90 minutes" in warnings[0]
    assert details["age_minutes"] > 90


def test_check_availability_future_timestamp_is_stale_not_ok(tmp_path):
    from lee_llm_router.doctor import check_availability

    now = _pinned_now()
    path = _write_snapshot(tmp_path, age_minutes=-10.0, now=now)

    errors, warnings, details = check_availability(path, now=now)

    assert errors == []
    assert len(warnings) == 1
    assert "future" in warnings[0]
    assert details["age_minutes"] < 0


def test_check_availability_small_future_skew_is_fresh(tmp_path):
    from lee_llm_router.doctor import check_availability

    now = _pinned_now()
    path = _write_snapshot(tmp_path, age_minutes=-1.0, now=now)

    errors, warnings, _details = check_availability(path, now=now)

    assert errors == []
    assert warnings == []


def test_check_availability_accepts_a_naive_now(tmp_path):
    from datetime import datetime, timezone

    from lee_llm_router.doctor import check_availability

    path = _write_snapshot(tmp_path)
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)

    errors, warnings, details = check_availability(path, now=naive_now)

    assert errors == []
    assert warnings == []
    assert details["age_minutes"] is not None


def test_check_availability_reports_every_channel(tmp_path):
    from lee_llm_router.availability import CHANNELS
    from lee_llm_router.doctor import check_availability

    _errors, _warnings, details = check_availability(_write_snapshot(tmp_path))

    assert list(details["channels"]) == list(CHANNELS)


def test_doctor_availability_fresh_exits_0(tmp_path, capsys):
    from lee_llm_router.doctor import main

    path = _write_snapshot(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--availability", "--availability-file", str(path)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "OK availability:" in out
    assert str(path) in out
    assert "2 buckets" in out
    assert "  anthropic-sub: healthy" in out
    assert sum(1 for line in out.splitlines() if line.startswith("  ")) == 6


def test_doctor_availability_stale_warns_exit_0(tmp_path, capsys):
    from lee_llm_router.doctor import main

    path = _write_snapshot(tmp_path, age_minutes=200.0)

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--availability", "--availability-file", str(path)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "stale" in out
    assert "OK availability:" not in out


def test_doctor_availability_future_timestamp_warns_exit_0(tmp_path, capsys):
    from lee_llm_router.doctor import main

    path = _write_snapshot(tmp_path, age_minutes=-10.0)

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--availability", "--availability-file", str(path)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "future" in out
    assert "OK availability:" not in out


def test_doctor_availability_missing_warns_exit_0(tmp_path, capsys):
    from lee_llm_router.doctor import main

    missing = tmp_path / "nope.json"

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--availability", "--availability-file", str(missing)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "missing" in out


def test_doctor_availability_malformed_exits_1(tmp_path, capsys):
    from lee_llm_router.doctor import main

    bad = tmp_path / "A8Max.json"
    bad.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--availability", "--availability-file", str(bad)])
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "unusable" in err
    assert "invalid JSON" in err


def test_doctor_availability_without_subscriptions_list_exits_1(tmp_path, capsys):
    from lee_llm_router.doctor import main

    bad = tmp_path / "A8Max.json"
    bad.write_text(json.dumps({"observed_at": "x"}), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--availability", "--availability-file", str(bad)])
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "unusable" in err
    assert "'subscriptions'" in err


def test_doctor_crews_and_availability_together_exit_0(tmp_path, capsys):
    from lee_llm_router.doctor import main

    path = _write_snapshot(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "doctor",
                "--crews",
                "--crews-file",
                str(CREWS_FIXTURE),
                "--availability",
                "--availability-file",
                str(path),
            ]
        )
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "OK crews:" in out
    assert "OK availability:" in out


# --------------------------------------------------------------------------
# crews page
# --------------------------------------------------------------------------


def _write_page_evidence(path: Path, *, score: int = 88) -> Path:
    """Write one valid staffing-evidence row matching the crews fixture."""
    payload = {
        "schema_version": "benchmark.staffing-evidence/2",
        "rows": [
            {
                "acceptance": "accepted",
                "accepted_count": 1,
                "cost_low_usd": "0.50",
                "cost_high_usd": "0.75",
                "role": "coder",
                "run_count": 1,
                "run_ids": ["synthetic-run"],
                "score_100": score,
                "task_key": "task-a@v1",
                "worker_key": "gpt-5.6-sol|codex|high",
                "worker": {
                    "effort": "high",
                    "harness": "codex",
                    "model": "gpt-5.6-sol",
                    "provider": "codex",
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _page_args(
    output: Path,
    crews_file: Path,
    availability_file: Path,
    *extra: str,
) -> list[str]:
    """Build an isolated page command argument list."""
    return [
        "crews",
        "page",
        "--out",
        str(output),
        "--crews-file",
        str(crews_file),
        "--availability-file",
        str(availability_file),
        *extra,
    ]


def test_crews_page_cli_generates_live_shaped_page_and_validates_events(
    tmp_path, capsys
):
    """Page success loads every selected input and prints the output path."""
    from lee_llm_router.doctor import main

    availability_file = _write_snapshot(tmp_path)
    benchmark_file = _write_page_evidence(
        tmp_path / "staffing-evidence-2026-09-08.json"
    )
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"synthetic": true}\n', encoding="utf-8")
    output = tmp_path / "crews.html"

    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                output,
                CREWS_FIXTURE,
                availability_file,
                "--benchmark-file",
                str(benchmark_file),
                "--events-file",
                str(events_file),
            )
        )

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == str(output)
    page = output.read_text(encoding="utf-8")
    assert "test-flagship" in page
    assert "Best score" in page
    assert "88" in page
    assert "synthetic-run" in page


def test_crews_page_cli_discovers_lexically_latest_benchmark(tmp_path, monkeypatch):
    """Omitted evidence selects the latest sidecar by filename, not mtime."""
    from lee_llm_router.doctor import main

    home = tmp_path / "home"
    exports = home / "projects" / "ai-workforce-benchmark" / "exports"
    exports.mkdir(parents=True)
    old = _write_page_evidence(exports / "staffing-evidence-2026-09-07.json", score=71)
    latest = _write_page_evidence(
        exports / "staffing-evidence-2026-09-08.json", score=93
    )
    old.touch()
    latest.touch()
    monkeypatch.setenv("HOME", str(home))

    output = tmp_path / "crews.html"
    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                output,
                CREWS_FIXTURE,
                _write_snapshot(tmp_path),
            )
        )

    assert exc_info.value.code == 0
    assert "93" in output.read_text(encoding="utf-8")
    assert "71" not in output.read_text(encoding="utf-8")


def test_crews_page_cli_missing_benchmark_succeeds_with_notice(tmp_path, capsys):
    """An explicitly missing optional sidecar is the documented absent state."""
    from lee_llm_router.doctor import main

    output = tmp_path / "crews.html"
    missing = tmp_path / "missing-staffing-evidence.json"
    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                output,
                CREWS_FIXTURE,
                _write_snapshot(tmp_path),
                "--benchmark-file",
                str(missing),
            )
        )

    assert exc_info.value.code == 0
    assert "No benchmark evidence yet." in output.read_text(encoding="utf-8")
    assert capsys.readouterr().err == ""


def test_crews_page_cli_missing_availability_succeeds_with_all_unknown(
    tmp_path, capsys
):
    """A missing availability snapshot renders every worker as unknown."""
    from lee_llm_router.doctor import main

    output = tmp_path / "crews.html"
    missing_availability = tmp_path / "missing-availability.json"
    missing_benchmark = tmp_path / "missing-staffing-evidence.json"
    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                output,
                CREWS_FIXTURE,
                missing_availability,
                "--benchmark-file",
                str(missing_benchmark),
            )
        )

    assert exc_info.value.code == 0
    assert not missing_availability.exists()
    assert capsys.readouterr().err == ""

    page = output.read_text(encoding="utf-8")
    from lee_llm_router.crews import load_crews

    worker_count = sum(
        len(stage.workers)
        for crew in load_crews(CREWS_FIXTURE).crews.values()
        for stage in crew.stages.values()
    )
    assert page.count('class="headroom unknown"') == worker_count
    assert page.count("<time>unknown</time>") == worker_count
    assert page.count("Stale: yes") == worker_count


@pytest.mark.parametrize(
    ("kind", "content"),
    [
        ("benchmark", "{not json"),
        ("events", '{"valid": true}\nnot-json\n'),
        ("availability", "{not json"),
    ],
)
def test_crews_page_cli_rejects_malformed_input_without_output(
    tmp_path, capsys, kind, content
):
    """Malformed benchmark, event, and availability inputs fail closed."""
    from lee_llm_router.doctor import main

    availability_file = _write_snapshot(tmp_path)
    benchmark_file = _write_page_evidence(tmp_path / "evidence.json")
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"valid": true}\n', encoding="utf-8")
    selected = {
        "benchmark": tmp_path / "bad-evidence.json",
        "events": tmp_path / "bad-events.jsonl",
        "availability": tmp_path / "bad-availability.json",
    }[kind]
    selected.write_text(content, encoding="utf-8")
    output = tmp_path / f"{kind}.html"
    args = _page_args(
        output,
        CREWS_FIXTURE,
        availability_file,
        "--benchmark-file",
        str(benchmark_file),
        "--events-file",
        str(events_file),
    )
    if kind == "benchmark":
        args[args.index("--benchmark-file") + 1] = str(selected)
    elif kind == "events":
        args[args.index("--events-file") + 1] = str(selected)
    else:
        args[args.index("--availability-file") + 1] = str(selected)

    with pytest.raises(SystemExit) as exc_info:
        main(args)

    assert exc_info.value.code == 3
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "configuration error" in captured.err


def test_crews_page_cli_rejects_present_non_file_without_output(tmp_path, capsys):
    """A present availability directory is not a usable snapshot file."""
    from lee_llm_router.doctor import main

    availability_dir = tmp_path / "availability"
    availability_dir.mkdir()
    output = tmp_path / "crews.html"

    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                output,
                CREWS_FIXTURE,
                availability_dir,
                "--benchmark-file",
                str(tmp_path / "missing-evidence.json"),
            )
        )

    assert exc_info.value.code == 3
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "configuration error" in captured.err


def test_crews_page_cli_rejects_bad_crews_and_output_write_failure(tmp_path, capsys):
    """Crew parsing and output filesystem failures do not leave a page."""
    from lee_llm_router.doctor import main

    bad_crews = tmp_path / "bad-crews.yaml"
    bad_crews.write_text("crews: []\n", encoding="utf-8")
    output = tmp_path / "bad-crews.html"
    with pytest.raises(SystemExit) as exc_info:
        main(_page_args(output, bad_crews, _write_snapshot(tmp_path)))
    assert exc_info.value.code == 3
    assert not output.exists()
    assert len(capsys.readouterr().err.splitlines()) == 1

    blocking_parent = tmp_path / "not-a-directory"
    blocking_parent.write_text("block", encoding="utf-8")
    blocked_output = blocking_parent / "crews.html"
    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                blocked_output,
                CREWS_FIXTURE,
                _write_snapshot(tmp_path),
            )
        )
    assert exc_info.value.code == 3
    assert not blocked_output.exists()
    assert len(capsys.readouterr().err.splitlines()) == 1


def test_crews_page_cli_does_not_call_subprocess_or_write_default_events(
    tmp_path, monkeypatch
):
    """Page generation remains a read-only projection with lazy pure imports."""
    from lee_llm_router.doctor import main

    def fail_subprocess(*_args, **_kwargs):
        raise AssertionError("page generation must not start a subprocess")

    def fail_event_write(*_args, **_kwargs):
        raise AssertionError("page generation must not write an event")

    monkeypatch.setattr("subprocess.run", fail_subprocess)
    monkeypatch.setattr("lee_llm_router.events.append_event", fail_event_write)
    ledger = tmp_path / "default-events.jsonl"
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(ledger))

    output = tmp_path / "crews.html"
    with pytest.raises(SystemExit) as exc_info:
        main(
            _page_args(
                output,
                CREWS_FIXTURE,
                _write_snapshot(tmp_path),
                "--benchmark-file",
                str(tmp_path / "missing-evidence.json"),
            )
        )

    assert exc_info.value.code == 0
    assert output.exists()
    assert not ledger.exists()


# --------------------------------------------------------------------------
# doctor --catalog (staffing catalog documents)
# --------------------------------------------------------------------------


def test_doctor_catalog_valid_exits_0_with_ok_summary(tmp_path, capsys):
    """A valid six-document catalog exits 0 with a concise OK summary."""
    from lee_llm_router.doctor import main

    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--catalog", "--catalog-dir", str(tmp_path)])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert f"OK catalog: {tmp_path}" in out
    assert "(routes 2, channels 2, terms 1, crews 2)" in out


@pytest.mark.parametrize("name", sorted(DOCUMENT_ORDER))
def test_doctor_catalog_unexpected_field_exits_3_names_document_and_field(
    tmp_path, capsys, name
):
    """Each invalid document exits 3 with a stable error naming doc and path."""
    from lee_llm_router.doctor import main

    docs = {doc_name: builder() for doc_name, builder in _DOC_BUILDERS.items()}
    docs[name]["unexpected_field"] = "surprise"
    write_docs(tmp_path, docs)

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--catalog", "--catalog-dir", str(tmp_path)])
    assert exc_info.value.code == 3

    captured = capsys.readouterr()
    assert "catalog invalid:" in captured.err
    assert f"'{name}'" in captured.err
    assert "$.unexpected_field" in captured.err


def test_doctor_catalog_defaults_to_repo_config_staffing_exits_0(capsys):
    """--catalog without --catalog-dir validates the repo config/staffing dir."""
    from pathlib import Path

    from lee_llm_router.doctor import _default_catalog_dir, main

    default_dir = _default_catalog_dir()
    assert default_dir == Path(__file__).resolve().parents[1] / "config" / "staffing"
    for name in DOCUMENT_ORDER:
        assert (default_dir / f"{name}.yaml").is_file(), name

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--catalog"])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert f"OK catalog: {default_dir}" in out


def test_doctor_catalog_gate1_command_without_catalog_dir_exits_0(
    tmp_path, capsys, monkeypatch
):
    """The gate-1 command `doctor --catalog --crews --availability` exits 0
    with no --catalog-dir, defaulting to the repo config/staffing directory."""
    from lee_llm_router.doctor import _default_catalog_dir, main

    monkeypatch.setenv("LEE_LLM_ROUTER_CREWS_FILE", str(CREWS_FIXTURE))
    snapshot = _write_snapshot(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "doctor",
                "--catalog",
                "--crews",
                "--availability",
                "--crews-file",
                str(CREWS_FIXTURE),
                "--availability-file",
                str(snapshot),
            ]
        )
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    default_dir = _default_catalog_dir()
    assert f"OK catalog: {default_dir}" in out
    assert "OK crews:" in out
    assert "OK availability:" in out


def test_doctor_catalog_missing_document_exits_3_names_document(tmp_path, capsys):
    """A directory missing a document exits 3 naming that document."""
    from lee_llm_router.doctor import main

    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "channels.yaml").unlink()

    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--catalog", "--catalog-dir", str(tmp_path)])
    assert exc_info.value.code == 3

    err = capsys.readouterr().err
    assert "catalog invalid:" in err
    assert "'channels'" in err


def test_doctor_catalog_with_crews_and_config_exits_0(tmp_path, capsys):
    """--catalog composes with --crews and --config without changing exits."""
    from lee_llm_router.doctor import main

    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "doctor",
                "--catalog",
                "--catalog-dir",
                str(tmp_path),
                "--crews",
                "--crews-file",
                str(CREWS_FIXTURE),
                "--config",
                str(FIXTURES / "llm_test.yaml"),
            ]
        )
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "OK catalog:" in out
    assert "OK crews:" in out
    assert "All checks passed" in out


# ---------------------------------------------------------------------------
# classify-failure (P3-1): deterministic D213 ruling 3 classification CLI
# ---------------------------------------------------------------------------

FAILURE_FIXTURES = FIXTURES / "staffing" / "failure-classify"


@pytest.mark.parametrize(
    ("class_name", "fixture_name"),
    [
        ("platform_timeout", "platform_timeout"),
        ("platform_env", "platform_env"),
        ("unaccounted_spend", "unaccounted_spend"),
        ("oracle_failed", "oracle_failed"),
        ("unknown", "unknown"),
        ("spec_rejected", "spec_rejected"),
        ("capability_rejected", "capability_rejected"),
    ],
)
def test_classify_failure_cli_record_fixture_prints_class(
    capsys, class_name, fixture_name
):
    """Every class has an exact evidence fixture the CLI classifies verbatim."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "classify-failure",
                "--record",
                str(FAILURE_FIXTURES / f"{fixture_name}.json"),
            ]
        )
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    if fixture_name == "unknown":
        # The unknown fixture's prose names both judgment classes; neither may
        # be inferred from text (D213 ruling 3).
        assert out.strip() == "unknown"
    else:
        assert out.strip() == fixture_name


@pytest.mark.parametrize(
    ("class_name", "fixture_name"),
    [
        ("platform_timeout", "platform_timeout"),
        ("platform_env", "platform_env"),
        ("unaccounted_spend", "unaccounted_spend"),
        ("oracle_failed", "oracle_failed"),
        ("unknown", "unknown"),
        ("spec_rejected", "spec_rejected"),
        ("capability_rejected", "capability_rejected"),
        (None, "none"),
    ],
)
def test_classify_failure_cli_json_record_fixture(capsys, class_name, fixture_name):
    """--json emits the exact compact {"failure_class": ...} object."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "classify-failure",
                "--record",
                str(FAILURE_FIXTURES / f"{fixture_name}.json"),
                "--json",
            ]
        )
    assert exc_info.value.code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"failure_class": class_name}


def test_classify_failure_cli_explicit_flags_and_none_text(capsys):
    """Explicit evidence flags classify without a record; no failure prints none."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["classify-failure", "--exit-code", "124", "--verdict", "fail"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == "platform_timeout"

    with pytest.raises(SystemExit) as exc_info:
        main(["classify-failure", "--verdict", "pass"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == "none"


def test_classify_failure_cli_json_none(capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["classify-failure", "--json", "--verdict", "pass"])
    assert exc_info.value.code == 0
    assert json.loads(capsys.readouterr().out) == {"failure_class": None}


def test_classify_failure_cli_explicit_judgment_with_review_verdict(capsys):
    """spec_rejected enters only through explicit --judgment after review."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "classify-failure",
                "--verdict",
                "fail",
                "--judgment",
                "spec_rejected",
                "--review-verdict",
                "fail",
            ]
        )
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == "spec_rejected"


def test_classify_failure_cli_judgment_never_inferred_from_text(capsys):
    """Prose naming a judgment class never classifies as spec_rejected."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "classify-failure",
                "--verdict",
                "fail",
                "--stderr",
                "the reviewer wrote: spec rejected, capability rejected",
            ]
        )
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == "oracle_failed"


def test_classify_failure_cli_judgment_without_review_verdict_exits_3(capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["classify-failure", "--judgment", "capability_rejected"])
    assert exc_info.value.code == 3
    err = capsys.readouterr().err
    assert err.startswith("classify-failure:")
    assert "review verdict" in err


def test_classify_failure_cli_judgment_with_pass_review_exits_3(capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "classify-failure",
                "--judgment",
                "spec_rejected",
                "--review-verdict",
                "pass",
            ]
        )
    assert exc_info.value.code == 3
    assert "cannot justify" in capsys.readouterr().err


def test_classify_failure_cli_unknown_judgment_value_exits_3(capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "classify-failure",
                "--judgment",
                "platform_env",
                "--review-verdict",
                "fail",
            ]
        )
    assert exc_info.value.code == 3
    assert "explicit judgment admits only" in capsys.readouterr().err


def test_classify_failure_cli_unreadable_record_exits_3(tmp_path, capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["classify-failure", "--record", str(tmp_path / "absent.json")])
    assert exc_info.value.code == 3
    err = capsys.readouterr().err
    assert err.startswith("classify-failure: record file cannot be read:")


def test_classify_failure_cli_malformed_record_exits_3(tmp_path, capsys):
    from lee_llm_router.doctor import main

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        main(["classify-failure", "--record", str(bad)])
    assert exc_info.value.code == 3
    assert "not valid JSON" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# next-action (P3-2): the /supervise loop step over the pure Phase 2 mapping
# ---------------------------------------------------------------------------


def _write_classify_output(path: Path, failure_class) -> Path:
    """Write exactly the JSON object 'classify-failure --json' prints."""
    path.write_text(
        json.dumps({"failure_class": failure_class}, separators=(",", ":")),
        encoding="utf-8",
    )
    return path


def _forbid_run_and_provider_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every subprocess, network, socket, and ledger call explode."""

    def fail_subprocess(*_args, **_kwargs):
        raise AssertionError("next-action must not start a subprocess")

    def fail_network(*_args, **_kwargs):
        raise AssertionError("next-action must not touch the network")

    def fail_ledger(*_args, **_kwargs):
        raise AssertionError("next-action must not write a ledger event")

    monkeypatch.setattr("subprocess.run", fail_subprocess)
    monkeypatch.setattr("subprocess.Popen", fail_subprocess)
    monkeypatch.setattr("subprocess.check_output", fail_subprocess)
    monkeypatch.setattr("subprocess.check_call", fail_subprocess)
    monkeypatch.setattr("urllib.request.urlopen", fail_network)
    monkeypatch.setattr("http.client.HTTPConnection.request", fail_network)
    monkeypatch.setattr("socket.socket.connect", fail_network)
    monkeypatch.setattr("lee_llm_router.events.append_event", fail_ledger)


@pytest.mark.parametrize(
    ("failure_class", "repair_count", "expected_action"),
    [
        ("platform_timeout", None, "retry_same_route_after_platform_repair"),
        ("platform_env", None, "retry_same_route_after_platform_repair"),
        ("spec_rejected", None, "return_to_planner"),
        ("capability_rejected", 0, "repair_same_route"),
        ("capability_rejected", 1, "escalate"),
        ("capability_rejected", 5, "escalate"),
        ("unaccounted_spend", None, "reconcile_then_retry"),
        ("oracle_failed", None, "supervisor_judgment"),
        ("unknown", None, "supervisor_judgment"),
        (None, None, "supervisor_judgment"),
    ],
)
def test_next_action_cli_maps_every_failure_class_exactly(
    tmp_path, capsys, failure_class, repair_count, expected_action
):
    """Every failure class maps through the pure Phase 2 mapping, exactly."""
    from lee_llm_router.doctor import main
    from lee_llm_router.staffing.next_action import next_action as pure_next_action

    args = [
        "next-action",
        "--input",
        str(_write_classify_output(tmp_path / "classified.json", failure_class)),
    ]
    if repair_count is not None:
        args += ["--repair-count", str(repair_count)]

    with pytest.raises(SystemExit) as exc_info:
        main(args)
    assert exc_info.value.code == 0

    payload = json.loads(capsys.readouterr().out)
    # The CLI calls the pure mapping: its output equals the pure function's
    # own decision for the same inputs, never a reimplemented one.
    attempt = None if repair_count is None else repair_count + 1
    assert payload == {
        "failure_class": failure_class,
        "repair_count": repair_count,
        "next_action": pure_next_action(failure_class, attempt),
    }
    assert payload["next_action"] == expected_action


def test_next_action_cli_matches_pure_function_on_every_sample(capsys, monkeypatch):
    """The CLI output is the pure mapping's output, key for key, value for value."""
    from lee_llm_router.doctor import main
    from lee_llm_router.staffing.next_action import next_action as pure_next_action

    samples = [
        ("platform_timeout", None),
        ("platform_env", 3),
        ("spec_rejected", 0),
        ("capability_rejected", 0),
        ("capability_rejected", 1),
        ("unaccounted_spend", 2),
        ("oracle_failed", 1),
        ("mystery", 7),
        (None, 0),
    ]
    for failure_class, repair_count in samples:
        args = ["next-action", "--input", "-"]
        if repair_count is not None:
            args += ["--repair-count", str(repair_count)]
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"failure_class": failure_class}))
        )
        with pytest.raises(SystemExit) as exc_info:
            main(args)
        assert exc_info.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_action"] == pure_next_action(
            failure_class,
            None if repair_count is None else repair_count + 1,
        )


def test_next_action_cli_capability_repair_count_boundary(tmp_path, capsys):
    """Count 0 is the first capability rejection; 1 or more escalates."""
    from lee_llm_router.doctor import main

    for repair_count, expected in [
        (0, "repair_same_route"),
        (1, "escalate"),
        (2, "escalate"),
        (99, "escalate"),
    ]:
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "next-action",
                    "--input",
                    str(
                        _write_classify_output(
                            tmp_path / f"cap-{repair_count}.json",
                            "capability_rejected",
                        )
                    ),
                    "--repair-count",
                    str(repair_count),
                ]
            )
        assert exc_info.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_action"] == expected


def test_next_action_cli_capability_without_count_fails_closed(tmp_path, capsys):
    """capability_rejected without a repair count fails closed, never guesses."""
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "next-action",
                "--input",
                str(
                    _write_classify_output(tmp_path / "cap.json", "capability_rejected")
                ),
            ]
        )
    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "failure_class": "capability_rejected",
        "repair_count": None,
        "next_action": "supervisor_judgment",
    }


def test_next_action_cli_repair_count_ignored_for_other_classes(tmp_path, capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "next-action",
                "--input",
                str(_write_classify_output(tmp_path / "spec.json", "spec_rejected")),
                "--repair-count",
                "4",
            ]
        )
    assert exc_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["next_action"] == "return_to_planner"


def test_next_action_cli_negative_repair_count_refused(tmp_path, capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "next-action",
                "--input",
                str(
                    _write_classify_output(tmp_path / "cap.json", "capability_rejected")
                ),
                "--repair-count",
                "-1",
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    err = captured.err
    assert err.startswith("next-action:")
    assert "nonnegative" in err


@pytest.mark.parametrize("bad_count", ["abc", "1.5", ""])
def test_next_action_cli_noninteger_repair_count_rejected_by_parser(
    tmp_path, capsys, bad_count
):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "next-action",
                "--input",
                str(
                    _write_classify_output(tmp_path / "cap.json", "capability_rejected")
                ),
                "--repair-count",
                bad_count,
            ]
        )
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid int value" in captured.err


def test_next_action_cli_stdin_contract(tmp_path, capsys, monkeypatch):
    """--input - reads the same single classify-failure JSON object from stdin."""
    from lee_llm_router.doctor import main

    monkeypatch.setattr(sys, "stdin", io.StringIO('{"failure_class": "platform_env"}'))
    with pytest.raises(SystemExit) as exc_info:
        main(["next-action", "--input", "-"])
    assert exc_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["next_action"] == (
        "retry_same_route_after_platform_repair"
    )


def test_next_action_cli_missing_input_file_refused(tmp_path, capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["next-action", "--input", str(tmp_path / "absent.json")])
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("next-action: input file cannot be read:")


@pytest.mark.parametrize(
    "body",
    [
        "{not json",
        "",
        "[]",
        '"platform_timeout"',
        "42",
        '{"failure_class": "platform_timeout", "extra": 1}',
        '{"next_action": "escalate"}',
        '{"failure_class": true}',
        '{"failure_class": 7}',
    ],
)
def test_next_action_cli_malformed_or_missing_json_refused(tmp_path, capsys, body):
    """Malformed, missing-key, non-object, and mis-typed inputs refuse."""
    from lee_llm_router.doctor import main

    bad = tmp_path / "bad.json"
    bad.write_text(body, encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        main(["next-action", "--input", str(bad)])
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("next-action:")
    assert len(captured.err.splitlines()) == 1


def test_next_action_cli_empty_stdin_refused(capsys, monkeypatch):
    from lee_llm_router.doctor import main

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as exc_info:
        main(["next-action", "--input", "-"])
    assert exc_info.value.code == 3
    assert "not valid JSON" in capsys.readouterr().err


def test_next_action_cli_never_runs_or_calls_a_provider(tmp_path, monkeypatch, capsys):
    """A successful mapping launches nothing: no subprocess, network, ledger."""
    from lee_llm_router.doctor import main

    _forbid_run_and_provider_calls(monkeypatch)
    ledger = tmp_path / "events.jsonl"
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(ledger))

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "next-action",
                "--input",
                str(
                    _write_classify_output(tmp_path / "classified.json", "platform_env")
                ),
            ]
        )
    assert exc_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["next_action"] == (
        "retry_same_route_after_platform_repair"
    )
    assert not ledger.exists()


def test_next_action_cli_never_runs_or_calls_a_provider_even_on_refusal(
    tmp_path, monkeypatch, capsys
):
    """Refusals launch nothing either."""
    from lee_llm_router.doctor import main

    _forbid_run_and_provider_calls(monkeypatch)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["next-action", "--input", str(bad)])
    assert exc_info.value.code == 3
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# staff --from-packet (P3-3 / D213 ruling 2)
# ---------------------------------------------------------------------------


def test_staff_from_packet_derives_and_records_class_overrides(tmp_path, capsys):
    """The packet class feeds the existing staff service without a route map."""
    from lee_llm_router.doctor import _default_catalog_dir, main

    packet = tmp_path / "packet.md"
    packet.write_text(
        """\
- Kind: impl
- Declared size: 2 files, at most 80 changed lines
- Owned paths: `src/database.py`, `tests/test_database.py`
- Oracle: `.venv/bin/pytest -q tests/test_database.py`
- Review: independent review required after the oracle passes.
""",
        encoding="utf-8",
    )
    snapshot = _write_snapshot(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "staff",
                "--from-packet",
                str(packet),
                "--size-band",
                "l",
                "--at",
                "2026-10-01",
                "--availability-file",
                str(snapshot),
                "--catalog-dir",
                str(_default_catalog_dir()),
                "--json",
            ]
        )
    assert exc_info.value.code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["class_key"] == "impl/deterministic/persistence/l/python"
    assert payload["class_derivation"]["class"]["oracle_type"] == "deterministic"
    assert payload["overrides"] == {"size_band": "l"}
    assert payload["class_derivation"]["domain_matches"] == [
        {"keyword": "database", "tag": "persistence"},
    ]
    assert "selected_route" in payload
    assert "selected_route" not in payload["class_derivation"]


def test_staff_from_packet_malformed_input_exits_3_without_output(tmp_path, capsys):
    """Malformed packet input fails closed through the normal staff boundary."""
    from lee_llm_router.doctor import main

    packet = tmp_path / "bad-packet.md"
    packet.write_text("- Owned paths: `src/a.py`\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["staff", "--from-packet", str(packet), "--json"])

    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("staff: packet class invalid:")
    assert len(captured.err.splitlines()) == 1


@pytest.mark.parametrize(
    "args",
    [
        ["--size-band", "l"],
        ["--from-packet", "packet.md", "--mode", "crew", "luna-sol"],
    ],
)
def test_staff_packet_options_do_not_change_existing_mode_contracts(
    tmp_path, capsys, args
):
    """Packet-only options are rejected rather than altering legacy modes."""
    from lee_llm_router.doctor import main

    (tmp_path / "packet.md").write_text(
        "- Kind: impl\n- Owned paths: `src/a.py`\n", encoding="utf-8"
    )
    resolved = [
        str(tmp_path / value) if value == "packet.md" else value for value in args
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["staff", *resolved])

    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1


# ---------------------------------------------------------------------------
# census (P3-4 / D213 ruling 4): live-run listing and stale cleanup
# ---------------------------------------------------------------------------


def _census_registry_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> str:
    """Redirect the per-host run registry to a scratch directory."""
    registry = str(tmp_path / "run-registry")
    monkeypatch.setenv("LEE_LLM_ROUTER_RUN_REGISTRY_DIR", registry)
    return registry


def test_census_cli_empty_registry_reports_nothing_live(tmp_path, monkeypatch, capsys):
    from lee_llm_router.doctor import main

    _census_registry_env(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(["census", "--json"])
    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"live": [], "cleaned": []}


def test_census_cli_lists_live_run_and_cleans_stale_pid_with_note(
    tmp_path, monkeypatch, capsys
):
    """census lists genuinely live rows, cleans stale pids, notes each."""
    import os

    from lee_llm_router.doctor import main
    from lee_llm_router.staffing.census import register_run

    registry = _census_registry_env(monkeypatch, tmp_path)
    live = register_run(
        route_id="codex-gpt-5-6-sol-low-openai-sub",
        packet_id="sha256:live-packet",
        owned_paths=[str(tmp_path / "owned-tree")],
        pid=os.getpid(),  # genuinely this process: census must keep it
        registry_dir=registry,
    )
    # A pid far beyond every platform's pid_max cannot exist.
    stale = register_run(
        route_id="pi-z-ai-glm-5-3-flash-openrouter",
        packet_id="sha256:stale-packet",
        owned_paths=[str(tmp_path / "other-tree")],
        pid=999999999,
        registry_dir=registry,
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["census", "--json"])
    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)

    assert [row["pid"] for row in payload["live"]] == [os.getpid()]
    live_row = payload["live"][0]
    assert live_row["route_id"] == "codex-gpt-5-6-sol-low-openai-sub"
    assert live_row["packet_id"] == "sha256:live-packet"
    assert live_row["owned_paths"] == [str(tmp_path / "owned-tree")]
    assert live_row["registry_path"] == str(live.path)

    assert len(payload["cleaned"]) == 1
    cleaned = payload["cleaned"][0]
    assert cleaned["pid"] == 999999999
    assert "no longer exists" in cleaned["reason"]
    assert cleaned["registry_path"] == str(stale.path)

    assert live.path is not None and live.path.exists()
    assert stale.path is not None and not stale.path.exists()


def test_census_cli_text_output_cleans_stale_with_note(tmp_path, monkeypatch, capsys):
    from lee_llm_router.doctor import main
    from lee_llm_router.staffing.census import register_run

    registry = _census_registry_env(monkeypatch, tmp_path)
    register_run(
        route_id="route-a",
        packet_id="sha256:stale",
        owned_paths=[str(tmp_path / "tree")],
        pid=999999999,
        registry_dir=registry,
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["census"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "0 live run(s), 1 stale record(s) cleaned" in out
    assert "cleaned stale record pid 999999999" in out
    assert "no longer exists" in out


def test_census_cli_corrupt_registry_record_exits_3(tmp_path, monkeypatch, capsys):
    from lee_llm_router.doctor import main

    registry = _census_registry_env(monkeypatch, tmp_path)
    from pathlib import Path

    Path(registry).mkdir(parents=True, exist_ok=True)
    (Path(registry) / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["census"])
    assert exc_info.value.code == 3
    assert "not valid JSON" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# run --instance CLI (M3-3)
# ---------------------------------------------------------------------------


def test_run_cli_instance_forwarded_to_select_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--instance parses and reaches select_route with the supplied instance id."""
    import lee_llm_router.staffing.run as run_module
    from lee_llm_router.doctor import main

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")
    snapshot = _write_snapshot(tmp_path)

    recorded_instance_id: dict[str, str | None] = {}
    orig_select_route = run_module.select_route

    def spy_select_route(*args, **kwargs):
        recorded_instance_id["value"] = kwargs.get("instance_id")
        return orig_select_route(*args, **kwargs)

    monkeypatch.setattr(run_module, "select_route", spy_select_route)

    # Calling with --instance test-pin-id will fail selection at test-pin-id,
    # cleanly proving that args.instance reached select_route(..., instance_id=...).
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "codex-gpt-5-6-sol-low-openai-sub",
                "--instance",
                "test-pin-id",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )

    assert exc_info.value.code == 3
    assert recorded_instance_id["value"] == "test-pin-id"


def test_run_cli_omitted_instance_defaults_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --instance is omitted, instance_id=None reaches select_route."""
    import lee_llm_router.staffing.run as run_module
    from lee_llm_router.doctor import main

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")
    snapshot = _write_snapshot(tmp_path)

    recorded_instance_id: dict[str, str | None] = {}
    orig_select_route = run_module.select_route

    def spy_select_route(*args, **kwargs):
        recorded_instance_id["value"] = kwargs.get("instance_id")
        return orig_select_route(*args, **kwargs)

    monkeypatch.setattr(run_module, "select_route", spy_select_route)

    # Stop after select_route by raising a dummy exception from the spy or letting
    # it proceed. Since we only want to test forwarding, we can let it raise exit 3.
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "no-such-route",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )

    assert recorded_instance_id["value"] is None


def test_run_cli_invalid_instance_refused_exit_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invalid --instance produces documented exit-3 refusal at the CLI boundary."""
    from lee_llm_router.doctor import main

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")
    snapshot = _write_snapshot(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "codex-gpt-5-6-sol-low-openai-sub",
                "--instance",
                "nonexistent-inst",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )

    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "run:" in captured.err
    assert "--instance 'nonexistent-inst'" in captured.err
    assert "does not match any enabled instance" in captured.err


# ---------------------------------------------------------------------------
# run credential staging at dispatch (M4-2)
# ---------------------------------------------------------------------------


def test_run_dispatch_staged_credential_visible_to_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-instance run stages credential to temporary HOME visible to
    popen for pi and opencode.
    """
    from lee_llm_router.doctor import main
    from lee_llm_router.staffing import credentials
    from tests.test_staffing_run import LaunchRecorder

    # Isolate credentials directory
    credentials_dir = tmp_path / "credentials"
    monkeypatch.setattr(credentials, "DEFAULT_CREDENTIALS_DIR", credentials_dir)

    # Write fake credential files
    cred_file_pi = credentials_dir / "opencode-go" / "a.json"
    cred_file_pi.parent.mkdir(parents=True, exist_ok=True)
    cred_file_pi.write_text(
        json.dumps(
            {
                "type": "api",
                "key": "fake-token-a",
                "instance_id": "a",
                "placed_at": "2026-09-15T00:00:00Z",
                "placed_by": "test",
            }
        ),
        encoding="utf-8",
    )

    cred_file_oc = credentials_dir / "opencode-go" / "b.json"
    cred_file_oc.write_text(
        json.dumps(
            {
                "type": "api",
                "key": "fake-token-b",
                "instance_id": "b",
                "placed_at": "2026-09-15T00:00:00Z",
                "placed_by": "test",
            }
        ),
        encoding="utf-8",
    )

    # Isolate registry and ledgers
    registry_dir = tmp_path / "run-registry"
    monkeypatch.setenv("LEE_LLM_ROUTER_RUN_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(tmp_path / "events.jsonl"))

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")

    subscriptions = [
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80.0,
            "instance": "a",
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 75.0,
            "instance": "b",
        },
    ]
    snapshot = _write_snapshot(tmp_path, subscriptions=subscriptions)

    # 1. Test Pi harness: pi-glm-5-3-flash-opencode-go on instance a
    captured_home_during_call: list[Path] = []
    auth_file_contents_during_call: list[str] = []

    launcher_pi = LaunchRecorder()

    def spy_popen_pi(argv, **kwargs):
        env = kwargs.get("env", {})
        home = Path(env["HOME"])
        captured_home_during_call.append(home)
        auth_file = home / ".pi/agent/auth.json"
        if auth_file.is_file():
            auth_file_contents_during_call.append(auth_file.read_text(encoding="utf-8"))
        return launcher_pi(argv, **kwargs)

    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", spy_popen_pi)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "pi-glm-5-3-flash-opencode-go",
                "--instance",
                "a",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )
    assert exc_info.value.code == 3
    assert len(launcher_pi.processes) == 1
    proc = launcher_pi.processes[0]
    child_env = proc.popen_kwargs.get("env")
    assert child_env is not None
    assert captured_home_during_call
    staged_home_pi = captured_home_during_call[0]
    assert child_env["HOME"] == str(staged_home_pi)
    assert child_env.get("PI_CODING_AGENT_DIR") == str(staged_home_pi / ".pi/agent")
    assert len(auth_file_contents_during_call) == 1
    assert json.loads(auth_file_contents_during_call[0]) == {
        "opencode-go": {"type": "api_key", "key": "fake-token-a"}
    }
    # And staging directory is deleted after dispatch
    assert not staged_home_pi.exists()

    # 2. Test OpenCode harness:
    # opencode-opencode-go-qwen3-7-plus-opencode-go on instance b
    captured_home_during_call.clear()
    auth_file_contents_during_call.clear()

    launcher_oc = LaunchRecorder()

    def spy_popen_oc(argv, **kwargs):
        env = kwargs.get("env", {})
        home = Path(env["HOME"])
        captured_home_during_call.append(home)
        auth_file = home / ".local/share/opencode/auth.json"
        if auth_file.is_file():
            auth_file_contents_during_call.append(auth_file.read_text(encoding="utf-8"))
        return launcher_oc(argv, **kwargs)

    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", spy_popen_oc)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "opencode-opencode-go-qwen3-7-plus-opencode-go",
                "--instance",
                "b",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )
    assert exc_info.value.code == 3
    assert len(launcher_oc.processes) == 1
    proc_oc = launcher_oc.processes[0]
    child_env_oc = proc_oc.popen_kwargs.get("env")
    assert child_env_oc is not None
    staged_home_oc = captured_home_during_call[0]
    assert len(auth_file_contents_during_call) == 1
    assert json.loads(auth_file_contents_during_call[0]) == {
        "opencode-go": {"type": "api", "key": "fake-token-b"}
    }
    assert not staged_home_oc.exists()


def test_run_dispatch_missing_credential_fails_closed_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing credential file fails closed before launch (exit 3),
    registering nothing.
    """
    import lee_llm_router.staffing.census as census_mod
    from lee_llm_router.doctor import main
    from lee_llm_router.staffing import credentials
    from tests.test_staffing_run import LaunchRecorder

    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir(parents=True, exist_ok=True)
    # Do not write any credential file
    monkeypatch.setattr(credentials, "DEFAULT_CREDENTIALS_DIR", credentials_dir)

    registry_dir = tmp_path / "run-registry"
    monkeypatch.setenv("LEE_LLM_ROUTER_RUN_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(tmp_path / "events.jsonl"))

    register_run_called = False
    orig_register = census_mod.register_run

    def spy_register_run(*args, **kwargs):
        nonlocal register_run_called
        register_run_called = True
        return orig_register(*args, **kwargs)

    monkeypatch.setattr(census_mod, "register_run", spy_register_run)

    launcher = LaunchRecorder()
    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", launcher)

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")

    subscriptions = [
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80.0,
            "instance": "a",
        },
    ]
    snapshot = _write_snapshot(tmp_path, subscriptions=subscriptions)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "pi-glm-5-3-flash-opencode-go",
                "--instance",
                "a",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "run:" in captured.err
    assert "credential staging failed:" in captured.err
    assert "Credential file does not exist" in captured.err

    # Crucially: register_run was never called and run registry is empty
    assert not register_run_called
    assert not registry_dir.exists() or list(registry_dir.iterdir()) == []
    # And popen was never attempted
    assert launcher.processes == []


def test_run_dispatch_single_instance_channel_unchanged_no_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Channel with no declared instances behaves identically without
    credential lookup.
    """
    from lee_llm_router.doctor import main
    from lee_llm_router.staffing import credentials
    from tests.test_staffing_run import CODEX_RECEIPT_STDOUT, LaunchRecorder

    # Credentials directory does not even exist
    credentials_dir = tmp_path / "nonexistent-credentials"
    monkeypatch.setattr(credentials, "DEFAULT_CREDENTIALS_DIR", credentials_dir)

    registry_dir = tmp_path / "run-registry"
    monkeypatch.setenv("LEE_LLM_ROUTER_RUN_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(tmp_path / "events.jsonl"))

    launcher = LaunchRecorder(chunks=[CODEX_RECEIPT_STDOUT.encode("utf-8")])
    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", launcher)

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")
    snapshot = _write_snapshot(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "codex-gpt-5-6-sol-low-openai-sub",
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )
    assert exc_info.value.code == 3
    assert len(launcher.processes) == 1
    proc = launcher.processes[0]
    # No env keyword argument forced
    assert "env" not in proc.popen_kwargs


def test_run_dispatch_unsupported_harness_fails_closed_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unsupported harness on declared instances channel fails closed
    before registration.
    """
    import shutil

    import yaml

    import lee_llm_router.staffing.census as census_mod
    from lee_llm_router.doctor import _default_catalog_dir, main
    from lee_llm_router.staffing import credentials
    from tests.test_staffing_run import LaunchRecorder

    # Setup scratch catalog with an unsupported harness on opencode-go
    catalog_dest = tmp_path / "catalog"
    shutil.copytree(_default_catalog_dir(), catalog_dest)
    routes_path = catalog_dest / "routes.yaml"
    routes_data = yaml.safe_load(routes_path.read_text(encoding="utf-8"))
    for r in routes_data["routes"]:
        if r["route_id"] == "pi-glm-5-3-flash-opencode-go":
            r["harness"] = "omp"  # unsupported for staging
    routes_path.write_text(yaml.safe_dump(routes_data), encoding="utf-8")

    credentials_dir = tmp_path / "credentials"
    monkeypatch.setattr(credentials, "DEFAULT_CREDENTIALS_DIR", credentials_dir)
    cred_file = credentials_dir / "opencode-go" / "a.json"
    cred_file.parent.mkdir(parents=True, exist_ok=True)
    cred_file.write_text(
        json.dumps({"type": "api", "key": "fake-token"}), encoding="utf-8"
    )

    registry_dir = tmp_path / "run-registry"
    monkeypatch.setenv("LEE_LLM_ROUTER_RUN_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(tmp_path / "events.jsonl"))

    register_run_called = False
    orig_register = census_mod.register_run

    def spy_register_run(*args, **kwargs):
        nonlocal register_run_called
        register_run_called = True
        return orig_register(*args, **kwargs)

    monkeypatch.setattr(census_mod, "register_run", spy_register_run)

    launcher = LaunchRecorder()
    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", launcher)

    packet = tmp_path / "packet.md"
    packet.write_text("- Kind: impl\n", encoding="utf-8")

    subscriptions = [
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80.0,
            "instance": "a",
        },
    ]
    snapshot = _write_snapshot(tmp_path, subscriptions=subscriptions)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/python",
                "--packet",
                str(packet),
                "--route",
                "pi-glm-5-3-flash-opencode-go",
                "--instance",
                "a",
                "--catalog-dir",
                str(catalog_dest),
                "--availability-file",
                str(snapshot),
                "--at",
                "2026-09-15",
                "--owned-paths",
                str(packet),
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "credential staging failed:" in captured.err
    assert "Credential staging is not supported for harness 'omp'" in captured.err
    assert not register_run_called
    assert launcher.processes == []
