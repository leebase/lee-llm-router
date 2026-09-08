"""Crew-aware worker resolution: strict, flex, and bind semantics.

Given a loaded crews file and an availability snapshot, :func:`resolve`
answers one question — *which worker runs this crew's stage right now, and
why* — and returns the answer as a :class:`Resolution` carrying the chosen
worker, its funding channel's headroom, the dispatch command, and a one-line
reason.

The module is pure: it reads the two objects it is handed, never touches the
filesystem, and never invokes a provider binary. The same inputs always
produce the same output.

Three modes, three different relationships with headroom:

``strict``
    The crew's named (first) worker for the stage, always. Headroom is a veto
    only when the worker's channel is actually out (``exhausted`` or
    ``likely_exhausted``). ``degraded`` and ``unknown`` pass, because a dead
    availability cron must never silently halt governed runs.

``flex``
    The stage's declared candidate list, in order, best-known headroom first:
    every ``healthy`` candidate, then ``degraded``, then ``unknown`` as a last
    resort. Expensive never-automatic workers are skipped unless the crew
    author left no alternative. A role-scoped model is never chosen for coding
    roles, but the skip is visible: the reason names every role-scoped candidate
    passed over and cites the decision that restricts it.

``bind``
    An explicit, authorized escalation to a named worker — in or out of the
    stage list. Headroom is reported, never a veto; the caller's reason and
    authority are recorded verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from lee_llm_router.availability import (
    AvailabilitySnapshot,
    Bucket,
    ChannelHeadroom,
    Health,
)
from lee_llm_router.crews import (
    ROLE_SCOPED_CITATION,
    CrewsConfig,
    CrewsConfigError,
    ResolvedWorker,
    Worker,
    is_never_automatic,
    is_role_scoped,
    resolve_worker,
    role_class,
)

MODES: tuple[str, ...] = ("strict", "flex", "bind")
"""The resolution modes :func:`resolve` accepts."""

EXIT_NOT_ELIGIBLE = 2
"""Exit code when nothing in the candidate set may be dispatched."""

EXIT_CONFIG_ERROR = 3
"""Exit code for a config error, a usage error, or a forbidden-model refusal."""

VETO_HEALTH: tuple[Health, ...] = (Health.EXHAUSTED, Health.LIKELY_EXHAUSTED)
"""Channel health states that mean "no headroom": never dispatched automatically."""

FLEX_TIERS: tuple[Health, ...] = (Health.HEALTHY, Health.DEGRADED, Health.UNKNOWN)
"""Flex eligibility tiers, best first. Anything else is never chosen."""

REMEDY_REFRESH = "refresh availability"
"""Remedy when every candidate's headroom is simply unknown."""

REMEDY_WAIT = "wait for reset"
"""Remedy when candidates are out of quota but no reset time is known."""

DEFAULT_EFFORT_TOKEN = "default"
"""Stands in for a missing effort in :attr:`Resolution.route_id`."""

PROMPT_PLACEHOLDER = "{prompt}"
"""Argv element that marks a harness as taking its prompt on the command line."""


