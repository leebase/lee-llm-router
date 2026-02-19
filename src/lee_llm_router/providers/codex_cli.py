"""Subprocess provider for Codex CLI."""

from __future__ import annotations

import subprocess
from typing import Any

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMRequest, LLMResponse, LLMUsage


class CodexCLIProvider:
    """Invokes the Codex CLI via subprocess and returns its stdout."""

    name = "codex_cli"
    supported_types = {"codex_cli"}

    def validate_config(self, config: dict[str, Any]) -> None:
        if "command" not in config:
            raise LLMRouterError(
                "codex_cli provider missing required config key: 'command'",
                failure_type=FailureType.PROVIDER_ERROR,
            )

    def complete(self, request: LLMRequest, config: dict[str, Any]) -> LLMResponse:
        command = config.get("command", "codex")
        model_flag = config.get("model_flag", "--model")
        output_flag = config.get("output_flag", "--output-last-message")
        timeout = request.timeout or float(config.get("timeout", 120.0))

        # Build prompt from last user message
        user_messages = [m for m in request.messages if m.get("role") == "user"]
        prompt = user_messages[-1]["content"] if user_messages else ""

        cmd = [command]
        if request.model:
            cmd.extend([model_flag, request.model])
        if output_flag:
            cmd.append(output_flag)
        cmd.append(prompt)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMRouterError(
                f"Codex CLI timed out after {timeout}s",
                failure_type=FailureType.TIMEOUT,
                cause=exc,
            ) from exc
        except FileNotFoundError as exc:
            raise LLMRouterError(
                f"Codex CLI binary not found: {command!r}",
                failure_type=FailureType.PROVIDER_ERROR,
                cause=exc,
            ) from exc

        if result.returncode != 0:
            raise LLMRouterError(
                f"Codex CLI exited {result.returncode}: {result.stderr[:200]}",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        text = result.stdout.strip()
        if not text:
            raise LLMRouterError(
                "Codex CLI returned empty output",
                failure_type=FailureType.INVALID_RESPONSE,
            )

        return LLMResponse(
            text=text,
            raw={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            },
            usage=LLMUsage(),  # CLI doesn't report token usage
            request_id=request.request_id,
            model=request.model,
            provider="codex_cli",
        )
