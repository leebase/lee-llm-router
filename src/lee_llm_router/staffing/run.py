"""Staffing ``run`` selection and subprocess dispatch (P1-5a).

Implements the selection-plus-dispatch foundation of the ``run`` command
(D209 ruling 4 via ``docs/staffing/phase1-contracts.md`` §``run``):

* **Selection.** Role/class selection (always required; ``--route`` is
  optional on top, per the Chief's corrected D209 contract in
  ``docs/staffing/chief-answers-p1-1.md``), over
  exactly the ``catalog explain`` path (:func:`evaluate_eligibility` over
  the committed catalog, an availability snapshot, dated terms, and
  marginal pricing). An explicit route must be active and currently
  eligible under the same role/class path; an excluded explicit route is
  a refusal (exit 3) carrying the
  exact explain reason, and nothing is launched. Role/class selection
  takes the first eligible route in ``catalog explain --json``
  marginal-price order and preserves the selection basis, reason, explain
  reference, and every excluded route id/reason — explain evidence only,
  never a new selection judgment (D206).
* **Dispatch.** The selected route's harness provider ``build_command``
  argv is substituted with the packet prompt and run exactly once through
  the repository's watchdog/subprocess boundary
  (:func:`lee_llm_router.dispatch.run_dispatch`), with ``cwd`` set to the
  workdir and no shell interpolation anywhere. Pi runs its JSON event
  mode and captures usage through the accepted P1-4a parser; Codex forces
  ``json_flag: --json`` (the P1-4b governed capture note) and parses the
  JSONL receipt; Claude reuses the committed governed capture
  (``--output-format stream-json``) and parses the result event through
  :func:`capture_claude_usage`.
  Governed dispatch (P1-8) also grants implementation routes the minimum
  noninteractive editing capability: Pi receives an explicit bounded
  editing tool allowlist (no ``bash``), Codex receives the exec-level
  writable-workspace sandbox and git-repo-check skip flags, and Claude
  receives the documented noninteractive permission flags
  (``--permission-mode acceptEdits --permission-prompts none``) so scoped
  edits are accepted without an interactive host; no dangerous bypass
  flag is ever emitted on any harness.
  Every other wired harness runs the same boundary and records
  ``usage.basis: unavailable`` with a specific reason — no parser ever
  invents tokens.

P1-5b2 completes the boundary: after the one worker and optional oracle,
``run`` assembles one v2 attempt record, calculates list/marginal cost only
from known counters and the selected dated price, validates it through the
committed ledger API, appends it once, and prints the same record compactly.
``run`` never escalates; parent and escalation-reason are only recorded as a
paired link supplied by its supervisor.

P1-4 ruling 3 (``docs/staffing/chief-answers-p1-4.md``) adds the optional
caller attestation ``--supervisor-route <route id>``: the caller attests its
own route. The id is resolved through the same committed catalog/eligibility
path as explicit ``--route`` selection — an unknown, inactive, or currently
ineligible id is a refusal (exit 3) before anything is launched — and the
accepted supervisor-route object (identity tuple plus observed provider) is
recorded only when the caller supplies the attestation. When the attested
dispatch succeeds, the oracle passes, and every existing evidence gate holds,
``verified_success`` is true; otherwise the record carries exactly one
``verified_success_reason`` from the closed P1-4 vocabulary
(:data:`VERIFIED_SUCCESS_REASON_UNATTESTED` when unattested, otherwise the
first blocking gap in a fixed documented order) — never a claimed success.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO

import yaml

from lee_llm_router.availability import AvailabilitySnapshot
from lee_llm_router.crews import HARNESS_PROVIDER_CHANNELS
from lee_llm_router.dispatch import run_dispatch
from lee_llm_router.providers.antigravity_cli import (
    AGY_GOVERNED_CONFIG,
    AGY_USAGE_SOURCE,
    AntigravityCLIProvider,
)
from lee_llm_router.providers.antigravity_cli import (
    capture_usage as capture_agy_usage,
)
from lee_llm_router.providers.base import FailureType, LLMRouterError
from lee_llm_router.providers.codex_cli import (
    CLAUDE_GOVERNED_CONFIG,
    CLAUDE_USAGE_SOURCE,
    CODEX_USAGE_SOURCE,
    ClaudeCodeCLIProvider,
    CodexCLIProvider,
    capture_claude_usage,
    claude_aggregate_models,
)
from lee_llm_router.providers.codex_cli import (
    capture_usage as capture_codex_usage,
)
from lee_llm_router.providers.omp_cli import (
    OMP_GOVERNED_CONFIG,
    OMP_USAGE_SOURCE,
    OmpCLIProvider,
)
from lee_llm_router.providers.omp_cli import (
    capture_usage as capture_omp_usage,
)
from lee_llm_router.providers.opencode_cli import (
    OPENCODE_GOVERNED_CONFIG,
    OPENCODE_USAGE_SOURCE,
    OpenCodeCLIProvider,
)
from lee_llm_router.providers.opencode_cli import (
    capture_usage as capture_opencode_usage,
)
from lee_llm_router.providers.pi_cli import (
    PI_USAGE_SOURCE,
    PiCLIProvider,
)
from lee_llm_router.providers.pi_cli import capture_usage as capture_pi_usage
from lee_llm_router.resolver import PROMPT_PLACEHOLDER, Resolution
from lee_llm_router.staffing.catalog import Route as StaffingRoute
from lee_llm_router.staffing.catalog import StaffingCatalog
from lee_llm_router.staffing.eligibility import (
    EligibilityPrice,
    EligibilityRow,
    StaffingEligibilityError,
    evaluate_eligibility,
)
from lee_llm_router.staffing.terms import (
    DEFAULT_OPENROUTER_SNAPSHOT_PATH,
    DEFAULT_RATE_TABLE_PATH,
    _verify_sha256,
)
from lee_llm_router.watchdog import DEFAULT_MAX_MINUTES, DEFAULT_STALL_MINUTES

__all__ = [
    "DEFAULT_POLL_SECONDS",
    "DEFAULT_RUN_TIMEOUT_SECONDS",
    "VERIFIED_SUCCESS_REASON_EVIDENCE",
    "VERIFIED_SUCCESS_REASON_ORACLE",
    "VERIFIED_SUCCESS_REASON_UNATTESTED",
    "VERIFIED_SUCCESS_REASON_WORKER_DISPATCH",
    "DispatchOutcome",
    "OracleOutcome",
    "RunDispatchError",
    "build_attempt_record",
    "packet_id_for_text",
    "RunSelectionError",
    "SELECTION_BASIS_EXPLAIN_CHEAPEST_ELIGIBLE",
    "SELECTION_BASIS_EXPLICIT",
    "SELECTION_EXIT_CODE",
    "SelectionOutcome",
    "build_dispatch_command",
    "dispatch_route",
    "oracle_timeout_seconds",
    "parse_oracle_command",
    "run_json_record",
    "run_oracle",
    "run_summary_lines",
    "select_route",
    "selection_record",
]

SELECTION_EXIT_CODE = 3
"""Process exit code for every selection refusal (mirrors ``catalog explain``)."""

SELECTION_BASIS_EXPLICIT = "explicit"
"""Selection basis when the caller named the route with ``--route``."""

SELECTION_BASIS_EXPLAIN_CHEAPEST_ELIGIBLE = "explain_cheapest_eligible"
"""Selection basis for role/class selection: first eligible route in the
``catalog explain --json`` marginal-price order."""

VERIFIED_SUCCESS_REASON_UNATTESTED = "supervisor_route_unattested"
"""P1-4 ruling 3: exact ``verified_success_reason`` recorded on every false
``router_run`` record built without a ``--supervisor-route`` attestation."""

VERIFIED_SUCCESS_REASON_WORKER_DISPATCH = "worker_dispatch_failed"
"""Attested but the worker dispatch failed: nonzero exit or ceiling timeout."""

VERIFIED_SUCCESS_REASON_ORACLE = "oracle_not_passed"
"""Attested with a successful dispatch but the oracle verdict is not ``pass``
(no oracle / unverified, nonzero exit, launch failure, or ceiling timeout)."""

VERIFIED_SUCCESS_REASON_EVIDENCE = "evidence_incomplete"
"""Attested with a successful dispatch and a passing oracle, but a remaining
route/usage/cost/duration evidence gate does not hold."""

DEFAULT_RUN_TIMEOUT_SECONDS: float | None = None
"""Default wall-clock ceiling: none, so the dispatch boundary default applies
(:data:`lee_llm_router.watchdog.DEFAULT_MAX_MINUTES`)."""

DEFAULT_POLL_SECONDS = 0.5
"""Watchdog polling cadence forwarded to the dispatch boundary."""

_TIMEOUT_EXIT_CODE = 124
"""Exit code the dispatch boundary reports for a ceiling timeout."""

DEFAULT_ORACLE_TIMEOUT_SECONDS = DEFAULT_MAX_MINUTES * 60.0
"""Standard wall-clock bound for an oracle when ``--timeout`` is absent."""

# Injected boundaries default to the real subprocess and clock so the CLI
# path is real; tests monkeypatch these module names for fake subprocesses.
_DEFAULT_POPEN: Callable[..., Any] = subprocess.Popen
_DEFAULT_CLOCK: Callable[[], float] = time.monotonic
_DEFAULT_SLEEP: Callable[[float], None] = time.sleep

#: Route harness -> provider class wired for ``run`` dispatch (P1-5a).
#: ``pi_cli`` is deliberately instantiated directly (it is a command builder,
#: not a registered completion provider); the rest mirror the committed
#: harness mappings in :data:`lee_llm_router.crews.WORKER_ENV_PREFIX_PROVIDERS`.
_HARNESS_PROVIDER_CLASSES: dict[str, type] = {
    "pi": PiCLIProvider,
    "codex": CodexCLIProvider,
    "claude": ClaudeCodeCLIProvider,
    "agy": AntigravityCLIProvider,
    "opencode": OpenCodeCLIProvider,
    "omp": OmpCLIProvider,
}

#: Route harness -> registered provider name, for provenance records only.
_HARNESS_PROVIDER_NAMES: dict[str, str] = {
    harness: provider_cls.name
    for harness, provider_cls in _HARNESS_PROVIDER_CLASSES.items()
}

#: Route harness -> authoritative usage taxonomy source string.
_HARNESS_USAGE_SOURCES: dict[str, str] = {
    "pi": PI_USAGE_SOURCE,
    "codex": CODEX_USAGE_SOURCE,
    "claude": CLAUDE_USAGE_SOURCE,
    "agy": AGY_USAGE_SOURCE,
    "opencode": OPENCODE_USAGE_SOURCE,
    "omp": OMP_USAGE_SOURCE,
}

#: Funding channel -> Pi backend provider id, the exact reverse of the
#: committed :data:`lee_llm_router.crews.HARNESS_PROVIDER_CHANNELS` mapping
#: (openai-codex -> openai-sub, openrouter -> openrouter,
#: opencode-go -> opencode-go, anthropic -> anthropic-sub). No id is invented.
_CHANNEL_TO_PI_PROVIDER_ID: dict[str, str] = {
    channel: provider for provider, channel in HARNESS_PROVIDER_CHANNELS.items()
}

_CODEX_GOVERNED_CONFIG: dict[str, Any] = {
    "json_flag": "--json",
    "sandbox_args": ["-s", "workspace-write", "--skip-git-repo-check"],
}
"""P1-4b future note + P1-8 governed edit fix: governed ``run`` capture
forces Codex to emit the JSONL usage receipt stream that
``codex_cli.capture_usage`` parses (``json_flag``), and grants the
exec-level flags a headless implementation worker needs to edit its
scoped file: ``-s workspace-write`` for a writable workspace sandbox and
``--skip-git-repo-check`` because scratch workdirs are not git
repositories. No approval/sandbox bypass flag is used."""

_RUN_EDIT_TOOLS = "read,edit,write,grep,find,ls"
"""P1-8 governed Pi editing tools for ``run`` dispatch: an explicit
bounded allowlist built from pi's committed built-in tool set minus
``bash`` — file edit/create capability for scoped implementation files
without shell escape. Pi's ``--mode json`` usage capture is unaffected."""

