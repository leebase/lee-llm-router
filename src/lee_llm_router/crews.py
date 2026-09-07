"""Loader for Auto-Orch's crews file.

A crew names a full roster: which worker runs each cognitive stage
(``envision``, ``ideate``, ``reconsider``, ``score``, ``author``) and which
governed routes a mission's playbook must mandate (``primary`` producer,
``reviewer``, ``judge``).

This module is strictly read-only: it never writes to the crews file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CREWS_FILE = Path("~/projects/auto-orch/config/crews.yaml")
"""Default crews file location (``~`` expanded at load time)."""

CREWS_FILE_ENV_VAR = "LEE_LLM_ROUTER_CREWS_FILE"
"""Environment variable that overrides the default crews file location."""

STAGE_NAMES: tuple[str, ...] = (
    "envision",
    "ideate",
    "reconsider",
    "score",
    "author",
)
"""The known cognitive stage names, in canonical cycle order."""

GOVERNED_ROLES: tuple[str, ...] = ("primary", "reviewer", "judge")
"""The governed route roles a crew may declare."""


class CrewsConfigError(ValueError):
    """Raised when the crews file is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class Worker:
    """A single stage worker declared under the top-level ``workers`` map.

    Attributes:
        id: The worker id (the YAML key).
        command: Shell command template used to run a stage.
        preflight_command: Shell command used to check worker availability.
        timeout_seconds: Per-invocation timeout in seconds.
    """

    id: str
    command: str
    preflight_command: str | None = None
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class Stage:
    """An ordered set of workers eligible to run one cognitive stage.

    Attributes:
        name: The stage name (one of :data:`STAGE_NAMES`).
        workers: Worker ids in declared preference order; the first entry is
            the primary worker for the stage.
    """

    name: str
    workers: tuple[str, ...]

    @property
    def primary(self) -> str:
        """Return the first (preferred) worker id for this stage."""
        return self.workers[0]


@dataclass(frozen=True)
class GovernedRoute:
    """A governed harness route for one role of a governed run.

    Attributes:
        role: One of :data:`GOVERNED_ROLES`.
        harness: Harness identifier (e.g. ``claude_code``, ``codex_cli``).
        model: Optional model identifier for the harness.
        effort: Optional reasoning-effort hint for the harness.
    """

    role: str
    harness: str
    model: str | None = None
    effort: str | None = None


@dataclass(frozen=True)
class Crew:
    """A named crew: stage workers plus governed routes.

    Attributes:
        name: The crew name (the YAML key).
        description: Human-readable description of the crew's intent.
        stages: Mapping of stage name to :class:`Stage`, in file order.
        governed: Mapping of governed role to :class:`GovernedRoute`.
        judge_model: Optional explicit semantic-judge model override.
    """

    name: str
    description: str
    stages: dict[str, Stage]
    governed: dict[str, GovernedRoute]
    judge_model: str | None = None

    def eligible(self, stage: str) -> tuple[str, ...]:
        """Return the ordered eligible worker ids for a stage.

        Args:
            stage: Stage name to look up.

        Returns:
            Worker ids in declared preference order.

        Raises:
            CrewsConfigError: If this crew does not declare that stage.
        """
        try:
            return self.stages[stage].workers
        except KeyError as exc:
            raise CrewsConfigError(
                f"crew {self.name!r} has no stage {stage!r}"
            ) from exc

    def primary(self, stage: str) -> str:
        """Return the preferred (first) worker id for a stage.

        Args:
            stage: Stage name to look up.

        Returns:
            The first eligible worker id.

        Raises:
            CrewsConfigError: If this crew does not declare that stage.
        """
        return self.eligible(stage)[0]


