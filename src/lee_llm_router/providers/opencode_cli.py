"""Subprocess provider for the OpenCode CLI.

Invokes ``opencode run -m <provider/model> [--agent <agent>] <message>`` and
returns stdout. The OpenCode CLI handles authentication internally through its
stored credentials, so no API key configuration is needed here.
"""

from __future__ import annotations

import subprocess
from typing import Any

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMRequest, LLMResponse, LLMUsage

PROMPT_PLACEHOLDER = "{prompt}"


class OpenCodeCLIProvider:
    """Invokes the OpenCode CLI via subprocess and returns its stdout."""

    name = "opencode_cli"
    supported_types = {"opencode_cli", "opencode"}
    default_command = "opencode"

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate the provider config block.

        Args:
            config: Provider configuration mapping.

        Raises:
            LLMRouterError: If a required key is missing or malformed.
        """
        command = config.get("command", self.default_command)
        if not isinstance(command, str) or not command.strip():
            raise LLMRouterError(
                f"{self.name} provider missing required config key: 'command'",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        model = config.get("model")
        if not isinstance(model, str) or not model.strip():
            raise LLMRouterError(
                f"{self.name} provider missing required config key: 'model'",
                failure_type=FailureType.PROVIDER_ERROR,
            )
        _validate_model(model, provider_name=self.name)

        agent = config.get("agent")
        if agent is not None and (not isinstance(agent, str) or not agent.strip()):
            raise LLMRouterError(
                f"{self.name} provider key 'agent' must be a non-empty string",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        timeout = config.get("timeout")
        if timeout is not None and not isinstance(timeout, (int, float)):
            raise LLMRouterError(
                f"{self.name} provider key 'timeout' must be a number",
                failure_type=FailureType.PROVIDER_ERROR,
            )

    def build_command(
        self,
        config: dict[str, Any],
        model: str | None = None,
        effort: str | None = None,
    ) -> list[str]:
        """Return the dispatch command template as an argv list.

        The final positional element is the literal ``{prompt}`` placeholder,
        which :meth:`complete` replaces with the resolved prompt text.

        Args:
            config: Provider configuration mapping.
            model: Optional model override (``provider/model`` form).
            effort: Accepted for interface parity; OpenCode has no effort flag.

        Returns:
            The argv list for the OpenCode CLI invocation.

        Raises:
            LLMRouterError: If the config or model override is invalid.
        """
        self.validate_config(config)
        command = config.get("command", self.default_command)
        resolved_model = model or config["model"]
        _validate_model(resolved_model, provider_name=self.name)

        cmd = [command, "run", "-m", resolved_model]
        agent = config.get("agent")
        if agent:
            cmd.extend(["--agent", agent])
        cmd.append(PROMPT_PLACEHOLDER)
        return cmd

    def complete(self, request: LLMRequest, config: dict[str, Any]) -> LLMResponse:
        """Run the OpenCode CLI and return its stdout as a response.

        Args:
            request: The routed completion request.
            config: Provider configuration mapping.

        Returns:
            The provider response carrying the CLI stdout.

        Raises:
            LLMRouterError: On timeout, missing binary, non-zero exit, or
                empty output.
        """
        self.validate_config(config)

        command = config.get("command", self.default_command)
        timeout = request.timeout or float(config.get("timeout", 120.0))
        prompt = _build_prompt(request)
        cmd = [
            prompt if part == PROMPT_PLACEHOLDER else part
            for part in self.build_command(
                config, model=request.model or None, effort=request.effort
            )
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMRouterError(
                f"opencode CLI timed out after {timeout}s",
                failure_type=FailureType.TIMEOUT,
                cause=exc,
            ) from exc
        except FileNotFoundError as exc:
            raise LLMRouterError(
                f"opencode CLI binary not found: {command!r}",
                failure_type=FailureType.PROVIDER_ERROR,
                cause=exc,
            ) from exc

        if result.returncode != 0:
            detail = _snippet(result.stderr) or _snippet(result.stdout) or "no output"
            raise LLMRouterError(
                f"opencode CLI exited {result.returncode}: {detail}",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        text = result.stdout.strip()
        if not text:
            raise LLMRouterError(
                "opencode CLI returned empty output",
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
            model=request.model or str(config["model"]),
            provider=self.name,
        )


def _validate_model(model: str, *, provider_name: str) -> None:
    """Raise if the model is not in ``provider/model`` form."""
    parts = model.split("/")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise LLMRouterError(
            f"{provider_name} provider key 'model' must look like "
            f"'provider/model', got {model!r}",
            failure_type=FailureType.PROVIDER_ERROR,
        )


def _build_prompt(request: LLMRequest) -> str:
    """Return the prompt text, prepending a system message when present."""
    user_messages = [m for m in request.messages if m.get("role") == "user"]
    prompt = user_messages[-1]["content"] if user_messages else ""
    system_messages = [m for m in request.messages if m.get("role") == "system"]
    if system_messages:
        prompt = f"{system_messages[0]['content']}\n\n{prompt}"
    return prompt


def _snippet(text: str, limit: int = 200) -> str:
    """Return a single-line, length-capped excerpt of ``text``."""
    normalized = " ".join(text.split())
    return normalized[:limit]