#: Governed ``run`` capture and noninteractive editing reuse the committed
#: Claude config (:data:`CLAUDE_GOVERNED_CONFIG`) verbatim, so ``claude -p``
#: emits the result event that ``codex_cli.capture_claude_usage`` parses
#: and accepts scoped edits via ``--permission-mode acceptEdits`` with
#: ``--permission-prompts none``; no bypass flag is ever emitted.


_TOKENS_PER_1M = 1_000_000

#: Harnesses whose authoritative ``total_tokens`` includes the cache-read
#: and cache-write components (Pi and OMP sum ``cacheRead``/``cacheWrite``
#: into ``totalTokens``; the Claude result event reports the same four
#: components). Codex treats cached input as a subset of input with
#: ``total = input + output``, and the proven agy receipt semantics keep
#: cache counters outside ``total_tokens``, so neither can derive cache
#: billing evidence from the total.
_TOTAL_INCLUDES_CACHE_HARNESSES = frozenset({"pi", "omp", "claude"})


class RunSelectionError(Exception):
    """A ``run`` selection refusal: nothing launched, the CLI exits 3.

    Mirrors :class:`lee_llm_router.resolver.ResolutionError`: a plain
    refusal carrying the process exit code and a stable machine ``kind``
    (``excluded``, ``unknown_route``, ``no_eligible``, ``invalid_class``,
    ``invalid_date``), not a provider failure.
    """

    def __init__(
        self,
        message: str,
        *,
        exit_code: int = SELECTION_EXIT_CODE,
        kind: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.kind = kind
        self.cause = cause


class RunDispatchError(LLMRouterError):
    """Raised when the selected route's harness cannot be dispatched.

    Chains into :class:`LLMRouterError` with
    :attr:`FailureType.PROVIDER_ERROR`; nothing has been launched when it
    is raised before the subprocess boundary.
    """

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message, failure_type=FailureType.PROVIDER_ERROR, cause=cause)


# ---------------------------------------------------------------------------
# Typed results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionOutcome:
    """One selected route plus the explain evidence behind the selection.

    ``basis`` is :data:`SELECTION_BASIS_EXPLICIT` or
    :data:`SELECTION_BASIS_EXPLAIN_CHEAPEST_ELIGIBLE`; ``excluded`` carries
    every excluded route's id and its exact explain reasons joined with
    ``"; "`` — explain evidence preserved verbatim, never re-judged.

    ``supervisor_route`` is the accepted supervisor-route object
    (``model``/``effort``/``harness``/``channel``/``provider``) built from the
    catalog when the caller attests one via ``--supervisor-route`` (P1-4
    ruling 3); ``None`` means the caller made no attestation and no
    supervisor identity is invented.
    """

    route: StaffingRoute
    basis: str
    reason: str
    explain_ref: str
    excluded: tuple[tuple[str, str], ...]
    pricing: EligibilityPrice | None = None
    supervisor_route: dict[str, Any] | None = None
    cache_replacement_usd_per_token: float | None = None
    cache_marginal_usd_per_token: float | None = None
    cache_rates_checked: bool = False


@dataclass(frozen=True)
class DispatchOutcome:
    """One completed subprocess dispatch of the selected route.

    ``argv`` is the final child argv (prompt substituted, no placeholder
    left); ``exit_code`` is the child's exit code, or ``124`` on a ceiling
    timeout (``timed_out`` True); ``stdout``/``stderr`` are the captured
    streams decoded with ``errors="replace"``; ``usage`` is the schema-valid
    attempt-record v2 usage mapping from the accepted harness capture
    function; ``usage_models`` is the sorted distinct Claude ``modelUsage``
    model ids when the receipt is a Claude result event with ``modelUsage``
    evidence (billing-relevance evidence for cost; ``None`` otherwise).
    """

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    usage: dict[str, Any]
    usage_models: tuple[str, ...] | None = None


@dataclass(frozen=True)
class OracleOutcome:
    """Captured result of one optional verification-oracle invocation.

    A missing oracle is represented by ``None`` at the result-building
    boundary, not by this class.  An oracle that cannot be launched has a
    ``None`` exit code and a deterministic ``error``; an oracle killed at its
    wall-clock bound has exit code ``124`` and ``timed_out=True``.
    """

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _marginal_price_sort_key(row: EligibilityRow) -> tuple[int, float, float, str]:
    """Marginal-price order: priced rows ascend, unpriced last, id tie-break.

    Exactly the committed ``catalog explain`` display key
    (``doctor._explain_sort_key``): the display ordering the
    ``catalog explain --json`` report presents, so role/class selection
    picks the same first eligible route the report shows first.
    """
    pricing = row.pricing
    if pricing is None:
        return (1, 0.0, 0.0, row.route_id)
    return (
        0,
        pricing.marginal_input_usd_per_token,
        pricing.marginal_output_usd_per_token,
        row.route_id,
    )