class ResolutionError(Exception):
    """Raised when a resolution is refused or the request is malformed.

    Attributes:
        message: Human-readable explanation, safe to print to a terminal.
        exit_code: ``2`` when nothing was eligible, ``3`` for a config, usage,
            or forbidden-model refusal.
        remedy: What the caller can do about it, when there is something.
        kind: A stable machine tag — ``not_eligible``, ``config``, ``usage``,
            or ``forbidden``.
    """

    def __init__(
        self,
        message: str,
        *,
        exit_code: int,
        kind: str,
        remedy: str | None = None,
    ) -> None:
        """Initialise the error.

        Args:
            message: Human-readable explanation.
            exit_code: Process exit code the CLI should use.
            kind: Stable machine tag for the refusal class.
            remedy: Optional suggested remedy.
        """
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.kind = kind
        self.remedy = remedy

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of this refusal."""
        return {
            "error": self.message,
            "exit_code": self.exit_code,
            "kind": self.kind,
            "remedy": self.remedy,
        }


@dataclass(frozen=True)
class Resolution:
    """One resolved worker, with the evidence behind the choice.

    Attributes:
        crew: The crew that was asked.
        role: The cognitive stage that was asked for.
        mode: The resolution mode used (``strict``, ``flex``, or ``bind``).
        worker_id: The chosen worker's crews-file id.
        provider: The registered router provider serving the worker.
        model: The model the worker runs.
        effort: The worker's reasoning-effort hint, when it declares one.
        channel: The funding channel the worker's usage bills to.
        headroom: The channel's health, as a wire string.
        headroom_remaining_fraction: Remaining quota ``0.0``–``1.0``, or None.
        pace_ratio: Burn pace of the limiting bucket, or None.
        reason: One line explaining why this worker was chosen.
        authorized_by: Who authorized the escalation; None outside bind mode.
        route_id: ``provider:model:effort`` route identity.
        dispatch_command: The provider's argv for this worker.
        prompt_delivery: ``argv`` when the argv carries ``{prompt}``, else
            ``stdin``.
        worker_command: The worker's raw crews-file command template.
        snapshot_observed_at: When the snapshot observed the quotas (ISO).
        snapshot_stale: Whether that snapshot was too old to trust.
    """

    crew: str
    role: str
    mode: str
    worker_id: str
    provider: str
    model: str
    effort: str | None
    channel: str
    headroom: str
    headroom_remaining_fraction: float | None
    pace_ratio: float | None
    reason: str
    authorized_by: str | None
    route_id: str
    dispatch_command: list[str]
    prompt_delivery: str
    worker_command: str
    snapshot_observed_at: str | None
    snapshot_stale: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of this resolution."""
        return {
            "crew": self.crew,
            "role": self.role,
            "mode": self.mode,
            "worker_id": self.worker_id,
            "provider": self.provider,
            "model": self.model,
            "effort": self.effort,
            "channel": self.channel,
            "headroom": self.headroom,
            "headroom_remaining_fraction": self.headroom_remaining_fraction,
            "pace_ratio": self.pace_ratio,
            "reason": self.reason,
            "authorized_by": self.authorized_by,
            "route_id": self.route_id,
            "dispatch_command": list(self.dispatch_command),
            "prompt_delivery": self.prompt_delivery,
            "worker_command": self.worker_command,
            "snapshot_observed_at": self.snapshot_observed_at,
            "snapshot_stale": self.snapshot_stale,
        }


def resolve(
    crews: CrewsConfig,
    snapshot: AvailabilitySnapshot,
    *,
    crew: str,
    role: str,
    mode: str = "strict",
    worker: str | None = None,
    authorized_by: str | None = None,
    reason: str | None = None,
) -> Resolution:
    """Resolve which worker should run a crew's stage.

    Args:
        crews: The loaded crews file.
        snapshot: The availability snapshot to read headroom from.
        crew: Crew name.
        role: Cognitive stage name (``envision``, ``ideate``, ...).
        mode: ``strict`` (default), ``flex``, or ``bind``.
        worker: Worker id to bind to. Only valid in bind mode.
        authorized_by: Who authorized the bind. Required in bind mode.
        reason: Why the bind was authorized. Required in bind mode.

    Returns:
        The :class:`Resolution` describing the chosen worker.

    Raises:
        ResolutionError: Exit ``2`` when nothing is eligible; exit ``3`` for an
            unknown crew, stage, mode, or worker, for a misused argument, for a
            worker whose model is role-scoped for that role class, or when the
            provider refuses to build a dispatch command.
    """
    if mode not in MODES:
        raise ResolutionError(
            f"unknown mode {mode!r} (known modes: {', '.join(MODES)})",
            exit_code=EXIT_CONFIG_ERROR,
            kind="usage",
        )
    if mode != "bind" and worker is not None:
        raise ResolutionError(
            f"worker {worker!r} may only be named in bind mode, not {mode!r} "
            "mode; use mode='bind' with authorized_by and reason to escalate",
            exit_code=EXIT_CONFIG_ERROR,
            kind="usage",
        )

    crew_obj = _config_guard(lambda: crews.crew(crew))
    candidates = _config_guard(lambda: crew_obj.eligible(role))
    r_class = _config_guard(lambda: role_class(role))

    if mode == "bind":
        return _resolve_bind(
            crews,
            snapshot,
            crew=crew,
            role=role,
            r_class=r_class,
            worker=worker,
            authorized_by=authorized_by,
            reason=reason,
        )
    if mode == "strict":
        return _resolve_strict(
            crews,
            snapshot,
            crew=crew,
            role=role,
            r_class=r_class,
            candidates=candidates,
        )
    return _resolve_flex(
        crews,
        snapshot,
        crew=crew,
        role=role,
        r_class=r_class,
        candidates=candidates,
    )


