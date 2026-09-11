"""Doctor CLI tests (Sprint 4 + Sprint 6 export workflow)."""

from __future__ import annotations

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
