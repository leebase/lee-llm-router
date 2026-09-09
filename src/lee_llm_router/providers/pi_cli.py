"""Pi CLI command builder (P0-2b — builder only).

Mirrors the proven argv shape from auto-orch's ``pi_stage_worker.py``
``_build_argv``: a fixed base of headless/read-only flags, optional
``--provider``/``--model``/``--thinking`` flags, and the literal
``{prompt}`` placeholder as the final positional element.

Deliberately scoped: this module builds argv only. There is no
``.complete()`` method, no subprocess execution, and no provider
registration here — those are later P0-2 phases.
"""

from __future__ import annotations

from typing import Any

from lee_llm_router.providers.base import FailureType, LLMRouterError

PROMPT_PLACEHOLDER = "{prompt}"

# The proven read-only tool set from pi_stage_worker.py (Sprint 36 doctrine:
# stage workers produce text, they do not edit files).
READ_ONLY_TOOLS = "read,grep,find,ls"

# The exact proven system prompt from pi_stage_worker.py, verbatim.
SYSTEM_PROMPT = (
    "You are a headless stage worker. Output only the JSON response the "
    "prompt asks for - no prose, no code fences."
)


class PiCLIProvider:
    """Builds the argv for a headless ``pi`` CLI invocation.

    Command-builder only: compatible with the repository's provider
    conventions (``name``/``supported_types``/``validate_config``/
    ``build_command``) to the degree needed for later registration,
    but intentionally omits completion execution.
    """

    name = "pi_cli"
    supported_types = {"pi_cli", "pi"}
    default_command = "pi"

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate the provider config block types.

        Args:
            config: Provider configuration mapping. All keys are optional;
                when present, ``command``, ``provider``, ``model``,
                ``thinking``, and ``effort`` must be non-empty strings.

        Raises:
            LLMRouterError: With ``FailureType.PROVIDER_ERROR`` if a key
                has the wrong type or is empty.
        """
        for key in ("command", "provider", "model", "thinking", "effort"):
            value = config.get(key)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise LLMRouterError(
                    f"{self.name} provider key {key!r} must be a non-empty "
                    f"string, got {type(value).__name__}",
                    failure_type=FailureType.PROVIDER_ERROR,
                )

    def build_command(
        self,
        config: dict[str, Any],
        model: str | None = None,
        effort: str | None = None,
    ) -> list[str]:
        """Return the Pi CLI dispatch command as an argv list.

        The argv shape mirrors ``pi_stage_worker.py`` ``_build_argv``
        exactly: fixed headless/read-only base flags, then optional
        ``--provider``/``--model``/``--thinking`` flags, then the literal
        ``{prompt}`` placeholder as the final element. The argv is always
        a list; callers must never shell-quote it into one string.

        Args:
            config: Provider configuration mapping. ``thinking`` (or the
                ``effort`` alias) supplies the ``--thinking`` value.
            model: Optional model override; beats ``config["model"]``.
            effort: Optional thinking-effort override; beats the config's
                ``thinking``/``effort`` value.

        Returns:
            The argv list for the Pi CLI invocation, ending in the literal
            ``{prompt}`` placeholder.

        Raises:
            LLMRouterError: If the config or overrides are of invalid type.
        """
        self.validate_config(config)

        command = config.get("command", self.default_command)
        provider = config.get("provider")
        resolved_model = model if model is not None else config.get("model")
        resolved_thinking = effort
        if resolved_thinking is None:
            resolved_thinking = config.get("thinking", config.get("effort"))
        if model is not None or effort is not None:
            # Overrides go through the same type checks as config values.
            self.validate_config(
                {
                    **({"model": model} if model is not None else {}),
                    **({"effort": effort} if effort is not None else {}),
                }
            )

        argv = [
            command,
            "--print",
            "--mode",
            "text",
            "--no-session",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--tools",
            READ_ONLY_TOOLS,
            "--system-prompt",
            SYSTEM_PROMPT,
        ]
        if provider:
            argv.extend(["--provider", provider])
        if resolved_model:
            argv.extend(["--model", resolved_model])
        if resolved_thinking:
            argv.extend(["--thinking", resolved_thinking])
        argv.append(PROMPT_PLACEHOLDER)
        return argv