def _resolve_strict(
    crews: CrewsConfig,
    snapshot: AvailabilitySnapshot,
    *,
    crew: str,
    role: str,
    r_class: str,
    candidates: Sequence[str],
) -> Resolution:
    """Resolve the crew's named worker, vetoing only on a spent channel."""
    resolved = _resolve_named(crews, candidates[0])
    if r_class == "coding" and is_role_scoped(resolved.model):
        _refuse_role_scoped(resolved, role=role, r_class=r_class)
    headroom = snapshot.headroom(resolved.channel)

    if headroom.health in VETO_HEALTH:
        raise ResolutionError(
            f"strict mode: crew {crew!r} names {resolved.worker_id} for stage "
            f"{role!r}, but {_describe(headroom)}",
            exit_code=EXIT_NOT_ELIGIBLE,
            kind="not_eligible",
            remedy=_remedy([headroom]),
        )

    reason = (
        f"strict mode: crew {crew!r} names {resolved.worker_id} for stage "
        f"{role!r}; {_describe(headroom)}"
    )
    if headroom.health is not Health.HEALTHY:
        reason += f"; strict mode does not veto on {headroom.health.value}"
    return _build(
        snapshot,
        crew=crew,
        role=role,
        mode="strict",
        resolved=resolved,
        headroom=headroom,
        reason=reason,
        authorized_by=None,
    )


def _resolve_flex(
    crews: CrewsConfig,
    snapshot: AvailabilitySnapshot,
    *,
    crew: str,
    role: str,
    r_class: str,
    candidates: Sequence[str],
) -> Resolution:
    """Resolve the best-funded candidate in the stage's declared order."""
    sole = len(candidates) == 1
    considered: list[ChannelHeadroom] = []
    usable: list[tuple[ResolvedWorker, ChannelHeadroom, bool]] = []
    skipped_role_scoped: list[ResolvedWorker] = []

    for worker_id in candidates:
        resolved = _resolve_named(crews, worker_id)
        if r_class == "coding" and is_role_scoped(resolved.model):
            skipped_role_scoped.append(resolved)
            continue
        headroom = snapshot.headroom(resolved.channel)
        considered.append(headroom)
        never_automatic = is_never_automatic(resolved.model)
        if never_automatic and not sole:
            continue
        if headroom.health in FLEX_TIERS:
            usable.append((resolved, headroom, never_automatic))

    if skipped_role_scoped and len(skipped_role_scoped) == len(candidates):
        _refuse_role_scoped(skipped_role_scoped[0], role=role, r_class=r_class)

    if not usable:
        raise ResolutionError(
            f"flex mode: no eligible worker for crew {crew!r} stage {role!r} "
            f"among {', '.join(candidates)}",
            exit_code=EXIT_NOT_ELIGIBLE,
            kind="not_eligible",
            remedy=_remedy(considered),
        )

    for tier in FLEX_TIERS:
        for resolved, headroom, never_automatic in usable:
            if headroom.health is not tier:
                continue
            return _build(
                snapshot,
                crew=crew,
                role=role,
                mode="flex",
                resolved=resolved,
                headroom=headroom,
                reason=_flex_reason(
                    resolved,
                    headroom,
                    tier,
                    never_automatic,
                    role=role,
                    skipped_role_scoped=skipped_role_scoped,
                ),
                authorized_by=None,
            )
    raise AssertionError("unreachable: usable candidates always match a tier")


