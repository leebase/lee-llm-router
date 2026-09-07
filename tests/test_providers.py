"""Unit tests for the provider layer (Sprint 2)."""

from __future__ import annotations

import subprocess
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
    assert "gemini_cli" in names
    assert "gemini" in names
    assert "claude_code_cli" in names
    assert "claude_code" in names
    assert "claude" in names


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


def test_codex_cli_provider_allows_disabling_default_flags_for_pi_harness():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config(
        "strict_success_json",
        response_format="json",
        model_flag=None,
        output_flag=None,
    )

    response = provider.complete(request, config)

    assert response.text == "pi strict harness: hello"


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


def test_codex_cli_provider_bad_usage_is_contract_violation():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="o3")
    config = make_pi_harness_config("bad_usage", response_format="json")

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


def test_gemini_cli_provider_defaults_and_prompt_flag():
    from lee_llm_router.providers.codex_cli import GeminiCLIProvider

    provider = GeminiCLIProvider()
    request = make_request(
        model="gemini-2.5-pro", messages=[{"role": "user", "content": "hello"}]
    )

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            ["gemini", "-p", "hello"], 0, "ok", ""
        ),
    ) as mock_run:
        response = provider.complete(request, {})

    assert mock_run.call_args.args[0][0] == "gemini"
    assert mock_run.call_args.args[0][-2:] == ["-p", "hello"]

    assert response.provider == "gemini_cli"
    assert response.text == "ok"


def test_claude_code_cli_provider_defaults_and_prompt_flag():
    from lee_llm_router.providers.codex_cli import ClaudeCodeCLIProvider

    provider = ClaudeCodeCLIProvider()
    request = make_request(
        model="claude-3.7-sonnet",
        messages=[{"role": "user", "content": "hello"}],
    )

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            ["claude", "-p", "hello"], 0, "ok", ""
        ),
    ) as mock_run:
        response = provider.complete(request, {"command": "claude"})

    assert mock_run.call_args.args[0][0] == "claude"
    assert mock_run.call_args.args[0][-2:] == ["-p", "hello"]
    assert response.provider == "claude_code_cli"
    assert response.text == "ok"


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


# ---------------------------------------------------------------------------
# OpenCodeCLIProvider
# ---------------------------------------------------------------------------

OPENCODE_CONFIG = {"model": "opencode-go/deepseek-v4-flash"}


def _opencode_provider():
    from lee_llm_router.providers.opencode_cli import OpenCodeCLIProvider

    return OpenCodeCLIProvider()


def test_opencode_validate_config_accepts_minimal_and_full_config():
    provider = _opencode_provider()

    provider.validate_config(dict(OPENCODE_CONFIG))
    provider.validate_config(
        {
            "command": "/usr/local/bin/opencode",
            "model": "opencode-go/deepseek-v4-flash",
            "agent": "build",
            "timeout": 45,
        }
    )


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"model": ""},
        {"model": "deepseek-v4-flash"},
        {"model": "a/b/c"},
        {"model": "opencode-go/deepseek-v4-flash", "command": ""},
        {"model": "opencode-go/deepseek-v4-flash", "agent": ""},
        {"model": "opencode-go/deepseek-v4-flash", "timeout": "soon"},
    ],
)
def test_opencode_validate_config_rejects_invalid(config):
    provider = _opencode_provider()

    with pytest.raises(LLMRouterError) as exc:
        provider.validate_config(config)
    assert exc.value.failure_type == FailureType.PROVIDER_ERROR


def test_opencode_build_command_exact_argv():
    provider = _opencode_provider()

    assert provider.build_command(dict(OPENCODE_CONFIG)) == [
        "opencode",
        "run",
        "-m",
        "opencode-go/deepseek-v4-flash",
        "{prompt}",
    ]


def test_opencode_build_command_with_agent_and_model_override():
    provider = _opencode_provider()

    cmd = provider.build_command(
        {"command": "oc", "model": "opencode-go/deepseek-v4-flash", "agent": "build"},
        model="openrouter/glm-5.3-flash",
    )
    assert cmd == [
        "oc",
        "run",
        "-m",
        "openrouter/glm-5.3-flash",
        "--agent",
        "build",
        "{prompt}",
    ]


