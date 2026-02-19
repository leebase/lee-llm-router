"""Unit tests for the provider layer (Sprint 2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError, should_retry
from lee_llm_router.providers.mock import MockProvider
from lee_llm_router.providers.registry import available, get, register
from lee_llm_router.response import LLMRequest, LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_request(**kwargs) -> LLMRequest:
    defaults = dict(
        role="test",
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
    )
    defaults.update(kwargs)
    return LLMRequest(**defaults)


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------


def test_mock_provider_returns_response():
    provider = MockProvider()
    request = make_request()
    response = provider.complete(request, {})

    assert isinstance(response, LLMResponse)
    assert isinstance(response.text, str)
    assert len(response.text) > 0
    assert response.request_id == request.request_id
    assert response.provider == "mock"


def test_mock_provider_custom_response_text():
    provider = MockProvider()
    request = make_request()
    response = provider.complete(request, {"response_text": "custom answer"})
    assert response.text == "custom answer"


def test_mock_provider_raises_on_flag():
    provider = MockProvider()
    request = make_request()
    with pytest.raises(LLMRouterError) as exc_info:
        provider.complete(request, {"raise_timeout": True})
    assert exc_info.value.failure_type == FailureType.TIMEOUT


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_roundtrip():
    class SentinelProvider:
        name = "_sentinel_test"
        supported_types = {"_sentinel_test"}

    register("_sentinel_test", SentinelProvider)
    assert get("_sentinel_test") is SentinelProvider


def test_registry_builtins_registered():
    names = available()
    assert "mock" in names
    assert "openrouter_http" in names
    assert "codex_cli" in names


def test_registry_missing_provider_raises():
    with pytest.raises(KeyError, match="not_a_real_provider"):
        get("not_a_real_provider")


# ---------------------------------------------------------------------------
# HTTP Provider
# ---------------------------------------------------------------------------


def test_http_provider_success():
    from lee_llm_router.providers.http import OpenRouterHTTPProvider

    provider = OpenRouterHTTPProvider()
    request = make_request(model="gpt-4o")
    config = {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Hello, world!"}}],
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch("lee_llm_router.providers.http.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.post.return_value = mock_resp
        response = provider.complete(request, config)

    assert response.text == "Hello, world!"
    assert response.model == "gpt-4o"
    assert response.usage.total_tokens == 15
    assert response.provider == "openrouter_http"


def test_http_provider_timeout_raises_llm_router_error():
    import httpx as httpx_lib

    from lee_llm_router.providers.http import OpenRouterHTTPProvider

    provider = OpenRouterHTTPProvider()
    request = make_request(model="gpt-4o", timeout=5.0)
    config = {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    }

    with patch("lee_llm_router.providers.http.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.post.side_effect = httpx_lib.TimeoutException("")
        with pytest.raises(LLMRouterError) as exc_info:
            provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.TIMEOUT


def test_http_provider_rate_limit_raises():
    from lee_llm_router.providers.http import OpenRouterHTTPProvider

    provider = OpenRouterHTTPProvider()
    request = make_request(model="gpt-4o")
    config = {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limited"

    with patch("lee_llm_router.providers.http.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.post.return_value = mock_resp
        with pytest.raises(LLMRouterError) as exc_info:
            provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.RATE_LIMIT


# ---------------------------------------------------------------------------
# Codex CLI Provider
# ---------------------------------------------------------------------------


def test_codex_cli_provider_success():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = {"command": "codex", "model_flag": "--model", "output_flag": "--output-last-message"}

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "This is the codex response\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        response = provider.complete(request, config)

    assert response.text == "This is the codex response"
    assert response.provider == "codex_cli"


def test_codex_cli_binary_not_found_raises():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request()
    config = {"command": "codex_not_installed"}

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(LLMRouterError) as exc_info:
            provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# Failure type contract
# ---------------------------------------------------------------------------


def test_failure_type_contract_violation_not_retried():
    """CONTRACT_VIOLATION must never be retried; other types may be."""
    cv_error = LLMRouterError(
        "json parse failed", failure_type=FailureType.CONTRACT_VIOLATION
    )
    timeout_error = LLMRouterError("timed out", failure_type=FailureType.TIMEOUT)
    rate_error = LLMRouterError("429", failure_type=FailureType.RATE_LIMIT)

    assert not should_retry(cv_error)
    assert should_retry(timeout_error)
    assert should_retry(rate_error)


def test_llm_router_error_carries_failure_type():
    err = LLMRouterError("something failed", failure_type=FailureType.PROVIDER_ERROR)
    assert err.failure_type == FailureType.PROVIDER_ERROR
    assert "something failed" in str(err)
