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
        "--verbose",
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
        "--verbose",
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
        "total_tokens": 190,
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
    assert result["total_tokens"] == 190


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

    # 100 + 7 input, 25 + 3 output, 60 cached, 5 cache creation:
    # the top-level usage object (500/500) is never added on top of the
    # summed model rows.
    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 107,
        "output_tokens": 28,
        "cached_input_tokens": 60,
        "reasoning_tokens": None,
        "total_tokens": 200,
    }


def test_cache_read_reports_zero_when_a_row_reports_zero():
    output = _result_event(
        modelUsage={
            "claude-opus-5": _model_usage_row(
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
            ),
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
        # Astra final-review finding 2: absent cache components are unknown,
        # never zero, so no total is manufactured from input + output alone.
        "total_tokens": None,
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

    # Cache reads map to cached_input_tokens and cache creation contributes
    # to total_tokens (10 + 4 + 3 + 2 = 19); cache creation has no v2 field
    # of its own.
    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 4,
        "cached_input_tokens": 3,
        "reasoning_tokens": None,
        "total_tokens": 19,
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
    # Cache creation is absent (unknown, never zero), so the total cannot
    # be calculated from the components and stays unknown.
    assert result["total_tokens"] is None


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


# ---------------------------------------------------------------------------
# Astra Claude usage aggregation regression tests
# ---------------------------------------------------------------------------


def test_reproducer_partial_cache_evidence_preserves_null_not_invented_zero():
    """Reproducer 1: two modelUsage rows, only first has cache count.

    Missing cache count in row 2 must not be treated as zero (which previously
    yielded numeric 5); truth is preserved as unavailable/null (both
    cached_input_tokens and total_tokens stay None).
    """
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
            },
            "claude-haiku-4": {
                "inputTokens": 50,
                "outputTokens": 10,
            },
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def test_reproducer_partial_cache_evidence_with_authoritative_row_totals():
    """Reproducer 1 with authoritative row totalTokens preserves reported total."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "totalTokens": 125,
            },
            "claude-haiku-4": {
                "inputTokens": 50,
                "outputTokens": 10,
                "totalTokens": 60,
            },
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 185,
    }


def test_reproducer_cache_creation_counted_in_total():
    """Reproducer 2: row input=100 output=20 cache-read=5 cache-creation=2.

    Total must be 127; previously computed 125 omitting cache-creation=2.
    """
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "cacheCreationInputTokens": 2,
            }
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 20,
        "cached_input_tokens": 5,
        "reasoning_tokens": None,
        "total_tokens": 127,
    }


def test_reproducer_cache_creation_contradictory_total_raises():
    """Reproducer 2 contradiction: row reports total=125 omitting cache-creation=2."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "cacheCreationInputTokens": 2,
                "totalTokens": 125,
            }
        }
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "total contradicts its components" in str(exc_info.value)


def test_reproducer_cache_creation_matching_total_succeeds():
    """Reproducer 2 with matching totalTokens=127 succeeds."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "cacheCreationInputTokens": 2,
                "totalTokens": 127,
            }
        }
    )

    result = capture_claude_usage(output)

    assert result["total_tokens"] == 127
    assert result["cached_input_tokens"] == 5


def test_normal_multi_row_aggregation_with_all_cache_components():
    """Normal multi-row aggregation where every row reports cache read and creation."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "cacheCreationInputTokens": 2,
            },
            "claude-haiku-4": {
                "inputTokens": 50,
                "outputTokens": 10,
                "cacheReadInputTokens": 3,
                "cacheCreationInputTokens": 1,
            },
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": 8,
        "reasoning_tokens": None,
        "total_tokens": 191,
    }


def test_normal_multi_row_aggregation_cache_reads_only():
    """Normal multi-row aggregation where all rows report cache read, none write."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
            },
            "claude-haiku-4": {
                "inputTokens": 50,
                "outputTokens": 10,
                "cacheReadInputTokens": 3,
            },
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": 8,
        "reasoning_tokens": None,
        # Cache creation is absent from every row: unknown, never zero, so
        # the total cannot be calculated from the components and stays
        # unknown unless the source reports it.
        "total_tokens": None,
    }


def test_normal_multi_row_aggregation_no_cache_components():
    """Normal multi-row aggregation where no rows report cache components."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
            },
            "claude-haiku-4": {
                "inputTokens": 50,
                "outputTokens": 10,
            },
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        # Astra final-review finding 2 reproducer shape: cache components
        # absent from every row are unknown, never zero, so the total is
        # never manufactured as input + output.
        "total_tokens": None,
    }