@dataclass(frozen=True)
class CrewsConfig:
    """Parsed crews file.

    Attributes:
        workers: Mapping of worker id to :class:`Worker`, in file order.
        crews: Mapping of crew name to :class:`Crew`, in file order.
        path: The resolved path the config was loaded from.
    """

    workers: dict[str, Worker]
    crews: dict[str, Crew]
    path: Path

    def crew(self, name: str) -> Crew:
        """Return a crew by name.

        Args:
            name: Crew name.

        Returns:
            The matching :class:`Crew`.

        Raises:
            CrewsConfigError: If no such crew exists.
        """
        try:
            return self.crews[name]
        except KeyError as exc:
            known = ", ".join(self.crews) or "<none>"
            raise CrewsConfigError(
                f"unknown crew {name!r} (known crews: {known})"
            ) from exc


def resolve_crews_path(explicit: str | Path | None = None) -> Path:
    """Resolve which crews file to load.

    Precedence: explicit argument, then the ``LEE_LLM_ROUTER_CREWS_FILE``
    environment variable, then :data:`DEFAULT_CREWS_FILE`.

    Args:
        explicit: Caller-supplied path, if any.

    Returns:
        An expanded (``~`` resolved) path. Existence is not checked here.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get(CREWS_FILE_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_CREWS_FILE.expanduser()


def _parse_workers(raw: Any, path: Path) -> dict[str, Worker]:
    """Parse the top-level ``workers`` mapping."""
    if not isinstance(raw, dict) or not raw:
        raise CrewsConfigError(f"{path}: 'workers' must be a non-empty mapping")
    workers: dict[str, Worker] = {}
    for worker_id, body in raw.items():
        if not isinstance(body, dict):
            raise CrewsConfigError(f"{path}: worker {worker_id!r} must be a mapping")
        command = body.get("command")
        if not isinstance(command, str) or not command.strip():
            raise CrewsConfigError(
                f"{path}: worker {worker_id!r} is missing a 'command' string"
            )
        timeout = body.get("timeout_seconds")
        if timeout is not None and not isinstance(timeout, int):
            raise CrewsConfigError(
                f"{path}: worker {worker_id!r} has a non-integer 'timeout_seconds'"
            )
        preflight = body.get("preflight_command")
        if preflight is not None and not isinstance(preflight, str):
            raise CrewsConfigError(
                f"{path}: worker {worker_id!r} has a non-string 'preflight_command'"
            )
        workers[str(worker_id)] = Worker(
            id=str(worker_id),
            command=command,
            preflight_command=preflight,
            timeout_seconds=timeout,
        )
    return workers


def _parse_stage(
    crew_name: str,
    stage_name: str,
    value: Any,
    known_workers: dict[str, Worker],
    path: Path,
) -> Stage:
    """Parse one stage value into a :class:`Stage`."""
    if stage_name not in STAGE_NAMES:
        raise CrewsConfigError(
            f"{path}: crew {crew_name!r} declares unknown stage "
            f"{stage_name!r} (known stages: {', '.join(STAGE_NAMES)})"
        )
    if isinstance(value, str):
        worker_ids: tuple[str, ...] = (value,)
    elif isinstance(value, list):
        if not value:
            raise CrewsConfigError(
                f"{path}: crew {crew_name!r} stage {stage_name!r} has an "
                "empty worker list"
            )
        for entry in value:
            if not isinstance(entry, str):
                raise CrewsConfigError(
                    f"{path}: crew {crew_name!r} stage {stage_name!r} list "
                    f"entry {entry!r} is not a string"
                )
        worker_ids = tuple(value)
    else:
        raise CrewsConfigError(
            f"{path}: crew {crew_name!r} stage {stage_name!r} must be a "
            f"worker id string or a list of worker id strings, got "
            f"{type(value).__name__}"
        )
    for worker_id in worker_ids:
        if worker_id not in known_workers:
            raise CrewsConfigError(
                f"{path}: crew {crew_name!r} stage {stage_name!r} references "
                f"unknown worker {worker_id!r}"
            )
    return Stage(name=stage_name, workers=worker_ids)


def _parse_governed(crew_name: str, raw: Any, path: Path) -> dict[str, GovernedRoute]:
    """Parse a crew's ``governed`` mapping."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CrewsConfigError(
            f"{path}: crew {crew_name!r} 'governed' must be a mapping"
        )
    routes: dict[str, GovernedRoute] = {}
    for role, body in raw.items():
        if not isinstance(body, dict):
            raise CrewsConfigError(
                f"{path}: crew {crew_name!r} governed role {role!r} must be "
                "a mapping"
            )
        harness = body.get("harness")
        if not isinstance(harness, str) or not harness.strip():
            raise CrewsConfigError(
                f"{path}: crew {crew_name!r} governed role {role!r} is "
                "missing a 'harness' string"
            )
        routes[str(role)] = GovernedRoute(
            role=str(role),
            harness=harness,
            model=body.get("model"),
            effort=body.get("effort"),
        )
    return routes


