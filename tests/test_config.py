"""Tests for the YAML config loader (Sprint 3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lee_llm_router.config import ConfigError, LLMConfig, load_config

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_config_valid():
    config = load_config(FIXTURES / "llm_test.yaml")

    assert isinstance(config, LLMConfig)
    assert config.default_role == "test"
    assert "mock" in config.providers
    assert config.providers["mock"].type == "mock"
    assert "test" in config.roles
    assert config.roles["test"].provider == "mock"
    assert config.roles["test"].temperature == 0.1
    assert config.roles["test"].model == "mock-model"


def test_env_interpolation(monkeypatch, tmp_path):
    """api_key_env: config stores the env var *name*; value is read by provider at call time."""
    monkeypatch.setenv("MY_TEST_KEY", "test-secret-value")

    config_file = tmp_path / "llm.yaml"
    config_file.write_text("""\
llm:
  default_role: http_role
  providers:
    openrouter:
      type: openrouter_http
      base_url: https://openrouter.ai/api/v1
      api_key_env: MY_TEST_KEY
  roles:
    http_role:
      provider: openrouter
      model: gpt-4o
""")
    config = load_config(config_file)

    # Config stores the var name, not the secret
    assert config.providers["openrouter"].raw["api_key_env"] == "MY_TEST_KEY"
    # The actual value is available in the environment at call time
    assert os.environ["MY_TEST_KEY"] == "test-secret-value"


def test_missing_required_field_raises(tmp_path):
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("""\
llm:
  providers:
    mock:
      type: mock
  roles:
    test:
      provider: mock
""")
    with pytest.raises(ConfigError, match="default_role"):
        load_config(config_file)


def test_role_inherits_provider_defaults(tmp_path):
    """A role with only 'provider' set gets dataclass defaults for all other fields."""
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text("""\
llm:
  default_role: minimal
  providers:
    mock:
      type: mock
  roles:
    minimal:
      provider: mock
""")
    config = load_config(config_file)
    role = config.roles["minimal"]

    assert role.model == ""
    assert role.temperature == 0.2
    assert role.json_mode is False
    assert role.max_tokens is None
    assert role.timeout == 60.0
    assert role.fallback_providers == []


def test_unknown_provider_reference_raises(tmp_path):
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("""\
llm:
  default_role: test
  providers:
    mock:
      type: mock
  roles:
    test:
      provider: nonexistent_provider
""")
    with pytest.raises(ConfigError, match="nonexistent_provider"):
        load_config(config_file)


def test_missing_top_level_llm_key_raises(tmp_path):
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("other_key: value\n")
    with pytest.raises(ConfigError, match="top-level 'llm' key"):
        load_config(config_file)