def test_multi_row_partial_cache_creation_withholds_total():
    """Multi-row with complete cache reads but partial creation withholds total."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "cacheCreationInputTokens": 2,
            },
            "claude-haiku-4": {
                "inputTokens": 50,
                "outputTokens": 10,
                "cacheReadInputTokens": 3,
            },
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": 8,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def test_top_level_usage_contradictory_total_raises():
    """Top-level usage fallback raises when totalTokens contradicts components."""
    output = _result_event(
        usage={
            "inputTokens": 100,
            "outputTokens": 20,
            "cacheReadInputTokens": 5,
            "cacheCreationInputTokens": 2,
            "totalTokens": 125,
        }
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "total contradicts its components" in str(exc_info.value)


def test_result_event_contradictory_top_level_total_raises():
    """Result event top-level totalTokens contradicts modelUsage total."""
    output = _result_event(
        totalTokens=999,
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
                "cacheCreationInputTokens": 2,
            }
        },
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "total contradicts its components" in str(exc_info.value)


def test_invalid_total_tokens_raises():
    """Invalid totalTokens counter (negative, bool, float) raises."""
    output = _result_event(
        usage={"inputTokens": 10, "outputTokens": 4, "totalTokens": -1}
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_astra_final_review_finding2_absent_cache_components_keep_total_unknown():
    """Quoted Astra final-review finding 2 reproducer.

    ``{"type":"result","usage":{"input_tokens":10,"output_tokens":2}}``
    previously returned ``total_tokens=12`` by substituting zero for the
    absent cache components; the total must stay unknown unless reported
    or calculated from complete authoritative components.
    """
    result = capture_claude_usage(
        '{"type":"result","usage":{"input_tokens":10,"output_tokens":2}}'
    )

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 2,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def test_regression_usages_are_schema_valid():
    """Validate all regression result shapes against attempt-record v2 schema."""
    validator = _usage_validator()
    repro1 = capture_claude_usage(
        _result_event(
            modelUsage={
                "claude-opus-5": {
                    "inputTokens": 100,
                    "outputTokens": 20,
                    "cacheReadInputTokens": 5,
                },
                "claude-haiku-4": {"inputTokens": 50, "outputTokens": 10},
            }
        )
    )
    repro2 = capture_claude_usage(
        _result_event(
            modelUsage={
                "claude-opus-5": {
                    "inputTokens": 100,
                    "outputTokens": 20,
                    "cacheReadInputTokens": 5,
                    "cacheCreationInputTokens": 2,
                }
            }
        )
    )
    normal_multi = capture_claude_usage(
        _result_event(
            modelUsage={
                "claude-opus-5": {
                    "inputTokens": 100,
                    "outputTokens": 20,
                    "cacheReadInputTokens": 5,
                    "cacheCreationInputTokens": 2,
                },
                "claude-haiku-4": {
                    "inputTokens": 50,
                    "outputTokens": 10,
                    "cacheReadInputTokens": 3,
                    "cacheCreationInputTokens": 1,
                },
            }
        )
    )
    for mapping in (repro1, repro2, normal_multi):
        validator.validate(mapping)


# ---------------------------------------------------------------------------
# Astra final re-review finding 1: totals below known cache components
# ---------------------------------------------------------------------------


def test_reproducer_cache_write_contradictory_total_without_cache_read_raises():
    """Astra final re-review finding 1: the exact CLI reproducer receipt.

    Top-level usage fallback with input=10, output=2,
    cache_creation_input_tokens=100, absent cache-read, and reported
    total_tokens=12 previously kept the reported total, silently
    discarding the known cache-write evidence and letting ``run`` bill
    input/output only. The total can never be below the components the
    source does report, so it raises instead.
    """
    output = _result_event(
        usage={
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_creation_input_tokens": 100,
            "total_tokens": 12,
        }
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "is below its known components" in str(exc_info.value)
    assert "112" in str(exc_info.value)


def test_model_usage_row_cache_write_total_below_known_components_raises():
    """The modelUsage path rejects the same contradictory row total."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "cacheCreationInputTokens": 100,
                "totalTokens": 12,
            }
        }
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "is below its known components" in str(exc_info.value)
    assert "112" in str(exc_info.value)