def _parse_crew(
    name: str, body: Any, known_workers: dict[str, Worker], path: Path
) -> Crew:
    """Parse a single crew entry."""
    if not isinstance(body, dict):
        raise CrewsConfigError(f"{path}: crew {name!r} must be a mapping")
    raw_stages = body.get("stages")
    if not isinstance(raw_stages, dict) or not raw_stages:
        raise CrewsConfigError(
            f"{path}: crew {name!r} must declare a non-empty 'stages' mapping"
        )
    stages: dict[str, Stage] = {}
    for stage_name, value in raw_stages.items():
        stages[str(stage_name)] = _parse_stage(
            name, str(stage_name), value, known_workers, path
        )
    description = body.get("description") or ""
    if not isinstance(description, str):
        raise CrewsConfigError(f"{path}: crew {name!r} 'description' must be a string")
    judge_model = body.get("judge_model")
    if judge_model is not None and not isinstance(judge_model, str):
        raise CrewsConfigError(f"{path}: crew {name!r} 'judge_model' must be a string")
    return Crew(
        name=name,
        description=description.strip(),
        stages=stages,
        governed=_parse_governed(name, body.get("governed"), path),
        judge_model=judge_model,
    )


def load_crews(path: str | Path | None = None) -> CrewsConfig:
    """Load and validate the Auto-Orch crews file.

    Args:
        path: Explicit crews file path. When omitted, the path is resolved by
            :func:`resolve_crews_path`.

    Returns:
        A :class:`CrewsConfig` preserving worker, crew, and stage file order.

    Raises:
        CrewsConfigError: If the file is missing, is not a mapping, lacks
            ``workers`` or ``crews``, or declares an invalid stage.
    """
    resolved = resolve_crews_path(path)
    if not resolved.is_file():
        raise CrewsConfigError(f"crews file not found: {resolved}")
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CrewsConfigError(f"{resolved}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise CrewsConfigError(f"{resolved}: top level must be a mapping")
    if "workers" not in raw:
        raise CrewsConfigError(f"{resolved}: missing top-level 'workers'")
    if "crews" not in raw:
        raise CrewsConfigError(f"{resolved}: missing top-level 'crews'")

    workers = _parse_workers(raw["workers"], resolved)
    raw_crews = raw["crews"]
    if not isinstance(raw_crews, dict) or not raw_crews:
        raise CrewsConfigError(f"{resolved}: 'crews' must be a non-empty mapping")
    crews = {
        str(name): _parse_crew(str(name), body, workers, resolved)
        for name, body in raw_crews.items()
    }
    return CrewsConfig(workers=workers, crews=crews, path=resolved)


WORKER_ENV_PREFIX_PROVIDERS: dict[str, str] = {
    "CODEX": "codex_cli",
    "CLAUDE": "claude_code_cli",
    "OMP": "omp_cli",
    "OPENCODE": "opencode_cli",
    "ANTIGRAVITY": "antigravity_cli",
}
"""Maps a stage-worker env-var prefix to a registered router provider name."""

WORKER_PROVIDER_OVERRIDES: dict[str, tuple[str, str, str | None]] = {}
"""Explicit ``worker_id -> (provider, model, effort)`` pins.

An entry here wins over parsing the worker's command string, so an unusual
worker can be routed correctly without editing the (Auto-Orch-owned) crews
file. Empty by default.
"""

NEVER_AUTOMATIC_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-fable-5",
        "gpt-5.6-luna",
        "claude-opus-5",
    }
)
"""Models that must never appear in an *automatic* fallback chain.

Per the crew-aware worker-resolver plan: Fable 5.1, Luna Max, and Opus 5 are
expensive escalation rungs that a resolver may only reach when a crew names
them explicitly. This constant is declarative only in strict mode — strict
mode returns exactly the crew's named worker, so nothing here is enforced by
:class:`~lee_llm_router.policy.CrewRoutingPolicy` yet.
"""

