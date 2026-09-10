"""P1-4d agy usage-capture tests using recorded output only.

The usage taxonomy is ``agy -p usage line (agent-orch worker.py)``. Receipt
semantics mirror the read-only Antigravity parser in Agent-Orch's
``worker.py``: an ERROR receipt is evidence only when it reports real tokens,
and successful zeroes remain real provider evidence. Every subprocess in this
module is patched; no agy binary or live subscription is used.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lee_llm_router.providers.antigravity_cli import (
    AGY_GOVERNED_CONFIG,
    AGY_USAGE_SOURCE,
    AntigravityCLIProvider,
    capture_usage,
)
from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT / "config" / "staffing" / "schema" / "attempt-record.schema.json"
)

UNAVAILABLE_COUNTERS = {
    "input_tokens": None,
    "output_tokens": None,
    "cached_input_tokens": None,
    "reasoning_tokens": None,
    "total_tokens": None,
}


def _usage_validator():
    """Validate the returned mapping against the strict v2 usage definition."""
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/usage"})


def _receipt(
    *,
    status: str = "SUCCESS",
    response: str = "done",
    usage: dict[str, object] | None = None,
    error: object = "",
) -> str:
    if usage is None:
        usage = {
            "input_tokens": 100,
            "output_tokens": 25,
            "thinking_tokens": 10,
            "cache_read_tokens": 50,
            "total_tokens": 125,
        }
    return json.dumps(
        {
            "conversation_id": "recorded-conversation",
            "status": status,
            "response": response,
            "error": error,
            "duration_seconds": 1.25,
            "num_turns": 1,
            "usage": usage,
        }
    )


def _request() -> LLMRequest:
    return LLMRequest(
        role="test",
        messages=[{"role": "user", "content": "hello"}],
        model="gemini-3.8-flash",
    )


# ---------------------------------------------------------------------------
# Governed command and response boundary
# ---------------------------------------------------------------------------


def test_usage_source_is_the_exact_phase1_taxonomy_string():
    assert AGY_USAGE_SOURCE == "agy -p usage line (agent-orch worker.py)"


def test_legacy_command_shape_is_unchanged():
    provider = AntigravityCLIProvider()

    assert provider.build_command(
        {"command": "agy", "model": "gemini-3.8-flash", "effort": "high"}
    ) == [
        "agy",
        "--dangerously-skip-permissions",
        "--model",
        "gemini-3.8-flash",
        "--effort",
        "high",
        "-p",
        "{prompt}",
    ]


def test_governed_command_adds_json_receipt_without_moving_prompt():
    provider = AntigravityCLIProvider()
    command = provider.build_command(
        {
            "command": "agy",
            "model": "gemini-3.8-flash",
            **AGY_GOVERNED_CONFIG,
        },
        effort="medium",
    )

    assert command == [
        "agy",
        "--dangerously-skip-permissions",
        "--model",
        "gemini-3.8-flash",
        "--effort",
        "medium",
        "--output-format",
        "json",
        "-p",
        "{prompt}",
    ]
    assert command[-2:] == ["-p", "{prompt}"]


def test_governed_complete_separates_response_from_receipt():
    provider = AntigravityCLIProvider()
    stdout = _receipt(response="completion text")

    with patch(
        "lee_llm_router.providers.antigravity_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, stdout, ""),
    ) as run:
        response = provider.complete(
            _request(),
            {
                "command": "agy",
                "model": "gemini-3.8-flash",
                **AGY_GOVERNED_CONFIG,
            },
        )

    assert run.call_count == 1
    assert response.text == "completion text"
    assert response.raw["stdout"] == stdout
    assert response.usage.prompt_tokens == 100
    assert response.usage.completion_tokens == 25
    assert response.usage.total_tokens == 125
    assert response.raw["command"][-2:] == ["-p", "hello"]


# ---------------------------------------------------------------------------
# Provider-reported and unavailable receipts
# ---------------------------------------------------------------------------


def test_success_receipt_reports_truthful_v2_counters():
    result = capture_usage(_receipt())

    assert result == {
        "basis": "provider_reported",
        "source": AGY_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 25,
        "cached_input_tokens": 50,
        "reasoning_tokens": 10,
        "total_tokens": 125,
    }


def test_error_receipt_with_real_usage_is_provider_reported():
    # This is the recorded worker-parser shape: cache history may exceed the
    # current input count, while total_tokens remains input + output.
    result = capture_usage(
        _receipt(
            status="ERROR",
            response="",
            error="timeout waiting for response",
            usage={
                "input_tokens": 151398,
                "output_tokens": 17770,
                "thinking_tokens": 11165,
                "cache_read_tokens": 1218308,
                "total_tokens": 169168,
            },
        )
    )

    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 151398
    assert result["output_tokens"] == 17770
    assert result["cached_input_tokens"] == 1218308
    assert result["reasoning_tokens"] == 11165
    assert result["total_tokens"] == 169168


def test_successful_zero_receipt_preserves_reported_zeroes():
    result = capture_usage(
        _receipt(
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "cache_read_tokens": 0,
                "total_tokens": 0,
            }
        )
    )

    assert result == {
        "basis": "provider_reported",
        "source": AGY_USAGE_SOURCE,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }


def test_error_zero_receipt_is_unavailable_not_zero_evidence():
    result = capture_usage(
        _receipt(
            status="ERROR",
            response="",
            error="timeout waiting for response",
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "cache_read_tokens": 0,
                "total_tokens": 0,
            },
        )
    )

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": "agy -p output contained no terminal usage receipt",
        **UNAVAILABLE_COUNTERS,
    }


def test_missing_receipt_is_unavailable_with_null_counters():
    result = capture_usage("completion text only")

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": "agy -p output contained no parseable JSON usage line",
        **UNAVAILABLE_COUNTERS,
    }


def test_empty_output_is_unavailable():
    result = capture_usage("  \n")

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": "agy -p output was empty",
        **UNAVAILABLE_COUNTERS,
    }


def test_malformed_line_is_unavailable_and_never_estimated():
    result = capture_usage("{not a recorded receipt")

    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "agy -p output contained no parseable JSON usage line"
    )
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_malformed_log_line_does_not_hide_a_valid_receipt():
    result = capture_usage("diagnostic text\n{not json\n" + _receipt())

    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 100
    assert result["total_tokens"] == 125


def test_receipt_missing_required_counter_is_unavailable():
    result = capture_usage(_receipt(usage={"input_tokens": 100, "total_tokens": 100}))

    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "agy -p usage receipt lacked valid input_tokens/output_tokens"
    )
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_absent_optional_counters_are_null_not_zero():
    result = capture_usage(_receipt(usage={"input_tokens": 10, "output_tokens": 4}))

    assert result["basis"] == "provider_reported"
    assert result["cached_input_tokens"] is None
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] == 14


# ---------------------------------------------------------------------------
# Fail closed on malformed reported values and contradictions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": 10, "output_tokens": 4, "thinking_tokens": -1},
        {"input_tokens": 10, "output_tokens": 4, "thinking_tokens": 5.5},
        {"input_tokens": 10, "output_tokens": 4, "cache_read_tokens": "5"},
        {"input_tokens": 10, "output_tokens": 4, "total_tokens": "14"},
    ],
    ids=["negative-reasoning", "fractional-reasoning", "string-cache", "string-total"],
)
def test_malformed_reported_counter_fails_closed(usage):
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(_receipt(usage=usage))

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_conflicting_aliases_fail_closed():
    result = {
        "status": "SUCCESS",
        "response": "done",
        "usage": {
            "input_tokens": 10,
            "prompt_tokens": 11,
            "output_tokens": 4,
        },
    }

    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(json.dumps(result))

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "conflicting values" in str(exc_info.value)


def test_conflicting_envelope_and_usage_values_fail_closed():
    result = {
        "status": "SUCCESS",
        "response": "done",
        "input_tokens": 11,
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }

    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(json.dumps(result))

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_contradictory_total_fails_closed():
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(
            _receipt(
                usage={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": 99,
                }
            )
        )

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "total_tokens contradicts" in str(exc_info.value)


def test_thinking_tokens_greater_than_output_fails_closed():
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(
            _receipt(
                usage={
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "thinking_tokens": 5,
                }
            )
        )

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_duplicate_json_key_fails_closed():
    output = (
        '{"status":"SUCCESS","response":"done",'
        '"usage":{"input_tokens":10,"input_tokens":11,"output_tokens":4}}'
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(output)

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_multiple_usage_receipts_fail_closed():
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(_receipt() + "\n" + _receipt())

    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


# ---------------------------------------------------------------------------
# Strict v2 shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output",
    [
        _receipt(),
        _receipt(
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        ),
        "",
        "plain completion without receipt",
    ],
    ids=["reported", "reported-zero", "empty", "unavailable"],
)
def test_every_returned_usage_has_exact_v2_keys(output):
    result = capture_usage(output)
    errors = list(_usage_validator().iter_errors(result))

    assert not errors, [(list(error.absolute_path), error.message) for error in errors]
    if result["basis"] == "provider_reported":
        assert set(result) == {
            "basis",
            "source",
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "total_tokens",
        }
    else:
        assert set(result) == {
            "basis",
            "unavailable_reason",
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "total_tokens",
        }
