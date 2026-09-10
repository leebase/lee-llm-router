"""P1-4a Pi JSON usage parser tests — inline recorded strings only.

Authority: D209 ruling 3 via docs/staffing/phase1-contracts.md
§Usage evidence taxonomy (exact source ``pi --mode json events``).
Parser semantics mirror the benchmark ``src/workbench/pi.py``
``_read_json_events`` and ``pi_stream_observation``. No Pi binary,
provider, router state, or fixtures are exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.providers.pi_cli import PI_USAGE_SOURCE, capture_usage

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
    model: str | None = "z-ai/glm-5.3-flash",
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
                    "reasoning": 8,
                    "totalTokens": 127,
                }
            ),
        ]
    )
    assert capture_usage(output) == {
        "basis": "provider_reported",
        "source": PI_USAGE_SOURCE,
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
    assert result["source"] == PI_USAGE_SOURCE
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


def test_all_malformed_output_unavailable() -> None:
    result = capture_usage("{not json\nalso {broken\n")
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Pi JSON output contained no parseable JSON events"
    )
    assert result["input_tokens"] is None
    assert result["total_tokens"] is None


def test_absent_usage_unavailable() -> None:
    output = _event("message_end", message={"role": "assistant", "content": "hi"})
    result = capture_usage(output)
    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Pi assistant message_end usage was incomplete; one or more "
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
        assert result["unavailable_reason"] == "Pi JSON output was empty"
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
        "Pi JSON output contained no assistant message_end events"
    )
    assert result["input_tokens"] is None


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
    assert result["source"] == PI_USAGE_SOURCE
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
            "reasoning": 30,
        }
    )
    result = capture_usage(output)
    assert result["basis"] == "provider_reported"
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] == 127


def test_cache_write_contributes_to_total_but_has_no_schema_field() -> None:
    # Pi's cacheWrite must remain internal evidence: it feeds totalTokens
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
            _assistant_usage(model="z-ai/glm-5.3-flash"),
            _assistant_usage(model="openai/gpt-5.6-luna"),
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
        # provider_reported with reasoning known.
        lambda: "\n".join(
            [
                _assistant_usage(
                    usage={
                        "input": 100,
                        "output": 20,
                        "cacheRead": 5,
                        "cacheWrite": 2,
                        "reasoning": 8,
                        "totalTokens": 127,
                    }
                )
            ]
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