def _excluded_summaries(
    rows: tuple[EligibilityRow, ...],
) -> tuple[tuple[str, str], ...]:
    """Explain-evidence excluded summaries: ``(route_id, joined reasons)``.

    Reasons are the exact explain reasons joined with ``"; "`` in row
    order; excluded routes always carry at least one reason.
    """
    return tuple(
        (row.route_id, "; ".join(row.reasons)) for row in rows if not row.eligible
    )


def _normalize_at_date(at_date: date | str) -> date:
    """Normalize ``at_date`` to a :class:`datetime.date`, failing closed."""
    if isinstance(at_date, date):
        return at_date
    try:
        return date.fromisoformat(at_date)
    except (TypeError, ValueError) as exc:
        raise RunSelectionError(
            f"at_date: not an ISO date (YYYY-MM-DD): {at_date!r}",
            kind="invalid_date",
            cause=exc,
        ) from exc


def select_route(
    catalog: StaffingCatalog,
    availability: AvailabilitySnapshot,
    *,
    role: str,
    oracle_type: str,
    size_band: str,
    language: str,
    domain_tags: tuple[str, ...] | list[str] = (),
    class_key: str,
    at_date: date | str,
    route_id: str | None = None,
    author_route_id: str | None = None,
    supervisor_route_id: str | None = None,
    openrouter_snapshot_path: str | Path | None = None,
    rate_table_path: str | Path | None = None,
) -> SelectionOutcome:
    """Select exactly one route, or refuse with nothing launched.

    Both bases evaluate eligibility over exactly the ``catalog explain``
    path — :func:`evaluate_eligibility` with the committed catalog, the
    supplied availability snapshot, dated terms at ``at_date``, and
    marginal pricing. No other checks, probabilities, or ladders apply.

    Args:
        catalog: The loaded staffing catalog (read-only).
        availability: An already-normalised availability snapshot.
        role: Class role (from the ``--class`` string; ``run`` has no
            separate role flag in explicit mode).
        oracle_type: Class oracle type.
        size_band: Class size band.
        language: Class language.
        domain_tags: Class domain-tag set.
        class_key: The canonical five-segment class string; must equal the
            canonical rendering of the structured fields (enforced by the
            eligibility evaluation).
        at_date: Date for the dated-terms check (ISO string or date).
        route_id: Explicit ``--route`` selection. The route must exist and
            be currently eligible; otherwise :class:`RunSelectionError`
            with exit code 3 and the exact explain reason.
        supervisor_route_id: Optional ``--supervisor-route`` attestation
            (P1-4 ruling 3): the caller attests its own route. The id must
            name a known, active, currently eligible catalog route under
            the same role/class path; otherwise
            :class:`RunSelectionError` with exit code 3 and nothing is
            launched. When resolved, the accepted supervisor-route object
            is carried on the outcome.
        author_route_id: Optional author route id, forwarded to the
            eligibility evaluation (review/judge independence). ``run``
            itself never supplies one.
        openrouter_snapshot_path: Injectable pinned OpenRouter snapshot
            path (defaults to the committed pinned file).
        rate_table_path: Injectable agent-orch rate-table path.

    Returns:
        The :class:`SelectionOutcome` for the single selected route, with
        the selection basis, reason, explain reference, and every excluded
        route id/reason preserved from the same evaluation.

    Raises:
        RunSelectionError: When the class arguments are invalid, the
            explicit route id matches no catalog route, the explicit route
            is not currently eligible, or no route is eligible for
            role/class selection. ``exit_code`` is always 3.
    """
    when = _normalize_at_date(at_date)
    try:
        rows = evaluate_eligibility(
            catalog,
            role=role,
            oracle_type=oracle_type,
            size_band=size_band,
            language=language,
            domain_tags=tuple(domain_tags),
            class_key=class_key,
            author_route_id=author_route_id,
            availability=availability,
            at_date=when,
            openrouter_snapshot_path=openrouter_snapshot_path,
            rate_table_path=rate_table_path,
        )
    except StaffingEligibilityError as exc:
        raise RunSelectionError(str(exc), kind="invalid_class", cause=exc) from exc

    excluded = _excluded_summaries(rows)
    explain_ref = (
        f"catalog explain --role {role} --class {class_key} "
        f"--at {when.isoformat()} --json"
    )

    # Optional caller attestation (P1-4 ruling 3): resolved through the same
    # committed catalog/eligibility path, failing closed before any branch
    # selects a worker route. ``None`` when the caller makes no attestation.
    attested_supervisor = (
        _resolve_supervisor_route(
            catalog,
            rows,
            supervisor_route_id=supervisor_route_id,
            class_key=class_key,
            when=when,
        )
        if supervisor_route_id is not None
        else None
    )

    if route_id is not None:
        row = next((r for r in rows if r.route_id == route_id), None)
        if row is None:
            raise RunSelectionError(
                f"--route {route_id!r} does not match any route_id in the "
                "routes catalog",
                kind="unknown_route",
            )
        route = next(r for r in catalog.routes.routes if r.route_id == route_id)
        if not row.eligible:
            raise RunSelectionError(
                f"explicit route {route_id!r} is not eligible for class "
                f"{class_key!r} at {when.isoformat()}: {'; '.join(row.reasons)}",
                kind="excluded",
            )
        cache_repl, cache_marg = _resolve_cache_rates(
            row.pricing,
            openrouter_snapshot_path=openrouter_snapshot_path,
            rate_table_path=rate_table_path,
        )
        return SelectionOutcome(
            route=route,
            basis=SELECTION_BASIS_EXPLICIT,
            reason=(
                f"explicit --route {route_id} is eligible for class "
                f"{class_key} at {when.isoformat()}"
            ),
            explain_ref=explain_ref,
            excluded=excluded,
            pricing=row.pricing,
            supervisor_route=attested_supervisor,
            cache_replacement_usd_per_token=cache_repl,
            cache_marginal_usd_per_token=cache_marg,
            cache_rates_checked=True,
        )

    eligible = sorted(
        (row for row in rows if row.eligible), key=_marginal_price_sort_key
    )
    if not eligible:
        raise RunSelectionError(
            f"no eligible route for class {class_key!r} at {when.isoformat()}; "
            f"{len(excluded)} routes excluded",
            kind="no_eligible",
        )
    selected = eligible[0]
    route = next(r for r in catalog.routes.routes if r.route_id == selected.route_id)
    cache_repl, cache_marg = _resolve_cache_rates(
        selected.pricing,
        openrouter_snapshot_path=openrouter_snapshot_path,
        rate_table_path=rate_table_path,
    )
    return SelectionOutcome(
        route=route,
        basis=SELECTION_BASIS_EXPLAIN_CHEAPEST_ELIGIBLE,
        reason=(
            f"first eligible route in catalog explain marginal-price order "
            f"for class {class_key} at {when.isoformat()}"
        ),
        explain_ref=explain_ref,
        excluded=excluded,
        pricing=selected.pricing,
        supervisor_route=attested_supervisor,
        cache_replacement_usd_per_token=cache_repl,
        cache_marginal_usd_per_token=cache_marg,
        cache_rates_checked=True,
    )


def selection_record(outcome: SelectionOutcome) -> dict[str, Any]:
    """The attempt-record v2 ``selection`` object for one selection outcome.

    Exactly the four schema fields (``basis``, ``reason``, ``explain_ref``,
    ``excluded``); excluded entries carry exactly ``route_id`` and
    ``reason``. Explain evidence only — never a new selection judgment.
    """
    return {
        "basis": outcome.basis,
        "reason": outcome.reason,
        "explain_ref": outcome.explain_ref,
        "excluded": [
            {"route_id": route_id, "reason": reason}
            for route_id, reason in outcome.excluded
        ],
    }


