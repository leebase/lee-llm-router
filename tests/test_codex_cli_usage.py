"""P1-4b Codex JSONL usage capture tests — inline recorded strings only.

Authority: D209 ruling 2 via docs/staffing/phase1-contracts.md
§Usage evidence taxonomy (exact source ``codex exec --json usage``).
Parser semantics mirror the agent-orch ``worker.py`` Codex JSONL receipt
parsing (``CodexCLIAdapter.extract_usage`` / ``_parse_provider_usage``)
and the accepted P1-4a ``pi_cli.capture_usage`` v2 usage shape. No Codex
binary, provider, router state, or fixtures are exercised.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.providers.codex_cli import (
    CODEX_USAGE_SOURCE,
    CodexCLIProvider,
    capture_usage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT / "config" / "staffing" / "schema" / "attempt-record.schema.json"
)


def _usage_validator():
    """Draft 2020-12 validator for the attempt-record v2 usage subschema.

    Wraps ``$defs/usage`` safely: the subschema is validated standalone by
    re-rooting the full schema's ``$defs`` and pointing ``$ref`` at it, so
    ``tokenCounter`` refs resolve without constructing a complete record.
    """
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/usage"})


def _event(event_type: str, **fields: object) -> str:
    return json.dumps({"type": event_type, **fields})


def _receipt(
    *,
    usage: dict[str, object] | None = None,
    omit_usage: bool = False,
) -> str:
    """Recorded-shape terminal receipt: 100 in (60 cached), 25 out, 5 reasoning."""
    if usage is None:
        usage = {
            "input_tokens": 100,
            "cached_input_tokens": 60,
            "output_tokens": 25,
            "reasoning_output_tokens": 5,
            "total_tokens": 125,
        }
    fields: dict[str, object] = {"usage": usage}
    if omit_usage:
        fields.pop("usage")
    return _event("turn.completed", **fields)


def _full_stream(usage: dict[str, object] | None = None) -> str:
    return "\n".join(
        [
            _event("thread.started", thread_id="t"),
            _event("turn.started"),
            _event("item.completed", item={"id": "item_0", "type": "agent_message"}),
            _receipt(usage=usage),
        ]
    )


# ---------------------------------------------------------------------------
# build_command: governed capture must include --json without changing the
# model/effort/prompt ordering; legacy default argv stays untouched.
# ---------------------------------------------------------------------------


def test_build_command_default_argv_unchanged() -> None:
    provider = CodexCLIProvider()
    assert provider.build_command({"command": "codex"}, model="gpt-5.6-sol") == [
        "codex",
        "exec",
        "--model",
        "gpt-5.6-sol",
        "{prompt}",
    ]


def test_build_command_governed_capture_exact_argv() -> None:
    provider = CodexCLIProvider()
    cmd = provider.build_command(
        {"command": "codex", "json_flag": "--json"}, model="gpt-5.6-sol"
    )
    assert cmd == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.6-sol",
        "{prompt}",
    ]


def test_build_command_governed_capture_keeps_model_effort_prompt_order() -> None:
    provider = CodexCLIProvider()
    plain = provider.build_command(
        {"command": "codex"}, model="gpt-5.6-sol", effort="low"
    )
    governed = provider.build_command(
        {"command": "codex", "json_flag": "--json"},
        model="gpt-5.6-sol",
        effort="low",
    )
    assert governed == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.6-sol",
        "-c",
        "model_reasoning_effort=low",
        "{prompt}",
    ]
    # Removing the injected flag restores the legacy argv element-for-element.
    assert [part for part in governed if part != "--json"] == plain


def test_build_command_json_flag_null_omits_flag() -> None:
    provider = CodexCLIProvider()
    cmd = provider.build_command(
        {"command": "codex", "json_flag": None}, model="gpt-5.6-sol"
    )
    assert "--json" not in cmd
    assert cmd == ["codex", "exec", "--model", "gpt-5.6-sol", "{prompt}"]


def test_build_command_json_flag_must_be_string_or_null() -> None:
    provider = CodexCLIProvider()
    with pytest.raises(LLMRouterError) as excinfo:
        provider.build_command({"command": "codex", "json_flag": True})
    assert excinfo.value.failure_type is FailureType.PROVIDER_ERROR


def test_complete_uses_governed_argv_and_preserves_response_parsing() -> None:
    provider = CodexCLIProvider()
    from lee_llm_router.response import LLMRequest

    request = LLMRequest(
        role="author",
        messages=[{"role": "user", "content": "hello"}],
        model="gpt-5.6-sol",
    )
    config = {
        "command": "codex",
        "json_flag": "--json",
        "response_format": "text",
    }
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "ok", ""),
    ) as mock_run:
        response = provider.complete(request, config)

    argv = mock_run.call_args.args[0]
    assert argv[:3] == ["codex", "exec", "--json"]
    assert argv[argv.index("--model") + 1] == "gpt-5.6-sol"
    assert argv[-1] == "hello"
    assert response.text == "ok"


def test_cli_subclass_defaults_do_not_inherit_json_flag() -> None:
    from lee_llm_router.providers.codex_cli import (
        ClaudeCodeCLIProvider,
        GeminiCLIProvider,
    )

    assert "--json" not in GeminiCLIProvider().build_command(
        {"command": "gemini", "prompt_flag": "-p"}, effort="high"
    )
    assert "--json" not in ClaudeCodeCLIProvider().build_command(
        {"command": "claude", "prompt_flag": "-p"}, effort="high"
    )
    # The key stays reusable on the shared builder when a harness needs it.
    assert GeminiCLIProvider().build_command(
        {"command": "gemini", "prompt_flag": "-p", "json_flag": "--json"}
    ) == ["gemini", "--json", "-p", "{prompt}"]


# ---------------------------------------------------------------------------
# capture_usage: terminal receipt parsing (recorded inline events only).
# ---------------------------------------------------------------------------


def test_known_receipt_jsonl_stream_reports_usage() -> None:
    result = capture_usage(_full_stream())
    assert result == {
        "basis": "provider_reported",
        "source": CODEX_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 25,
        "cached_input_tokens": 60,
        "reasoning_tokens": 5,
        "total_tokens": 125,
    }


def test_interim_events_with_usage_are_never_counted() -> None:
    output = "\n".join(
        [
            _event("turn.started"),
            _event(
                "item.completed",
                item={
                    "id": "item_1",
                    "type": "agent_message",
                    "usage": {
                        "input_tokens": 999,
                        "output_tokens": 999,
                        "total_tokens": 999,
                    },
                },
            ),
            _receipt(),
            _event("turn.completed", usage={"input_tokens": 1, "output_tokens": 1}),
        ]
    )
    # The second turn.completed is a duplicate terminal receipt: fail closed.
    with pytest.raises(LLMRouterError) as excinfo:
        capture_usage(output)
    assert excinfo.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "multiple terminal usage receipts" in str(excinfo.value)


def test_interim_usage_ignored_without_terminal_duplicate() -> None:
    output = "\n".join(
        [
            _event(
                "item.completed",
                item={
                    "usage": {"input_tokens": 999, "output_tokens": 999},
                },
            ),
            _receipt(),
        ]
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 25


def test_single_json_object_receipt() -> None:
    result = capture_usage(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 7, "output_tokens": 3},
            }
        )
    )
    assert result["basis"] == "provider_reported"
    assert result["source"] == CODEX_USAGE_SOURCE
    assert result["input_tokens"] == 7
    assert result["output_tokens"] == 3
    assert result["total_tokens"] == 10


def test_real_recorded_receipt_shape_parses() -> None:
    # Recorded transcript shape (agent-orch codex_real_receipt.jsonl):
    # no reported total; cached is a subset of input; reasoning reported 0.
    output = "\n".join(
        [
            '{"type":"thread.started","thread_id":"01a073e5-1cf2-71b3-a5cc-46ba0eb678f3"}',
            '{"type":"turn.started"}',
            '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}',
            '{"type":"turn.completed","usage":{"input_tokens":14646,"cached_input_tokens":11136,'
            '"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}',
        ]
    )
    result = capture_usage(output)
    assert result == {
        "basis": "provider_reported",
        "source": CODEX_USAGE_SOURCE,
        "input_tokens": 14646,
        "output_tokens": 5,
        "cached_input_tokens": 11136,
        "reasoning_tokens": 0,
        "total_tokens": 14651,
    }


def test_prompt_tokens_alias_consistent_value_accepted() -> None:
    output = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "prompt_tokens": 10,
                "output_tokens": 4,
                "completion_tokens": 4,
            },
        }
    )
    result = capture_usage(output)
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 4


def test_receipt_without_usage_object_unavailable() -> None:
    result = capture_usage(_receipt(omit_usage=True))
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Codex turn.completed receipt carried no usage object"
    )
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["cached_input_tokens"] is None
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] is None


def test_partial_usage_missing_output_unavailable() -> None:
    result = capture_usage(_receipt(usage={"input_tokens": 100}))
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Codex turn.completed usage was missing or had invalid required "
        "input_tokens/output_tokens"
    )
    assert result["input_tokens"] is None
    assert result["total_tokens"] is None


def test_invalid_required_counter_unavailable_never_zero() -> None:
    result = capture_usage(_receipt(usage={"input_tokens": "100", "output_tokens": 25}))
    assert result["basis"] == "unavailable"
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_empty_output_unavailable() -> None:
    for output in ("", "   \n\t"):
        result = capture_usage(output)
        assert result["basis"] == "unavailable"
        assert result["unavailable_reason"] == "Codex --json output was empty"
        assert result["input_tokens"] is None
        assert result["total_tokens"] is None


def test_interim_only_output_unavailable() -> None:
    result = capture_usage(_event("thread.started", thread_id="t"))
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Codex --json output contained no terminal turn.completed usage receipt"
    )
    assert result["input_tokens"] is None


def test_genuine_reported_zero_stays_zero() -> None:
    result = capture_usage(
        _receipt(
            usage={
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
            }
        )
    )
    assert result["basis"] == "provider_reported"
    assert result["source"] == CODEX_USAGE_SOURCE
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cached_input_tokens"] == 0
    assert result["reasoning_tokens"] == 0
    assert result["total_tokens"] == 0


def test_absent_cached_and_reasoning_stay_null() -> None:
    result = capture_usage(_receipt(usage={"input_tokens": 10, "output_tokens": 4}))
    assert result["basis"] == "provider_reported"
    assert result["cached_input_tokens"] is None
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] == 14
    assert set(result) == {
        "basis",
        "source",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    }


# ---------------------------------------------------------------------------
# Fail-closed paths: malformed, conflicting, multiple, failing receipts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output,match",
    [
        ("not json", "invalid Codex JSONL"),
        (
            "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "t"}),
                    '{"type": "turn.completed", "usage": {"input_tokens": 10',
                ]
            ),
            "invalid Codex JSONL",
        ),
        ("[]", "must be a JSON object or JSONL events"),
        (
            "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "t"}),
                    "[]",
                ]
            ),
            "event must be an object",
        ),
        (
            json.dumps({"type": "turn.failed", "error": {}}),
            "terminal failure event",
        ),
        (
            json.dumps({"type": "error", "message": "timeout"}),
            "terminal failure event",
        ),
        (
            "\n".join(
                [
                    json.dumps({"type": "error", "message": "stream disconnected"}),
                    _receipt(),
                ]
            ),
            "terminal failure event",
        ),
        (
            "\n".join([_receipt(), _receipt()]),
            "multiple terminal usage receipts",
        ),
        (
            _receipt(
                usage={
                    "input_tokens": 10,
                    "prompt_tokens": 11,
                    "output_tokens": 4,
                }
            ),
            "conflicting values",
        ),
        (
            _receipt(
                usage={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": 999,
                }
            ),
            "total_tokens contradicts",
        ),
        (
            _receipt(
                usage={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "reasoning_output_tokens": 9,
                }
            ),
            "reasoning_output_tokens contradicts",
        ),
        (
            _receipt(
                usage={
                    "input_tokens": 10,
                    "cached_input_tokens": 11,
                    "output_tokens": 4,
                }
            ),
            "cached_input_tokens contradicts",
        ),
        (
            _receipt(
                usage={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": "12",
                }
            ),
            "must be a nonnegative integer",
        ),
    ],
    ids=[
        "garbage-stdout",
        "truncated-final-line",
        "whole-output-non-object",
        "non-object-jsonl-line",
        "turn-failed",
        "error-event",
        "error-before-completion",
        "multiple-terminal-receipts",
        "conflicting-input-aliases",
        "total-contradicts-components",
        "reasoning-exceeds-output",
        "cached-exceeds-input",
        "invalid-optional-counter",
    ],
)
def test_untrustworthy_output_fails_closed(output: str, match: str) -> None:
    with pytest.raises(LLMRouterError) as excinfo:
        capture_usage(output)
    assert excinfo.value.failure_type is FailureType.CONTRACT_VIOLATION
    if match:
        assert match in str(excinfo.value)


# ---------------------------------------------------------------------------
# P1-5 schema validation: every returned usage mapping must be directly
# valid against attempt-record v2 $defs/usage (additionalProperties false).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output_factory",
    [
        # provider_reported with all optional counters reported.
        lambda: _full_stream(),
        # provider_reported with derived total (receipt reports no total).
        lambda: json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 14646,
                    "cached_input_tokens": 11136,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 0,
                },
            }
        ),
        # provider_reported with null cached/reasoning and genuine zeros.
        lambda: json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        ),
        # unavailable: empty output.
        lambda: "",
        # unavailable: no terminal receipt.
        lambda: _event("thread.started", thread_id="t"),
        # unavailable: receipt without usage object.
        lambda: _receipt(omit_usage=True),
    ],
    ids=[
        "provider-reported-full",
        "provider-reported-derived-total",
        "provider-reported-genuine-zero",
        "unavailable-empty-output",
        "unavailable-no-terminal-receipt",
        "unavailable-no-usage-object",
    ],
)
def test_returned_usage_is_schema_valid_v2_usage(output_factory) -> None:
    result = capture_usage(output_factory())
    errors = list(_usage_validator().iter_errors(result))
    assert not errors, [(list(e.absolute_path), e.validator, e.message) for e in errors]
