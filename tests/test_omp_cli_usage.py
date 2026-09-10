"""P1-4f OMP JSON usage parser and governed opt-in tests.

Authority: D209 ruling 3 via docs/staffing/phase1-contracts.md
§Usage evidence taxonomy (exact source ``omp -p --mode json events``).
Parser semantics mirror the accepted P1-4a Pi parser: omp is a pi fork
emitting the same agent-session event stream, and recorded local omp
session output confirms the usage shape (``input``, ``output``,
``cacheRead``, ``cacheWrite``, ``totalTokens``, ``reasoningTokens``, plus
an embedded ``cost`` object).  No omp binary, live model, or recorded
fixture file is exercised at test time: usage cases are inline recorded
strings and every subprocess is faked.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.providers.omp_cli import (
    OMP_USAGE_SOURCE,
    OmpCLIProvider,
    capture_usage,
)
from lee_llm_router.response import LLMRequest

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


def _assistant_usage(
    *,
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_read: int = 5,
    cache_write: int = 2,
    response_id: str | None = None,
    model: str | None = "openai/gpt-5.2",
    usage: dict[str, object] | None = None,
) -> str:
    if usage is None:
        usage = {
            "input": input_tokens,
            "output": output_tokens,
            "cacheRead": cache_read,
            "cacheWrite": cache_write,
            "totalTokens": input_tokens + output_tokens + cache_read + cache_write,
        }
    message: dict[str, object] = {"role": "assistant", "usage": usage}
    if model is not None:
        message["model"] = model
    if response_id is not None:
        message["responseId"] = response_id
    return _event("message_end", message=message)


# ---------------------------------------------------------------------------
# capture_usage: valid streams
# ---------------------------------------------------------------------------


def test_single_complete_message_end_jsonl() -> None:
    output = "\n".join(
        [
            _event("message_start"),
            _assistant_usage(
                usage={
                    "input": 100,
                    "output": 20,
                    "cacheRead": 5,
                    "cacheWrite": 2,
                    "reasoningTokens": 8,
                    "totalTokens": 127,
                }
            ),
        ]
    )
    assert capture_usage(output) == {
        "basis": "provider_reported",
        "source": OMP_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 20,
        "cached_input_tokens": 5,
        "reasoning_tokens": 8,
        "total_tokens": 127,
    }


def test_single_complete_message_end_json_object() -> None:
    output = json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "usage": {"input": 7, "output": 3, "cacheRead": 0, "cacheWrite": 0},
            },
        }
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["source"] == OMP_USAGE_SOURCE
    assert result["input_tokens"] == 7
    assert result["output_tokens"] == 3
    assert result["total_tokens"] == 10


def test_multiple_message_end_events_summed() -> None:
    output = "\n".join(
        [
            _assistant_usage(input_tokens=100, output_tokens=20),
            _assistant_usage(
                input_tokens=30, output_tokens=5, cache_read=0, cache_write=0
            ),
        ]
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 130
    assert result["output_tokens"] == 25
    assert result["cached_input_tokens"] == 5
    assert result["total_tokens"] == 162


def test_recorded_omp_usage_shape_with_reasoning_and_cost() -> None:
    # Shape copied from a recorded local omp session assistant message:
    # reasoningTokens alias plus an embedded cost object.  The cost object
    # is harness provenance and never influences token capture.
    output = _assistant_usage(
        usage={
            "input": 88649,
            "output": 430,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 89079,
            "reasoningTokens": 377,
            "cost": {
                "input": 0.0177298,
                "output": 0.000516,
                "cacheRead": 0,
                "cacheWrite": 0,
                "total": 0.0182458,
            },
        }
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["source"] == OMP_USAGE_SOURCE
    assert result["input_tokens"] == 88649
    assert result["output_tokens"] == 430
    assert result["reasoning_tokens"] == 377
    assert result["total_tokens"] == 89079


def test_agent_end_never_counted() -> None:
    output = "\n".join(
        [
            _assistant_usage(input_tokens=100, output_tokens=20),
            _event("agent_end"),
            _event(
                "agent_end",
                message={
                    "role": "assistant",
                    "usage": {
                        "input": 999,
                        "output": 999,
                        "cacheRead": 999,
                        "cacheWrite": 999,
                    },
                },
            ),
        ]
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 20


def test_duplicate_stable_id_counted_once() -> None:
    output = "\n".join(
        [
            _assistant_usage(input_tokens=100, output_tokens=20, response_id="resp_1"),
            _assistant_usage(input_tokens=999, output_tokens=999, response_id="resp_1"),
            _assistant_usage(input_tokens=10, output_tokens=4, response_id="resp_2"),
        ]
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 110
    assert result["output_tokens"] == 24


def test_non_assistant_message_end_not_counted() -> None:
    output = "\n".join(
        [
            _event(
                "message_end",
                message={
                    "role": "user",
                    "usage": {
                        "input": 50,
                        "output": 50,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                    },
                },
            ),
            _assistant_usage(input_tokens=100, output_tokens=20),
        ]
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 100


def test_malformed_lines_skipped_but_good_lines_counted() -> None:
    output = "\n".join(
        [
            "{not json",
            "",
            _assistant_usage(input_tokens=100, output_tokens=20),
            'truncated{"type":',
        ]
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 100


def test_genuine_reported_zero_is_valid() -> None:
    output = _assistant_usage(
        usage={
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 0,
        }
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["source"] == OMP_USAGE_SOURCE
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cached_input_tokens"] == 0
    assert result["total_tokens"] == 0


def test_reasoning_absent_withholds_only_reasoning() -> None:
    output = _assistant_usage(
        usage={"input": 100, "output": 20, "cacheRead": 5, "cacheWrite": 2}
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["reasoning_tokens"] is None
    # Optional reasoning stays null without a reason field: no schema key.
    assert set(result) == {
        "basis",
        "source",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
    assert result["total_tokens"] == 127


def test_reasoning_exceeding_output_withheld() -> None:
    output = _assistant_usage(
        usage={
            "input": 100,
            "output": 20,
            "cacheRead": 5,
            "cacheWrite": 2,
            "reasoningTokens": 30,
        }
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] == 127


def test_cache_write_contributes_to_total_but_has_no_schema_field() -> None:
    # omp's cacheWrite must remain internal evidence: it feeds totalTokens
    # reconciliation and total_tokens, yet never appears in the returned
    # mapping (the v2 usage subschema has no cache-write field).
    output = "\n".join(
        [
            _assistant_usage(input_tokens=100, output_tokens=20),  # 100+20+5+2
            _assistant_usage(  # 10+5+0+0
                input_tokens=10, output_tokens=5, cache_read=0, cache_write=0
            ),
        ]
    )
    result = capture_usage(output)
    assert result["total_tokens"] == (100 + 20 + 5 + 2) + (10 + 5)
    assert "cache_write_tokens" not in result


# ---------------------------------------------------------------------------
# capture_usage: missing / malformed streams are unavailable, never zero
# ---------------------------------------------------------------------------


def test_all_malformed_output_unavailable() -> None:
    result = capture_usage("{not json\nalso {broken\n")
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "OMP JSON output contained no parseable JSON events"
    )
    assert result["input_tokens"] is None
    assert result["total_tokens"] is None


def test_absent_usage_unavailable() -> None:
    output = _event("message_end", message={"role": "assistant", "content": "hi"})
    result = capture_usage(output)
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "OMP assistant message_end usage was incomplete; one or more "
        "counted assistant messages lacked valid input, output, or "
        "cache components"
    )
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] is None


def test_partial_usage_unavailable() -> None:
    output = _assistant_usage(usage={"input": 100, "output": 20})
    result = capture_usage(output)
    assert result["basis"] == "unavailable"
    assert "incomplete" in result["unavailable_reason"]
    assert result["total_tokens"] is None


def test_empty_output_unavailable() -> None:
    for output in ("", "   \n\t"):
        result = capture_usage(output)
        assert result["basis"] == "unavailable"
        assert result["unavailable_reason"] == "OMP JSON output was empty"
        assert result["input_tokens"] is None


def test_agent_end_only_output_unavailable() -> None:
    output = _event(
        "agent_end",
        message={
            "role": "assistant",
            "usage": {"input": 999, "output": 999, "cacheRead": 999, "cacheWrite": 999},
        },
    )
    result = capture_usage(output)
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "OMP JSON output contained no assistant message_end events"
    )
    assert result["input_tokens"] is None


# ---------------------------------------------------------------------------
# capture_usage: contradiction fails closed
# ---------------------------------------------------------------------------


def test_contradictory_total_rejected() -> None:
    output = _assistant_usage(
        usage={
            "input": 100,
            "output": 20,
            "cacheRead": 5,
            "cacheWrite": 2,
            "totalTokens": 999,
        }
    )
    with pytest.raises(LLMRouterError) as excinfo:
        capture_usage(output)
    assert excinfo.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "contradicts" in str(excinfo.value)


def test_non_integer_total_rejected() -> None:
    output = _assistant_usage(
        usage={
            "input": 100,
            "output": 20,
            "cacheRead": 5,
            "cacheWrite": 2,
            "totalTokens": "127",
        }
    )
    with pytest.raises(LLMRouterError) as excinfo:
        capture_usage(output)
    assert excinfo.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_conflicting_assistant_models_rejected() -> None:
    output = "\n".join(
        [
            _assistant_usage(model="openai/gpt-5.2"),
            _assistant_usage(model="z-ai/glm-5.3-flash"),
        ]
    )
    with pytest.raises(LLMRouterError) as excinfo:
        capture_usage(output)
    assert excinfo.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "conflicting assistant models" in str(excinfo.value)


# ---------------------------------------------------------------------------
# P1-5 schema validation: every returned usage mapping must be directly
# valid against attempt-record v2 $defs/usage (additionalProperties false).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output_factory",
    [
        # provider_reported with reasoningTokens known.
        lambda: _assistant_usage(
            usage={
                "input": 100,
                "output": 20,
                "cacheRead": 5,
                "cacheWrite": 2,
                "reasoningTokens": 8,
                "totalTokens": 127,
            }
        ),
        # provider_reported with reasoning withheld (null) and cacheWrite
        # folded into total_tokens only.
        lambda: _assistant_usage(
            usage={"input": 100, "output": 20, "cacheRead": 5, "cacheWrite": 2}
        ),
        # provider_reported with genuine source-reported zeros.
        lambda: _assistant_usage(
            usage={
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 0,
            }
        ),
        # unavailable: empty output.
        lambda: "",
        # unavailable: assistant message with no usage block.
        lambda: _event("message_end", message={"role": "assistant", "content": "hi"}),
    ],
    ids=[
        "provider-reported-reasoning-known",
        "provider-reported-reasoning-null",
        "provider-reported-genuine-zero",
        "unavailable-empty-output",
        "unavailable-no-usage",
    ],
)
def test_returned_usage_is_schema_valid_v2_usage(output_factory) -> None:
    result = capture_usage(output_factory())
    errors = list(_usage_validator().iter_errors(result))
    assert not errors, [(list(e.absolute_path), e.validator, e.message) for e in errors]


# ---------------------------------------------------------------------------
# Governed opt-in: command building
# ---------------------------------------------------------------------------


def test_build_command_legacy_has_no_mode_flag() -> None:
    provider = OmpCLIProvider()
    assert provider.build_command({}) == ["omp", "-p"]
    assert provider.build_command({"model": "m"}) == ["omp", "-p", "--model", "m"]


def test_build_command_explicit_text_mode_stays_legacy() -> None:
    provider = OmpCLIProvider()
    assert provider.build_command({"mode": "text"}) == ["omp", "-p"]


def test_build_command_governed_json_opt_in_injects_mode() -> None:
    provider = OmpCLIProvider()
    assert provider.build_command({"mode": "json"}) == ["omp", "-p", "--mode", "json"]
    assert provider.build_command({"mode": "json", "model": "openai/gpt-5.2"}) == [
        "omp",
        "-p",
        "--mode",
        "json",
        "--model",
        "openai/gpt-5.2",
    ]


def test_build_command_rejects_unknown_mode() -> None:
    provider = OmpCLIProvider()
    for mode in ("rpc", "rpc-ui", "jsonl", True):
        with pytest.raises(LLMRouterError) as excinfo:
            provider.build_command({"mode": mode})
        assert excinfo.value.failure_type is FailureType.PROVIDER_ERROR
        assert "'mode'" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Governed opt-in: complete() response extraction with faked subprocesses
# ---------------------------------------------------------------------------


def _json_stream() -> str:
    return "\n".join(
        [
            _event("session"),
            _event("agent_start"),
            _event("message_start", message={"role": "assistant", "content": []}),
            _event(
                "message_end",
                message={
                    "role": "assistant",
                    "model": "openai/gpt-5.2",
                    "content": [
                        {"type": "thinking", "thinking": "hmm"},
                        {"type": "text", "text": "ship it"},
                    ],
                    "usage": {
                        "input": 100,
                        "output": 20,
                        "cacheRead": 5,
                        "cacheWrite": 2,
                        "totalTokens": 127,
                        "reasoningTokens": 8,
                    },
                },
            ),
            _event("agent_end"),
        ]
    )


def test_complete_legacy_text_mode_preserved() -> None:
    provider = OmpCLIProvider()
    request = LLMRequest(role="worker", messages=[{"role": "user", "content": "hi"}])

    with patch(
        "lee_llm_router.providers.omp_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "Working...\nanswer\n", ""),
    ) as mock_run:
        response = provider.complete(request, {"model": "openai/gpt-5.2"})

    argv = mock_run.call_args.args[0]
    assert argv == ["omp", "-p", "--model", "openai/gpt-5.2"]
    assert "--mode" not in argv
    assert mock_run.call_args.kwargs["input"] == "hi"
    assert response.text == "answer"
    assert (response.usage.prompt_tokens, response.usage.total_tokens) == (0, 0)
    assert set(response.raw) == {"stdout", "stderr", "returncode", "command"}


def test_complete_json_mode_extracts_text_and_usage() -> None:
    provider = OmpCLIProvider()
    request = LLMRequest(role="worker", messages=[{"role": "user", "content": "hi"}])

    with patch(
        "lee_llm_router.providers.omp_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, _json_stream(), ""),
    ) as mock_run:
        response = provider.complete(request, {"mode": "json", "model": "m"})

    argv = mock_run.call_args.args[0]
    assert argv == ["omp", "-p", "--mode", "json", "--model", "m"]
    assert mock_run.call_args.kwargs["input"] == "hi"
    assert response.text == "ship it"
    assert response.usage.prompt_tokens == 100
    assert response.usage.completion_tokens == 20
    assert response.usage.total_tokens == 127
    assert response.raw["captured_usage"] == {
        "basis": "provider_reported",
        "source": OMP_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 20,
        "cached_input_tokens": 5,
        "reasoning_tokens": 8,
        "total_tokens": 127,
    }


def test_complete_json_mode_unavailable_usage_keeps_zero_counters() -> None:
    provider = OmpCLIProvider()
    request = LLMRequest(role="worker", messages=[{"role": "user", "content": "hi"}])
    stream = "\n".join(
        [
            _event(
                "message_end",
                message={
                    "role": "assistant",
                    "content": [{"type": "text", "text": "no usage here"}],
                },
            ),
        ]
    )

    with patch(
        "lee_llm_router.providers.omp_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, stream, ""),
    ):
        response = provider.complete(request, {"mode": "json"})

    assert response.text == "no usage here"
    assert response.usage.prompt_tokens == 0
    assert response.usage.completion_tokens == 0
    assert response.usage.total_tokens == 0
    assert response.raw["captured_usage"]["basis"] == "unavailable"
    assert response.raw["captured_usage"]["input_tokens"] is None


def test_complete_json_mode_toolcall_only_response_is_invalid() -> None:
    provider = OmpCLIProvider()
    request = LLMRequest(role="worker", messages=[{"role": "user", "content": "hi"}])
    stream = _event(
        "message_end",
        message={
            "role": "assistant",
            "content": [{"type": "toolCall", "id": "t1", "name": "read"}],
            "usage": {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0},
        },
    )

    with patch(
        "lee_llm_router.providers.omp_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, stream, ""),
    ):
        with pytest.raises(LLMRouterError) as excinfo:
            provider.complete(request, {"mode": "json"})
    assert excinfo.value.failure_type is FailureType.INVALID_RESPONSE


def test_complete_json_mode_multiple_text_blocks_joined() -> None:
    provider = OmpCLIProvider()
    request = LLMRequest(role="worker", messages=[{"role": "user", "content": "hi"}])
    stream = "\n".join(
        [
            _event(
                "message_end",
                message={
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "part one"},
                        {"type": "text", "text": "part two"},
                    ],
                    "usage": {"input": 1, "output": 2, "cacheRead": 0, "cacheWrite": 0},
                },
            ),
        ]
    )

    with patch(
        "lee_llm_router.providers.omp_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, stream, ""),
    ):
        response = provider.complete(request, {"mode": "json"})

    assert response.text == "part one\npart two"


def test_complete_legacy_empty_output_still_invalid() -> None:
    provider = OmpCLIProvider()
    request = LLMRequest(role="worker", messages=[{"role": "user", "content": "hi"}])

    with patch(
        "lee_llm_router.providers.omp_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "Working...\n", ""),
    ):
        with pytest.raises(LLMRouterError) as excinfo:
            provider.complete(request, {})
    assert excinfo.value.failure_type is FailureType.INVALID_RESPONSE