def _resolve_supervisor_route(
    catalog: StaffingCatalog,
    rows: tuple[EligibilityRow, ...],
    *,
    supervisor_route_id: str,
    class_key: str,
    when: date,
) -> dict[str, Any]:
    """Resolve an attested supervisor route id, failing closed (P1-4 r3).

    The attested id must name a known catalog route, be ``active``, and be
    currently eligible under exactly the same role/class explain path the
    run itself uses — the same gate explicit ``--route`` selection applies.
    Any failure raises :class:`RunSelectionError` (exit 3) before anything
    is launched.

    Returns:
        The accepted supervisor-route object: the identity tuple
        ``model``/``effort``/``harness``/``channel`` plus the observed
        ``provider`` name — exactly the record's ``route`` object shape,
        never an invented identity.
    """
    route = next(
        (r for r in catalog.routes.routes if r.route_id == supervisor_route_id),
        None,
    )
    if route is None:
        raise RunSelectionError(
            f"--supervisor-route {supervisor_route_id!r} does not match any "
            "route_id in the routes catalog",
            kind="unknown_route",
        )
    if route.status != "active":
        raise RunSelectionError(
            f"--supervisor-route {supervisor_route_id!r} is not active "
            f"(status {route.status!r}); an attested supervisor route must be "
            "an active catalog route",
            kind="excluded",
        )
    row = next(r for r in rows if r.route_id == supervisor_route_id)
    if not row.eligible:
        raise RunSelectionError(
            f"--supervisor-route {supervisor_route_id!r} is not eligible for "
            f"class {class_key!r} at {when.isoformat()}: "
            f"{'; '.join(row.reasons)}",
            kind="excluded",
        )
    return {
        "model": route.model,
        "effort": route.effort,
        "harness": route.harness,
        "channel": route.channel,
        "provider": _HARNESS_PROVIDER_NAMES.get(route.harness, route.harness),
    }


