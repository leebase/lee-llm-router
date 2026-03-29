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
