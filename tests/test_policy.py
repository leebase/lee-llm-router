"""Tests for the crew-aware routing policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig
from lee_llm_router.crews import load_crews
from lee_llm_router.policy import CrewRoutingPolicy, ProviderChoice
from lee_llm_router.providers.base import FailureType, LLMRouterError

FIXTURE = Path(__file__).parent / "fixtures" / "crews.yaml"


def _config(**providers: str) -> LLMConfig:
    entries = {
        name: ProviderConfig(name=name, type=ptype, raw={})
        for name, ptype in providers.items()
    }
    first = next(iter(entries), "none")
    return LLMConfig(
        default_role="author",
        providers=entries,
        roles={"author": RoleConfig(name="author", provider=first)},
    )


@pytest.fixture()
def crews():
    return load_crews(FIXTURE)


@pytest.fixture()
def config() -> LLMConfig:
    return _config(codex="codex_cli", claude="claude_code_cli")


def test_strict_mode_attribute(crews) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    assert policy.mode == "strict"


def test_choose_returns_named_worker_provider(crews, config) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    choice = policy.choose("envision", config)

    assert isinstance(choice, ProviderChoice)
    assert choice.provider_name == "codex"
    assert choice.request_overrides == {"model": "gpt-5.6-sol", "effort": "high"}


def test_choose_crosses_vendor_for_a_claude_stage(crews, config) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    choice = policy.choose("ideate", config)

    assert choice.provider_name == "claude"
    assert choice.request_overrides["model"] == "claude-opus-5"


def test_choose_uses_stage_primary_for_list_valued_stage(crews, config) -> None:
    policy = CrewRoutingPolicy("test-flex", crews=crews)

    choice = policy.choose("envision", config)

    assert choice.provider_name == "codex"
    assert choice.request_overrides["model"] == "gpt-5.6-luna"


def test_provider_alias_type_matches(crews) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    choice = policy.choose("ideate", _config(anthropic="claude_code"))

    assert choice.provider_name == "anthropic"


def test_lazy_load_from_crews_path(config) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews_path=FIXTURE)

    assert policy.choose("author", config).provider_name == "codex"


def test_unknown_crew_raises_provider_error(crews, config) -> None:
    policy = CrewRoutingPolicy("nope", crews=crews)

    with pytest.raises(LLMRouterError) as exc_info:
        policy.choose("envision", config)

    assert exc_info.value.failure_type is FailureType.PROVIDER_ERROR
    assert "nope" in str(exc_info.value)


def test_unknown_stage_raises_provider_error(crews, config) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    with pytest.raises(LLMRouterError) as exc_info:
        policy.choose("summarize", config)

    assert exc_info.value.failure_type is FailureType.PROVIDER_ERROR
    assert "summarize" in str(exc_info.value)


def test_missing_provider_type_names_crew_stage_and_worker(crews) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    with pytest.raises(LLMRouterError) as exc_info:
        policy.choose("ideate", _config(codex="codex_cli"))

    message = str(exc_info.value)
    assert exc_info.value.failure_type is FailureType.PROVIDER_ERROR
    assert "test-flagship" in message
    assert "ideate" in message
    assert "claude_opus5_high" in message
    assert "claude_code_cli" in message


# ---------------------------------------------------------------------------
# Strict mode must not inherit the role's fallback chain (H1)
# ---------------------------------------------------------------------------


def test_provider_choice_allows_fallback_by_default() -> None:
    assert ProviderChoice(provider_name="mock").allow_fallback is True


def test_crew_choice_disallows_fallback(crews, config) -> None:
    policy = CrewRoutingPolicy("test-flagship", crews=crews)

    choice = policy.choose("envision", config)

    assert choice.allow_fallback is False


def test_simple_policy_choice_allows_fallback() -> None:
    from lee_llm_router.policy import SimpleRoutingPolicy

    choice = SimpleRoutingPolicy().choose("author", _config(codex="codex_cli"))

    assert choice.allow_fallback is True