def _resolve_bind(
    crews: CrewsConfig,
    snapshot: AvailabilitySnapshot,
    *,
    crew: str,
    role: str,
    r_class: str,
    worker: str | None,
    authorized_by: str | None,
    reason: str | None,
) -> Resolution:
    """Resolve an explicitly authorized worker, reporting headroom only."""
    missing = [
        name
        for name, value in (
            ("worker", worker),
            ("authorized_by", authorized_by),
            ("reason", reason),
        )
        if value is None or not value.strip()
    ]
    if missing:
        raise ResolutionError(
            f"bind mode requires {', '.join(missing)}; an escalation is only "
            "on the record when it names a worker, an authority, and a reason",
            exit_code=EXIT_CONFIG_ERROR,
            kind="usage",
        )
    assert worker is not None and authorized_by is not None and reason is not None

    if worker not in crews.workers:
        known = ", ".join(crews.workers) or "<none>"
        raise ResolutionError(
            f"unknown worker {worker!r} (known workers: {known})",
            exit_code=EXIT_CONFIG_ERROR,
            kind="config",
        )

    resolved = _resolve_named(crews, worker)
    if r_class == "coding" and is_role_scoped(resolved.model):
        _refuse_role_scoped(resolved, role=role, r_class=r_class)
    headroom = snapshot.headroom(resolved.channel)
    return _build(
        snapshot,
        crew=crew,
        role=role,
        mode="bind",
        resolved=resolved,
        headroom=headroom,
        reason=reason,
        authorized_by=authorized_by,
    )


def _flex_reason(
    resolved: ResolvedWorker,
    headroom: ChannelHeadroom,
    tier: Health,
    never_automatic: bool,
    *,
    role: str,
    skipped_role_scoped: Sequence[ResolvedWorker] = (),
) -> str:
    """Compose the one-line reason for a flex choice.

    Args:
        resolved: The worker flex chose.
        headroom: That worker's channel headroom.
        tier: The eligibility tier the choice came from.
        never_automatic: Whether the chosen model is never-automatic.
        role: Cognitive stage/role name.
        skipped_role_scoped: Role-scoped candidates passed over on the way to
            the choice. Each is named in the reason, with its model and the
            governing decision, so a skip is never silent.

    Returns:
        A single line — no newline — naming the choice, its headroom, and every
        candidate that was skipped.
    """
    if tier is Health.HEALTHY:
        reason = (
            f"flex mode: {resolved.worker_id} is the first candidate with "
            f"healthy headroom ({_describe(headroom)})"
        )
    elif tier is Health.DEGRADED:
        reason = (
            f"flex mode: {resolved.worker_id} chosen on degraded headroom "
            f"({_describe(headroom)}); no candidate had healthy headroom"
        )
    else:
        reason = (
            f"flex mode: {resolved.worker_id} chosen as a last resort "
            f"({_describe(headroom)}); nothing better had known headroom"
        )
    if never_automatic:
        reason += (
            f"; {resolved.model} is never-automatic but the crew author left "
            "no alternative for this stage"
        )
    for skipped in skipped_role_scoped:
        reason += (
            f"; skipped {skipped.worker_id} (role-scoped model {skipped.model} is "
            f"never automatic for coding role '{role}', {ROLE_SCOPED_CITATION})"
        )
    return reason


def _build(
    snapshot: AvailabilitySnapshot,
    *,
    crew: str,
    role: str,
    mode: str,
    resolved: ResolvedWorker,
    headroom: ChannelHeadroom,
    reason: str,
    authorized_by: str | None,
) -> Resolution:
    """Assemble a :class:`Resolution` from a chosen worker and its headroom."""
    argv = _dispatch_command(resolved)
    limiting = _limiting_bucket(headroom)
    return Resolution(
        crew=crew,
        role=role,
        mode=mode,
        worker_id=resolved.worker_id,
        provider=resolved.provider,
        model=resolved.model,
        effort=resolved.effort,
        channel=resolved.channel,
        headroom=headroom.health.value,
        headroom_remaining_fraction=headroom.remaining_fraction,
        pace_ratio=None if limiting is None else limiting.pace_ratio,
        reason=reason,
        authorized_by=authorized_by,
        route_id=route_id(resolved.provider, resolved.model, resolved.effort),
        dispatch_command=argv,
        prompt_delivery="argv" if PROMPT_PLACEHOLDER in argv else "stdin",
        worker_command=resolved.dispatch_command,
        snapshot_observed_at=_iso(snapshot.observed_at),
        snapshot_stale=snapshot.stale,
    )


