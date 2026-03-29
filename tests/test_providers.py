"""Unit tests for the provider layer (Sprint 2)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError, should_retry
from lee_llm_router.providers.mock import MockProvider
from lee_llm_router.providers.registry import available, get, register
from lee_llm_router.response import LLMRequest, LLMResponse

FIXTURES = Path(__file__).parent / "fixtures"
PI_HARNESS = FIXTURES / "pi_harness.py"

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


def make_pi_harness_config(mode: str, **overrides):
    config = {
        "command": sys.executable,
        "args": [str(PI_HARNESS), mode],
        "model_flag": "--model",
        "output_flag": "--output-last-message",
    }
    config.update(overrides)
    return config


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
    assert "openai_codex_subscription_http" in names
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
        MockClient.return_value.__enter__.return_value.post.side_effect = (
            httpx_lib.TimeoutException("")
        )
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


def test_openai_codex_subscription_provider_success(monkeypatch):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(model="gpt-5.3-codex")
    config = {
        "base_url": "https://chatgpt.com/backend-api/codex",
        "access_token_env": "OPENAI_CODEX_ACCESS_TOKEN",
        "account_id_env": "OPENAI_CODEX_ACCOUNT_ID",
    }
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "token-123")
    monkeypatch.setenv("OPENAI_CODEX_ACCOUNT_ID", "acct-xyz")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_text.return_value = [
        'data: {"type":"response.output_text.delta","delta":"Hello from "}\n\n',
        'data: {"type":"response.output_text.delta","delta":"codex subscription"}\n\n',
        (
            'data: {"type":"response.completed","response":{"id":"resp_123",'
            '"model":"gpt-5.3-codex","output_text":"Hello from codex subscription",'
            '"usage":{"input_tokens":11,"output_tokens":7,"total_tokens":18}}}\n\n'
        ),
        "data: [DONE]\n\n",
    ]

    with patch(
        "lee_llm_router.providers.openai_codex_subscription.httpx.Client"
    ) as MockClient:
        client = MockClient.return_value.__enter__.return_value
        client.stream.return_value.__enter__.return_value = mock_resp

        response = provider.complete(request, config)

    assert response.text == "Hello from codex subscription"
    assert response.model == "gpt-5.3-codex"
    assert response.usage.total_tokens == 18
    assert response.provider == "openai_codex_subscription_http"

    _, kwargs = client.stream.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer token-123"
    assert kwargs["headers"]["ChatGPT-Account-Id"] == "acct-xyz"
    assert kwargs["json"]["store"] is False
    assert kwargs["json"]["stream"] is True
    assert kwargs["json"]["instructions"] == "You are a helpful assistant."
    assert kwargs["headers"]["Accept"] == "text/event-stream"
    assert "temperature" not in kwargs["json"]


def test_openai_codex_subscription_provider_lifts_system_message_into_instructions(
    monkeypatch,
):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(
        model="gpt-5.4",
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Plan the tutorial."},
        ],
    )
    config = {
        "base_url": "https://chatgpt.com/backend-api/codex",
        "access_token_env": "OPENAI_CODEX_ACCESS_TOKEN",
    }
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "token-123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_text.return_value = [
        (
            'data: {"type":"response.completed","response":{"model":"gpt-5.4",'
            '"output_text":"planned"}}\n\n'
        )
    ]

    with patch(
        "lee_llm_router.providers.openai_codex_subscription.httpx.Client"
    ) as MockClient:
        client = MockClient.return_value.__enter__.return_value
        client.stream.return_value.__enter__.return_value = mock_resp

        provider.complete(request, config)

    _, kwargs = client.stream.call_args
    assert kwargs["json"]["instructions"] == "Return JSON only."
    assert kwargs["json"]["input"] == [
        {"role": "user", "content": "Plan the tutorial."}
    ]


def test_openai_codex_subscription_provider_reads_codex_auth_file(
    monkeypatch, tmp_path
):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(model="gpt-5.3-codex")

    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("""\
{
  "tokens": {
    "access_token": "file-token-abc",
    "refresh_token": "refresh-xyz",
    "account_id": "acct-file"
  }
}
""")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_text.return_value = [
        (
            'data: {"type":"response.completed","response":{"model":"gpt-5.3-codex",'
            '"output":[{"type":"message","content":[{"type":"output_text",'
            '"text":"ok from file auth"}]}]}}\n\n'
        )
    ]

    with patch(
        "lee_llm_router.providers.openai_codex_subscription.httpx.Client"
    ) as MockClient:
        client = MockClient.return_value.__enter__.return_value
        client.stream.return_value.__enter__.return_value = mock_resp

        response = provider.complete(
            request, {"base_url": "https://chatgpt.com/backend-api"}
        )

    assert response.text == "ok from file auth"
    _, kwargs = client.stream.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer file-token-abc"
    assert kwargs["headers"]["ChatGPT-Account-Id"] == "acct-file"
    assert kwargs["json"]["store"] is False


def test_openai_codex_subscription_provider_assembles_stream_without_final_response(
    monkeypatch,
):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(model="gpt-5.4")
    config = {
        "base_url": "https://chatgpt.com/backend-api/codex",
        "access_token_env": "OPENAI_CODEX_ACCESS_TOKEN",
    }
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "token-123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_text.return_value = [
        'data: {"type":"response.output_text.delta","delta":"hello "}\n\n',
        'data: {"type":"response.output_text.delta","delta":"world"}\n\n',
        "data: [DONE]\n\n",
    ]

    with patch(
        "lee_llm_router.providers.openai_codex_subscription.httpx.Client"
    ) as MockClient:
        client = MockClient.return_value.__enter__.return_value
        client.stream.return_value.__enter__.return_value = mock_resp

        response = provider.complete(request, config)

    assert response.text == "hello world"
    assert response.model == "gpt-5.4"


def test_openai_codex_subscription_provider_handles_crlf_sse_chunks(monkeypatch):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(model="gpt-5.4")
    config = {
        "base_url": "https://chatgpt.com/backend-api/codex",
        "access_token_env": "OPENAI_CODEX_ACCESS_TOKEN",
    }
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "token-123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_text.return_value = [
        'data: {"type":"response.output_text.delta","delta":"hello"}\r\n\r\n',
        (
            'data: {"type":"response.completed","response":{"model":"gpt-5.4",'
            '"output_text":"hello"}}\r\n\r\n'
        ),
        "data: [DONE]\r\n\r\n",
    ]

    with patch(
        "lee_llm_router.providers.openai_codex_subscription.httpx.Client"
    ) as MockClient:
        client = MockClient.return_value.__enter__.return_value
        client.stream.return_value.__enter__.return_value = mock_resp

        response = provider.complete(request, config)

    assert response.text == "hello"
    _, kwargs = client.stream.call_args
    assert kwargs["headers"]["Accept"] == "text/event-stream"


def test_openai_codex_subscription_provider_enforces_wall_clock_timeout(
    monkeypatch,
):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(model="gpt-5.4", timeout=1.0)
    config = {
        "base_url": "https://chatgpt.com/backend-api/codex",
        "access_token_env": "OPENAI_CODEX_ACCESS_TOKEN",
    }
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "token-123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_text.return_value = [
        'data: {"type":"response.output_text.delta","delta":"hello"}\n\n',
        'data: {"type":"response.output_text.delta","delta":"world"}\n\n',
    ]

    with (
        patch(
            "lee_llm_router.providers.openai_codex_subscription.httpx.Client"
        ) as MockClient,
        patch(
            "lee_llm_router.providers.openai_codex_subscription.time.monotonic",
            side_effect=[0.0, 1.5],
        ),
    ):
        client = MockClient.return_value.__enter__.return_value
        client.stream.return_value.__enter__.return_value = mock_resp

        with pytest.raises(LLMRouterError) as exc_info:
            provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.TIMEOUT


def test_openai_codex_subscription_provider_missing_credentials_raises(monkeypatch):
    from lee_llm_router.providers.openai_codex_subscription import (
        OpenAICodexSubscriptionHTTPProvider,
    )

    provider = OpenAICodexSubscriptionHTTPProvider()
    request = make_request(model="gpt-5.3-codex")

    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("CODEX_HOME", "/tmp/definitely-no-codex-home-credentials")

    with pytest.raises(LLMRouterError) as exc_info:
        provider.complete(
            request,
            {
                "base_url": "https://chatgpt.com/backend-api/codex",
                "access_token_env": "OPENAI_CODEX_ACCESS_TOKEN",
            },
        )

    assert exc_info.value.failure_type == FailureType.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# Codex CLI Provider
# ---------------------------------------------------------------------------


def test_codex_cli_provider_success():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config("success_text")

    response = provider.complete(request, config)

    assert response.text == "pi text harness: hello"
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


def test_codex_cli_provider_json_harness_success():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config("success_json", response_format="json")

    response = provider.complete(request, config)

    assert response.text == "pi json harness: hello"
    assert response.model == "pi-harness-o3"
    assert response.usage.total_tokens == 20
    assert response.raw["command"][0] == sys.executable


def test_codex_cli_provider_malformed_json_is_contract_violation():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config("malformed_json", response_format="json")

    with pytest.raises(LLMRouterError) as exc_info:
        provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_codex_cli_provider_missing_text_is_contract_violation():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config("missing_text", response_format="json")

    with pytest.raises(LLMRouterError) as exc_info:
        provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_codex_cli_provider_timeout_raises():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3", timeout=0.1)
    config = make_pi_harness_config("timeout")

    with pytest.raises(LLMRouterError) as exc_info:
        provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.TIMEOUT


def test_codex_cli_provider_nonzero_exit_raises_provider_error():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config("stderr_exit")

    with pytest.raises(LLMRouterError) as exc_info:
        provider.complete(request, config)

    assert exc_info.value.failure_type == FailureType.PROVIDER_ERROR
    assert "pi harness exploded" in str(exc_info.value)


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