def _utc_timestamp() -> str:
    """Return one aware UTC timestamp for a router attempt and its event."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_attempt_id() -> str:
    """Return a schema-safe id for a run that has no caller-supplied id."""
    return f"router-run-{uuid.uuid4().hex}"


def packet_id_for_text(packet_text: str) -> str:
    """Return the canonical content identity for the dispatched packet.

    The governed CLI accepts a packet file but no separately asserted packet
    identifier.  A filesystem path is location metadata, not packet identity,
    so the identifier is the SHA-256 of the exact UTF-8 text sent to the
    provider.  Equal packet text therefore has one stable identity regardless
    of where the file is stored.

    Args:
        packet_text: Exact packet text passed to :func:`dispatch_route`.

    Returns:
        ``sha256:<lowercase hex digest>``.
    """
    digest = hashlib.sha256(packet_text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _known_token_count(usage: Mapping[str, Any], field: str) -> bool:
    """Whether one billable counter is an actual nonnegative integer."""
    value = usage.get(field)
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_cache_price(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return float(parsed)


def _load_openrouter_cache_rates(path: Path) -> dict[str, float]:
    try:
        _verify_sha256(path)
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        return {}
    rates: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str):
            continue
        model_id = row["id"]
        pricing = row.get("pricing")
        if isinstance(pricing, Mapping):
            parsed = _parse_cache_price(pricing.get("input_cache_read"))
            if parsed is not None:
                rates[model_id] = parsed
    return rates


def _load_rate_table_cache_rates(path: Path) -> dict[str, float]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rates = data.get("rates") if isinstance(data, Mapping) else None
    if not isinstance(rates, Mapping):
        return {}
    prices: dict[str, float] = {}
    for model_id, row in rates.items():
        if not isinstance(model_id, str) or not isinstance(row, Mapping):
            continue
        parsed = _parse_cache_price(row.get("cache_read_usd_per_1m"))
        if parsed is not None:
            prices[model_id] = parsed / _TOKENS_PER_1M
    return prices


def _resolve_cache_rates(
    pricing: EligibilityPrice | None,
    *,
    openrouter_snapshot_path: str | Path | None = None,
    rate_table_path: str | Path | None = None,
) -> tuple[float | None, float | None]:
    """Resolve replacement and marginal cache-read price per token.

    Uses the authoritative P0-4 pricing sources named in ``pricing.source``:
    either the pinned OpenRouter snapshot (``input_cache_read``) or the
    agent-orch rate table (``cache_read_usd_per_1m``).

    Returns:
        ``(replacement_cache_rate, marginal_cache_rate)`` where each is a
        nonnegative float, or ``(None, None)`` when no cache price is
        sourced.
    """
    if pricing is None or not pricing.source:
        return None, None

    replacement_rate: float | None = None
    if pricing.source.startswith("openrouter-snapshot:"):
        model_id = pricing.source.split(":", 1)[1]
        snap_path = (
            Path(openrouter_snapshot_path)
            if openrouter_snapshot_path is not None
            else DEFAULT_OPENROUTER_SNAPSHOT_PATH
        )
        rates = _load_openrouter_cache_rates(snap_path)
        replacement_rate = rates.get(model_id)

    elif pricing.source.startswith("rate-table:"):
        key = pricing.source.split(":", 1)[1]
        rt_path = (
            Path(rate_table_path)
            if rate_table_path is not None
            else DEFAULT_RATE_TABLE_PATH
        )
        rates = _load_rate_table_cache_rates(rt_path)
        replacement_rate = rates.get(key)

    if replacement_rate is None:
        return None, None

    marginal_rate = replacement_rate * pricing.multiplier
    return replacement_rate, marginal_rate


def _is_cached_input_subset(
    outcome: SelectionOutcome, usage: Mapping[str, Any]
) -> bool:
    """Whether usage semantics treat cached input tokens as a subset of input.

    Codex reports cached input and reasoning as subsets of input and output
    respectively, with total = input + output. Pi, Claude, OMP, and
    Antigravity treat cached tokens as separate counters (or history not
    constrained by input).
    """
    if getattr(outcome.route, "harness", None) == "codex":
        return True
    if usage.get("source") == CODEX_USAGE_SOURCE:
        return True
    return False


def _attempt_cost(
    outcome: SelectionOutcome,
    usage: Mapping[str, Any],
    *,
    aggregate_models: tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], str]:
    """Calculate list and marginal token cost from the selected P0-4 price.

    The committed price API exposes the dated replacement input/output rates,
    the badge-adjusted marginal rates, and authoritative cache-read rates from
    the selected dated terms source.

    When cached tokens are reported:
    * If cached input is a subset of input (Codex), uncached input is separated
      (``input_tokens - cached_input_tokens``). An invalid relationship where
      cached input exceeds input fails closed as unavailable cost.
    * If cached input is reported separately (Pi and other non-subset harnesses),
      ``input_tokens`` is already uncached input and cached tokens are added at
      the cache rate.
    * Cache rates from authoritative P0-4 sources are applied when cached
      tokens are present. If cached tokens are nonzero but cache price evidence
      is unavailable for the model, cost fails closed as unavailable.
    * Null/absent cached tokens do not bill cache and do not fabricate zeros.
    * Reasoning tokens remain an evidence subset of output and are never billed
      as an unknown extra counter.

    Complete-billing-evidence gates (Astra final review finding 1):
    * The selected dated price terms price exactly the selected route's
      model. A usage aggregate that spans multiple models (the Claude
      ``modelUsage`` ids surfaced as ``aggregate_models``) cannot be priced
      at that single rate and fails closed as unavailable, as does a
      single-model aggregate for a model other than the priced route model.
    * For harnesses whose authoritative ``total_tokens`` includes the
      cache-read and cache-write components (Pi, OMP, Claude), cost exists
      only when the total is known and every token it counts is
      representable as billing evidence: an unknown total could hide
      cache-write tokens, and a positive remainder over the represented
      input/output/cache-read components is exactly the unrepresentable
      cache-write charge. Either gap fails closed as unavailable cost
      rather than billing a subset of the receipt.
    """
    if usage.get("basis") == "unavailable":
        return {"basis": ["unavailable"]}, "usage basis is unavailable"
    if not _known_token_count(usage, "input_tokens"):
        return {"basis": ["unavailable"]}, "input_tokens is unknown"
    if not _known_token_count(usage, "output_tokens"):
        return {"basis": ["unavailable"]}, "output_tokens is unknown"
    pricing = outcome.pricing
    if pricing is None:
        return {"basis": ["unavailable"]}, "selected route has no dated price"

    if aggregate_models is not None:
        if len(aggregate_models) > 1:
            return {"basis": ["unavailable"]}, (
                "aggregated multi-model usage cannot be priced at the "
                "selected route's model rate"
            )
        if aggregate_models and aggregate_models[0] != outcome.route.model:
            return {"basis": ["unavailable"]}, (
                "usage model does not match the selected route's priced model"
            )

    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]

    if getattr(outcome.route, "harness", None) in _TOTAL_INCLUDES_CACHE_HARNESSES:
        if not _known_token_count(usage, "total_tokens"):
            return {"basis": ["unavailable"]}, (
                "total_tokens is unknown, so unrepresented cache-write "
                "tokens cannot be ruled out"
            )
        cached_known = _known_token_count(usage, "cached_input_tokens")
        cached_represented = usage["cached_input_tokens"] if cached_known else 0
        unrepresented = (
            usage["total_tokens"] - input_tokens - output_tokens - cached_represented
        )
        if unrepresented < 0:
            return {"basis": ["unavailable"]}, (
                "total_tokens contradicts the represented billing components"
            )
        if unrepresented > 0:
            return {"basis": ["unavailable"]}, (
                "total_tokens includes cache-write tokens that the v2 "
                "usage mapping cannot represent as billing evidence"
            )

    cached_tokens: int | None = None
    if "cached_input_tokens" in usage and usage["cached_input_tokens"] is not None:
        if not _known_token_count(usage, "cached_input_tokens"):
            return {"basis": ["unavailable"]}, "cached_input_tokens is invalid"
        cached_tokens = usage["cached_input_tokens"]

    is_subset = _is_cached_input_subset(outcome, usage)
    if cached_tokens is not None and is_subset:
        if cached_tokens > input_tokens:
            return {
                "basis": ["unavailable"]
            }, "cached_input_tokens contradicts input_tokens"
        uncached_input_tokens = input_tokens - cached_tokens
    else:
        uncached_input_tokens = input_tokens

    cache_repl = outcome.cache_replacement_usd_per_token
    cache_marg = outcome.cache_marginal_usd_per_token
    if not outcome.cache_rates_checked and cache_repl is None:
        cache_repl, cache_marg = _resolve_cache_rates(pricing)

    cache_tokens_known = cached_tokens is not None and cached_tokens > 0
    if cache_tokens_known:
        if cache_repl is None:
            return {
                "basis": ["unavailable"]
            }, "cache price is unavailable for the selected model"
        if (
            not isinstance(cache_repl, (int, float))
            or isinstance(cache_repl, bool)
            or not math.isfinite(cache_repl)
            or cache_repl < 0
        ):
            return {"basis": ["unavailable"]}, "cache price is invalid"
        if cache_marg is None:
            cache_marg = cache_repl * pricing.multiplier
        if (
            not isinstance(cache_marg, (int, float))
            or isinstance(cache_marg, bool)
            or not math.isfinite(cache_marg)
            or cache_marg < 0
        ):
            return {"basis": ["unavailable"]}, "cache price is invalid"

    cache_cost_list = cached_tokens * cache_repl if cache_tokens_known else 0.0
    cache_cost_marg = cached_tokens * cache_marg if cache_tokens_known else 0.0

    list_cost = (
        uncached_input_tokens * pricing.replacement_input_usd_per_token
        + output_tokens * pricing.replacement_output_usd_per_token
        + cache_cost_list
    )
    marginal_cost = (
        uncached_input_tokens * pricing.marginal_input_usd_per_token
        + output_tokens * pricing.marginal_output_usd_per_token
        + cache_cost_marg
    )

    if not math.isfinite(list_cost) or not math.isfinite(marginal_cost):
        return {"basis": ["unavailable"]}, "calculated cost is not finite"

    note = (
        "cost calculated from known input/output/cache counters"
        if cached_tokens is not None and cached_tokens > 0
        else "cost calculated from known input/output counters"
    )
    return {
        "basis": ["list", "marginal"],
        "usd_list": list_cost,
        "usd_marginal": marginal_cost,
    }, note


def build_attempt_record(
    outcome: SelectionOutcome,
    dispatch: DispatchOutcome,
    oracle: OracleOutcome | None,
    *,
    packet_id: str,
    class_record: Mapping[str, Any],
    availability: AvailabilitySnapshot,
    at_date: date,
    oracle_cmd: str | None = None,
    parent_attempt_id: str | None = None,
    escalation_reason: str | None = None,
    supervisor_route: Mapping[str, Any] | None = None,
    attempt_id: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Build one strict v2 router-run attempt record.

    This function only assembles facts already produced by selection,
    dispatch, the optional oracle, and the committed pricing/eligibility
    path. Schema validation and the single append belong to
    :mod:`lee_llm_router.staffing.ledger`; no retry or escalation is done.

    Args:
        outcome: Selected route and catalog-explain evidence.
        dispatch: The one completed worker dispatch and usage receipt.
        oracle: The one optional oracle outcome.
        packet_id: Canonical identifier of the exact dispatched packet.
        class_record: Canonical class block reconstructed from ``--class``.
        availability: The snapshot used during eligibility evaluation.
        at_date: Dated-terms date used during selection.
        oracle_cmd: Original command string, or ``None`` when no oracle ran.
        parent_attempt_id: Optional escalation parent.
        escalation_reason: Optional paired escalation reason.
        supervisor_route: Optional attested supervisor route object (P1-4
            ruling 3), resolved against the committed catalog by
            :func:`select_route` from ``--supervisor-route``. It must not be
            invented when the caller records no supervisor identity.
        attempt_id: Optional caller-supplied id; generated when absent.
        captured_at: Optional aware UTC capture timestamp, primarily for tests.

    Returns:
        A mapping in the committed attempt-record v2 shape. It is not
        written by this function.
    """
    route = outcome.route
    usage = dict(dispatch.usage)
    cost, cost_note = _attempt_cost(
        outcome, usage, aggregate_models=dispatch.usage_models
    )
    verdict = _oracle_verdict(oracle)
    timestamp = captured_at or _utc_timestamp()
    channel_headroom = availability.headroom(route.channel)
    provider = _HARNESS_PROVIDER_NAMES.get(route.harness, route.harness)

    # ``router_event`` is the existing event shape embedded as provenance
    # evidence. A run is a strict eligibility decision, not a new resolver
    # mode; the event remains a normal 17-field build_event result.
    from lee_llm_router import events as events_mod

    router_event = events_mod.build_event(
        ts=timestamp,
        harness="cli",
        crew="run",
        role=class_record["role"],
        mode="strict",
        worker_id=route.route_id,
        provider=provider,
        model=route.model,
        effort=route.effort,
        channel=route.channel,
        headroom=channel_headroom.health.value,
        reason=outcome.reason,
        authorized_by=None,
        route_id=route.route_id,
        snapshot_observed_at=channel_headroom.observed_at,
        snapshot_stale=channel_headroom.stale,
    )

    wall_clock_ms = max(
        0,
        round(
            (dispatch.duration_seconds + (oracle.duration_seconds if oracle else 0.0))
            * 1000.0
        ),
    )
    notes = [
        "router-run dispatch facts: "
        f"exit_code={dispatch.exit_code}, timed_out={dispatch.timed_out}, "
        f"duration_seconds={dispatch.duration_seconds:.6f}",
        f"oracle verdict: {verdict}; command={'present' if oracle_cmd else 'none'}",
        f"cost: {cost_note}; dated terms at {at_date.isoformat()}",
    ]
    if oracle is not None:
        notes.append(
            "oracle evidence: "
            f"exit_code={oracle.exit_code}, timed_out={oracle.timed_out}, "
            f"error={oracle.error or 'none'}"
        )

    record: dict[str, Any] = {
        "schema_version": 2,
        "attempt_id": attempt_id or _new_attempt_id(),
        "record_kind": "router_run",
        "packet_id": packet_id,
        "parent_attempt_id": parent_attempt_id,
        "escalation_reason": escalation_reason,
        "captured_at": timestamp,
        "verified_success": False,
        "route": {
            "model": route.model,
            "effort": route.effort,
            "harness": route.harness,
            "channel": route.channel,
            "provider": provider,
        },
        "class_record": dict(class_record),
        "verdict": verdict,
        "failure_class": _failure_class(dispatch, oracle),
        "oracle_cmd": oracle_cmd if verdict != "unverified" else None,
        "usage": usage,
        "cost": cost,
        "wall_clock_ms": wall_clock_ms,
        "selection": selection_record(outcome),
        "router_event": router_event,
        "provenance": {
            "source": "router-run",
            "recorded_by": "lee-llm-router run",
            "source_refs": [
                "src/lee_llm_router/events.py EVENT_FIELDS and build_event contract",
                ("config/staffing/terms.yaml via staffing.terms_at and " "route_price"),
                (
                    "docs/staffing/phase1-contracts.md §Attempt record v2 "
                    "placement, §Usage evidence taxonomy, §Cost rule"
                ),
            ],
            "notes": notes,
        },
    }
    if supervisor_route is not None:
        record["supervisor_route"] = dict(supervisor_route)

    # The v2 gate is intentionally conservative. The CLI does not claim to
    # observe its caller's route; direct callers may supply one only when it
    # is real source evidence (P1-4 ruling 3: the ``--supervisor-route``
    # attestation resolved against the committed catalog). Worker success is
    # also required even though the schema cannot infer it from the
    # provenance note. When the gate does not hold, exactly one
    # ``verified_success_reason`` from the closed P1-4 vocabulary names the
    # first blocking gap in the fixed order below; a true record never
    # carries a reason (schema-forbidden).
    reason = _verified_success_reason(dispatch, verdict, record, usage, cost)
    record["verified_success"] = reason is None
    if reason is not None:
        record["verified_success_reason"] = reason
    return record


