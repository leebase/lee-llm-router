"""RoutingPolicy abstraction (Phase 1 — additive).

A RoutingPolicy accepts a role name + config snapshot and returns a
ProviderChoice (which provider to use, plus any overrides). The router
logs every choice as a `policy.choice` event for auditability.

Default: SimpleRoutingPolicy — resolves role.provider, preserving P0 behaviour.
Custom policies (cost-aware, A/B, canary) can be injected via LLMRouter.__init__.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lee_llm_router.config import LLMConfig
    from lee_llm_router.crews import CrewsConfig


@dataclass
class ProviderChoice:
    """Result returned by a RoutingPolicy."""

    provider_name: str
    provider_overrides: dict[str, Any] = field(default_factory=dict)
    request_overrides: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)  # legacy alias
    allow_fallback: bool = True
    """Whether the router may extend this choice with the role's fallback chain.

    ``True`` (the default) preserves the historical behaviour: the router tries
    ``provider_name`` first and then every entry of ``role.fallback_providers``.
    ``False`` means strict routing — the named provider or a typed failure,
    never a substituted worker.
    """

    def __post_init__(self) -> None:
        if self.overrides:
            if self.provider_overrides:
                self.provider_overrides = {**self.overrides, **self.provider_overrides}
            else:
                self.provider_overrides = dict(self.overrides)
        # Keep overrides attribute pointing at provider_overrides for legacy readers.
        self.overrides = self.provider_overrides


@runtime_checkable
class RoutingPolicy(Protocol):
    """Interface for provider selection strategies."""

    def choose(self, role: str, config: LLMConfig) -> ProviderChoice:
        """Return the provider to use for this role + config snapshot."""
        ...


class SimpleRoutingPolicy:
    """Default policy: resolve role → use role.provider, no overrides.

    Falls back to config.default_role when the requested role is absent,
    matching the same semantics as LLMRouter._resolve_role().
    """

    def choose(self, role: str, config: LLMConfig) -> ProviderChoice:
        role_cfg = config.roles.get(role) or config.roles.get(config.default_role)
        if role_cfg is None:
            from lee_llm_router.providers.base import FailureType, LLMRouterError

            raise LLMRouterError(
                f"SimpleRoutingPolicy: no role config for {role!r} "
                f"and default_role {config.default_role!r} also missing",
                failure_type=FailureType.PROVIDER_ERROR,
            )
        return ProviderChoice(provider_name=role_cfg.provider)


class CrewRoutingPolicy:
    """Strict crew-aware policy: route a stage to the crew's named worker.

    The ``role`` passed to :meth:`choose` is an Auto-Orch cognitive stage name
    (``envision``, ``ideate``, ``reconsider``, ``score``, ``author``). The
    crew's first eligible worker for that stage is resolved onto a router
    provider, and the config's provider entry of that type is selected.

    Strict mode performs no substitution: if the crew's worker cannot be
    served by the supplied config, the call fails rather than falling back.
    """

    mode = "strict"

    def __init__(
        self,
        crew: str,
        crews: CrewsConfig | None = None,
        crews_path: str | Path | None = None,
    ) -> None:
        """Initialise the policy.

        Args:
            crew: Crew name to route with.
            crews: Already-loaded crews config; loaded on demand when omitted.
            crews_path: Explicit crews file path used when ``crews`` is None.
        """
        self.crew_name = crew
        self._crews = crews
        self._crews_path = crews_path

    @property
    def crews(self) -> CrewsConfig:
        """Return the crews config, loading it on first use."""
        if self._crews is None:
            from lee_llm_router.crews import load_crews

            self._crews = load_crews(self._crews_path)
        return self._crews

    def choose(self, role: str, config: LLMConfig) -> ProviderChoice:
        """Return the provider serving this crew's worker for ``role``.

        Args:
            role: Cognitive stage name.
            config: The router config snapshot.

        Returns:
            A :class:`ProviderChoice` naming the config provider key, with
            ``model`` and (when known) ``effort`` request overrides, and
            ``allow_fallback=False`` so the router never substitutes another
            worker for the crew's named one.

        Raises:
            LLMRouterError: If the crew or stage is unknown, the worker cannot
                be resolved, or no config provider serves the required type.
        """
        from lee_llm_router.crews import CrewsConfigError, resolve_worker
        from lee_llm_router.providers.base import FailureType, LLMRouterError

        try:
            crew = self.crews.crew(self.crew_name)
            worker_id = crew.primary(role)
            worker = self.crews.workers[worker_id]
            resolved = resolve_worker(worker)
        except CrewsConfigError as exc:
            raise LLMRouterError(
                f"CrewRoutingPolicy: crew {self.crew_name!r} stage {role!r}: {exc}",
                failure_type=FailureType.PROVIDER_ERROR,
            ) from exc

        provider_name = self._match_provider(resolved.provider, config)
        if provider_name is None:
            raise LLMRouterError(
                f"CrewRoutingPolicy: crew {self.crew_name!r} stage {role!r} "
                f"worker {resolved.worker_id!r} requires a provider of type "
                f"{resolved.provider!r}, but config declares none "
                f"(providers: {', '.join(sorted(config.providers)) or '<none>'})",
                failure_type=FailureType.PROVIDER_ERROR,
            )

        overrides: dict[str, Any] = {"model": resolved.model}
        if resolved.effort is not None:
            overrides["effort"] = resolved.effort
        return ProviderChoice(
            provider_name=provider_name,
            request_overrides=overrides,
            allow_fallback=False,
        )

    @staticmethod
    def _match_provider(required: str, config: LLMConfig) -> str | None:
        """Return the config provider key whose type matches ``required``."""
        from lee_llm_router.providers import registry

        try:
            required_cls = registry.get(required)
        except KeyError:
            return None
        for name, provider_cfg in config.providers.items():
            if provider_cfg.type == required:
                return name
            try:
                if registry.get(provider_cfg.type) is required_cls:
                    return name
            except KeyError:
                continue
        return None
