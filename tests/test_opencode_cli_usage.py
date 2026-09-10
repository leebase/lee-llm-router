"""P1-4e OpenCode usage capture with fake process and scratch evidence only.

The event shape follows the installed read-only benchmark parser:
``step_finish.part.tokens`` from ``opencode run --format json``. No test calls
OpenCode or any model.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.providers.opencode_cli import (
    OPENCODE_GOVERNED_CONFIG,
    OPENCODE_USAGE_SOURCE,
    OPENCODE_WORKER_USAGE_SOURCE,
    OpenCodeCLIProvider,
    capture_usage,
)
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
    """Return a validator rooted at the strict attempt-record v2 usage shape."""
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/usage"})


def _event(event_type: str, **fields: object) -> str:
    return json.dumps({"type": event_type, **fields})


def _step(
    *,
    input_tokens: int = 100,
    output_tokens: int = 25,
    reasoning_tokens: int | None = 5,
    cached_input_tokens: int | None = 40,
    tokens: dict[str, object] | None = None,
    envelope: bool = False,
) -> str:
    """Build the recorded/reference OpenCode terminal event shape."""
    if tokens is None:
        tokens = {"input": input_tokens, "output": output_tokens}
        if reasoning_tokens is not None:
            tokens["reasoning"] = reasoning_tokens
        if cached_input_tokens is not None:
            tokens["cache"] = {"read": cached_input_tokens, "write": 3}
    if envelope:
        return _event("step_finish", tokens=tokens, cost=0.01)
    return _event("step_finish", part={"tokens": tokens, "cost": 0.01})


def _artifact_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "basis": "provider_reported",
        "source": OPENCODE_USAGE_SOURCE,
        "input_tokens": 12,
        "output_tokens": 4,
        "cached_input_tokens": 3,
        "reasoning_tokens": 2,
        "total_tokens": 18,
    }
    payload.update(overrides)
    return payload


def _request() -> LLMRequest:
    return LLMRequest(
        role="test",
        messages=[{"role": "user", "content": "hello"}],
        model="opencode-go/deepseek-v4-flash",
    )


def test_taxonomy_sources_are_exact() -> None:
    assert OPENCODE_USAGE_SOURCE == "opencode run JSON usage event"
    assert OPENCODE_WORKER_USAGE_SOURCE == (
        "opencode worker-written usage.json from provider output"
    )


def test_legacy_command_and_response_are_unchanged() -> None:
    provider = OpenCodeCLIProvider()
    config = {"model": "opencode-go/deepseek-v4-flash", "agent": "build"}
    assert provider.build_command(config) == [
        "opencode",
        "run",
        "-m",
        "opencode-go/deepseek-v4-flash",
        "--agent",
        "build",
        "{prompt}",
    ]

    with patch(
        "lee_llm_router.providers.opencode_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "  legacy answer  ", ""),
    ) as run:
        response = provider.complete(_request(), config)

    assert run.call_count == 1
    assert "--format" not in run.call_args.args[0]
    assert response.text == "legacy answer"
    assert response.raw["stdout"] == "  legacy answer  "
    assert response.usage.prompt_tokens == 0
    assert response.usage.completion_tokens == 0
    assert response.usage.total_tokens == 0


def test_governed_json_is_explicit_opt_in_and_preserves_argument_order() -> None:
    provider = OpenCodeCLIProvider()
    config = {
        "model": "opencode-go/deepseek-v4-flash",
        "agent": "build",
        **OPENCODE_GOVERNED_CONFIG,
    }
    assert provider.build_command(config) == [
        "opencode",
        "run",
        "-m",
        "opencode-go/deepseek-v4-flash",
        "--agent",
        "build",
        "--format",
        "json",
        "{prompt}",
    ]


@pytest.mark.parametrize("value", ["", "JSON", "yaml", True, 1])
def test_invalid_output_format_is_rejected(value: object) -> None:
    provider = OpenCodeCLIProvider()
    with pytest.raises(LLMRouterError) as exc_info:
        provider.validate_config(
            {"model": "opencode-go/deepseek-v4-flash", "output_format": value}
        )
    assert exc_info.value.failure_type is FailureType.PROVIDER_ERROR


def test_governed_complete_extracts_text_and_usage_from_one_fake_process() -> None:
    provider = OpenCodeCLIProvider()
    stdout = "\n".join(
        [
            _event("text", part={"text": "first"}),
            _event("text", part={"text": "second"}),
            _step(),
        ]
    )
    with patch(
        "lee_llm_router.providers.opencode_cli.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, stdout, ""),
    ) as run:
        response = provider.complete(
            _request(),
            {
                "model": "opencode-go/deepseek-v4-flash",
                **OPENCODE_GOVERNED_CONFIG,
            },
        )

    assert run.call_count == 1
    assert run.call_args.args[0][-3:] == ["--format", "json", "hello"]
    assert response.text == "first\nsecond"
    assert response.usage.prompt_tokens == 100
    assert response.usage.completion_tokens == 25
    assert response.usage.total_tokens == 130


def test_single_native_step_reports_strict_v2_usage() -> None:
    assert capture_usage(_step()) == {
        "basis": "provider_reported",
        "source": OPENCODE_USAGE_SOURCE,
        "input_tokens": 100,
        "output_tokens": 25,
        "cached_input_tokens": 40,
        "reasoning_tokens": 5,
        "total_tokens": 130,
    }


def test_multiple_step_finish_events_are_summed_once_each() -> None:
    output = "\n".join(
        [
            _event("text", part={"text": "answer"}),
            _step(),
            _step(
                input_tokens=10,
                output_tokens=4,
                reasoning_tokens=1,
                cached_input_tokens=2,
            ),
        ]
    )
    result = capture_usage(output)
    assert result["input_tokens"] == 110
    assert result["output_tokens"] == 29
    assert result["cached_input_tokens"] == 42
    assert result["reasoning_tokens"] == 6
    assert result["total_tokens"] == 145


def test_reference_envelope_fallback_and_snake_aliases_are_supported() -> None:
    result = capture_usage(
        _step(
            envelope=True,
            tokens={
                "input_tokens": 7,
                "output_tokens": 3,
                "reasoning_tokens": 1,
                "cache": {"cached_input_tokens": 2},
            },
        )
    )
    assert result["input_tokens"] == 7
    assert result["output_tokens"] == 3
    assert result["cached_input_tokens"] == 2
    assert result["reasoning_tokens"] == 1
    assert result["total_tokens"] == 11


def test_absent_optional_counters_stay_null_and_total_is_not_estimated() -> None:
    result = capture_usage(
        _step(tokens={"input": 7, "output": 3}, reasoning_tokens=None)
    )
    assert result["basis"] == "provider_reported"
    assert result["cached_input_tokens"] is None
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] is None


def test_mixed_optional_presence_stays_null_instead_of_assuming_zero() -> None:
    output = "\n".join(
        [
            _step(),
            _step(tokens={"input": 10, "output": 4}),
        ]
    )
    result = capture_usage(output)
    assert result["cached_input_tokens"] is None
    assert result["reasoning_tokens"] is None
    assert result["total_tokens"] is None


def test_genuine_reported_zeroes_are_preserved() -> None:
    result = capture_usage(
        _step(
            tokens={
                "input": 0,
                "output": 0,
                "reasoning": 0,
                "cache": {"read": 0, "write": 0},
            }
        )
    )
    assert result == {
        "basis": "provider_reported",
        "source": OPENCODE_USAGE_SOURCE,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }


@pytest.mark.parametrize(
    ("output", "reason"),
    [
        ("", "OpenCode --format json output was empty"),
        ("not json", "contained no parseable JSON events"),
        (_event("text", part={"text": "answer"}), "no step_finish usage event"),
        (_event("step_finish", part={"cost": 1.25}), "usage was incomplete"),
        (_step(tokens={"input": 10}), "usage was incomplete"),
    ],
    ids=["empty", "malformed", "no-step", "cost-only", "partial"],
)
def test_missing_event_usage_is_unavailable_not_an_estimate(
    output: str, reason: str
) -> None:
    result = capture_usage(output)
    assert result["basis"] == "unavailable"
    assert reason in result["unavailable_reason"]
    assert "source" not in result
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


@pytest.mark.parametrize(
    "tokens",
    [
        {"input": -1, "output": 2},
        {"input": 1.5, "output": 2},
        {"input": True, "output": 2},
        {"input": "1", "output": 2},
        {"input": 1, "output": -2},
        {"input": 1, "output": 2, "reasoning": None},
        {"input": 1, "output": 2, "cache": {"read": False}},
    ],
)
def test_malformed_reported_counters_fail_closed(tokens: dict[str, object]) -> None:
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(_step(tokens=tokens))
    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_conflicting_aliases_fail_closed() -> None:
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(
            _step(
                tokens={
                    "input": 10,
                    "input_tokens": 11,
                    "output": 4,
                }
            )
        )
    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "conflicting values" in str(exc_info.value)


def test_duplicate_json_key_fails_closed() -> None:
    output = (
        '{"type":"step_finish","part":{"tokens":' '{"input":10,"input":11,"output":4}}}'
    )
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(output)
    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_non_object_cache_fails_closed() -> None:
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage(_step(tokens={"input": 10, "output": 4, "cache": 3}))
    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION


def test_provider_copied_worker_artifact_is_only_fallback(tmp_path: Path) -> None:
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(json.dumps(_artifact_payload()), encoding="utf-8")

    result = capture_usage(
        _event("text", part={"text": "answer"}),
        worker_usage_path=usage_path,
    )
    assert result == {
        "basis": "provider_reported",
        "source": OPENCODE_WORKER_USAGE_SOURCE,
        "input_tokens": 12,
        "output_tokens": 4,
        "cached_input_tokens": 3,
        "reasoning_tokens": 2,
        "total_tokens": 18,
    }


@pytest.mark.parametrize(
    "payload",
    [
        _artifact_payload(source="manual count"),
        _artifact_payload(basis="calculated"),
        _artifact_payload(estimate_method="characters / 4"),
        {"input_tokens": 12, "output_tokens": 4},
    ],
    ids=["wrong-source", "calculated", "estimate-field", "no-provenance"],
)
def test_unqualified_worker_artifact_remains_unavailable(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(json.dumps(payload), encoding="utf-8")
    result = capture_usage("", worker_usage_path=usage_path)
    assert result["basis"] == "unavailable"
    assert "source" not in result
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_missing_worker_artifact_remains_unavailable(tmp_path: Path) -> None:
    result = capture_usage("", worker_usage_path=tmp_path / "missing-usage.json")
    assert result["basis"] == "unavailable"
    assert all(result[key] is None for key in UNAVAILABLE_COUNTERS)


def test_worker_artifact_contradictory_total_fails_closed(tmp_path: Path) -> None:
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(
        json.dumps(_artifact_payload(total_tokens=999)), encoding="utf-8"
    )
    with pytest.raises(LLMRouterError) as exc_info:
        capture_usage("", worker_usage_path=usage_path)
    assert exc_info.value.failure_type is FailureType.CONTRACT_VIOLATION
    assert "contradicts" in str(exc_info.value)


def test_json_event_usage_wins_without_consulting_artifact(tmp_path: Path) -> None:
    usage_path = tmp_path / "usage.json"
    usage_path.write_text("{not json", encoding="utf-8")
    result = capture_usage(_step(), worker_usage_path=usage_path)
    assert result["source"] == OPENCODE_USAGE_SOURCE
    assert result["input_tokens"] == 100


@pytest.mark.parametrize(
    "output",
    [
        _step(),
        _step(
            tokens={
                "input": 0,
                "output": 0,
                "reasoning": 0,
                "cache": {"read": 0},
            }
        ),
        _step(tokens={"input": 1, "output": 2}),
        "",
        "plain text",
    ],
    ids=["reported", "zero", "optional-null", "empty", "unavailable"],
)
def test_every_event_result_is_strict_v2(output: str) -> None:
    result = capture_usage(output)
    errors = list(_usage_validator().iter_errors(result))
    assert not errors, [(list(error.absolute_path), error.message) for error in errors]
    assert set(result) == (
        {"basis", "source", *UNAVAILABLE_COUNTERS}
        if result["basis"] == "provider_reported"
        else {"basis", "unavailable_reason", *UNAVAILABLE_COUNTERS}
    )


def test_worker_artifact_result_is_strict_v2(tmp_path: Path) -> None:
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(json.dumps(_artifact_payload()), encoding="utf-8")
    result = capture_usage("", worker_usage_path=usage_path)
    errors = list(_usage_validator().iter_errors(result))
    assert not errors, [(list(error.absolute_path), error.message) for error in errors]
