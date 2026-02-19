"""End-to-end router + client tests (Sprint 3)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from lee_llm_router.client import LLMClient
from lee_llm_router.config import load_config
from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMResponse
from lee_llm_router.router import LLMRouter

FIXTURES = Path(__file__).parent / "fixtures"
MESSAGES = [{"role": "user", "content": "hello"}]


@pytest.fixture
def mock_config():
    return load_config(FIXTURES / "llm_test.yaml")


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------


def test_complete_success(mock_config, tmp_path):
    router = LLMRouter(mock_config, trace_dir=tmp_path)
    response = router.complete("test", MESSAGES)

    assert isinstance(response, LLMResponse)
    assert len(response.text) > 0
    assert response.provider == "mock"
    assert response.request_id  # non-empty UUID


def test_complete_logs_telemetry_events(mock_config, tmp_path, caplog):
    router = LLMRouter(mock_config, trace_dir=tmp_path)

    with caplog.at_level(logging.INFO, logger="lee_llm_router"):
        router.complete("test", MESSAGES)

    messages = [r.message for r in caplog.records]
    assert "llm.complete.start" in messages
    assert "llm.complete.success" in messages


def test_complete_writes_trace_file(mock_config, tmp_path):
    router = LLMRouter(mock_config, trace_dir=tmp_path)
    response = router.complete("test", MESSAGES)

    trace_files = list(tmp_path.rglob("*.json"))
    assert len(trace_files) == 1

    data = json.loads(trace_files[0].read_text())
    assert data["request_id"] == response.request_id
    assert data["failure_type"] is None
    assert data["elapsed_ms"] is not None
    assert data["role"] == "test"


def test_complete_error_raises_llm_router_error(mock_config, tmp_path):
    # Inject a flag into the mock provider's raw config to trigger an error
    mock_config.providers["mock"].raw["raise_contract_violation"] = True

    router = LLMRouter(mock_config, trace_dir=tmp_path)
    with pytest.raises(LLMRouterError) as exc_info:
        router.complete("test", MESSAGES)

    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION

    # Trace file must be written even on error
    trace_files = list(tmp_path.rglob("*.json"))
    assert len(trace_files) == 1
    data = json.loads(trace_files[0].read_text())
    assert data["failure_type"] == "CONTRACT_VIOLATION"


def test_complete_falls_back_to_default_role(mock_config, tmp_path):
    """Requesting a nonexistent role falls back to config.default_role."""
    router = LLMRouter(mock_config, trace_dir=tmp_path)
    response = router.complete("nonexistent_role", MESSAGES)
    assert isinstance(response, LLMResponse)


def test_complete_per_call_override(mock_config, tmp_path):
    router = LLMRouter(mock_config, trace_dir=tmp_path)
    response = router.complete("test", MESSAGES, model="overridden-model")
    # The request_id in the trace should reflect the overridden model
    data = json.loads(list(tmp_path.rglob("*.json"))[0].read_text())
    assert data["model"] == "overridden-model"


# ---------------------------------------------------------------------------
# LLMClient (legacy wrapper)
# ---------------------------------------------------------------------------


def test_llm_client_complete_returns_response(mock_config, tmp_path):
    client = LLMClient(mock_config, trace_dir=tmp_path)
    response = client.complete("test", MESSAGES)

    assert isinstance(response, LLMResponse)
    assert response.provider == "mock"


def test_public_api_imports():
    """Acceptance: all Phase 0 public names importable from package root."""
    from lee_llm_router import (  # noqa: F401
        FailureType,
        LLMClient,
        LLMRequest,
        LLMResponse,
        LLMRouterError,
        LLMRouter,
        load_config,
    )