def route_id(provider: str, model: str, effort: str | None) -> str:
    """Return the ``provider:model:effort`` route identity.

    Args:
        provider: Registered router provider name.
        model: Model identifier.
        effort: Reasoning-effort hint, or None.

    Returns:
        ``f"{provider}:{model}:{effort}"``, with a missing effort rendered as
        the literal ``default`` so the string ``None`` never appears in a route
        identity the benchmark has to group by.
    """
    return f"{provider}:{model}:{effort or DEFAULT_EFFORT_TOKEN}"


def _dispatch_command(resolved: ResolvedWorker) -> list[str]:
    """Build the provider's argv for a resolved worker.

    Args:
        resolved: The worker to dispatch.

    Returns:
        The argv list the provider would run.

    Raises:
        ResolutionError: Exit ``3`` when the provider refuses the config —
            an unsupported effort level or an unusable model string, for
            example. No binary is executed here.
    """
    if resolved.provider == "codex_cli" and (
        resolved.harness_binary is None
        or (
            isinstance(resolved.harness_binary, str) and resolved.harness_binary.strip()
        )
    ):
        cmd = [resolved.harness_binary or "codex", "exec"]
        if resolved.model:
            cmd.extend(["--model", str(resolved.model)])
        if resolved.effort:
            cmd.extend(["-c", f"model_reasoning_effort={resolved.effort}"])
        cmd.append(PROMPT_PLACEHOLDER)
        return cmd

    from lee_llm_router.providers.base import LLMRouterError

    provider_cls: type | None = None
    if resolved.provider == "codex_cli":
        from lee_llm_router.providers.codex_cli import CodexCLIProvider

        provider_cls = CodexCLIProvider
    elif resolved.provider in ("claude_code_cli", "claude_code", "claude"):
        from lee_llm_router.providers.codex_cli import ClaudeCodeCLIProvider

        provider_cls = ClaudeCodeCLIProvider
    elif resolved.provider in ("gemini_cli", "gemini"):
        from lee_llm_router.providers.codex_cli import GeminiCLIProvider

        provider_cls = GeminiCLIProvider
    elif resolved.provider in ("antigravity_cli", "antigravity", "agy"):
        from lee_llm_router.providers.antigravity_cli import AntigravityCLIProvider

        provider_cls = AntigravityCLIProvider
    elif resolved.provider == "omp_cli":
        from lee_llm_router.providers.omp_cli import OmpCLIProvider

        provider_cls = OmpCLIProvider
    elif resolved.provider in ("opencode_cli", "opencode"):
        from lee_llm_router.providers.opencode_cli import OpenCodeCLIProvider

        provider_cls = OpenCodeCLIProvider
    elif resolved.provider in (
        "openrouter_http",
        "openai_http",
        "opencode_subscription_http",
    ):
        from lee_llm_router.providers.http import OpenRouterHTTPProvider

        provider_cls = OpenRouterHTTPProvider
    elif resolved.provider in (
        "openai_codex_subscription_http",
        "openai_codex_http",
        "chatgpt_subscription_http",
    ):
        from lee_llm_router.providers.openai_codex_subscription import (
            OpenAICodexSubscriptionHTTPProvider,
        )

        provider_cls = OpenAICodexSubscriptionHTTPProvider
    elif resolved.provider == "mock":
        from lee_llm_router.providers.mock import MockProvider

        provider_cls = MockProvider
    else:
        from lee_llm_router.providers import registry

        try:
            provider_cls = registry.get(resolved.provider)
        except KeyError as exc:  # pragma: no cover - resolve_worker checks first
            raise ResolutionError(
                str(exc), exit_code=EXIT_CONFIG_ERROR, kind="config"
            ) from exc

    config: dict[str, Any] = {"model": resolved.model}
    if resolved.harness_binary:
        config = {"command": resolved.harness_binary, "model": resolved.model}
    try:
        return list(
            provider_cls().build_command(
                config, model=resolved.model, effort=resolved.effort
            )
        )
    except LLMRouterError as exc:
        raise ResolutionError(
            f"worker {resolved.worker_id!r}: {exc}",
            exit_code=EXIT_CONFIG_ERROR,
            kind="config",
        ) from exc