def _verified_success_reason(
    dispatch: DispatchOutcome,
    verdict: str,
    record: Mapping[str, Any],
    usage: Mapping[str, Any],
    cost: Mapping[str, Any],
) -> str | None:
    """The exact reason ``verified_success`` is false, or ``None`` when true.

    Fixed truthful precedence (P1-4 ruling 3): the attestation gap first,
    then the worker dispatch result, then the oracle verdict, then the
    remaining evidence gate. The first blocking gap in this order names the
    field; later gaps in the same record are never claimed instead, and a
    passing run is never dressed up as a success it cannot evidence.
    """
    if record.get("supervisor_route") is None:
        return VERIFIED_SUCCESS_REASON_UNATTESTED
    if dispatch.timed_out or dispatch.exit_code != 0:
        return VERIFIED_SUCCESS_REASON_WORKER_DISPATCH
    if verdict != "pass":
        return VERIFIED_SUCCESS_REASON_ORACLE
    if (
        not record["route"]
        or not record["class_record"]
        or not record["oracle_cmd"]
        or record["failure_class"] is not None
        or usage.get("basis") == "unavailable"
        or not _known_token_count(usage, "input_tokens")
        or not _known_token_count(usage, "output_tokens")
        or cost.get("basis") != ["list", "marginal"]
        or not isinstance(record["wall_clock_ms"], int)
    ):
        return VERIFIED_SUCCESS_REASON_EVIDENCE
    return None


def _failure_class(
    dispatch: DispatchOutcome, oracle: OracleOutcome | None
) -> str | None:
    """Return only a failure class directly supported by run evidence."""
    if dispatch.timed_out or (oracle is not None and oracle.timed_out):
        return "platform_timeout"
    if oracle is not None and oracle.error is not None:
        return "platform_env"
    if oracle is not None and oracle.exit_code not in (None, 0):
        return "spec_rejected"
    return None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _pi_provider_id_for_channel(channel: str) -> str:
    """The Pi backend provider id for a funding channel, from committed data.

    The exact reverse of the committed
    :data:`lee_llm_router.crews.HARNESS_PROVIDER_CHANNELS` mapping; no id
    is invented for an unmapped channel (fail closed).
    """
    provider_id = _CHANNEL_TO_PI_PROVIDER_ID.get(channel)
    if provider_id is None:
        raise RunDispatchError(
            f"no committed Pi provider id for channel {channel!r} "
            "(crews.HARNESS_PROVIDER_CHANNELS has no reverse entry)"
        )
    return provider_id


def build_dispatch_command(route: StaffingRoute) -> list[str]:
    """Build the route's dispatch argv through its harness provider.

    The argv comes from the route harness provider's ``build_command`` —
    never from the catalog ``dispatch_template`` shell string and never
    shell-quoted or interpolated. The final element is the literal
    ``{prompt}`` placeholder for harnesses that take the prompt as argv;
    stdin-delivery harnesses (``omp``) end without it and receive the
    prompt on stdin at the subprocess boundary.

    Pi config carries the channel's committed provider id (e.g.
    ``openrouter``) plus the P1-8 bounded editing tool allowlist
    (:data:`_RUN_EDIT_TOOLS`, bash excluded) because governed
    implementation dispatch must be able to edit its scoped file; Codex
    config forces ``json_flag: --json`` so the governed capture receives
    the JSONL usage receipt and appends the exec-level
    ``-s workspace-write --skip-git-repo-check`` sandbox flags for
    noninteractive edits in a non-git scratch workdir; Claude config
    reuses the committed ``CLAUDE_GOVERNED_CONFIG``
    (``--output-format stream-json`` plus the documented safe
    noninteractive permission flags
    ``--permission-mode acceptEdits --permission-prompts none``) for the
    same reason; the agy, OpenCode, and OMP configs apply their accepted
    governed JSON flags (:data:`AGY_GOVERNED_CONFIG` →
    ``--output-format json``, :data:`OPENCODE_GOVERNED_CONFIG` →
    ``--format json``, :data:`OMP_GOVERNED_CONFIG` → ``--mode json``) so
    each harness emits exactly the receipt its accepted P1-4d–f parser
    captures (Astra final review finding 3). No dangerous bypass flag is
    ever emitted.

    Raises:
        RunDispatchError: When the route's harness has no wired provider,
            or a Pi route's channel has no committed provider id.
    """
    harness = route.harness
    provider_cls = _HARNESS_PROVIDER_CLASSES.get(harness)
    if provider_cls is None:
        raise RunDispatchError(
            f"harness {harness!r} has no provider wired for run dispatch"
        )
    provider = provider_cls()
    if harness == "pi":
        config: dict[str, Any] = {
            "provider": _pi_provider_id_for_channel(route.channel),
            "tools": _RUN_EDIT_TOOLS,
        }
    elif harness == "codex":
        config = dict(_CODEX_GOVERNED_CONFIG)
    elif harness == "claude":
        config = dict(CLAUDE_GOVERNED_CONFIG)
    elif harness == "agy":
        config = {"model": route.model, **AGY_GOVERNED_CONFIG}
    elif harness == "opencode":
        config = {"model": route.model, **OPENCODE_GOVERNED_CONFIG}
    elif harness == "omp":
        config = dict(OMP_GOVERNED_CONFIG)
    else:
        config = {}
    return provider.build_command(config, model=route.model, effort=route.effort)


