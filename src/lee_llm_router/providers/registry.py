"""Provider registration and discovery."""

from __future__ import annotations

_REGISTRY: dict[str, type] = {}


def register(name: str, provider_cls: type) -> None:
    """Register a provider class under the given name."""
    _REGISTRY[name] = provider_cls


def get(name: str) -> type:
    """Retrieve a registered provider class by name.

    Raises KeyError if the provider is not registered.
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"Provider {name!r} not registered. Available: {list(_REGISTRY)}"
        )
    return _REGISTRY[name]


def available() -> list[str]:
    """Return a list of all registered provider names."""
    return list(_REGISTRY.keys())


def _register_builtins() -> None:
    """Auto-register built-in provider adapters."""
    from lee_llm_router.providers.codex_cli import CodexCLIProvider
    from lee_llm_router.providers.http import OpenRouterHTTPProvider
    from lee_llm_router.providers.mock import MockProvider

    register("mock", MockProvider)
    register("openrouter_http", OpenRouterHTTPProvider)
    register("codex_cli", CodexCLIProvider)


_register_builtins()