def _resolve_named(crews: CrewsConfig, worker_id: str) -> ResolvedWorker:
    """Map a worker id onto a provider, surfacing config errors as exit 3."""
    worker: Worker = _config_guard(lambda: _worker(crews, worker_id))
    return _config_guard(lambda: resolve_worker(worker))


def _worker(crews: CrewsConfig, worker_id: str) -> Worker:
    """Return a worker by id, raising :class:`CrewsConfigError` when absent."""
    try:
        return crews.workers[worker_id]
    except KeyError as exc:
        known = ", ".join(crews.workers) or "<none>"
        raise CrewsConfigError(
            f"unknown worker {worker_id!r} (known workers: {known})"
        ) from exc


def _refuse_role_scoped(
    resolved: ResolvedWorker,
    *,
    role: str,
    r_class: str,
) -> None:
    """Refuse a worker whose model is role-scoped for this role class.

    Args:
        resolved: The worker under consideration.
        role: Cognitive stage/role name.
        r_class: The role class ('coding' or 'planning_review').

    Raises:
        ResolutionError: Exit ``3``, kind ``forbidden``, citing the decision
            that restricts the model.
    """
    raise ResolutionError(
        f"worker {resolved.worker_id!r} runs {resolved.model}, which is "
        f"role-scoped and forbidden for {r_class} role {role!r} "
        f"({ROLE_SCOPED_CITATION})",
        exit_code=EXIT_CONFIG_ERROR,
        kind="forbidden",
        remedy=f"pick a different worker for this stage ({ROLE_SCOPED_CITATION})",
    )


def _describe(headroom: ChannelHeadroom) -> str:
    """Render a channel's headroom as a human-readable clause."""
    details: list[str] = []
    limiting = _limiting_bucket(headroom)
    if limiting is not None and limiting.raw_status:
        details.append(limiting.raw_status)
    if headroom.remaining_fraction is not None:
        details.append(f"{round(headroom.remaining_fraction * 100)}% remaining")
    text = f"channel {headroom.channel} {headroom.health.value}"
    if details:
        text += f" ({', '.join(details)})"
    return text


def _limiting_bucket(headroom: ChannelHeadroom) -> Bucket | None:
    """Return the bucket that set a channel's health, when it is named."""
    if headroom.limiting_bucket is None:
        return None
    for bucket in headroom.buckets:
        if bucket.name == headroom.limiting_bucket:
            return bucket
    return None  # pragma: no cover - limiting_bucket always names a bucket


def _remedy(headrooms: Iterable[ChannelHeadroom]) -> str:
    """Suggest what would make a refused candidate set resolvable.

    Args:
        headrooms: The headroom of every candidate that was considered.

    Returns:
        ``refresh availability`` when nothing is known about any candidate —
        the snapshot, not the quota, is the problem — otherwise the earliest
        reset time among the spent candidates, or a plain wait when no reset
        time was reported.
    """
    seen = list(headrooms)
    if seen and all(headroom.health is Health.UNKNOWN for headroom in seen):
        return REMEDY_REFRESH
    resets: list[datetime] = []
    for headroom in seen:
        if headroom.health not in VETO_HEALTH:
            continue
        limiting = _limiting_bucket(headroom)
        if limiting is not None and limiting.resets_at is not None:
            resets.append(limiting.resets_at)
    if resets:
        return f"{REMEDY_WAIT} at {min(resets).isoformat()}"
    return REMEDY_WAIT


def _config_guard(thunk: Any) -> Any:
    """Run ``thunk``, re-raising a :class:`CrewsConfigError` as exit 3."""
    try:
        return thunk()
    except CrewsConfigError as exc:
        raise ResolutionError(
            str(exc), exit_code=EXIT_CONFIG_ERROR, kind="config"
        ) from exc


def _iso(moment: datetime | None) -> str | None:
    """Render an optional datetime as an ISO string."""
    return None if moment is None else moment.isoformat()
