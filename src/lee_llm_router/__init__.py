"""
Lee LLM Router — shared LLM routing kernel.

Extracted from LeeClaw/Meridian for reuse across projects.

Public names are loaded lazily (PEP 562 module ``__getattr__``): importing
this package does not import ``client``, ``router``, ``providers.http``, or
any other submodule until a name is actually accessed. This keeps cold-start
consumers — the crew resolver, the availability reader, the event ledger —
free of the ``httpx``-bearing import chain. See
``docs/crew-resolver/sprint-plan.md`` Sprint 3's "under 50 ms" done
condition.
"""

from __future__ import annotations

import importlib
from typing import Any

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Phase 0
    "LLMRouter",
    "LLMClient",
    "load_config",
    "LLMConfig",
    "LLMRequest",
    "LLMResponse",
    "LLMUsage",
    "LLMRouterError",
    "FailureType",
    # Phase 1
    "RoutingPolicy",
    "SimpleRoutingPolicy",
    "ProviderChoice",
    "TraceStore",
    "LocalFileTraceStore",
    # Phase 2
    "EventSink",
    "RouterEvent",
]

# Maps each lazily-exported name to the submodule that defines it. Accessing
# `lee_llm_router.<name>` imports that submodule (and only that submodule) on
# first use, then caches the result on this module so identity is stable and
# subsequent lookups are plain attribute access.
_ATTR_MODULES: dict[str, str] = {
    "LLMRouter": "lee_llm_router.router",
    "LLMClient": "lee_llm_router.client",
    "load_config": "lee_llm_router.config",
    "LLMConfig": "lee_llm_router.config",
    "LLMRequest": "lee_llm_router.response",
    "LLMResponse": "lee_llm_router.response",
    "LLMUsage": "lee_llm_router.response",
    "LLMRouterError": "lee_llm_router.providers.base",
    "FailureType": "lee_llm_router.providers.base",
    "RoutingPolicy": "lee_llm_router.policy",
    "SimpleRoutingPolicy": "lee_llm_router.policy",
    "ProviderChoice": "lee_llm_router.policy",
    "TraceStore": "lee_llm_router.telemetry",
    "LocalFileTraceStore": "lee_llm_router.telemetry",
    "EventSink": "lee_llm_router.telemetry",
    "RouterEvent": "lee_llm_router.telemetry",
}


def __getattr__(name: str) -> Any:
    """Lazily resolve a public name to its defining submodule (PEP 562)."""
    module_name = _ATTR_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
