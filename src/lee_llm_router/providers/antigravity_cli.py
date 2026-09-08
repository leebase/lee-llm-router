"""Subprocess provider for the Antigravity CLI (``agy``).

Invokes ``agy --dangerously-skip-permissions --model <model> [--effort <level>]
[--print-timeout <dur>] -p <prompt>`` in print mode with the prompt delivered
as the argument to ``-p``.
The harness handles authentication internally through its stored Google
subscription credentials, so no API key configuration is needed here.
"""

from __future__ import annotations

import subprocess
from typing import Any

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMRequest, LLMResponse, LLMUsage

PROMPT_PLACEHOLDER = "{prompt}"
VALID_EFFORTS = ("low", "medium", "high")


class AntigravityCLIProvider:
    """Invokes the Antigravity CLI via subprocess and returns its stdout."""

    name = "antigravity_cli"
    supported_types = {"antigravity_cli", "antigravity", "agy"}
    default_command = "agy"

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

        effort = config.get("effort")
        if effort is not None:
            _validate_effort(effort, provider_name=self.name)

        timeout = config.get("timeout")
        if timeout is not None and not isinstance(timeout, (int, float)):
            raise LLMRouterError(
                f"{self.name} provider key 'timeout' must be a number",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        if "print_timeout" in config:
            print_timeout = config["print_timeout"]
            if not isinstance(print_timeout, str) or not print_timeout.strip():
                raise LLMRouterError(
                    f"{self.name} provider key 'print_timeout' "
                    "must be a non-empty string",
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
            model: Optional model override.
            effort: Optional effort override (``low``/``medium``/``high``).

        Returns:
            The argv list for the Antigravity CLI invocation.

        Raises:
            LLMRouterError: If the config or an override is invalid.
        """
        self.validate_config(config)
        command = config.get("command", self.default_command)
        resolved_model = model or config["model"]
        resolved_effort = effort if effort is not None else config.get("effort")

        cmd = [command, "--dangerously-skip-permissions", "--model", resolved_model]
        if resolved_effort is not None:
            _validate_effort(resolved_effort, provider_name=self.name)
            cmd.extend(["--effort", resolved_effort])
        print_timeout = config.get("print_timeout")
        if print_timeout is not None:
            cmd.extend(["--print-timeout", print_timeout])
        cmd.extend(["-p", PROMPT_PLACEHOLDER])
        return cmd

    def complete(self, request: LLMRequest, config: dict[str, Any]) -> LLMResponse:
        """Run the Antigravity CLI and return its stdout as a response.

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
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMRouterError(
                f"agy CLI timed out after {timeout}s",
                failure_type=FailureType.TIMEOUT,
                cause=exc,
            ) from exc
        except FileNotFoundError as exc:
            raise LLMRouterError(
                f"agy CLI binary not found: {command!r}",
                failure_type=FailureType.PROVIDER_ERROR,
                cause=exc,
            ) from exc

        if result.returncode != 0:
            detail = _snippet(result.stderr) or _snippet(result.stdout) or "no output"
            raise LLMRouterError(
                f"agy CLI exited {result.returncode}: {detail}",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        text = result.stdout.strip()
        if not text:
            raise LLMRouterError(
                "agy CLI returned empty output",
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


def _validate_effort(effort: Any, *, provider_name: str) -> None:
    """Raise unless ``effort`` is one of the supported levels.

    The ``agy`` CLI accepts only ``low``, ``medium``, or ``high`` reasoning
    effort (it has no ``max`` level).
    """
    if effort not in VALID_EFFORTS:
        raise LLMRouterError(
            f"{provider_name} provider key 'effort' must be one of "
            f"{', '.join(VALID_EFFORTS)}, got {effort!r}",
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