def test_cache_write_total_equal_to_known_minimum_is_preserved():
    """Valid neighbor: a total at the known-component minimum is kept.

    With the cache-read component absent (unknown), a reported total of
    exactly input + output + cache-write is consistent evidence: the
    authoritative total is preserved, no cache-read count is invented,
    and the cache-write evidence stays representable through the total.
    """
    output = _result_event(
        usage={
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_creation_input_tokens": 100,
            "total_tokens": 112,
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 2,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 112,
    }
    _usage_validator().validate(result)


def test_model_usage_row_cache_write_total_equal_to_known_minimum_is_preserved():
    """Valid neighbor on the modelUsage path: total 112 with unknown cache-read."""
    output = _result_event(
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "cacheCreationInputTokens": 100,
                "totalTokens": 112,
            }
        }
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 2,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 112,
    }
    _usage_validator().validate(result)


def test_event_total_below_known_cache_components_raises():
    """A result-event total below known components is a contradiction too.

    The rows report cache-creation evidence without row totals, so the
    event's own ``totalTokens`` would previously become the aggregate
    total unvalidated — silently dropping the cache-write evidence from
    billing. It must be rejected.
    """
    output = _result_event(
        totalTokens=12,
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "cacheCreationInputTokens": 100,
            }
        },
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "is below its known components" in str(exc_info.value)


def test_event_total_equal_to_known_cache_components_is_preserved():
    """Valid neighbor: event total 112 fills the unknown aggregate truthfully."""
    output = _result_event(
        totalTokens=112,
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "cacheCreationInputTokens": 100,
            }
        },
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 10,
        "output_tokens": 2,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 112,
    }
    _usage_validator().validate(result)


def test_partial_cache_rows_with_contradictory_event_total_raise():
    """Partial cache evidence still bounds the event total from below.

    Only the first row reports cache-read evidence; the summed known
    components (150 + 30 + 5 = 185) are a lower bound for the event
    total, so totalTokens=12 is contradictory and raises.
    """
    output = _result_event(
        totalTokens=12,
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
            },
            "claude-haiku-4": {"inputTokens": 50, "outputTokens": 10},
        },
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "is below its known components" in str(exc_info.value)


def test_partial_cache_rows_with_consistent_event_total_is_preserved():
    """Valid neighbor: event total 185 with partial cache evidence succeeds."""
    output = _result_event(
        totalTokens=185,
        modelUsage={
            "claude-opus-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 5,
            },
            "claude-haiku-4": {"inputTokens": 50, "outputTokens": 10},
        },
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 150,
        "output_tokens": 30,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 185,
    }
    _usage_validator().validate(result)


# ---------------------------------------------------------------------------
# Astra final-gate finding 1: reported row totals reconcile with the
# other rows' known-component lower bounds; contradictory event totals
# are rejected instead of accepted.
# ---------------------------------------------------------------------------


def _final_gate_receipt(**event_fields: object) -> str:
    """The exact final-gate receipt shape: one total-reporting row with
    absent cache counters, one complete-component row without a total,
    and optionally the event's own totalTokens."""
    return _result_event(
        modelUsage={
            "claude-sonnet-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 112,
            },
            "claude-haiku-4": {
                "inputTokens": 20,
                "outputTokens": 3,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 0,
            },
        },
        **event_fields,
    )


def test_final_gate_contradictory_event_total_below_reconciled_rows_raises():
    """The exact final-gate blocker 1 reproducer must fail closed.

    Row A reports totalTokens=112 (absent cache counters) and row B
    reports complete components (20 + 3 + 0 + 0 = 23, no row total), so
    the reconciled aggregate truth is 112 + 23 = 135. The event's own
    totalTokens=35 was previously accepted as ``provider_reported``
    because the reported row total was excluded from the aggregate and
    35 merely covered input + output + known cache. It contradicts the
    rows and must raise.
    """
    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(_final_gate_receipt(totalTokens=35))
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "event total contradicts" in str(exc_info.value)


def test_final_gate_reconciled_rows_without_event_total():
    """Valid neighbor: no event total keeps the reconciled row truth.

    The reported row total (112) is never discarded just because the
    other row lacks a total; together with the other row's complete
    component sum (23) the aggregate total is exact at 135. Row A's
    absent cache counters stay unknown, so ``cached_input_tokens``
    stays null with no invented zero.
    """
    result = capture_claude_usage(_final_gate_receipt())

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 30,
        "output_tokens": 5,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 135,
    }
    _usage_validator().validate(result)


def test_final_gate_event_total_equal_to_reconciled_rows_is_preserved():
    """Valid neighbor: an event total matching the reconciled rows passes."""
    result = capture_claude_usage(_final_gate_receipt(totalTokens=135))

    assert result["total_tokens"] == 135
    assert result["input_tokens"] == 30
    assert result["output_tokens"] == 5
    assert result["cached_input_tokens"] is None
    _usage_validator().validate(result)


