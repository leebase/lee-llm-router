"""Sprint 5 tests: async completion, fallback chain, token hook, EventSink, trace CLI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig
from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.response import LLMRequest, LLMResponse, LLMUsage
from lee_llm_router.router import LLMRouter
from lee_llm_router.telemetry import EventSink, RouterEvent


# ---------------------------------------------------------------------------
# Config factory helpers
# ---------------------------------------------------------------------------


def make_config(*, fallback_providers: list[str] | None = None) -> LLMConfig:
    """Config with a 'mock' primary provider and an optional 'mock2' fallback."""
    providers = {
        "mock": ProviderConfig(name="mock", type="mock", raw={}),
        "mock2": ProviderConfig(name="mock2", type="mock", raw={}),
    }
    roles = {
        "test": RoleConfig(
            name="test",
            provider="mock",
            model="mock-model",
            fallback_providers=fallback_providers or [],
        )
    }
    return LLMConfig(default_role="test", providers=providers, roles=roles)


# ---------------------------------------------------------------------------
# Async completion — basic
# ---------------------------------------------------------------------------


def test_complete_async_success(tmp_path: Path):
    config = make_config()
    router = LLMRouter(config, trace_dir=tmp_path)

    response = asyncio.run(
        router.complete_async("test", [{"role": "user", "content": "hi"}])
    )

    assert isinstance(response, LLMResponse)
    assert response.text != ""


def test_complete_async_trace_written(tmp_path: Path):
    config = make_config()
    router = LLMRouter(config, trace_dir=tmp_path)

    asyncio.run(router.complete_async("test", [{"role": "user", "content": "hi"}]))

    trace_files = list(tmp_path.rglob("*.json"))
    assert len(trace_files) == 1
    data = json.loads(trace_files[0].read_text())
    assert data["role"] == "test"
    assert data["error"] is None


def test_complete_async_uses_provider_complete_async(tmp_path: Path):
    """If provider has complete_async, it is called directly (not via to_thread)."""
    config = make_config()
    router = LLMRouter(config, trace_dir=tmp_path)

    fake_response = LLMResponse(
        text="async native",
        provider="mock",
        model="mock-model",
        usage=LLMUsage(),
    )

    with patch("lee_llm_router.providers.mock.MockProvider.complete_async", new=AsyncMock(return_value=fake_response)):
        response = asyncio.run(
            router.complete_async("test", [{"role": "user", "content": "hi"}])
        )

    assert response.text == "async native"


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


def test_complete_fallback_chain_sync(tmp_path: Path, caplog):
    """Sync: primary raises RATE_LIMIT → fallback provider succeeds."""
    config = make_config(fallback_providers=["mock2"])
    router = LLMRouter(config, trace_dir=tmp_path)

    call_count = 0

    def _complete(self, request, cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise LLMRouterError("rate limited", failure_type=FailureType.RATE_LIMIT)
        return LLMResponse(text="fallback ok", provider="mock2", model="mock-model", usage=LLMUsage())

    with patch("lee_llm_router.providers.mock.MockProvider.complete", _complete):
        import logging
        with caplog.at_level(logging.INFO, logger="lee_llm_router"):
            response = router.complete("test", [{"role": "user", "content": "hi"}])

    assert response.text == "fallback ok"
    assert any("policy.fallback" in r.message for r in caplog.records)


def test_fallback_writes_trace_per_attempt(tmp_path: Path):
    """Each fallback attempt writes its own trace file with failure context."""
    config = make_config(fallback_providers=["mock2"])
    router = LLMRouter(config, trace_dir=tmp_path)

    call_count = 0

    def _complete(self, request, cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise LLMRouterError("rate limited", failure_type=FailureType.RATE_LIMIT)
        return LLMResponse(text="fallback ok", provider="mock2", model="mock-model", usage=LLMUsage())

    with patch("lee_llm_router.providers.mock.MockProvider.complete", _complete):
        router.complete("test", [{"role": "user", "content": "hi"}])

    trace_files = list(tmp_path.rglob("*.json"))
    assert len(trace_files) == 2
    attempts = {}
    for path in trace_files:
        data = json.loads(path.read_text())
        attempts[data["attempt"]] = data
    assert attempts[0]["provider"] == "mock"
    assert attempts[0]["failure_type"] == "RATE_LIMIT"
    assert attempts[1]["provider"] == "mock2"
    assert attempts[1]["failure_type"] is None


def test_complete_async_fallback_chain(tmp_path: Path, caplog):
    """Async: primary raises TIMEOUT → fallback provider succeeds."""
    config = make_config(fallback_providers=["mock2"])
    router = LLMRouter(config, trace_dir=tmp_path)

    call_count = 0

    async def _complete_async(self, request, cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise LLMRouterError("timed out", failure_type=FailureType.TIMEOUT)
        return LLMResponse(text="async fallback", provider="mock2", model="mock-model", usage=LLMUsage())

    with patch("lee_llm_router.providers.mock.MockProvider.complete_async", new=_complete_async):
        import logging
        with caplog.at_level(logging.INFO, logger="lee_llm_router"):
            response = asyncio.run(
                router.complete_async("test", [{"role": "user", "content": "hi"}])
            )

    assert response.text == "async fallback"
    assert any("policy.fallback" in r.message for r in caplog.records)


def test_complete_all_fallbacks_fail_raises(tmp_path: Path):
    """When all providers raise, the last error propagates."""
    config = make_config(fallback_providers=["mock2"])
    router = LLMRouter(config, trace_dir=tmp_path)

    def _complete(self, request, cfg):
        raise LLMRouterError("always fails", failure_type=FailureType.RATE_LIMIT)

    with patch("lee_llm_router.providers.mock.MockProvider.complete", _complete):
        with pytest.raises(LLMRouterError) as exc_info:
            router.complete("test", [{"role": "user", "content": "hi"}])

    assert exc_info.value.failure_type == FailureType.RATE_LIMIT


def test_contract_violation_does_not_fallback(tmp_path: Path):
    """CONTRACT_VIOLATION must never trigger fallback."""
    config = make_config(fallback_providers=["mock2"])
    router = LLMRouter(config, trace_dir=tmp_path)

    call_count = 0

    def _complete(self, request, cfg):
        nonlocal call_count
        call_count += 1
        raise LLMRouterError("bad schema", failure_type=FailureType.CONTRACT_VIOLATION)

    with patch("lee_llm_router.providers.mock.MockProvider.complete", _complete):
        with pytest.raises(LLMRouterError) as exc_info:
            router.complete("test", [{"role": "user", "content": "hi"}])

    assert exc_info.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert call_count == 1  # only primary was called


# ---------------------------------------------------------------------------
# Token accounting hook
# ---------------------------------------------------------------------------


def test_token_usage_hook_called(tmp_path: Path):
    config = make_config()
    calls: list[tuple] = []

    def hook(usage: LLMUsage, role: str, provider: str):
        calls.append((usage, role, provider))

    router = LLMRouter(config, trace_dir=tmp_path, on_token_usage=hook)
    router.complete("test", [{"role": "user", "content": "hi"}])

    assert len(calls) == 1
    usage, role, provider = calls[0]
    assert isinstance(usage, LLMUsage)
    assert role == "test"
    assert provider == "mock"


def test_token_usage_hook_async(tmp_path: Path):
    config = make_config()
    calls: list[tuple] = []

    def hook(usage: LLMUsage, role: str, provider: str):
        calls.append((usage, role, provider))

    router = LLMRouter(config, trace_dir=tmp_path, on_token_usage=hook)
    asyncio.run(router.complete_async("test", [{"role": "user", "content": "hi"}]))

    assert len(calls) == 1


def test_token_usage_hook_exception_does_not_propagate(tmp_path: Path):
    """A buggy hook must not break the request."""
    config = make_config()

    def bad_hook(usage, role, provider):
        raise RuntimeError("hook exploded")

    router = LLMRouter(config, trace_dir=tmp_path, on_token_usage=bad_hook)
    response = router.complete("test", [{"role": "user", "content": "hi"}])
    assert response.text != ""


# ---------------------------------------------------------------------------
# EventSink
# ---------------------------------------------------------------------------


def test_event_sink_receives_events(tmp_path: Path):
    config = make_config()
    events: list[RouterEvent] = []

    class Sink:
        def emit(self, event: RouterEvent) -> None:
            events.append(event)

    router = LLMRouter(config, trace_dir=tmp_path, event_sink=Sink())
    router.complete("test", [{"role": "user", "content": "hi"}])

    event_names = [e.event for e in events]
    assert "policy.choice" in event_names
    assert "llm.complete.success" in event_names


def test_event_sink_exception_does_not_propagate(tmp_path: Path):
    """A buggy EventSink must not break the request."""
    config = make_config()

    class BrokenSink:
        def emit(self, event: RouterEvent) -> None:
            raise RuntimeError("sink exploded")

    router = LLMRouter(config, trace_dir=tmp_path, event_sink=BrokenSink())
    response = router.complete("test", [{"role": "user", "content": "hi"}])
    assert response.text != ""


# ---------------------------------------------------------------------------
# EventSink import
# ---------------------------------------------------------------------------


def test_event_sink_importable():
    from lee_llm_router import EventSink, RouterEvent
    assert EventSink is not None
    assert RouterEvent is not None


# ---------------------------------------------------------------------------
# Trace CLI — trace --last N
# ---------------------------------------------------------------------------


def test_trace_cli_no_directory(tmp_path: Path, capsys):
    from lee_llm_router.doctor import main

    nonexistent = str(tmp_path / "no_traces_here")
    with pytest.raises(SystemExit) as exc_info:
        main(["trace", "--last", "5", "--dir", nonexistent])
    assert exc_info.value.code == 1


def test_trace_cli_shows_traces(tmp_path: Path, capsys):
    """After writing a trace, trace --last 1 should print a line for it."""
    from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig
    from lee_llm_router.doctor import main

    config = make_config()
    router = LLMRouter(config, trace_dir=tmp_path)
    router.complete("test", [{"role": "user", "content": "hi"}])

    with pytest.raises(SystemExit) as exc_info:
        main(["trace", "--last", "1", "--dir", str(tmp_path)])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "OK" in captured.out
    assert "a0" in captured.out


def test_trace_cli_empty_directory(tmp_path: Path, capsys):
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()

    from lee_llm_router.doctor import main
    with pytest.raises(SystemExit) as exc_info:
        main(["trace", "--last", "5", "--dir", str(trace_dir)])
    assert exc_info.value.code == 0
    assert "No traces found" in capsys.readouterr().out