def test_opencode_build_command_rejects_bad_model_override():
    provider = _opencode_provider()

    with pytest.raises(LLMRouterError) as exc:
        provider.build_command(dict(OPENCODE_CONFIG), model="nope")
    assert exc.value.failure_type == FailureType.PROVIDER_ERROR


def test_opencode_complete_success_substitutes_prompt():
    provider = _opencode_provider()
    request = make_request(
        model="opencode-go/deepseek-v4-flash",
        messages=[{"role": "user", "content": "hello"}],
    )

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "  answer  ", ""),
    ) as mock_run:
        response = provider.complete(request, dict(OPENCODE_CONFIG))

    assert mock_run.call_args.args[0] == [
        "opencode",
        "run",
        "-m",
        "opencode-go/deepseek-v4-flash",
        "hello",
    ]
    assert "input" not in mock_run.call_args.kwargs
    assert response.text == "answer"
    assert response.provider == "opencode_cli"
    assert response.model == "opencode-go/deepseek-v4-flash"


def test_opencode_complete_timeout_is_typed_timeout():
    provider = _opencode_provider()
    request = make_request(model="", messages=[{"role": "user", "content": "hello"}])

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("opencode", 1)):
        with pytest.raises(LLMRouterError) as exc:
            provider.complete(request, dict(OPENCODE_CONFIG))

    assert exc.value.failure_type == FailureType.TIMEOUT


def test_opencode_complete_nonzero_exit_is_provider_error():
    provider = _opencode_provider()
    request = make_request(model="", messages=[{"role": "user", "content": "hello"}])

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 2, "", "boom"),
    ):
        with pytest.raises(LLMRouterError) as exc:
            provider.complete(request, dict(OPENCODE_CONFIG))

    assert exc.value.failure_type == FailureType.PROVIDER_ERROR
    assert "boom" in str(exc.value)


def test_opencode_complete_missing_binary_is_provider_error():
    provider = _opencode_provider()
    request = make_request(model="", messages=[{"role": "user", "content": "hello"}])

    with patch("subprocess.run", side_effect=FileNotFoundError("opencode")):
        with pytest.raises(LLMRouterError) as exc:
            provider.complete(request, dict(OPENCODE_CONFIG))

    assert exc.value.failure_type == FailureType.PROVIDER_ERROR


def test_opencode_complete_with_fake_script(tmp_path):
    provider = _opencode_provider()
    script = tmp_path / "fake_opencode.py"
    script.write_text("import sys\nprint('from-fake:' + sys.argv[-1])\n")
    request = make_request(model="", messages=[{"role": "user", "content": "ping"}])

    config = {"command": sys.executable, "model": "opencode-go/deepseek-v4-flash"}
    with patch.object(
        provider,
        "build_command",
        return_value=[sys.executable, str(script), "{prompt}"],
    ):
        response = provider.complete(request, config)

    assert response.text == "from-fake:ping"


def test_opencode_complete_request_model_overrides_config():
    provider = _opencode_provider()
    request = make_request(
        model="openrouter/glm-5.3-flash",
        messages=[{"role": "user", "content": "hello"}],
    )

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "ok", ""),
    ) as mock_run:
        response = provider.complete(request, dict(OPENCODE_CONFIG))

    assert mock_run.call_args.args[0][3] == "openrouter/glm-5.3-flash"
    assert response.model == "openrouter/glm-5.3-flash"


def test_opencode_registry_lookup_by_name_and_alias():
    from lee_llm_router.providers.opencode_cli import OpenCodeCLIProvider

    assert get("opencode_cli") is OpenCodeCLIProvider
    assert get("opencode") is OpenCodeCLIProvider


# ---------------------------------------------------------------------------
# AntigravityCLIProvider
# ---------------------------------------------------------------------------

AGY_CONFIG = {"model": "gemini-3.7-flash"}


def _antigravity_provider():
    from lee_llm_router.providers.antigravity_cli import AntigravityCLIProvider

    return AntigravityCLIProvider()


