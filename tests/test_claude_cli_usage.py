"""P1-4c Claude Code governed command and usage capture tests.

Authority: docs/staffing/phase1-contracts.md §Usage evidence taxonomy
(exact source ``claude -p --output-format stream-json result event``),
with the authoritative result-event shape documented in the benchmark
``src/workbench/capture.py`` result-event reader and the accepted
P1-4a/P1-4b v2 usage mapping conventions. Every scenario feeds inline
recorded strings; no Claude binary, provider, router state, or live
call is exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.providers.codex_cli import (
    CLAUDE_GOVERNED_CONFIG,
    CLAUDE_USAGE_SOURCE,
    ClaudeCodeCLIProvider,
    CodexCLIProvider,
    capture_claude_usage,
)

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
    """Draft 2020-12 validator for the attempt-record v2 usage subschema.

    Re-roots the full schema's ``$defs`` so the ``$defs/usage`` subschema
    can be validated standalone and ``tokenCounter`` refs resolve.
    """
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/usage"})


def _event(event_type: str, **fields: object) -> str:
    return json.dumps({"type": event_type, **fields})


def _model_usage_row(**counters: int) -> dict[str, int]:
    """Recorded-shape modelUsage row in camelCase."""
    base = {
        "inputTokens": 100,
        "outputTokens": 25,
        "cacheReadInputTokens": 60,
        "cacheCreationInputTokens": 5,
    }
    base.update(counters)
    return base


def _result_event(**fields: object) -> str:
    return _event("result", **fields)


# ---------------------------------------------------------------------------
# Governed command argv
# ---------------------------------------------------------------------------


def test_usage_source_is_the_exact_taxonomy_string():
    assert CLAUDE_USAGE_SOURCE == ("claude -p --output-format stream-json result event")


def test_governed_command_includes_stream_json_and_safe_permission_flags():
    """P1-8: governed argv carries the documented safe noninteractive pair."""
    provider = ClaudeCodeCLIProvider()

    cmd = provider.build_command({"command": "claude", **CLAUDE_GOVERNED_CONFIG})

    assert cmd == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--permission-mode",
        "acceptEdits",
        "--permission-prompts",
        "none",
        "{prompt}",
    ]


def test_governed_command_contains_no_bypass_flag():
    """The governed argv never carries any documented bypass form."""
    provider = ClaudeCodeCLIProvider()

    cmd = provider.build_command({"command": "claude", **CLAUDE_GOVERNED_CONFIG})

    for forbidden in (
        "bypassPermissions",
        "--permission-mode=bypassPermissions",
        "--dangerously-skip-permissions",
    ):
        assert forbidden not in cmd


def test_governed_command_keeps_model_and_effort_before_the_format_pair():
    provider = ClaudeCodeCLIProvider()

    cmd = provider.build_command(
        {"command": "claude", "model": "claude-opus-5", **CLAUDE_GOVERNED_CONFIG},
        effort="high",
    )

    assert cmd == [
        "claude",
        "--model",
        "claude-opus-5",
        "--effort",
        "high",
        "-p",
        "--output-format",
        "stream-json",
        "--permission-mode",
        "acceptEdits",
        "--permission-prompts",
        "none",
        "{prompt}",
    ]


def test_legacy_claude_and_codex_argv_are_unchanged():
    provider = ClaudeCodeCLIProvider()

    assert provider.build_command({"command": "claude"}, effort="high") == [
        "claude",
        "--effort",
        "high",
        "-p",
        "{prompt}",
    ]
    assert CodexCLIProvider().build_command(
        {"command": "codex", "model": "m", "json_flag": "--json"}
    ) == ["codex", "exec", "--json", "--model", "m", "{prompt}"]


def test_permission_args_without_output_format_still_precede_the_prompt():
    """The governed pair is prompt-adjacent even without governed capture."""
    provider = ClaudeCodeCLIProvider()

    cmd = provider.build_command(
        {
            "command": "claude",
            "permission_args": ["--permission-mode", "acceptEdits"],
        }
    )

    assert cmd == [
        "claude",
        "-p",
        "--permission-mode",
        "acceptEdits",
        "{prompt}",
    ]


@pytest.mark.parametrize(
    "bypass_args",
    [
        ["--permission-mode", "bypassPermissions"],
        ["--permission-mode=bypassPermissions"],
        ["--dangerously-skip-permissions"],
    ],
    ids=["mode_value", "mode_equals", "skip_flag"],
)
def test_permission_args_bypass_forms_are_rejected(bypass_args):
    """The builder fails closed instead of ever emitting a bypass flag."""
    provider = ClaudeCodeCLIProvider()

    with pytest.raises(LLMRouterError) as exc_info:
        provider.build_command({"command": "claude", "permission_args": bypass_args})

    assert "permission bypass flag" in str(exc_info.value)


def test_invalid_permission_args_type_is_rejected():
    provider = ClaudeCodeCLIProvider()

    with pytest.raises(LLMRouterError) as exc_info:
        provider.build_command(
            {"command": "claude", "permission_args": ["--permission-mode", 1]}
        )

    assert "'permission_args' must be a list of strings" in str(exc_info.value)


# ---------------------------------------------------------------------------
# provider_reported: object and JSONL result events
# ---------------------------------------------------------------------------


def test_single_json_object_result_event_with_model_usage():
    output = _result_event(
        modelUsage={"claude-opus-5": _model_usage_row()},
    )

    assert capture_claude_usage(output) == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 25,
        "cached_input_tokens": 60,
        "reasoning_tokens": None,
        "total_tokens": 185,
    }


def test_jsonl_stream_uses_the_last_result_event():
    output = "\n".join(
        [
            _event("assistant", message={"role": "assistant"}),
            _result_event(usage={"inputTokens": 1, "outputTokens": 1}),
            _result_event(
                usage={"input_tokens": 999, "output_tokens": 1},
                modelUsage={"claude-opus-5": _model_usage_row()},
            ),
        ]
    )

    result = capture_claude_usage(output)

    assert result["basis"] == "provider_reported"
    assert result["input_tokens"] == 100
    assert result["total_tokens"] == 185


def test_model_rows_are_summed_once_and_top_level_usage_is_not_added():
    output = _result_event(
        usage={"input_tokens": 500, "output_tokens": 500},
        modelUsage={
            "claude-opus-5": _model_usage_row(),
            "claude-haiku-4": _model_usage_row(
                inputTokens=7,
                outputTokens=3,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
            ),
        },
    )

    result = capture_claude_usage(output)

    # 100 + 7 input, 25 + 3 output, 60 cached: the top-level usage object
    # (500/500) is never added on top of the summed model rows.
    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 107,
        "output_tokens": 28,
        "cached_input_tokens": 60,
        "reasoning_tokens": None,
        "total_tokens": 195,
    }


def test_cache_read_reports_zero_when_a_row_reports_zero():
    output = _result_event(
        modelUsage={
            "claude-opus-5": _model_usage_row(cacheReadInputTokens=0),
        },
    )

    result = capture_claude_usage(output)

    assert result["cached_input_tokens"] == 0
    assert result["total_tokens"] == 125


def test_top_level_usage_fallback_snake_aliases():
    output = _result_event(usage={"input_tokens": 10, "output_tokens": 4})

    assert capture_claude_usage(output) == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 4,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 14,
    }


def test_top_level_usage_fallback_camel_aliases_and_cached_reads():
    output = _result_event(
        usage={
            "inputTokens": 10,
            "outputTokens": 4,
            "cacheReadInputTokens": 3,
            "cacheCreationInputTokens": 2,
        },
    )

    result = capture_claude_usage(output)

    # Cache reads map to cached_input_tokens and count toward the
    # observed-component total; cache creation has no v2 field and is
    # omitted entirely.
    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 4,
        "cached_input_tokens": 3,
        "reasoning_tokens": None,
        "total_tokens": 17,
    }


def test_top_level_usage_snake_cached_alias():
    output = _result_event(
        usage={
            "input_tokens": 10,
            "output_tokens": 4,
            "cache_read_input_tokens": 3,
        },
    )

    result = capture_claude_usage(output)

    assert result["cached_input_tokens"] == 3
    assert result["total_tokens"] == 17


def test_zero_usage_is_provider_reported_not_unknown():
    output = _result_event(
        modelUsage={
            "claude-opus-5": _model_usage_row(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
            ),
        },
    )

    assert capture_claude_usage(output) == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": None,
        "total_tokens": 0,
    }


# ---------------------------------------------------------------------------
# unavailable: missing, malformed, unrelated
# ---------------------------------------------------------------------------


def test_empty_output_is_unavailable():
    result = capture_claude_usage("   \n  ")

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": "Claude stream-json output was empty",
        **UNAVAILABLE_COUNTERS,
    }


def test_output_without_result_event_is_unavailable():
    output = "\n".join(
        [
            _event("system", subtype="init"),
            _event("assistant", message={"role": "assistant"}),
        ]
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": (
            "Claude stream-json output contained no terminal result event"
        ),
        **UNAVAILABLE_COUNTERS,
    }


def test_malformed_jsonl_is_unavailable():
    result = capture_claude_usage('{broken json\n{"type": "result"}\n')

    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Claude stream-json output had malformed JSON on line 1"
    )
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_whole_text_non_object_json_is_unavailable():
    result = capture_claude_usage("[1, 2, 3]")

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": (
            "Claude stream-json output was a JSON value, not an object"
        ),
        **UNAVAILABLE_COUNTERS,
    }


def test_result_event_without_usage_evidence_is_unavailable():
    output = _result_event(total_cost_usd=0.003)

    result = capture_claude_usage(output)

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": (
            "Claude result event carried no modelUsage or usage token evidence"
        ),
        **UNAVAILABLE_COUNTERS,
    }


def test_present_but_empty_model_usage_is_unavailable_even_with_top_level_usage():
    # modelUsage is the sole aggregate token source when the key is
    # present: an empty mapping must not fall through to the top-level
    # usage object (P1-4c review finding 2).
    output = _result_event(
        modelUsage={},
        usage={"input_tokens": 10, "output_tokens": 4},
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "unavailable",
        "unavailable_reason": ("Claude result event modelUsage was present but empty"),
        **UNAVAILABLE_COUNTERS,
    }


def test_valid_result_event_followed_by_malformed_json_is_unavailable():
    # Any malformed event invalidates the whole stream, so a valid
    # result event before it can never yield provider_reported usage
    # (P1-4c review finding 1).
    result = capture_claude_usage(
        '{"type":"result","modelUsage":{"m":{"inputTokens":10,'
        '"outputTokens":4}}}\n{broken'
    )

    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Claude stream-json output had malformed JSON on line 2"
    )
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_valid_result_event_followed_by_non_object_json_is_unavailable():
    # A non-object JSON event invalidates the whole stream just like a
    # malformed one.
    output = "\n".join(
        [
            _result_event(usage={"inputTokens": 10, "outputTokens": 4}),
            "[1, 2]",
        ]
    )

    result = capture_claude_usage(output)

    assert result["basis"] == "unavailable"
    assert result["unavailable_reason"] == (
        "Claude stream-json output had a non-object JSON event on line 2"
    )
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_model_usage_row_missing_required_counters_is_unavailable():
    output = _result_event(
        modelUsage={"claude-opus-5": {"cacheReadInputTokens": 3}},
    )

    result = capture_claude_usage(output)

    assert result["basis"] == "unavailable"
    assert "lacked valid inputTokens/outputTokens" in result["unavailable_reason"]
    assert "claude-opus-5" in result["unavailable_reason"]
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


# ---------------------------------------------------------------------------
# fail closed: contradictory terminal evidence raises
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [True, -5, 1.5, "12"],
    ids=["bool", "negative", "fractional", "string"],
)
def test_invalid_required_counter_in_model_row_raises(bad_value):
    output = _result_event(
        modelUsage={"claude-opus-5": _model_usage_row(inputTokens=bad_value)},
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


@pytest.mark.parametrize(
    "field",
    ["cacheReadInputTokens", "cacheCreationInputTokens"],
)
@pytest.mark.parametrize(
    "bad_value",
    [True, -1, 2.5],
    ids=["bool", "negative", "fractional"],
)
def test_invalid_cache_counter_raises(field, bad_value):
    output = _result_event(
        modelUsage={"claude-opus-5": _model_usage_row(**{field: bad_value})},
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_conflicting_model_row_aliases_raise():
    row = _model_usage_row()
    row["input_tokens"] = 999
    output = _result_event(modelUsage={"claude-opus-5": row})

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "conflicting values" in str(exc_info.value)


def test_conflicting_top_level_usage_aliases_raise():
    output = _result_event(
        usage={"inputTokens": 10, "input_tokens": 20, "output_tokens": 4},
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_invalid_top_level_required_counter_raises():
    output = _result_event(
        usage={"inputTokens": 10, "outputTokens": -4},
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_non_object_model_usage_raises():
    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(_result_event(modelUsage="claude-opus-5"))
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_non_object_model_usage_row_raises():
    output = _result_event(modelUsage={"claude-opus-5": 12})

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_non_object_result_usage_raises():
    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(_result_event(usage=[1, 2]))
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


# ---------------------------------------------------------------------------
# schema validity of the returned usage mapping
# ---------------------------------------------------------------------------


def test_returned_usages_are_schema_valid():
    validator = _usage_validator()
    available = capture_claude_usage(
        _result_event(modelUsage={"claude-opus-5": _model_usage_row()})
    )
    unavailable = capture_claude_usage("")

    for mapping in (available, unavailable):
        validator.validate(mapping)
    assert set(available) == {
        "basis",
        "source",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
    assert set(unavailable) == {
        "basis",
        "unavailable_reason",
        *UNAVAILABLE_COUNTERS,
    }