def _capture_failure_usage(harness: str, exc: Exception) -> dict[str, Any]:
    """Schema-valid unavailable v2 usage preserving a capture failure diagnostic."""
    err = str(exc).strip() or type(exc).__name__
    source_desc = _HARNESS_USAGE_SOURCES.get(harness)
    if source_desc:
        reason = f"usage capture failed for harness {harness!r} ({source_desc}): {err}"
    else:
        reason = f"usage capture failed for harness {harness!r}: {err}"
    return {
        "basis": "unavailable",
        "unavailable_reason": reason,
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def _usage_for_harness(harness: str, stdout_text: str) -> dict[str, Any]:
    """Schema-valid v2 usage from the harness's accepted capture function.

    Pi, Codex, Claude, agy, OpenCode, and OMP have accepted P1-4a–f capture
    parsers; every wired harness records ``unavailable`` with a specific
    reason only when its accepted parser fails closed. The dispatch argv for
    agy, OpenCode, and OMP carries the accepted governed JSON flags
    (:data:`AGY_GOVERNED_CONFIG`, :data:`OPENCODE_GOVERNED_CONFIG`,
    :data:`OMP_GOVERNED_CONFIG`) so the harness emits exactly the receipt
    its parser accepts. When a capture function raises after the worker
    completes, the failure is recorded as unavailable usage preserving the
    failure diagnostic so the completed worker is never dropped from the
    attempt ledger. No parser estimates tokens from text, context length,
    cost, or elapsed time.
    """
    try:
        if harness == "pi":
            return capture_pi_usage(stdout_text)
        if harness == "codex":
            return capture_codex_usage(stdout_text)
        if harness == "claude":
            return capture_claude_usage(stdout_text)
        if harness == "agy":
            return capture_agy_usage(stdout_text)
        if harness == "opencode":
            return capture_opencode_usage(stdout_text)
        if harness == "omp":
            return capture_omp_usage(stdout_text)
    except Exception as exc:
        return _capture_failure_usage(harness, exc)
    return {
        "basis": "unavailable",
        "unavailable_reason": (
            f"no usage capture parser wired for harness {harness!r}"
        ),
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def _dispatch_resolution(route: StaffingRoute, argv: list[str]) -> Resolution:
    """Build the dispatch-boundary resolution for one selected route."""
    return Resolution(
        crew="run",
        role="run",
        mode="run",
        worker_id=route.route_id,
        provider=_HARNESS_PROVIDER_NAMES.get(route.harness, route.harness),
        model=route.model,
        effort=route.effort,
        channel=route.channel,
        headroom="",
        headroom_remaining_fraction=None,
        pace_ratio=None,
        reason="staffing run dispatch",
        authorized_by=None,
        route_id=route.route_id,
        dispatch_command=list(argv),
        prompt_delivery=("argv" if PROMPT_PLACEHOLDER in argv else "stdin"),
        worker_command=route.dispatch_template,
        snapshot_observed_at=None,
        snapshot_stale=False,
    )


def dispatch_route(
    route: StaffingRoute,
    prompt: str,
    *,
    workdir: str | Path | None = None,
    timeout_seconds: float | None = DEFAULT_RUN_TIMEOUT_SECONDS,
    stall_minutes: float = DEFAULT_STALL_MINUTES,
    popen: Callable[..., Any] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    stderr: TextIO | None = None,
) -> DispatchOutcome:
    """Dispatch the selected route once through the watchdog boundary.

    The route's provider ``build_command`` argv carries the packet prompt
    (argv substitution, or stdin delivery when the harness has no
    placeholder), the child's ``cwd`` is the workdir when supplied, and
    nothing is ever shell-quoted or interpolated. The single launch is
    supervised by :func:`lee_llm_router.dispatch.run_dispatch` (stall
    watchdog + wall-clock ceiling); there is no retry and no escalation.

    Args:
        route: The selected catalog route.
        prompt: The prompt text taken verbatim from the packet.
        workdir: Optional child working directory; must exist.
        timeout_seconds: Wall-clock ceiling in seconds; ``None`` uses the
            boundary default (:data:`DEFAULT_MAX_MINUTES` minutes).
        stall_minutes: Silence minutes before a stall is flagged (a stall
            never kills; only the ceiling does).
        popen: Injected process spawner (tests).
        clock: Injected monotonic clock (tests).
        sleep: Injected sleep callable (tests).
        poll_seconds: Watchdog polling cadence.
        stderr: Stream for watchdog warnings (defaults to ``sys.stderr``).

    Returns:
        The :class:`DispatchOutcome` with the final argv, captured
        stdout/stderr, exit code, wall-clock duration, timeout flag, the
        schema-valid usage from the harness's accepted capture function,
        and the Claude ``usage_models`` billing evidence when the receipt
        carries ``modelUsage`` model ids.

    Raises:
        RunDispatchError: When the harness has no wired provider, a Pi
            route's channel has no committed provider id, the workdir does
            not exist, or the timeout is not positive.
    """
    harness = route.harness
    argv = build_dispatch_command(route)

    if workdir is not None:
        workdir_path = Path(workdir)
        if not workdir_path.is_dir():
            raise RunDispatchError(f"workdir is not a directory: {workdir_path}")

    if timeout_seconds is None:
        max_minutes: float = DEFAULT_MAX_MINUTES
    else:
        if timeout_seconds <= 0:
            raise RunDispatchError(
                f"timeout must be a positive number of seconds, got "
                f"{timeout_seconds!r}"
            )
        max_minutes = float(timeout_seconds) / 60.0

    base_popen = popen if popen is not None else _DEFAULT_POPEN
    clock_fn = clock if clock is not None else _DEFAULT_CLOCK
    sleep_fn = sleep if sleep is not None else _DEFAULT_SLEEP
    cwd = str(Path(workdir)) if workdir is not None else None

    def safe_popen(child_argv: list[str], **kwargs: Any) -> Any:
        """Keep the worker boundary explicitly argv-only and non-shell."""
        kwargs["shell"] = False
        if cwd is not None:
            kwargs["cwd"] = cwd
        return base_popen(child_argv, **kwargs)

    popen_fn: Callable[..., Any] = safe_popen

    resolution = _dispatch_resolution(route, argv)
    stdout_buf = bytearray()
    stderr_buf = bytearray()

    started = clock_fn()
    exit_code = run_dispatch(
        resolution,
        prompt,
        stall_minutes=stall_minutes,
        max_minutes=max_minutes,
        popen=popen_fn,
        clock=clock_fn,
        sleep=sleep_fn,
        poll_seconds=poll_seconds,
        sink=stdout_buf.extend,
        err_sink=stderr_buf.extend,
        stderr=stderr,
    )
    duration = clock_fn() - started

    stdout_text = bytes(stdout_buf).decode("utf-8", errors="replace")
    try:
        usage = _usage_for_harness(harness, stdout_text)
    except Exception as exc:
        usage = _capture_failure_usage(harness, exc)
    # Claude ``modelUsage`` model ids are billing-relevance evidence: the
    # selected dated price terms price exactly the route's model, so cost
    # needs to know when the receipt aggregates several models.
    usage_models = claude_aggregate_models(stdout_text) if harness == "claude" else None
    return DispatchOutcome(
        argv=tuple(argv),
        exit_code=exit_code,
        stdout=stdout_text,
        stderr=bytes(stderr_buf).decode("utf-8", errors="replace"),
        duration_seconds=duration,
        timed_out=(exit_code == _TIMEOUT_EXIT_CODE),
        usage=usage,
        usage_models=usage_models,
    )


def parse_oracle_command(command: str) -> list[str]:
    """Parse one oracle command into argv without invoking a shell.

    Args:
        command: The command supplied by ``--oracle``.

    Returns:
        The non-empty argv produced by :func:`shlex.split`.

    Raises:
        RunDispatchError: If the command is empty or has malformed shell
            quoting.  The command is only parsed; shell operators are never
            interpreted.
    """
    if not isinstance(command, str) or not command.strip():
        raise RunDispatchError("oracle command must not be empty")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise RunDispatchError(
            f"oracle command is malformed: {exc}", cause=exc
        ) from exc
    if not argv:
        raise RunDispatchError("oracle command must not be empty")
    return argv


def oracle_timeout_seconds(
    declared_timeout_seconds: float | None,
    worker_duration_seconds: float,
) -> float:
    """Return the oracle's remaining wall-clock budget.

    A declared ``--timeout`` is a shared worker-plus-oracle budget.  Without
    one, the dispatch boundary's standard ceiling is used as the total
    bounded budget.  An exhausted worker budget becomes an immediate oracle
    timeout rather than an unbounded subprocess.
    """
    total = (
        DEFAULT_ORACLE_TIMEOUT_SECONDS
        if declared_timeout_seconds is None
        else float(declared_timeout_seconds)
    )
    return max(0.0, total - max(0.0, float(worker_duration_seconds)))


def _set_nonblocking(stream: Any) -> None:
    """Best-effort nonblocking setup for a captured subprocess stream."""
    try:
        os.set_blocking(stream.fileno(), False)
    except (AttributeError, OSError, ValueError):
        # Small fakes often expose only ``read``; their read method is already
        # nonblocking from the test boundary's perspective.
        pass


def _drain_stream(stream: Any) -> bytes:
    """Drain currently available bytes from a real or fake pipe."""
    if stream is None:
        return b""
    chunks: list[bytes] = []
    while True:
        try:
            chunk = stream.read(65536)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", errors="replace")
        if not isinstance(chunk, bytes):
            chunk = bytes(chunk)
        chunks.append(chunk)
    return b"".join(chunks)


def run_oracle(
    argv: list[str] | tuple[str, ...] | str,
    *,
    workdir: str | Path | None = None,
    timeout_seconds: float | None = DEFAULT_ORACLE_TIMEOUT_SECONDS,
    popen: Callable[..., Any] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> OracleOutcome:
    """Run one parsed oracle command through the safe subprocess boundary.

    The command is always passed as an argv sequence with ``shell=False``.
    stdout and stderr are drained without waiting on either pipe, and the
    process is killed with exit code ``124`` at the injected wall-clock
    deadline. Launch failures are returned as failed oracle evidence instead
    of being retried or promoted to a worker failure.

    Args:
        argv: Parsed oracle argv, or a command string parsed here for direct
            callers.
        workdir: Child working directory, when supplied.
        timeout_seconds: Remaining wall-clock budget. ``None`` selects the
            standard bounded default; zero is an immediate timeout budget.
        popen: Injectable process spawner.
        clock: Injectable monotonic clock.
        sleep: Injectable polling sleep.
        poll_seconds: Maximum polling interval.

    Returns:
        One :class:`OracleOutcome` containing all oracle evidence.

    Raises:
        RunDispatchError: If ``workdir`` is not a directory or the argv is
            empty. A child launch error itself is represented in the result.
    """
    oracle_argv = parse_oracle_command(argv) if isinstance(argv, str) else list(argv)
    if not oracle_argv:
        raise RunDispatchError("oracle command must not be empty")
    if workdir is not None and not Path(workdir).is_dir():
        raise RunDispatchError(f"workdir is not a directory: {Path(workdir)}")

    popen_fn = popen if popen is not None else _DEFAULT_POPEN
    clock_fn = clock if clock is not None else _DEFAULT_CLOCK
    sleep_fn = sleep if sleep is not None else _DEFAULT_SLEEP
    if timeout_seconds is None:
        budget = DEFAULT_ORACLE_TIMEOUT_SECONDS
    else:
        budget = max(0.0, float(timeout_seconds))
    cwd = str(Path(workdir)) if workdir is not None else None
    started = clock_fn()

    try:
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        if cwd is not None:
            kwargs["cwd"] = cwd
        process = popen_fn(oracle_argv, **kwargs)
    except Exception as exc:
        duration = max(0.0, clock_fn() - started)
        return OracleOutcome(
            argv=tuple(oracle_argv),
            exit_code=None,
            stdout="",
            stderr="",
            duration_seconds=duration,
            timed_out=False,
            error=f"launch failure: {type(exc).__name__}: {exc}",
        )

    _set_nonblocking(getattr(process, "stdout", None))
    _set_nonblocking(getattr(process, "stderr", None))
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    poll_delay = max(0.001, float(poll_seconds))

    while True:
        stdout_buf.extend(_drain_stream(getattr(process, "stdout", None)))
        stderr_buf.extend(_drain_stream(getattr(process, "stderr", None)))
        exit_code = process.poll()
        if exit_code is not None:
            # Capture bytes emitted at the exact exit boundary.
            stdout_buf.extend(_drain_stream(getattr(process, "stdout", None)))
            stderr_buf.extend(_drain_stream(getattr(process, "stderr", None)))
            duration = max(0.0, clock_fn() - started)
            return OracleOutcome(
                argv=tuple(oracle_argv),
                exit_code=exit_code,
                stdout=bytes(stdout_buf).decode("utf-8", errors="replace"),
                stderr=bytes(stderr_buf).decode("utf-8", errors="replace"),
                duration_seconds=duration,
                timed_out=False,
            )

        elapsed = max(0.0, clock_fn() - started)
        if elapsed >= budget:
            try:
                process.kill()
            except Exception:
                pass
            try:
                process.wait(poll_delay)
            except (TypeError, OSError):
                try:
                    process.wait()
                except Exception:
                    pass
            stdout_buf.extend(_drain_stream(getattr(process, "stdout", None)))
            stderr_buf.extend(_drain_stream(getattr(process, "stderr", None)))
            duration = max(0.0, clock_fn() - started)
            return OracleOutcome(
                argv=tuple(oracle_argv),
                exit_code=_TIMEOUT_EXIT_CODE,
                stdout=bytes(stdout_buf).decode("utf-8", errors="replace"),
                stderr=bytes(stderr_buf).decode("utf-8", errors="replace"),
                duration_seconds=duration,
                timed_out=True,
            )

        sleep_for = min(poll_delay, budget - elapsed)
        sleep_fn(max(0.0, sleep_for))


def _oracle_verdict(oracle: OracleOutcome | None) -> str:
    """Map optional oracle evidence to the canonical verification verdict."""
    if oracle is None:
        return "unverified"
    if oracle.exit_code == 0 and not oracle.timed_out and oracle.error is None:
        return "pass"
    return "fail"


def verification_record(oracle: OracleOutcome | None) -> dict[str, Any]:
    """Build only the verification evidence added to the P1-5a result."""
    verdict = _oracle_verdict(oracle)
    if oracle is None:
        return {
            "oracle_type": "none",
            "verdict": verdict,
            "oracle": None,
        }
    return {
        "oracle_type": "command",
        "verdict": verdict,
        "oracle": {
            "argv": list(oracle.argv),
            "exit_code": oracle.exit_code,
            "stdout": oracle.stdout,
            "stderr": oracle.stderr,
            "duration_seconds": oracle.duration_seconds,
            "timed_out": oracle.timed_out,
            "error": oracle.error,
        },
    }


def run_json_record(
    outcome: SelectionOutcome,
    dispatch: DispatchOutcome,
    oracle: OracleOutcome | None = None,
) -> dict[str, Any]:
    """The ``run --json`` result with selection, dispatch, and verification.

    This remains a P1-5a result rather than an attempt record: P1-5b1 adds
    only the optional oracle evidence and canonical verdict. Cost, attempt
    identifiers, provenance, validation, and ledger writes remain outside
    this packet.
    """
    return {
        "schema_version": 2,
        "record_kind": "router_run",
        "route": {
            "model": outcome.route.model,
            "effort": outcome.route.effort,
            "harness": outcome.route.harness,
            "channel": outcome.route.channel,
        },
        "selection": selection_record(outcome),
        "usage": dispatch.usage,
        "verification": verification_record(oracle),
        "wall_clock_ms": max(0, round(dispatch.duration_seconds * 1000.0)),
        "dispatch": {
            "argv": list(dispatch.argv),
            "exit_code": dispatch.exit_code,
            "timed_out": dispatch.timed_out,
            "duration_seconds": dispatch.duration_seconds,
            "stdout": dispatch.stdout,
            "stderr": dispatch.stderr,
        },
    }


def run_summary_lines(
    outcome: SelectionOutcome,
    dispatch: DispatchOutcome,
    oracle: OracleOutcome | None = None,
    *,
    record: Mapping[str, Any] | None = None,
) -> list[str]:
    """The compact plain-text ``run`` summary (one fact per line).

    Mirrors the v2 record when ``record`` is supplied: selected route and
    basis, the dispatch exit and wall clock, the authoritative usage basis
    with its reported counters (``-`` when unknown), cost, and oracle verdict.
    Never prints the packet prompt or the full captured stdout/stderr.
    """
    route = outcome.route
    model = route.model if route.effort is None else f"{route.model}/{route.effort}"
    lines = [
        f"route: {route.route_id} ({route.harness} {model} via {route.channel})",
        f"selection: {outcome.basis} — {outcome.reason}",
        f"dispatch: exit {dispatch.exit_code}"
        + (" (ceiling timeout)" if dispatch.timed_out else "")
        + f", wall {dispatch.duration_seconds:.1f}s",
    ]
    usage = dispatch.usage
    if usage.get("basis") == "unavailable":
        lines.append(f"usage: unavailable ({usage.get('unavailable_reason')})")
    else:
        counters = " ".join(
            f"{name}={usage.get(field)}"
            for field, name in (
                ("input_tokens", "in"),
                ("output_tokens", "out"),
                ("cached_input_tokens", "cached"),
                ("reasoning_tokens", "reasoning"),
                ("total_tokens", "total"),
            )
        )
        lines.append(f"usage: {usage.get('basis')} ({usage.get('source')}) {counters}")

    if record is not None:
        cost = record.get("cost", {})
        if cost.get("basis") == ["list", "marginal"]:
            lines.append(
                "cost: list ${:.8f}, marginal ${:.8f}".format(
                    cost["usd_list"], cost["usd_marginal"]
                )
            )
        else:
            lines.append("cost: unavailable")
        lines.append(f"attempt: {record.get('attempt_id', '-')}")

    verdict = _oracle_verdict(oracle)
    if oracle is None:
        lines.append("verification: unverified (no oracle)")
    elif oracle.error is not None:
        lines.append(f"verification: {verdict} ({oracle.error})")
    elif oracle.timed_out:
        lines.append("verification: fail (oracle ceiling timeout)")
    else:
        lines.append(f"verification: {verdict} (oracle exit {oracle.exit_code})")
    return lines
