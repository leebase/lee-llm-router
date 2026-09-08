"""Smoke tests: verify the package installs and basic imports work."""

import importlib
import os
import subprocess
import sys
from pathlib import Path


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


def test_public_api_identity_unchanged():
    """Lazy __getattr__ must still hand back the real, identical objects."""
    import lee_llm_router
    from lee_llm_router import (
        client,
        config,
        policy,
        providers,
        response,
        router,
        telemetry,
    )

    assert lee_llm_router.LLMRouter is router.LLMRouter
    assert lee_llm_router.LLMClient is client.LLMClient
    assert lee_llm_router.load_config is config.load_config
    assert lee_llm_router.LLMConfig is config.LLMConfig
    assert lee_llm_router.LLMRequest is response.LLMRequest
    assert lee_llm_router.LLMResponse is response.LLMResponse
    assert lee_llm_router.LLMUsage is response.LLMUsage
    assert lee_llm_router.LLMRouterError is providers.base.LLMRouterError
    assert lee_llm_router.FailureType is providers.base.FailureType
    assert lee_llm_router.RoutingPolicy is policy.RoutingPolicy
    assert lee_llm_router.SimpleRoutingPolicy is policy.SimpleRoutingPolicy
    assert lee_llm_router.ProviderChoice is policy.ProviderChoice
    assert lee_llm_router.TraceStore is telemetry.TraceStore
    assert lee_llm_router.LocalFileTraceStore is telemetry.LocalFileTraceStore
    assert lee_llm_router.EventSink is telemetry.EventSink
    assert lee_llm_router.RouterEvent is telemetry.RouterEvent
    for name in lee_llm_router.__all__:
        assert name in dir(lee_llm_router)


def test_resolver_import_chain_excludes_httpx():
    """Cold-start consumers must never pull httpx into sys.modules (contract 2)."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import lee_llm_router.resolver, lee_llm_router.crews, "
            "lee_llm_router.availability, lee_llm_router.events, sys; "
            "assert 'httpx' not in sys.modules, sorted(sys.modules)",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
    )
    assert result.returncode == 0, result.stderr


def test_registry_cli_lookup_excludes_httpx():
    """Registry lookups the resolver needs must not import httpx (contract 3)."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from lee_llm_router.providers import registry; "
            "registry.get('codex_cli'); "
            "import sys; assert 'httpx' not in sys.modules, sorted(sys.modules)",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
    )
    assert result.returncode == 0, result.stderr


def test_registry_http_lookup_still_works():
    """The HTTP provider is still registered and usable (contract 3)."""
    from lee_llm_router.providers import registry

    http_cls = registry.get("openrouter_http")
    assert http_cls.name == "openrouter_http"
    provider = http_cls()
    provider.validate_config(
        {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "X"}
    )


def test_resolve_does_not_import_watchdog():
    """resolve subcommand must never import watchdog."""
    cmd = [
        sys.executable,
        "-c",
        "import sys\n"
        "from lee_llm_router import doctor\n"
        "fast_args = doctor._try_fast_resolve("
        "['--crew', 'openai-economy', '--role', 'author', "
        "'--mode', 'flex', '--no-event'])\n"
        "assert fast_args is not None\n"
        "doctor._run_resolve(fast_args)\n"
        "assert 'lee_llm_router.watchdog' not in sys.modules, sorted(sys.modules)\n",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
    )
    assert result.returncode == 0, result.stderr


def test_resolve_does_not_import_yaml_on_cache_hit():
    """resolve subcommand must not import yaml on parse cache hit."""
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
    }
    warmup_cmd = [
        sys.executable,
        "-c",
        "from lee_llm_router import doctor\n"
        "fast_args = doctor._try_fast_resolve("
        "['--crew', 'openai-economy', '--role', 'author', "
        "'--mode', 'flex', '--no-event'])\n"
        "assert fast_args is not None\n"
        "doctor._run_resolve(fast_args)\n",
    ]
    subprocess.run(warmup_cmd, capture_output=True, text=True, env=env, check=True)

    check_cmd = [
        sys.executable,
        "-c",
        "import sys\n"
        "from lee_llm_router import doctor\n"
        "fast_args = doctor._try_fast_resolve("
        "['--crew', 'openai-economy', '--role', 'author', "
        "'--mode', 'flex', '--no-event'])\n"
        "assert fast_args is not None\n"
        "doctor._run_resolve(fast_args)\n"
        "assert 'yaml' not in sys.modules, sorted(sys.modules)\n",
    ]
    result = subprocess.run(check_cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr


def test_no_module_mutates_builtins():
    """No module in this package may patch the builtins module (P27)."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import builtins, lee_llm_router.dispatch, lee_llm_router.doctor; "
            "assert not hasattr(builtins, 're')",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
    )
    assert result.returncode == 0, result.stderr


def test_resolve_no_event_does_not_import_events():
    """resolve with --no-event must not import the events ledger module."""
    cmd = [
        sys.executable,
        "-c",
        "import sys\n"
        "from lee_llm_router import doctor\n"
        "fast_args = doctor._try_fast_resolve("
        "['--crew', 'openai-economy', '--role', 'author', "
        "'--mode', 'flex', '--no-event'])\n"
        "assert fast_args is not None\n"
        "doctor._run_resolve(fast_args)\n"
        "assert 'lee_llm_router.events' not in sys.modules, sorted(sys.modules)\n",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
    )
    assert result.returncode == 0, result.stderr
