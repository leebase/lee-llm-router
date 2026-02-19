"""Shared pytest fixtures for lee_llm_router tests."""

import os
import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Remove LLM-related env vars so tests start from a known state."""
    for key in list(os.environ.keys()):
        if key.startswith(("OPENROUTER_", "OPENAI_", "LLM_")):
            monkeypatch.delenv(key, raising=False)