def test_antigravity_validate_config_accepts_minimal_and_full_config():
    provider = _antigravity_provider()

    provider.validate_config(dict(AGY_CONFIG))
    provider.validate_config(
        {
            "command": "/usr/local/bin/agy",
            "model": "gemini-3.7-flash",
            "effort": "high",
            "timeout": 300,
        }
    )


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"model": ""},
        {"model": 123},
        {"model": "gemini-3.7-flash", "command": ""},
        {"model": "gemini-3.7-flash", "effort": "extreme"},
        {"model": "gemini-3.7-flash", "effort": 3},
        {"model": "gemini-3.7-flash", "timeout": "soon"},
    ],
)
def test_antigravity_validate_config_rejects_invalid(config):
    provider = _antigravity_provider()

    with pytest.raises(LLMRouterError) as exc:
        provider.validate_config(config)
    assert exc.value.failure_type == FailureType.PROVIDER_ERROR


def test_antigravity_build_command_exact_argv():
    provider = _antigravity_provider()

    assert provider.build_command(dict(AGY_CONFIG)) == [
        "agy",
        "-p",
        "--model",
        "gemini-3.7-flash",
        "--dangerously-skip-permissions",
    ]


def test_antigravity_build_command_with_effort_and_overrides():
    provider = _antigravity_provider()

    cmd = provider.build_command(
        {"command": "agy", "model": "gemini-3.7-flash", "effort": "low"},
        model="gemini-3.1-pro",
        effort="high",
    )
    assert cmd == [
        "agy",
        "-p",
        "--model",
        "gemini-3.1-pro",
        "--effort",
        "high",
        "--dangerously-skip-permissions",
    ]


def test_antigravity_build_command_rejects_bad_effort_override():
    provider = _antigravity_provider()

    with pytest.raises(LLMRouterError) as exc:
        provider.build_command(dict(AGY_CONFIG), effort="ludicrous")
    assert exc.value.failure_type == FailureType.PROVIDER_ERROR


def test_antigravity_complete_success_sends_prompt_on_stdin():
    provider = _antigravity_provider()
    request = make_request(
        model="gemini-3.7-flash",
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hello"},
        ],
    )

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "answer\n", ""),
    ) as mock_run:
        response = provider.complete(
            request, {"model": "gemini-3.7-flash", "effort": "medium"}
        )

    assert mock_run.call_args.args[0] == [
        "agy",
        "-p",
        "--model",
        "gemini-3.7-flash",
        "--effort",
        "medium",
        "--dangerously-skip-permissions",
    ]
    assert mock_run.call_args.kwargs["input"] == "be terse\n\nhello"
    assert response.text == "answer"
    assert response.provider == "antigravity_cli"


def test_antigravity_complete_timeout_is_typed_timeout():
    provider = _antigravity_provider()
    request = make_request(messages=[{"role": "user", "content": "hello"}])

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("agy", 1)):
        with pytest.raises(LLMRouterError) as exc:
            provider.complete(request, dict(AGY_CONFIG))

    assert exc.value.failure_type == FailureType.TIMEOUT


def test_antigravity_complete_nonzero_exit_is_provider_error():
    provider = _antigravity_provider()
    request = make_request(messages=[{"role": "user", "content": "hello"}])

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 1, "", "kaboom"),
    ):
        with pytest.raises(LLMRouterError) as exc:
            provider.complete(request, dict(AGY_CONFIG))

    assert exc.value.failure_type == FailureType.PROVIDER_ERROR
    assert "kaboom" in str(exc.value)


def test_antigravity_complete_missing_binary_is_provider_error():
    provider = _antigravity_provider()
    request = make_request(messages=[{"role": "user", "content": "hello"}])

    with patch("subprocess.run", side_effect=FileNotFoundError("agy")):
        with pytest.raises(LLMRouterError) as exc:
            provider.complete(request, dict(AGY_CONFIG))

    assert exc.value.failure_type == FailureType.PROVIDER_ERROR


def test_antigravity_complete_with_fake_script(tmp_path):
    provider = _antigravity_provider()
    script = tmp_path / "fake_agy.py"
    script.write_text("import sys\nprint('stdin:' + sys.stdin.read().strip())\n")
    request = make_request(messages=[{"role": "user", "content": "ping"}])

    with patch.object(
        provider,
        "build_command",
        return_value=[sys.executable, str(script)],
    ):
        response = provider.complete(request, dict(AGY_CONFIG))

    assert response.text == "stdin:ping"