def test_final_gate_event_total_above_exact_rows_contradicts():
    """Event total above an exact row aggregate is also contradictory.

    With both rows exact (a reported total and complete components),
    the summed row truth 135 is the aggregate; any other event total,
    higher included, contradicts it and raises.
    """
    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(_final_gate_receipt(totalTokens=140))
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "event total contradicts" in str(exc_info.value)


def test_final_gate_mixed_unknown_cache_event_total_below_row_total_raises():
    """Mixed rows with unknown cache still bound the event total from below.

    Row B here lacks cache counters and a row total, so only its known
    components (23) are a lower bound; row A's reported total (112) is
    exact. The reconciled lower bound is 135, so the contradictory
    event totalTokens=35 raises instead of being accepted.
    """
    output = _result_event(
        totalTokens=35,
        modelUsage={
            "claude-sonnet-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 112,
            },
            "claude-haiku-4": {"inputTokens": 20, "outputTokens": 3},
        },
    )

    with pytest.raises(LLMRouterError) as exc_info:
        capture_claude_usage(output)
    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "is below its known components" in str(exc_info.value)
    assert "(135)" in str(exc_info.value)


def test_final_gate_mixed_unknown_cache_event_total_at_lower_bound_is_preserved():
    """Valid neighbor: event total at the reconciled lower bound fills it."""
    output = _result_event(
        totalTokens=135,
        modelUsage={
            "claude-sonnet-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 112,
            },
            "claude-haiku-4": {"inputTokens": 20, "outputTokens": 3},
        },
    )

    result = capture_claude_usage(output)

    assert result["total_tokens"] == 135
    _usage_validator().validate(result)


def test_final_gate_mixed_unknown_cache_event_total_above_lower_bound_is_preserved():
    """Valid neighbor: an event total above the lower bound is consistent.

    The unknown cache in the row without a total can only add tokens,
    so event totalTokens=140 is consistent with the reconciled rows and
    becomes the aggregate without inventing any counter.
    """
    output = _result_event(
        totalTokens=140,
        modelUsage={
            "claude-sonnet-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 112,
            },
            "claude-haiku-4": {"inputTokens": 20, "outputTokens": 3},
        },
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 30,
        "output_tokens": 5,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": 140,
    }
    _usage_validator().validate(result)


def test_final_gate_mixed_unknown_cache_without_event_total_keeps_total_unknown():
    """Adjacent valid case: with an unknown-cache row and no event total,

    the aggregate total stays unknown even though one row reports a
    total — the other row's cache could add tokens beyond the 135
    lower bound, and nothing is invented.
    """
    output = _result_event(
        modelUsage={
            "claude-sonnet-5": {
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 112,
            },
            "claude-haiku-4": {"inputTokens": 20, "outputTokens": 3},
        },
    )

    result = capture_claude_usage(output)

    assert result == {
        "basis": "provider_reported",
        "source": CLAUDE_USAGE_SOURCE,
        "input_tokens": 30,
        "output_tokens": 5,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }
    _usage_validator().validate(result)


def test_final_gate_regressions_are_schema_valid():
    """The exact gate receipt shapes that yield usage validate against v2."""
    validator = _usage_validator()
    for mapping in (
        capture_claude_usage(_final_gate_receipt()),
        capture_claude_usage(_final_gate_receipt(totalTokens=135)),
    ):
        validator.validate(mapping)


def test_stream_json_argv_carries_verbose_flag():
    """`--print --output-format=stream-json` requires `--verbose`.

    Without it the Claude CLI exits before emitting anything:
    "Error: When using --print, --output-format=stream-json requires
    --verbose", so every governed Claude dispatch failed instantly with empty
    stdout and an unavailable usage record.
    """
    from lee_llm_router.providers.codex_cli import (
        CLAUDE_GOVERNED_CONFIG,
        ClaudeCodeCLIProvider,
    )

    provider = ClaudeCodeCLIProvider()
    config = {
        "command": "claude",
        **CLAUDE_GOVERNED_CONFIG,
    }
    argv = provider.build_command(config)

    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv, f"stream-json argv must carry --verbose: {argv}"
    assert argv[-1] == "{prompt}", f"prompt must stay last: {argv}"


def test_non_stream_json_output_format_does_not_add_verbose():
    """Other output formats keep their existing argv contract unchanged."""
    from lee_llm_router.providers.codex_cli import ClaudeCodeCLIProvider

    provider = ClaudeCodeCLIProvider()
    argv = provider.build_command(
        {"command": "claude", "output_format": "json"}
    )

    assert "--verbose" not in argv, f"unexpected --verbose: {argv}"