FORBIDDEN_MODELS = frozenset({"gemini-3.1-pro"})
"""Models the resolver must never choose at all (decisions.md D152/D153)."""

CHANNELS: tuple[str, ...] = (
    "openai-sub",
    "anthropic-sub",
    "gemini-sub",
    "gemini-sub-thirdparty",
    "openrouter",
    "opencode-go",
)
"""The funding channels a worker's usage can be drawn from.

A *channel* is the subscription or metered account that pays for a worker's
tokens. It is deliberately coarser than a provider: several providers can draw
on one channel, and one harness (Antigravity) draws on two -- Google's own
models bill to ``gemini-sub`` while the third-party Claude/GPT models it
brokers bill to ``gemini-sub-thirdparty``.

This mapping lives here rather than in ``crews.yaml`` because funding is the
router's concern, not Auto-Orch's.
"""

PROVIDER_CHANNELS: dict[str, str] = {
    "codex_cli": "openai-sub",
    "claude_code_cli": "anthropic-sub",
    "antigravity_cli": "gemini-sub",
    "opencode_cli": "opencode-go",
    "omp_cli": "openrouter",
}
"""Default funding channel for each registered router provider."""

WORKER_CHANNEL_OVERRIDES: dict[str, str] = {}
"""Explicit ``worker_id -> channel`` pins that beat :data:`PROVIDER_CHANNELS`.

Use this for a worker whose funding differs from its provider's default -- for
example an Antigravity worker running a brokered Claude or GPT model, which
bills to ``gemini-sub-thirdparty`` rather than ``gemini-sub``. Empty by
default.
"""


def channel_for(worker_id: str, provider: str) -> str:
    """Return the funding channel a worker's usage bills to.

    Args:
        worker_id: The worker id from the crews file.
        provider: The registered router provider the worker resolves to.

    Returns:
        One of :data:`CHANNELS`.

    Raises:
        CrewsConfigError: If neither an override nor a provider default maps
            the worker to a known channel.
    """
    override = WORKER_CHANNEL_OVERRIDES.get(worker_id)
    if override is not None:
        if override not in CHANNELS:
            raise CrewsConfigError(
                f"worker {worker_id!r} is pinned to unknown channel "
                f"{override!r} (known channels: {', '.join(CHANNELS)})"
            )
        return override
    try:
        channel = PROVIDER_CHANNELS[provider]
    except KeyError as exc:
        known = ", ".join(sorted(PROVIDER_CHANNELS))
        raise CrewsConfigError(
            f"worker {worker_id!r} resolves to provider {provider!r}, which has "
            f"no funding channel (mapped providers: {known})"
        ) from exc
    if channel not in CHANNELS:  # pragma: no cover - guards a bad edit here
        raise CrewsConfigError(
            f"provider {provider!r} maps to unknown channel {channel!r}"
        )
    return channel


_WORKER_ENV_RE = re.compile(
    r"(?P<prefix>[A-Z]+)_STAGE_WORKER_"
    r"(?P<key>REASONING_EFFORT|EFFORT|BINARY|MODEL)="
    r"(?P<value>\S+)"
)


def is_never_automatic(model: str | None) -> bool:
    """Return whether a model may only be used when explicitly named.

    Args:
        model: Model identifier, or ``None``.

    Returns:
        ``True`` if the model is in :data:`NEVER_AUTOMATIC_MODELS`.
    """
    return model is not None and model in NEVER_AUTOMATIC_MODELS