def test_antigravity_registry_lookup_by_name_and_aliases():
    from lee_llm_router.providers.antigravity_cli import AntigravityCLIProvider

    assert get("antigravity_cli") is AntigravityCLIProvider
    assert get("antigravity") is AntigravityCLIProvider
    assert get("agy") is AntigravityCLIProvider


# ---------------------------------------------------------------------------
# Dispatch-command templates and effort flags (H2/H4)
# ---------------------------------------------------------------------------


def _omp_provider():
    from lee_llm_router.providers.omp_cli import OmpCLIProvider

    return OmpCLIProvider()


def test_omp_build_command_exact_argv():
    provider = _omp_provider()

    assert provider.build_command({"model": "gemini-3.8-flash-high"}) == [
        "omp",
        "-p",
        "--model",
        "gemini-3.8-flash-high",
    ]


def test_omp_build_command_model_override_and_ignored_effort():
    provider = _omp_provider()

    cmd = provider.build_command(
        {"command": "/usr/local/bin/omp", "model": "a"}, model="b", effort="high"
    )

    assert cmd == ["/usr/local/bin/omp", "-p", "--model", "b"]


def test_omp_build_command_without_model_omits_flag():
    provider = _omp_provider()

    assert provider.build_command({}) == ["omp", "-p"]


def test_omp_complete_uses_build_command():
    provider = _omp_provider()
    request = make_request(model="gemini-3.8-flash-high")

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "answer\n", ""),
    ) as mock_run:
        response = provider.complete(request, {"model": "ignored"})

    assert mock_run.call_args.args[0] == provider.build_command(
        {"model": "gemini-3.8-flash-high"}
    )
    assert response.text == "answer"


def test_codex_build_command_exact_argv():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()

    assert provider.build_command({"command": "codex"}, model="gpt-5.6-sol") == [
        "codex",
        "--model",
        "gpt-5.6-sol",
        "--output-last-message",
        "{prompt}",
    ]


def test_codex_build_command_with_effort_uses_config_override_flag():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()

    cmd = provider.build_command({}, model="gpt-5.6-sol", effort="high")

    assert cmd == [
        "codex",
        "--model",
        "gpt-5.6-sol",
        "-c",
        "model_reasoning_effort=high",
        "--output-last-message",
        "{prompt}",
    ]


def test_codex_build_command_without_effort_omits_flag():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()

    cmd = provider.build_command({}, model="gpt-5.6-sol")

    assert "-c" not in cmd
    assert not any(part.startswith("model_reasoning_effort") for part in cmd)


def test_codex_complete_passes_request_effort_to_argv():
    from lee_llm_router.providers.codex_cli import CodexCLIProvider

    provider = CodexCLIProvider()
    request = make_request(model="gpt-5.6-sol", effort="high")

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "ok", ""),
    ) as mock_run:
        provider.complete(request, {"command": "codex"})

    argv = mock_run.call_args.args[0]
    assert argv[argv.index("-c") + 1] == "model_reasoning_effort=high"
    assert argv[-1] == "hello"


def test_claude_code_cli_effort_flag_is_its_own():
    from lee_llm_router.providers.codex_cli import ClaudeCodeCLIProvider

    provider = ClaudeCodeCLIProvider()

    cmd = provider.build_command({"command": "claude"}, effort="high")

    assert cmd == ["claude", "--effort", "high", "-p", "{prompt}"]


def test_gemini_cli_has_no_effort_flag():
    from lee_llm_router.providers.codex_cli import GeminiCLIProvider

    provider = GeminiCLIProvider()

    assert provider.build_command({}, effort="high") == ["gemini", "-p", "{prompt}"]


def test_antigravity_complete_passes_request_effort():
    provider = _antigravity_provider()
    request = make_request(model="gemini-3.7-flash", effort="low")

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "ok", ""),
    ) as mock_run:
        provider.complete(request, {"model": "gemini-3.7-flash", "effort": "high"})

    argv = mock_run.call_args.args[0]
    assert argv[argv.index("--effort") + 1] == "low"


def test_opencode_ignores_request_effort():
    provider = _opencode_provider()
    request = make_request(model="opencode-go/deepseek-v4-flash", effort="high")

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "ok", ""),
    ) as mock_run:
        provider.complete(request, dict(OPENCODE_CONFIG))

    argv = mock_run.call_args.args[0]
    assert "--effort" not in argv
    assert "high" not in argv
