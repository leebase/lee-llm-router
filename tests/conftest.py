"""Shared pytest fixtures for lee_llm_router tests."""

import os
import sys
from pathlib import Path

import pytest

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


@pytest.fixture
def clean_env(monkeypatch):
    """Remove LLM-related env vars so tests start from a known state."""
    for key in list(os.environ.keys()):
        if key.startswith(("OPENROUTER_", "OPENAI_", "LLM_")):
            monkeypatch.delenv(key, raising=False)