def is_forbidden(model: str | None) -> bool:
    """Return whether a model must never be chosen by the resolver.

    Args:
        model: Model identifier, or ``None``.

    Returns:
        ``True`` if the model is in :data:`FORBIDDEN_MODELS`.
    """
    return model is not None and model in FORBIDDEN_MODELS


@dataclass(frozen=True)
class ResolvedWorker:
    """A crews-file worker mapped onto a router provider.

    Attributes:
        worker_id: The worker id from the crews file.
        provider: Registered router provider name (e.g. ``codex_cli``).
        model: Model identifier the worker runs.
        effort: Reasoning-effort hint, when the worker declares one.
        harness_binary: Path to the harness binary, when declared.
        dispatch_command: The worker's raw command template, unchanged.
        channel: The funding channel this worker's usage bills to.
    """

    worker_id: str
    provider: str
    model: str
    effort: str | None
    harness_binary: str | None
    dispatch_command: str
    channel: str


def _parse_worker_command(worker: Worker) -> tuple[str, str, str | None, str | None]:
    """Parse ``(prefix, model, effort, binary)`` out of a worker command."""
    prefix: str | None = None
    fields: dict[str, str] = {}
    for match in _WORKER_ENV_RE.finditer(worker.command):
        found = match.group("prefix")
        if prefix is None:
            prefix = found
        elif found != prefix:
            raise CrewsConfigError(
                f"worker {worker.id!r} mixes stage-worker env prefixes "
                f"{prefix!r} and {found!r} in its command"
            )
        key = match.group("key")
        fields.setdefault("EFFORT" if key.endswith("EFFORT") else key, match["value"])
    if prefix is None:
        raise CrewsConfigError(
            f"worker {worker.id!r} command declares no "
            f"<PREFIX>_STAGE_WORKER_* environment variables: {worker.command!r}"
        )
    if prefix not in WORKER_ENV_PREFIX_PROVIDERS:
        known = ", ".join(sorted(WORKER_ENV_PREFIX_PROVIDERS))
        raise CrewsConfigError(
            f"worker {worker.id!r} uses unknown stage-worker prefix {prefix!r} "
            f"(known prefixes: {known})"
        )
    model = fields.get("MODEL")
    if not model:
        raise CrewsConfigError(
            f"worker {worker.id!r} command declares no " f"{prefix}_STAGE_WORKER_MODEL"
        )
    return prefix, model, fields.get("EFFORT"), fields.get("BINARY")


def resolve_worker(worker: Worker) -> ResolvedWorker:
    """Map a crews-file worker onto a registered router provider.

    The mapping is derived from the worker's command template, which sets
    ``<PREFIX>_STAGE_WORKER_BINARY``/``_MODEL``/``_EFFORT`` (or
    ``_REASONING_EFFORT``) before invoking the stage-worker script. An entry
    in :data:`WORKER_PROVIDER_OVERRIDES` wins over that parse.

    Args:
        worker: The worker to resolve.

    Returns:
        The :class:`ResolvedWorker` for this worker.

    Raises:
        CrewsConfigError: If the command uses an unknown prefix, declares no
            model, resolves to a provider that is not registered, or resolves
            to a provider with no funding channel.
    """
    override = WORKER_PROVIDER_OVERRIDES.get(worker.id)
    if override is not None:
        provider, model, effort = override
        binary: str | None = None
    else:
        prefix, model, effort, binary = _parse_worker_command(worker)
        provider = WORKER_ENV_PREFIX_PROVIDERS[prefix]

    from lee_llm_router.providers import registry

    try:
        registry.get(provider)
    except KeyError as exc:
        raise CrewsConfigError(
            f"worker {worker.id!r} resolves to provider {provider!r}, which is "
            f"not registered (available: {', '.join(registry.available())})"
        ) from exc

    return ResolvedWorker(
        worker_id=worker.id,
        provider=provider,
        model=model,
        effort=effort,
        harness_binary=binary,
        dispatch_command=worker.command,
        channel=channel_for(worker.id, provider),
    )
