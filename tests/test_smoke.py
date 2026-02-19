"""Smoke tests: verify the package installs and basic imports work."""

import importlib
import sys


def test_package_importable():
    """lee_llm_router must be importable without errors."""
    import lee_llm_router  # noqa: F401


def test_version_string():
    """__version__ must be a non-empty string."""
    import lee_llm_router

    assert isinstance(lee_llm_router.__version__, str)
    assert len(lee_llm_router.__version__) > 0


def test_submodules_importable():
    """All planned submodules must be importable (even if empty stubs)."""
    submodules = [
        "lee_llm_router.config",
        "lee_llm_router.router",
        "lee_llm_router.client",
        "lee_llm_router.response",
        "lee_llm_router.compression",
        "lee_llm_router.telemetry",
        "lee_llm_router.doctor",
        "lee_llm_router.providers",
        "lee_llm_router.providers.base",
        "lee_llm_router.providers.http",
        "lee_llm_router.providers.codex_cli",
        "lee_llm_router.providers.mock",
        "lee_llm_router.providers.registry",
    ]
    for mod in submodules:
        assert importlib.import_module(mod) is not None, f"Failed to import {mod}"


def test_package_in_sys_modules():
    """Importing the package populates sys.modules."""
    import lee_llm_router  # noqa: F401

    assert "lee_llm_router" in sys.modules
