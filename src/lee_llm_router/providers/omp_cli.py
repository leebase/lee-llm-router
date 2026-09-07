"""Subprocess provider for the omp (oh-my-pi) harness.

Invokes `omp -p --model <model>` with the prompt on stdin and returns stdout.
The omp harness handles auth internally via its stored credentials.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMRequest, LLMResponse, LLMUsage


class OmpCLIProvider:
    """Invokes the omp harness via subprocess and returns its stdout."""

    name = "omp_cli"
    supported_types = {"omp_cli"}
    default_command = "omp"

    def validate_config(self, config: dict[str, Any]) -> None:
        command = config.get("command", self.default_command)
        if not isinstance(command, str) or not command.strip():
            raise LLMRouterError(
                f"{self.name} provider missing required config key: 'command'",
                failure_type=FailureType.PROVIDER_ERROR,
            )

    def build_command(
        self,
        config: dict[str, Any],
        model: str | None = None,
        effort: str | None = None,
    ) -> list[str]:
        """Return the dispatch command template as an argv list.

        The prompt is delivered on stdin, so the argv list carries no prompt
        placeholder. The omp harness exposes no reasoning-effort flag, so
        ``effort`` is accepted for interface parity and ignored.

        Args:
            config: Provider configuration mapping.
            model: Optional model override; falls back to ``config['model']``.
            effort: Accepted for interface parity; omp has no effort flag.

        Returns:
            The argv list for the omp CLI invocation.

        Raises:
            LLMRouterError: If the config is invalid.
        """
        self.validate_config(config)
        command = config.get("command", self.default_command)
        resolved_model = model or config.get("model", "")

        cmd = [command, "-p"]
        if resolved_model:
            cmd.extend(["--model", resolved_model])
        return cmd

    def complete(self, request: LLMRequest, config: dict[str, Any]) -> LLMResponse:
        self.validate_config(config)

        command = config.get("command", self.default_command)
        timeout = request.timeout or float(config.get("timeout", 120.0))

        # Build prompt from last user message
        user_messages = [m for m in request.messages if m.get("role") == "user"]
        prompt = user_messages[-1]["content"] if user_messages else ""

        # If there's a system message, prepend it
        system_messages = [m for m in request.messages if m.get("role") == "system"]
        if system_messages:
            system_prompt = system_messages[0]["content"]
            prompt = f"{system_prompt}\n\n{prompt}"

        model = request.model or config.get("model", "")
        cmd = self.build_command(
            config, model=request.model or None, effort=request.effort
        )

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMRouterError(
                f"omp CLI timed out after {timeout}s",
                failure_type=FailureType.TIMEOUT,
                cause=exc,
            ) from exc
        except FileNotFoundError as exc:
            raise LLMRouterError(
                f"omp CLI binary not found: {command!r}",
                failure_type=FailureType.PROVIDER_ERROR,
                cause=exc,
            ) from exc

        if result.returncode != 0:
            detail = _snippet(result.stderr) or _snippet(result.stdout) or "no output"
            raise LLMRouterError(
                f"omp CLI exited {result.returncode}: {detail}",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        text = _clean_output(result.stdout)
        if not text:
            raise LLMRouterError(
                "omp CLI returned empty output",
                failure_type=FailureType.INVALID_RESPONSE,
            )

        return LLMResponse(
            text=text,
            raw={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": cmd,
            },
            usage=LLMUsage(),
            request_id=request.request_id,
            model=request.model or model,
            provider=self.name,
        )


def _clean_output(stdout: str) -> str:
    """Strip omp's 'Working...' prefix and trailing whitespace from output."""
    text = stdout.strip()
    # Remove the "Working..." status line if present
    text = re.sub(r"^Working\.\.\.\s*\n?", "", text)
    return text.strip()


def _snippet(text: str, limit: int = 200) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]
