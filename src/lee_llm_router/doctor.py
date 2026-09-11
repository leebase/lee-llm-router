"""Doctor CLI - config validation, environment diagnostics, and source export.

Commands:
    lee-llm-router doctor --config <path> [--role <role>] [--crews]
                          [--availability] [--catalog [--catalog-dir <dir>]]
    lee-llm-router crews list [--crews-file <path>] [--json]
    lee-llm-router crews page --out <path> [--crews-file <path>]
                          [--availability-file <path>] [--benchmark-file <path>]
                          [--events-file <path>]
    lee-llm-router resolve --crew <name> --role <stage> [--mode strict|flex|bind]
                           [--worker <id>] [--authorized-by <who>] [--reason <why>]
                           [--harness <tag>] [--json] [--crews-file <path>]
                           [--availability-file <path>] [--events-file <path>]
                           [--no-event]
    lee-llm-router dispatch --crew <name> --role <stage> [--mode strict|flex|bind]
                            [--worker <id>] [--authorized-by <who>] [--reason <why>]
                            [--harness <tag>] [--prompt-file <path> | --prompt <text>]
                            [--stall-minutes N] [--max-minutes N]
                            [--watch-dir <path> ...] [--crews-file <path>]
                            [--availability-file <path>] [--events-file <path>]
                            [--no-event] [--dry-run]
    lee-llm-router shims install (--dry-run | --apply) [--force] [--harness <tag>]
                                 [--project <path>]
    lee-llm-router shims diff [--harness <tag>] [--project <path>]
    lee-llm-router catalog explain --role ROLE --class CLASS
                                  [--at DATE] [--availability-file PATH]
                                  [--catalog-dir PATH]
                                  [--author-route ROUTE_ID] [--json]
    lee-llm-router run --role ROLE --class CLASS --packet FILE
                       [--route ROUTE_ID] [--supervisor-route ROUTE_ID]
                       [--author-route ROUTE_ID]
                       [--oracle CMD] [--workdir DIR]
                       [--parent ATTEMPT_ID --escalation-reason R]
                       [--timeout S] [--at DATE] [--availability-file PATH]
                       [--catalog-dir PATH] [--json]
    lee-llm-router template
    lee-llm-router trace --last N
    lee-llm-router evidence rollup
    lee-llm-router evidence import (--benchmark PATH [--csv PATH] |
                                    --agent-orch PATH)
    lee-llm-router export-source --dest <path> [--force]
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse
    from datetime import datetime
    from pathlib import Path

MANIFEST_NAME = ".lee_llm_router_export.json"


def check_config(
    config_path: str,
    role: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a config file and its environment.

    Returns:
        (errors, warnings) - errors are blocking; warnings are informational.
    """
    import os
    import shutil
    from pathlib import Path

    from lee_llm_router.config import ConfigError, load_config
    from lee_llm_router.providers.base import LLMRouterError
    from lee_llm_router.providers.registry import get as get_provider

    errors: list[str] = []
    warnings: list[str] = []

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        return [f"Config invalid: {exc}"], []
    except Exception as exc:
        return [f"Unexpected error loading config: {exc}"], []

    for pname, pcfg in config.providers.items():
        try:
            provider = get_provider(pcfg.type)()
            provider.validate_config(pcfg.raw)
        except KeyError:
            warnings.append(
                f"Provider {pname!r}: unknown type {pcfg.type!r} - cannot validate"
            )
            continue
        except LLMRouterError as exc:
            errors.append(f"Provider {pname!r}: {exc}")
            continue

        if pcfg.type in ("openrouter_http", "openai_http"):
            api_key_env = pcfg.raw.get("api_key_env")
            if api_key_env and not os.environ.get(api_key_env):
                errors.append(f"Provider {pname!r}: env var {api_key_env!r} is not set")
            if not pcfg.raw.get("base_url"):
                warnings.append(
                    f"Provider {pname!r}: 'base_url' not set - will use default"
                )

        elif pcfg.type in (
            "codex_cli",
            "gemini_cli",
            "gemini",
            "claude_code_cli",
            "claude_code",
            "claude",
        ):
            if pcfg.type.startswith("gemini"):
                default_command = "gemini"
            elif pcfg.type.startswith("claude"):
                default_command = "claude"
            else:
                default_command = "codex"
            command = pcfg.raw.get("command", default_command)
            if not shutil.which(command):
                errors.append(
                    f"Provider {pname!r}: binary {command!r} not found in PATH"
                )

        elif pcfg.type in (
            "openai_codex_subscription_http",
            "openai_codex_http",
            "chatgpt_subscription_http",
        ):
            access_token_env = pcfg.raw.get("access_token_env")
            if access_token_env:
                if not os.environ.get(access_token_env):
                    errors.append(
                        f"Provider {pname!r}: env var {access_token_env!r} is not set"
                    )
            else:
                codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
                auth_path = codex_home / "auth.json"
                if not auth_path.exists():
                    warnings.append(
                        "Provider "
                        f"{pname!r}: no access_token_env set and no auth file found at "
                        f"{auth_path}"
                    )

        elif pcfg.type == "mock":
            pass

    target_role = role or config.default_role
    if target_role not in config.roles:
        errors.append(
            f"Role {target_role!r} not found in config. "
            f"Known roles: {', '.join(sorted(config.roles))}"
        )
        return errors, warnings

    try:
        role_cfg = config.roles[target_role]
        provider_cfg = config.providers[role_cfg.provider]
        get_provider(provider_cfg.type)
    except KeyError as exc:
        errors.append(f"Role {target_role!r} references an unknown provider: {exc}")

    return errors, warnings


def get_template() -> str:
    """Return the contents of the bundled llm.example.yaml."""
    from pathlib import Path

    template_path = Path(__file__).parent / "templates" / "llm.example.yaml"
    return template_path.read_text(encoding="utf-8")


def export_source(dest: str | Path, force: bool = False) -> dict[str, str | None]:
    """Export the package tree as a vendorable source snapshot."""
    import json
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    from lee_llm_router import __version__

    package_root = Path(__file__).resolve().parent
    repo_root = package_root.parent.parent
    destination = Path(dest).expanduser().resolve()

    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Destination exists and is not a directory: {destination}")

    if destination.exists() and any(destination.iterdir()):
        if not force:
            raise FileExistsError(
                f"Destination is not empty: {destination}. "
                "Re-run with --force to overwrite."
            )
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        package_root,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    manifest = {
        "package": "lee_llm_router",
        "version": __version__,
        "source_repo": str(repo_root),
        "source_subdir": "src/lee_llm_router",
        "source_commit": _get_git_commit(repo_root),
        "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    manifest_path = destination / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "destination": str(destination),
        "manifest": str(manifest_path),
        "version": __version__,
        "source_commit": manifest["source_commit"],
    }


def _get_git_commit(repo_root: Path) -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def check_availability(
    snapshot_file: str | Path | None = None,
    now: datetime | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Inspect the availability snapshot the refresh script writes.

    The staleness, clock-skew, and malformed-input rules all belong to
    :func:`lee_llm_router.availability.load_availability`; this check only
    renders that reader's verdict. Absence is a valid state: before the hourly
    refresh has ever run there is no snapshot, and the resolver degrades to
    ``unknown`` rather than failing, so a missing file is a warning. A snapshot
    that is merely stale — too old, or stamped beyond the tolerated future skew
    — is also a warning. Only a file that exists but cannot be used at all is an
    error.

    Args:
        snapshot_file: Explicit snapshot path, or None to resolve the default.
        now: Reference time for the age calculation. A naive value is read as
            UTC by the reader, never as host-local time.

    Returns:
        ``(errors, warnings, details)`` where ``details`` carries the resolved
        ``path``, the snapshot's ``written_at``/``observed_at`` as ISO strings,
        its ``age_minutes`` (or None), the ``bucket_count``, and a
        ``channels`` map of channel name to health.
    """
    from lee_llm_router.availability import (
        FUTURE_TIMESTAMP_REASON,
        load_availability,
        resolve_availability_path,
    )

    path = resolve_availability_path(snapshot_file)
    details: dict[str, Any] = {
        "path": str(path),
        "written_at": None,
        "observed_at": None,
        "age_minutes": None,
        "bucket_count": 0,
        "channels": {},
    }

    if not path.is_file():
        return (
            [],
            [f"availability snapshot missing: {path} (run refresh_availability.sh)"],
            details,
        )

    snapshot = load_availability(path, now=now)
    details["written_at"] = (
        snapshot.written_at.isoformat() if snapshot.written_at else None
    )
    details["observed_at"] = (
        snapshot.observed_at.isoformat() if snapshot.observed_at else None
    )
    details["age_minutes"] = snapshot.age_minutes
    details["bucket_count"] = _count_buckets(snapshot)
    details["channels"] = {
        name: headroom.health.value for name, headroom in snapshot.channels.items()
    }

    if snapshot.stale and snapshot.stale_reason == FUTURE_TIMESTAMP_REASON:
        return [], [_stale_warning(path, snapshot)], details
    if snapshot.problem is not None:
        return (
            [f"availability snapshot unusable: {path}: {snapshot.problem}"],
            [],
            details,
        )
    if snapshot.stale:
        return [], [_stale_warning(path, snapshot)], details
    return [], [], details


def _count_buckets(snapshot: Any) -> int:
    """Count the distinct source entries behind a snapshot's channels.

    One raw ``ai-subs`` entry can feed more than one channel, so the per-channel
    buckets are de-duplicated by their provider and bucket name.

    Args:
        snapshot: The :class:`~lee_llm_router.availability.AvailabilitySnapshot`.

    Returns:
        The number of distinct ``(provider, name)`` pairs.
    """
    seen = {
        (bucket.provider, bucket.name)
        for headroom in snapshot.channels.values()
        for bucket in headroom.buckets
    }
    return len(seen)


def _stale_warning(path: Path, snapshot: Any) -> str:
    """Render the one-line staleness warning for a snapshot.

    Args:
        path: The snapshot path, for the message.
        snapshot: The :class:`~lee_llm_router.availability.AvailabilitySnapshot`.

    Returns:
        A warning naming the reader's ``stale_reason`` and the age it measured.
    """
    reason = snapshot.stale_reason or "snapshot is stale"
    if snapshot.age_minutes is None:
        return f"availability snapshot stale ({reason}): {path}, age unknown"
    return (
        f"availability snapshot stale ({reason}): {path}, "
        f"age {snapshot.age_minutes:.0f} min"
    )


GOVERNED_HARNESSES: tuple[str, ...] = (
    "codex_cli",
    "claude_code",
    "claude_code_cli",
    "omp_cli",
    "pi_cli",
    "opencode_cli",
    "antigravity_cli",
)
"""Harness identifiers a crew's governed route may name."""


def _first_sentence(text: str) -> str:
    """Return the first sentence of a description, collapsed to one line."""
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    head, sep, _ = collapsed.partition(". ")
    return head + ("." if sep else "")


def check_crews(
    crews_file: str | None = None,
) -> tuple[list[str], list[str], int, int, int]:
    """Resolve every worker declared in the crews file, not only stage refs.

    Every entry of the top-level ``workers`` map is resolved, so a malformed
    worker is reported even when no crew stage references it. A crew stage whose
    role class is coding and names a worker that resolves to a role-scoped model
    (or an unmapped stage name) is reported as a warning rather than an error: the
    crews file is Auto-Orch's, not ours.

    Args:
        crews_file: Explicit crews file path, or None to use the default.

    Returns:
        ``(errors, warnings, crew_count, resolved_worker_count,
        total_worker_count)``.
    """
    from lee_llm_router.crews import (
        ROLE_SCOPED_CITATION,
        CrewsConfigError,
        is_role_scoped,
        load_crews,
        resolve_worker,
        role_class,
    )

    try:
        crews_config = load_crews(crews_file)
    except CrewsConfigError as exc:
        return [f"Crews invalid: {exc}"], [], 0, 0, 0

    errors: list[str] = []
    warnings: list[str] = []
    resolved: set[str] = set()
    resolved_workers: dict[str, Any] = {}

    for worker_id, worker in crews_config.workers.items():
        try:
            resolved_worker = resolve_worker(worker)
        except CrewsConfigError as exc:
            errors.append(f"Worker {worker_id!r}: {exc}")
            continue
        resolved.add(worker_id)
        resolved_workers[worker_id] = resolved_worker

    for crew in crews_config.crews.values():
        for stage in crew.stages.values():
            try:
                stage_class = role_class(stage.name)
            except CrewsConfigError:
                warnings.append(
                    f"stage {stage.name!r} has no role class ({ROLE_SCOPED_CITATION})"
                )
                stage_class = None

            for worker_id in stage.workers:
                worker = crews_config.workers.get(worker_id)
                if worker is None:
                    errors.append(
                        f"Crew {crew.name!r} stage {stage.name!r}: unknown worker "
                        f"{worker_id!r}"
                    )
                    continue
                if worker_id not in resolved:
                    errors.append(
                        f"Crew {crew.name!r} stage {stage.name!r}: worker "
                        f"{worker_id!r} could not be resolved"
                    )
                    continue

                if stage_class == "coding":
                    resolved_worker = resolved_workers[worker_id]
                    if is_role_scoped(resolved_worker.model):
                        warnings.append(
                            f"Crew {crew.name!r} stage {stage.name!r} uses role-scoped "
                            f"model {resolved_worker.model!r} in a coding role; the "
                            f"resolver will never choose it there "
                            f"({ROLE_SCOPED_CITATION})"
                        )

        for route in crew.governed.values():
            if route.harness not in GOVERNED_HARNESSES:
                errors.append(
                    f"Crew {crew.name!r} governed role {route.role!r}: unknown "
                    f"harness {route.harness!r} (known: "
                    f"{', '.join(GOVERNED_HARNESSES)})"
                )

    return (
        errors,
        warnings,
        len(crews_config.crews),
        len(resolved),
        len(crews_config.workers),
    )


def crews_summary(crews_file: str | None = None) -> list[dict[str, Any]]:
    """Build a JSON-serialisable summary of every crew.

    Args:
        crews_file: Explicit crews file path, or None to use the default.

    Returns:
        One entry per crew, with resolved stage workers and governed routes.
    """
    from lee_llm_router.crews import STAGE_NAMES, load_crews, resolve_worker

    crews_config = load_crews(crews_file)
    summary: list[dict[str, Any]] = []
    for crew in crews_config.crews.values():
        stages: dict[str, Any] = {}
        for stage_name in STAGE_NAMES:
            stage = crew.stages.get(stage_name)
            if stage is None:
                continue
            worker = crews_config.workers[stage.primary]
            resolved = resolve_worker(worker)
            stages[stage_name] = {
                "worker_id": resolved.worker_id,
                "provider": resolved.provider,
                "model": resolved.model,
                "effort": resolved.effort,
                "eligible": list(stage.workers),
            }
        summary.append(
            {
                "name": crew.name,
                "description": _first_sentence(crew.description),
                "stages": stages,
                "governed": {
                    role: {
                        "harness": route.harness,
                        "model": route.model,
                        "effort": route.effort,
                    }
                    for role, route in crew.governed.items()
                },
            }
        )
    return summary


def _format_crew(entry: dict[str, Any]) -> list[str]:
    """Render one crew summary entry as plain-text lines."""
    lines = [f"{entry['name']} — {entry['description']}".rstrip(" —")]
    for stage_name, stage in entry["stages"].items():
        model = stage["model"]
        if stage["effort"]:
            model = f"{model}/{stage['effort']}"
        lines.append(
            f"  {stage_name}: {stage['worker_id']} ({stage['provider']} {model})"
        )
    governed = entry["governed"]
    if governed:
        parts = []
        for role, route in governed.items():
            target = route["harness"]
            if route["model"]:
                target = f"{target}/{route['model']}"
            if route["effort"]:
                target = f"{target}/{route['effort']}"
            parts.append(f"{role}={target}")
        lines.append("  governed: " + ", ".join(parts))
    return lines


def _run_crews_list(args: argparse.Namespace) -> int:
    import json

    from lee_llm_router.crews import CrewsConfigError

    try:
        summary = crews_summary(getattr(args, "crews_file", None))
    except CrewsConfigError as exc:
        print(f"Crews invalid: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    for entry in summary:
        for line in _format_crew(entry):
            print(line)
    return 0


class _CrewPageInputError(ValueError):
    """Raised when a crew-page input cannot be used safely."""


def _discover_benchmark_file() -> Path | None:
    """Return the lexically latest optional staffing-evidence sidecar."""
    from pathlib import Path

    exports = Path.home() / "projects" / "ai-workforce-benchmark" / "exports"
    candidates = sorted(
        (path for path in exports.glob("staffing-evidence-*.json") if path.is_file()),
        key=lambda path: path.name,
    )
    return candidates[-1] if candidates else None


def _read_page_events(path: str | Path) -> None:
    """Validate a caller-supplied event ledger without using the default one."""
    from lee_llm_router.events import read_events

    try:
        records = read_events(path)
    except (OSError, UnicodeError) as exc:
        raise _CrewPageInputError(f"event file cannot be read: {exc}") from exc
    if any("_malformed" in record for record in records):
        raise _CrewPageInputError(f"event file is malformed JSONL: {path}")


def _run_crews_page(args: argparse.Namespace) -> int:
    """Generate the static crew page from explicitly selected input paths."""
    import stat
    from pathlib import Path

    from lee_llm_router.availability import (
        load_availability,
        resolve_availability_path,
    )
    from lee_llm_router.crew_page import (
        BenchmarkEvidenceError,
        load_benchmark_evidence,
        select_proposals,
        write_crew_page,
    )
    from lee_llm_router.crews import CrewsConfigError, load_crews

    try:
        config = load_crews(getattr(args, "crews_file", None))
        availability_path = resolve_availability_path(
            getattr(args, "availability_file", None)
        )
        try:
            availability_stat = availability_path.stat()
        except FileNotFoundError:
            if availability_path.is_symlink():
                raise _CrewPageInputError(
                    f"availability snapshot is not a regular file: {availability_path}"
                )
            availability_present = False
        except OSError as exc:
            raise _CrewPageInputError(
                f"availability snapshot cannot be inspected: {availability_path}: {exc}"
            ) from exc
        else:
            availability_present = True
            if not stat.S_ISREG(availability_stat.st_mode):
                raise _CrewPageInputError(
                    f"availability snapshot is not a regular file: {availability_path}"
                )

        availability = load_availability(availability_path)
        if availability.problem is not None and availability_present:
            raise _CrewPageInputError(
                f"availability snapshot unusable: {availability.path}: "
                f"{availability.problem}"
            )

        benchmark_path = getattr(args, "benchmark_file", None)
        if benchmark_path is None:
            benchmark_path = _discover_benchmark_file()
        evidence = load_benchmark_evidence(benchmark_path)

        events_path = getattr(args, "events_file", None)
        if events_path is not None:
            _read_page_events(events_path)

        proposals = select_proposals(config, evidence)
    except (
        BenchmarkEvidenceError,
        CrewsConfigError,
        _CrewPageInputError,
        OSError,
        UnicodeError,
    ) as exc:
        message = " ".join(str(exc).split())
        print(f"crews page: configuration error: {message}", file=sys.stderr)
        return 3

    try:
        written = write_crew_page(
            Path(args.out).expanduser(), config, availability, evidence, proposals
        )
    except (OSError, UnicodeError, ValueError) as exc:
        message = " ".join(str(exc).split())
        print(f"crews page: could not write output: {message}", file=sys.stderr)
        return 3

    print(written)
    return 0


RESOLVE_MODES: tuple[str, ...] = ("strict", "flex", "bind")
"""The ``--mode`` values ``resolve`` accepts (mirrors ``resolver.MODES``)."""


def _resolve_field_lines(resolution: Any) -> list[str]:
    """Render a successful resolution as the ``resolve`` text-output fields.

    Args:
        resolution: The :class:`~lee_llm_router.resolver.Resolution`.

    Returns:
        One line per field, in the command's documented order, with an
        ``authorized_by`` line appended when the resolution is a bind.
    """
    import shlex

    from lee_llm_router.resolver import DEFAULT_EFFORT_TOKEN

    dispatch = shlex.join(resolution.dispatch_command)
    if resolution.prompt_delivery == "stdin":
        dispatch += " [prompt on stdin]"

    if resolution.headroom_remaining_fraction is None:
        headroom = resolution.headroom
    else:
        pct = round(resolution.headroom_remaining_fraction * 100)
        headroom = f"{resolution.headroom} ({pct}% remaining)"

    lines = [
        f"worker: {resolution.worker_id}",
        f"provider: {resolution.provider}",
        f"model: {resolution.model}",
        f"effort: {resolution.effort or DEFAULT_EFFORT_TOKEN}",
        f"channel: {resolution.channel}",
        f"headroom: {headroom}",
        f"route_id: {resolution.route_id}",
        f"dispatch: {dispatch}",
        f"reason: {resolution.reason}",
    ]
    if resolution.mode == "bind":
        lines.append(f"authorized_by: {resolution.authorized_by}")
    return lines


def _print_resolve_refusal(
    error: Any,
    *,
    as_json: bool,
    prefix: str = "resolve",
) -> int:
    """Print a ``resolve`` refusal and return its exit code.

    Args:
        error: The :class:`~lee_llm_router.resolver.ResolutionError`.
        as_json: Whether ``--json`` was requested.
        prefix: Subcommand name for stderr message (default: ``"resolve"``).

    Returns:
        ``error.exit_code``.
    """
    print(f"{prefix}: {error.message}", file=sys.stderr)
    if error.remedy:
        print(f"remedy: {error.remedy}", file=sys.stderr)
    if as_json:
        import json

        print(json.dumps(error.to_dict(), indent=2))
    return error.exit_code


def _perform_resolve(
    args: argparse.Namespace,
    *,
    as_json: bool = False,
    prefix: str = "resolve",
) -> tuple[Any | None, int]:
    """Resolve which worker runs a crew's stage.

    Args:
        args: Parsed command arguments.
        as_json: Whether refusals should be emitted as JSON.
        prefix: Subcommand prefix for stderr on refusal.

    Returns:
        ``(resolution, exit_code)`` where ``exit_code`` is 0 on success, or 2/3
        on refusal after printing to stderr.
    """
    from lee_llm_router.availability import load_availability
    from lee_llm_router.crews import CrewsConfigError, load_crews
    from lee_llm_router.resolver import ResolutionError, resolve

    try:
        crews_config = load_crews(getattr(args, "crews_file", None))
    except CrewsConfigError as exc:
        error = ResolutionError(str(exc), exit_code=3, kind="config")
        return None, _print_resolve_refusal(error, as_json=as_json, prefix=prefix)

    snapshot = load_availability(getattr(args, "availability_file", None))

    try:
        resolution = resolve(
            crews_config,
            snapshot,
            crew=args.crew,
            role=args.role,
            mode=args.mode,
            worker=args.worker,
            authorized_by=args.authorized_by,
            reason=args.reason,
        )
    except ResolutionError as exc:
        return None, _print_resolve_refusal(exc, as_json=as_json, prefix=prefix)

    return resolution, 0


def _record_resolution_event(
    resolution: Any,
    args: argparse.Namespace,
) -> tuple[str | None, str | None]:
    """Append one event to the ledger unless ``--no-event`` is given.

    Args:
        resolution: The :class:`~lee_llm_router.resolver.Resolution`.
        args: Parsed command arguments.

    Returns:
        ``(event_path, event_error)`` where ``event_path`` is the path written
        to, and ``event_error`` is the error message string on write failure.
    """
    if args.no_event:
        return None, None

    from lee_llm_router import events as events_mod

    event = events_mod.build_event(
        harness=args.harness,
        crew=resolution.crew,
        role=resolution.role,
        mode=resolution.mode,
        worker_id=resolution.worker_id,
        provider=resolution.provider,
        model=resolution.model,
        effort=resolution.effort,
        channel=resolution.channel,
        headroom=resolution.headroom,
        reason=resolution.reason,
        authorized_by=resolution.authorized_by,
        route_id=resolution.route_id,
        snapshot_observed_at=resolution.snapshot_observed_at,
        snapshot_stale=resolution.snapshot_stale,
    )
    try:
        written = events_mod.append_event(event, getattr(args, "events_file", None))
        return str(written), None
    except (events_mod.EventError, OSError) as exc:
        return None, str(exc)


RESOLVE_USAGE_MESSAGE: str = (
    "specify either 'resolve CREW ROLE [options]' or "
    "'resolve --crew CREW --role ROLE [options]'"
)


def _run_resolve(args: argparse.Namespace) -> int:
    """Resolve which worker runs a crew's stage and print/record the result.

    Loads the crews file and the availability snapshot, calls
    :func:`lee_llm_router.resolver.resolve`, prints the resolution (text or
    ``--json``), and appends one event to the ledger for every successful
    resolution unless ``--no-event`` is given. A failure to write the event
    still prints the resolution but turns the exit code into ``3``: an
    unrecorded resolution is not a completed one.
    """
    positionals = getattr(args, "positionals", None) or []
    has_positionals = bool(positionals)
    has_crew = getattr(args, "crew", None) is not None
    has_role = getattr(args, "role", None) is not None

    if has_positionals and (has_crew or has_role):
        from lee_llm_router.resolver import ResolutionError

        error = ResolutionError(
            RESOLVE_USAGE_MESSAGE,
            exit_code=3,
            kind="usage",
        )
        return _print_resolve_refusal(error, as_json=getattr(args, "json", False))

    if has_positionals:
        if len(positionals) != 2:
            from lee_llm_router.resolver import ResolutionError

            error = ResolutionError(
                RESOLVE_USAGE_MESSAGE,
                exit_code=3,
                kind="usage",
            )
            return _print_resolve_refusal(error, as_json=getattr(args, "json", False))
        args.crew = positionals[0]
        args.role = positionals[1]
    elif not (has_crew and has_role):
        from lee_llm_router.resolver import ResolutionError

        error = ResolutionError(
            RESOLVE_USAGE_MESSAGE,
            exit_code=3,
            kind="usage",
        )
        return _print_resolve_refusal(error, as_json=getattr(args, "json", False))

    resolution, exit_code = _perform_resolve(args, as_json=args.json)
    if resolution is None:
        return exit_code

    event_path, event_error = _record_resolution_event(resolution, args)

    if args.json:
        import json

        payload = resolution.to_dict()
        payload["event_path"] = event_path
        print(json.dumps(payload, indent=2))
    else:
        for line in _resolve_field_lines(resolution):
            print(line)
        if args.no_event:
            print("event: not recorded (--no-event)")
        elif event_path is not None:
            print(f"event: {event_path}")

    if event_error is not None:
        print(f"resolve: could not record event: {event_error}", file=sys.stderr)
        return 3

    return 0


def _run_dispatch(args: argparse.Namespace) -> int:
    """Resolve, run the harness, supervise with the stall watchdog."""
    resolution, exit_code = _perform_resolve(args)
    if resolution is None:
        return exit_code

    if args.dry_run:
        event_path, event_error = _record_resolution_event(resolution, args)
        for line in _resolve_field_lines(resolution):
            print(line)
        if args.no_event:
            print("event: not recorded (--no-event)")
        elif event_path is not None:
            print(f"event: {event_path}")
        if event_error is not None:
            print(f"dispatch: could not record event: {event_error}", file=sys.stderr)
            return 3
        return 0

    if args.prompt is not None and args.prompt_file is not None:
        print(
            "dispatch: cannot specify both --prompt and --prompt-file",
            file=sys.stderr,
        )
        return 3

    if args.prompt is not None:
        prompt = args.prompt
    elif args.prompt_file is not None:
        from pathlib import Path

        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"dispatch: could not read prompt file: {exc}", file=sys.stderr)
            return 3
    else:
        if sys.stdin.isatty():
            print(
                "dispatch: prompt required via --prompt, --prompt-file, "
                "or non-TTY stdin",
                file=sys.stderr,
            )
            return 3
        prompt = sys.stdin.read()

    if not prompt.strip():
        print("dispatch: prompt is empty", file=sys.stderr)
        return 3

    event_path, event_error = _record_resolution_event(resolution, args)
    if event_error is not None:
        print(f"dispatch: could not record event: {event_error}", file=sys.stderr)
        return 3

    from lee_llm_router.dispatch import run_dispatch

    return run_dispatch(
        resolution=resolution,
        prompt=prompt,
        stall_minutes=args.stall_minutes,
        max_minutes=args.max_minutes,
        watch_dirs=args.watch_dir or (),
    )


def check_catalog(
    catalog_dir: str | Path,
    schema_dir: str | Path | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Validate and load the six staffing catalog documents in a directory.

    All shape validation, schema handling, and typed construction belong to
    :func:`lee_llm_router.staffing.catalog.load_staffing_catalog`; this check
    only renders that reader's verdict. The returned errors carry the loader's
    stable message, which always names the offending document and, when known,
    the JSON path of the field at fault.

    Args:
        catalog_dir: Directory holding the six YAML documents.
        schema_dir: Explicit schema directory, or None for the bundled default.

    Returns:
        ``(errors, warnings, details)`` where ``details`` carries the resolved
        ``path`` and, on success, per-document element counts under ``counts``.
    """
    from pathlib import Path

    from lee_llm_router.staffing.catalog import (
        StaffingCatalogError,
        load_staffing_catalog,
    )

    path = Path(catalog_dir)
    details: dict[str, Any] = {"path": str(path), "counts": {}}

    try:
        catalog = load_staffing_catalog(path, schema_dir=schema_dir)
    except StaffingCatalogError as exc:
        return [f"catalog invalid: {exc}"], [], details

    details["counts"] = {
        "routes": len(catalog.routes.routes),
        "channels": len(catalog.channels.channels),
        "terms": len(catalog.terms.terms),
        "crews": len(catalog.crews.crews),
    }
    return [], [], details


def _default_catalog_dir() -> Path:
    """Return the repository's bundled ``config/staffing`` catalog directory."""
    from pathlib import Path

    return Path(__file__).resolve().parents[2] / "config" / "staffing"


def _run_doctor(args: argparse.Namespace) -> int:
    config_path = args.config
    role = getattr(args, "role", None)

    if getattr(args, "catalog", False):
        catalog_dir = getattr(args, "catalog_dir", None)
        if catalog_dir is None:
            catalog_dir = _default_catalog_dir()
        catalog_errors, catalog_warnings, catalog_details = check_catalog(catalog_dir)
        for warning in catalog_warnings:
            print(f"  !  {warning}")
        for error in catalog_errors:
            print(f"  x  {error}", file=sys.stderr)
        if catalog_errors:
            print(
                f"\nStatus: {len(catalog_errors)} catalog error(s) found",
                file=sys.stderr,
            )
            return 3
        counts = catalog_details["counts"]
        print(
            f"OK catalog: {catalog_details['path']} "
            f"(routes {counts['routes']}, channels {counts['channels']}, "
            f"terms {counts['terms']}, crews {counts['crews']})"
        )
        if config_path is None and not any(
            getattr(args, flag, False) for flag in ("crews", "availability")
        ):
            return 0
        print()

    if getattr(args, "crews", False):
        (
            crew_errors,
            crew_warnings,
            crew_count,
            worker_count,
            total_workers,
        ) = check_crews(getattr(args, "crews_file", None))
        for warning in crew_warnings:
            print(f"  !  {warning}")
        for error in crew_errors:
            print(f"  x  {error}", file=sys.stderr)
        if crew_errors:
            print(f"\nStatus: {len(crew_errors)} crews error(s) found", file=sys.stderr)
            return 1
        print(
            f"OK crews: {crew_count} crews, "
            f"{worker_count}/{total_workers} workers resolved, "
            f"{len(crew_warnings)} role-scoped warning(s)"
        )
        if config_path is None and not getattr(args, "availability", False):
            return 0
        print()

    if getattr(args, "availability", False):
        avail_errors, avail_warnings, details = check_availability(
            getattr(args, "availability_file", None)
        )
        for warning in avail_warnings:
            print(f"  !  {warning}")
        for error in avail_errors:
            print(f"  x  {error}", file=sys.stderr)
        if avail_errors:
            print(
                f"\nStatus: {len(avail_errors)} availability error(s) found",
                file=sys.stderr,
            )
            return 1
        if not avail_warnings:
            age = details["age_minutes"] or 0.0
            print(
                f"OK availability: {details['path']}, age {age:.0f} min, "
                f"{details['bucket_count']} buckets"
            )
            for channel, health in details["channels"].items():
                print(f"  {channel}: {health}")
        if config_path is None:
            return 0
        print()

    if config_path is None:
        print(
            "doctor requires --config (or --crews / --availability / --catalog)",
            file=sys.stderr,
        )
        return 1

    print("Lee LLM Router Doctor")
    print(f"Config: {config_path}")
    print()

    errors, warnings = check_config(config_path, role)

    for warning in warnings:
        print(f"  !  {warning}")
    for error in errors:
        print(f"  x  {error}", file=sys.stderr)

    if not errors and not warnings:
        print("  OK  All checks passed")
    elif not errors:
        print(f"\n  OK  {len(warnings)} warning(s) - no blocking errors")

    if errors:
        print(f"\nStatus: {len(errors)} error(s) found", file=sys.stderr)
        return 1

    return 0


def _run_template(_args: argparse.Namespace) -> int:
    print(get_template(), end="")
    return 0


def _run_trace(args: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    trace_dir = Path(args.dir) if args.dir else Path(".lee-llm-router") / "traces"
    n = args.last

    if not trace_dir.exists():
        print(f"No trace directory found: {trace_dir}", file=sys.stderr)
        return 1

    trace_files = sorted(
        trace_dir.rglob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not trace_files:
        print("No traces found.")
        return 0

    for trace_file in trace_files[:n]:
        try:
            data = json.loads(trace_file.read_text(encoding="utf-8"))
            status = "ERROR" if data.get("error") else "OK"
            elapsed = f"{data.get('elapsed_ms') or 0:.0f}ms"
            attempt = int(data.get("attempt", 0) or 0)
            print(
                f"{str(data.get('request_id', '?'))[:8]}  "
                f"{str(data.get('started_at', '?'))[:19]}  "
                f"{str(data.get('role', '?')):<12}  "
                f"{str(data.get('provider', '?')):<20}  "
                f"a{attempt:<5}  "
                f"{str(data.get('model', '?')):<20}  "
                f"{status:<6}  {elapsed}"
            )
        except Exception as exc:
            print(f"  [could not parse {trace_file}: {exc}]", file=sys.stderr)

    return 0


def _run_evidence_rollup(_args: argparse.Namespace) -> int:
    """Read the configured validated attempt ledger and print its rollup."""
    from lee_llm_router.staffing.ledger import AttemptLedgerError
    from lee_llm_router.staffing.rollup import render_rollup, rollup_ledger

    try:
        summary = rollup_ledger()
    except (AttemptLedgerError, OSError, UnicodeError) as exc:
        message = " ".join(str(exc).split())
        print(f"evidence rollup: {message}", file=sys.stderr)
        return 3

    print(render_rollup(summary))
    return 0


def _run_evidence_import(args: argparse.Namespace) -> int:
    """Import benchmark or recent Agent-Orch evidence."""
    from lee_llm_router.staffing.import_evidence import (
        EvidenceImportError,
        import_agent_orch_evidence,
        import_benchmark_evidence,
    )
    from lee_llm_router.staffing.ledger import AttemptLedgerError, ShortWriteError

    try:
        if args.agent_orch is not None:
            if args.csv is not None:
                raise EvidenceImportError("--csv requires --benchmark")
            summary = import_agent_orch_evidence(args.agent_orch)
        else:
            summary = import_benchmark_evidence(args.benchmark, csv_path=args.csv)
    except (EvidenceImportError, AttemptLedgerError, ShortWriteError, OSError) as exc:
        message = " ".join(str(exc).split())
        print(f"evidence import: {message}", file=sys.stderr)
        return 3
    for issue in summary.issues:
        identity = f" run_id={issue.run_id}" if issue.run_id else ""
        print(
            f"evidence import: skipped row {issue.row_number}{identity}: "
            f"{issue.reason}",
            file=sys.stderr,
        )
    print(f"imported={summary.imported} skipped={summary.skipped}")
    return 0


def _run_export_source(args: argparse.Namespace) -> int:
    try:
        result = export_source(args.dest, force=args.force)
    except (FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Lee LLM Router Source Export")
    print(f"Destination: {result['destination']}")
    print(f"Manifest: {result['manifest']}")
    print(f"Version: {result['version']}")
    print(f"Source commit: {result['source_commit'] or 'unknown'}")
    return 0


def _run_shims_install(args: argparse.Namespace) -> int:
    dry_run = getattr(args, "dry_run", False)
    apply = getattr(args, "apply", False)
    if (dry_run and apply) or (not dry_run and not apply):
        print(
            "shims install: exactly one of --dry-run or --apply is required",
            file=sys.stderr,
        )
        return 3

    from lee_llm_router import shims

    try:
        return shims.install_shims(
            dry_run=dry_run,
            apply=apply,
            force=getattr(args, "force", False),
            harnesses=getattr(args, "harness", None),
            project=getattr(args, "project", None),
        )
    except shims.ShimUsageError as exc:
        print(f"shims install: {exc}", file=sys.stderr)
        return 3


def _run_shims_diff(args: argparse.Namespace) -> int:
    from lee_llm_router import shims

    try:
        return shims.diff_shims(
            harnesses=getattr(args, "harness", None),
            project=getattr(args, "project", None),
        )
    except shims.ShimUsageError as exc:
        print(f"shims diff: {exc}", file=sys.stderr)
        return 3


def _run_shims_no_subcommand(_args: argparse.Namespace) -> int:
    print("shims: subcommand required (install, diff)", file=sys.stderr)
    return 3


# ---------------------------------------------------------------------------
# catalog explain (P0-5b): per-route eligibility report over the catalog
# ---------------------------------------------------------------------------

FLOORS_DISCLOSURE: str = "floors recorded, not enforced"
"""Chief round 15 (D86/D87) fact printed exactly once per explain run.

The committed catalog's ``role_floors`` records are recorded data only in
Phase 0: eligibility applies no floor check and excludes no route by one.
"""

INDEPENDENCE_NOT_EVALUATED: str = "independence not evaluated (no --author-route)"
"""Chief round 15 (packet D) absent-input disclosure, printed exactly once.

Independence is enforced only when explain receives ``--author-route``
(Chief round 15 ruling 2); when the input is absent this exact disclosure
replaces any exclusion — no route is excluded for independence without it.
"""

_INDEPENDENCE_APPLICABLE_ROLES: frozenset[str] = frozenset({"review", "judge"})
"""Roles for which author-route independence applies (review/judge only)."""


def _independence_record(
    role: str,
    author_route_id: str | None,
    catalog: Any,
) -> dict[str, Any]:
    """Build the deterministic top-level ``independence`` explain record.

    Absent input: ``evaluated`` false plus the exact absent-input
    disclosure. Supplied input for review/judge: ``evaluated`` true plus
    the author route, its derived family, and the family source. Supplied
    input for any other role: not applicable — ``evaluated`` stays false
    and the record says so rather than pretending the check ran. Raises
    :class:`StaffingEligibilityError` on an unknown author route id (the
    eligibility evaluation already fails closed on the same input).
    """
    from lee_llm_router.staffing.eligibility import (
        resolve_author_route,
        resolve_route_family,
    )

    applicable = role in _INDEPENDENCE_APPLICABLE_ROLES
    if author_route_id is None:
        return {
            "evaluated": False,
            "applicable": applicable,
            "disclosure": INDEPENDENCE_NOT_EVALUATED,
        }
    author_route = resolve_author_route(catalog, author_route_id)
    family, family_source = resolve_route_family(author_route)
    record: dict[str, Any] = {
        "evaluated": applicable,
        "applicable": applicable,
        "author_route": author_route_id,
        "author_family": family,
        "family_source": family_source,
    }
    if not applicable:
        record["disclosure"] = f"independence not applicable for role {role!r}"
    return record


def _independence_text_line(record: dict[str, Any]) -> str:
    """Render the one independence disclosure line for text output."""
    if record["evaluated"]:
        return (
            f"independence: author route {record['author_route']}, "
            f"family {record['author_family']} "
            f"(from {record['family_source']})"
        )
    if record.get("author_route") is not None:
        # Not-applicable-with-input case: record the supplied author route,
        # its derived family, and the source once, alongside the disclosure.
        return (
            f"{record['disclosure']} (author route {record['author_route']}, "
            f"family {record['author_family']} "
            f"(from {record['family_source']}))"
        )
    return record["disclosure"]


def _parse_class_string(
    class_string: str,
) -> tuple[str, str, tuple[str, ...], str, str]:
    """Parse the canonical five-segment class string into its fields.

    Grammar: ``role/oracle_type/domain_tags/size_band/language``; the
    domain-tags segment is ``+``-joined tags with the empty set written as
    the literal ``none``. Raises ``ValueError`` with a user-facing message
    for any non-canonical shape; committed enumerations and canonical-key
    equality are enforced by the eligibility API itself.
    """
    segments = class_string.split("/")
    if len(segments) != 5 or any(segment == "" for segment in segments):
        raise ValueError(
            "--class must be the canonical five-segment string "
            "role/oracle_type/domain_tags/size_band/language (e.g. "
            "impl/deterministic/none/s/python)"
        )
    role, oracle_type, tags_segment, size_band, language = segments
    if tags_segment == "none":
        domain_tags: tuple[str, ...] = ()
    else:
        domain_tags = tuple(tags_segment.split("+"))
        if any(not tag for tag in domain_tags):
            raise ValueError(
                "--class domain_tags segment is not a canonical '+ '-joined "
                "tag list or the literal 'none'"
            )
    return role, oracle_type, domain_tags, size_band, language


def _explain_sort_key(row: Any) -> tuple[int, float, float, str]:
    """Display order: marginal price ascending, unpriced last, id tie-break.

    Display-only ordering (allowed by the P0-5b packet); eligibility itself
    is never ranked, chosen, or filtered by this ordering.
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


def _explain_route_json(row: Any) -> dict[str, Any]:
    """JSON view of one eligibility row: committed fields only.

    Deliberately excludes the row's model, effort, harness, status_reason,
    and pricing-source machinery — the route id is the only route label.
    """
    pricing = row.pricing
    return {
        "route_id": row.route_id,
        "eligible": row.eligible,
        "channel": row.channel,
        "badge": row.availability_badge,
        "headroom": row.availability_headroom,
        "health": row.availability_health,
        "marginal_input_usd_per_token": (
            pricing.marginal_input_usd_per_token if pricing else None
        ),
        "marginal_output_usd_per_token": (
            pricing.marginal_output_usd_per_token if pricing else None
        ),
        "replacement_input_usd_per_token": (
            pricing.replacement_input_usd_per_token if pricing else None
        ),
        "replacement_output_usd_per_token": (
            pricing.replacement_output_usd_per_token if pricing else None
        ),
        "reasons": list(row.reasons),
    }


def _explain_table(rows: list[dict[str, Any]]) -> list[str]:
    """Render the aligned human-readable table for ordered route dicts."""

    def price(value: Any) -> str:
        return "-" if value is None else f"{value:.8g}"

    def headroom(value: Any) -> str:
        return "-" if value is None else f"{value * 100:.0f}%"

    headers = (
        "ROUTE ID",
        "STATUS",
        "CHANNEL",
        "BADGE",
        "HEADROOM",
        "HEALTH",
        "MARG IN $/TOK",
        "MARG OUT $/TOK",
        "REPL IN $/TOK",
        "REPL OUT $/TOK",
        "REASONS",
    )
    table_rows: list[tuple[str, ...]] = []
    for route in rows:
        table_rows.append(
            (
                route["route_id"],
                "eligible" if route["eligible"] else "excluded",
                route["channel"],
                route["badge"] or "-",
                headroom(route["headroom"]),
                route["health"],
                price(route["marginal_input_usd_per_token"]),
                price(route["marginal_output_usd_per_token"]),
                price(route["replacement_input_usd_per_token"]),
                price(route["replacement_output_usd_per_token"]),
                "; ".join(route["reasons"]) if route["reasons"] else "-",
            )
        )
    widths = [
        (
            max(len(headers[i]), *(len(r[i]) for r in table_rows))
            if table_rows
            else len(headers[i])
        )
        for i in range(len(headers))
    ]
    lines = [
        "  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip(),
        "  ".join("-" * w for w in widths),
    ]
    for table_row in table_rows:
        lines.append(
            "  ".join(cell.ljust(w) for cell, w in zip(table_row, widths)).rstrip()
        )
    return lines


def _selected_terms_view(
    catalog: Any,
    at_date: Any,
) -> dict[str, dict[str, Any]] | None:
    """Selected dated terms per channel via the committed ``terms_at`` lookup.

    Display-only projection of :func:`lee_llm_router.staffing.terms.terms_at`
    — no date selection is reimplemented here: each channel's selected
    ``effective_from``, ``fee_usd_month``, and term-kind tier label
    (``kind``, the TermsEntry field, verbatim) are copied unchanged, with
    the ``"unknown"`` literal shown without coercion. Returns ``None``
    when the committed lookup fails closed for the requested date (e.g. no
    entry yet); no value is ever invented. Channel order follows the
    committed channels document, so the view is deterministic.
    """
    from lee_llm_router.staffing import StaffingTermsError, terms_at

    try:
        selected = terms_at(at_date, catalog)
    except StaffingTermsError:
        return None
    return {
        channel: {
            "effective_from": entry.effective_from,
            "fee_usd_month": entry.fee_usd_month,
            "kind": entry.kind,
        }
        for channel, entry in selected.items()
    }


def _terms_lines(
    terms_view: dict[str, dict[str, Any]] | None,
    at_date: Any,
) -> list[str]:
    """Render the compact deterministic selected-terms lines for text output."""
    if terms_view is None:
        return [f"selected terms: unavailable at {at_date.isoformat()}"]
    lines = [f"selected terms at {at_date.isoformat()}"]
    for channel, entry in terms_view.items():
        lines.append(
            f"  {channel}: effective_from {entry['effective_from']}, "
            f"fee_usd_month {entry['fee_usd_month']}"
        )
    return lines


def _run_catalog_explain(args: argparse.Namespace) -> int:
    """Run ``catalog explain``: eligibility per route, ordered for display.

    The report also projects the dated terms the committed ``terms_at``
    lookup selects for the requested date (display only, in both text and
    ``--json`` output) so the selected ``effective_from``/``fee_usd_month``
    terms and the per-channel term-kind tier label (``kind``, JSON terms
    view only) are observable; it performs no choice, probability, or
    ladder.
    Per Chief round 15 (D86/D87) it discloses exactly once per run — as the
    ``floors recorded, not enforced`` text line and as the top-level
    ``floors_disclosure`` JSON value — that the catalog's ``role_floors``
    records are recorded data only in Phase 0 and exclude no route.
    Per Chief round 15 packet D it also discloses author-route independence
    exactly once: with no ``--author-route`` the exact absent-input line
    ``independence not evaluated (no --author-route)`` (text) and the
    top-level ``independence`` record (JSON, ``evaluated`` false); with an
    author route supplied for review/judge the author route, its derived
    family, and the family source are recorded once, and eligibility has
    already excluded that route and every same-family candidate with the
    reason ``independence``. For other roles the check is recorded as not
    applicable rather than evaluated. Independence is an author/candidate
    comparison, never a class-to-model preference (D206).
    """
    import json
    from datetime import date
    from pathlib import Path

    from lee_llm_router.availability import load_availability
    from lee_llm_router.staffing import (
        StaffingCatalogError,
        StaffingEligibilityError,
        evaluate_eligibility,
        load_staffing_catalog,
    )

    def fail(message: str) -> int:
        print(f"catalog explain: {message}", file=sys.stderr)
        return 3

    try:
        role, oracle_type, domain_tags, size_band, language = _parse_class_string(
            args.class_string
        )
    except ValueError as exc:
        return fail(str(exc))
    if role != args.role:
        return fail(
            f"--role {args.role!r} does not equal the --class role segment " f"{role!r}"
        )

    if args.at is not None:
        try:
            at_date = date.fromisoformat(args.at)
        except ValueError:
            return fail(f"--at: not an ISO date (YYYY-MM-DD): {args.at!r}")
    else:
        at_date = date.today()

    catalog_dir = (
        Path(args.catalog_dir)
        if args.catalog_dir is not None
        else _default_catalog_dir()
    )
    try:
        catalog = load_staffing_catalog(catalog_dir)
    except StaffingCatalogError as exc:
        return fail(f"catalog invalid: {exc}")
    except Exception as exc:  # no traceback on unexpected catalog problems
        return fail(f"catalog invalid: {exc}")

    availability = load_availability(args.availability_file)
    if args.availability_file is not None and availability.problem is not None:
        return fail(f"availability snapshot unusable: {availability.problem}")

    try:
        rows = evaluate_eligibility(
            catalog,
            role=role,
            oracle_type=oracle_type,
            size_band=size_band,
            language=language,
            domain_tags=domain_tags,
            class_key=args.class_string,
            author_route_id=args.author_route,
            availability=availability,
            at_date=at_date,
        )
    except StaffingEligibilityError as exc:
        return fail(str(exc))
    except Exception as exc:  # no traceback on unexpected evaluation errors
        return fail(f"evaluation failed: {exc}")

    try:
        independence = _independence_record(role, args.author_route, catalog)
    except StaffingEligibilityError as exc:
        return fail(str(exc))

    ordered = sorted(rows, key=_explain_sort_key)
    route_views = [_explain_route_json(row) for row in ordered]
    eligible_count = sum(1 for route in route_views if route["eligible"])
    terms_view = _selected_terms_view(catalog, at_date)

    if args.json:
        print(
            json.dumps(
                {
                    "role": role,
                    "class_key": args.class_string,
                    "at": at_date.isoformat(),
                    "terms": terms_view,
                    "floors_disclosure": FLOORS_DISCLOSURE,
                    "independence": independence,
                    "routes": route_views,
                },
                indent=2,
            )
        )
    else:
        print(f"catalog explain — class {args.class_string} at {at_date.isoformat()}")
        print()
        for line in _explain_table(route_views):
            print(line)
        print(
            f"\n{len(route_views)} routes: {eligible_count} eligible, "
            f"{len(route_views) - eligible_count} excluded "
            "(ordered by marginal price)"
        )
        for line in _terms_lines(terms_view, at_date):
            print(line)
        print(FLOORS_DISCLOSURE)
        print(_independence_text_line(independence))
    return 0


def _run_catalog_no_subcommand(_args: argparse.Namespace) -> int:
    print("catalog: subcommand required (explain)", file=sys.stderr)
    return 3


# ---------------------------------------------------------------------------
# staffing run (P1-5b2): select one route, dispatch it once, and record it
# ---------------------------------------------------------------------------


def _run_run(args: argparse.Namespace) -> int:
    """Run ``run``: select, dispatch, validate, append, and print one attempt.

    Corrected D209 contract (Chief ruling,
    ``docs/staffing/chief-answers-p1-1.md``, quoted):
    ``lee-llm-router run --role R --class C --packet FILE [--route ID]
    [--supervisor-route ROUTE_ID] [--author-route ROUTE_ID] [--workdir DIR]
    [--parent ATTEMPT_ID --escalation-reason R] [--timeout S] [--json]``.
    ``--role`` and ``--class`` are always
    required: they describe the work and drive eligibility (role scoping,
    never-automatic, headroom, don't-cheap-trial flag). Without ``--route``
    the selection basis is ``explain_cheapest_eligible`` for that role and
    class; with ``--route ID`` the basis is ``explicit`` and the route must
    be eligible under the same role/class eligibility path as ``catalog
    explain`` — an ineligible explicit route exits 3 with the explain
    reason. ``--author-route ROUTE_ID`` (Astra final-review finding 4) is
    forwarded to the same path: for a review/judge class the author route
    and every same-family candidate are excluded with the reason
    ``independence`` exactly as ``catalog explain --author-route`` reports,
    and an unknown author id fails closed. With ``--supervisor-route
    ROUTE_ID`` the caller attests its own route (P1-4 ruling 3); the id is
    validated as a governed identity (known, active, currently usable —
    unknown/inactive/exhausted ids exit 3 and launch nothing) without
    imposing the worker's role/class capability policy on the attested
    supervisor, and the attested run can reach ``verified_success: true``
    only when dispatch, oracle, and every evidence gate hold.

    All caller-controlled record metadata (the ``--parent``/
    ``--escalation-reason`` pair and ``attempt_id``) is validated against
    the committed attempt-record v2 value rules before anything is launched
    (Astra final-review finding 6): an invalid value is an exit-3 refusal
    that launches nothing and appends nothing. P1-5a dispatches exactly one
    provider ``build_command`` argv through
    the watchdog subprocess boundary, with the packet text as the prompt,
    ``cwd`` set to the workdir, and no shell anywhere. Pi runs its JSON event
    mode, Codex is forced to ``json_flag: --json``, and Claude reuses the
    committed governed stream-json capture. P1-5b1 adds one optional,
    parsed-with-shlex oracle after the worker. The oracle is argv-only, uses
    the workdir, and receives only the remaining timeout budget. Its result
    is verification evidence; it never retries or escalates. When the oracle
    cannot be launched or set up *after* the worker completed (for example a
    workdir deleted between the two boundaries), the completed worker is
    never dropped: exactly one schema-valid attempt is persisted preserving
    the worker evidence and the oracle failure with a truthful verdict,
    failure class, and ``verified_success``, then the governed failure is
    returned (exit 3). P1-5b2 now
    calculates cost, builds one v2 record, validates it, appends it once,
    and prints that record (or a compact equivalent). ``run`` never
    escalates: a supplied parent/reason pair is recorded as a link.

    Exit codes: 0 when the child exited 0; the child's exit code otherwise
    (124 on a ceiling timeout); 3 for every refusal before or around the
    launch (argument pairing, packet/workdir problems, catalog or snapshot
    errors, selection refusals, dispatch wiring errors) — a refused run
    launches nothing.
    """
    import json
    from datetime import date
    from pathlib import Path

    from lee_llm_router.availability import load_availability
    from lee_llm_router.providers.base import LLMRouterError
    from lee_llm_router.staffing import (
        load_staffing_catalog,
    )
    from lee_llm_router.staffing.json_int import dump_json
    from lee_llm_router.staffing.ledger import append_attempt
    from lee_llm_router.staffing.run import (
        OracleOutcome,
        RunDispatchError,
        RunSelectionError,
        build_attempt_record,
        dispatch_route,
        oracle_timeout_seconds,
        packet_id_for_text,
        parse_oracle_command,
        run_oracle,
        run_summary_lines,
        select_route,
        validate_attempt_metadata,
    )

    def fail(message: str, *, as_json: bool = False, exit_code: int = 3) -> int:
        print(f"run: {message}", file=sys.stderr)
        if as_json:
            print(
                json.dumps(
                    {"error": message, "exit_code": exit_code},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        return exit_code

    as_json = bool(getattr(args, "json", False))
    route_id = getattr(args, "route", None)
    role = args.role
    class_string = args.class_string

    # Optional parent/escalation pair: parsed, pairing-checked, and
    # value-validated against the committed attempt-record v2 rules before
    # anything is launched (Astra final-review finding 6).  ``run`` never
    # escalates; a supervisor supplies the link when it launches one.
    parent = getattr(args, "parent", None)
    escalation_reason = getattr(args, "escalation_reason", None)
    if (parent is None) != (escalation_reason is None):
        return fail(
            "--parent and --escalation-reason must be supplied together",
            as_json=as_json,
        )
    try:
        validate_attempt_metadata(
            parent_attempt_id=parent,
            escalation_reason=escalation_reason,
            attempt_id=getattr(args, "attempt_id", None),
        )
    except RunSelectionError as exc:
        return fail(str(exc), as_json=as_json, exit_code=exc.exit_code)

    packet_path = Path(args.packet).expanduser()
    try:
        prompt = packet_path.read_text(encoding="utf-8")
    except OSError as exc:
        return fail(f"packet file cannot be read: {exc}", as_json=as_json)
    if not prompt.strip():
        return fail(f"packet file is empty: {packet_path}", as_json=as_json)

    # --role and --class are always required (Chief's corrected D209
    # contract): they describe the work and drive eligibility even when
    # --route names the candidate explicitly. No stored or default class;
    # no eligibility check that omits class policy.
    try:
        class_role, oracle_type, domain_tags, size_band, language = _parse_class_string(
            class_string
        )
    except ValueError as exc:
        return fail(str(exc), as_json=as_json)
    if class_role != role:
        return fail(
            f"--role {role!r} does not equal the --class role segment "
            f"{class_role!r}",
            as_json=as_json,
        )

    if args.at is not None:
        try:
            at_date = date.fromisoformat(args.at)
        except ValueError:
            return fail(
                f"--at: not an ISO date (YYYY-MM-DD): {args.at!r}", as_json=as_json
            )
    else:
        at_date = date.today()

    catalog_dir = (
        Path(args.catalog_dir)
        if args.catalog_dir is not None
        else _default_catalog_dir()
    )
    try:
        catalog = load_staffing_catalog(catalog_dir)
    except Exception as exc:
        return fail(f"catalog invalid: {exc}", as_json=as_json)

    availability = load_availability(args.availability_file)
    if args.availability_file is not None and availability.problem is not None:
        return fail(
            f"availability snapshot unusable: {availability.problem}", as_json=as_json
        )

    try:
        outcome = select_route(
            catalog,
            availability,
            role=role,
            oracle_type=oracle_type,
            size_band=size_band,
            language=language,
            domain_tags=domain_tags,
            class_key=class_string,
            at_date=at_date,
            author_route_id=getattr(args, "author_route", None),
            route_id=route_id,
            supervisor_route_id=getattr(args, "supervisor_route", None),
            openrouter_snapshot_path=args.openrouter_snapshot,
            rate_table_path=args.rate_table,
        )
    except RunSelectionError as exc:
        return fail(str(exc), as_json=as_json, exit_code=exc.exit_code)

    # Parse and validate before the worker boundary. This is deliberately
    # after selection (so it cannot alter routing) but before any launch.
    oracle_argv = None
    if getattr(args, "oracle", None) is not None:
        try:
            oracle_argv = parse_oracle_command(args.oracle)
        except LLMRouterError as exc:
            return fail(f"oracle command invalid: {exc}", as_json=as_json)

    try:
        dispatch = dispatch_route(
            outcome.route,
            prompt,
            workdir=args.workdir,
            timeout_seconds=args.timeout,
        )
    except LLMRouterError as exc:
        return fail(f"dispatch failed: {exc}", as_json=as_json)

    oracle = None
    oracle_setup_error: str | None = None
    if oracle_argv is not None:
        try:
            oracle = run_oracle(
                oracle_argv,
                workdir=args.workdir,
                timeout_seconds=oracle_timeout_seconds(
                    args.timeout, dispatch.duration_seconds
                ),
            )
        except RunDispatchError as exc:
            # Astra final-review finding 6: the worker has completed, so a
            # governed oracle setup failure must never drop it. The failure
            # is recorded as failed oracle evidence (launch/setup error,
            # no exit code) and exactly one schema-valid attempt preserving
            # both the worker evidence and the oracle failure is appended
            # below; the governed failure is then returned (exit 3).
            oracle_setup_error = str(exc)
            oracle = OracleOutcome(
                argv=tuple(oracle_argv),
                exit_code=None,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                timed_out=False,
                error=str(exc),
            )

    class_record = {
        "class_key": class_string,
        "role": class_role,
        "oracle_type": oracle_type,
        "domain_tags": list(domain_tags),
        "size_band": size_band,
        "language": language,
    }
    try:
        record = build_attempt_record(
            outcome,
            dispatch,
            oracle,
            packet_id=packet_id_for_text(prompt),
            class_record=class_record,
            availability=availability,
            at_date=at_date,
            oracle_cmd=getattr(args, "oracle", None),
            parent_attempt_id=parent,
            escalation_reason=escalation_reason,
            supervisor_route=outcome.supervisor_route,
            attempt_id=getattr(args, "attempt_id", None),
        )
    except (LLMRouterError, OSError, TypeError, ValueError) as exc:
        return fail(f"attempt record could not be built: {exc}", as_json=as_json)

    # append_attempt performs the one schema validation immediately before
    # its one O_APPEND write. There is no pre-write repair or retry path.
    try:
        append_attempt(record)
    except (LLMRouterError, OSError, TypeError, ValueError) as exc:
        return fail(f"attempt record could not be appended: {exc}", as_json=as_json)

    if as_json:
        # One compact JSON object is both the command result and the exact
        # object encoded by append_attempt (the ledger adds only its newline).
        # This holds on the governed oracle-setup-failure path too: the result
        # is the persisted record; the failure is reported on stderr. The
        # bounded serializer keeps every huge token counter an exact JSON
        # integer, byte-identical to the appended ledger line.
        print(dump_json(record))
    else:
        for line in run_summary_lines(outcome, dispatch, oracle, record=record):
            print(line)
    if oracle_setup_error is None:
        return dispatch.exit_code
    # The one attempt record is already persisted; return the governed
    # failure for the oracle that could not run (never a fake success).
    print(f"run: oracle failed: {oracle_setup_error}", file=sys.stderr)
    return 3


class _FastResolveArgs:
    """Fast-path argument namespace for resolve."""

    __slots__ = (
        "command",
        "positionals",
        "crew",
        "role",
        "mode",
        "worker",
        "authorized_by",
        "reason",
        "harness",
        "json",
        "crews_file",
        "availability_file",
        "events_file",
        "no_event",
    )

    def __init__(
        self,
        crew: str | None = None,
        role: str | None = None,
        mode: str = "strict",
        worker: str | None = None,
        authorized_by: str | None = None,
        reason: str | None = None,
        harness: str = "cli",
        as_json: bool = False,
        crews_file: str | None = None,
        availability_file: str | None = None,
        events_file: str | None = None,
        no_event: bool = False,
        positionals: list[str] | None = None,
    ) -> None:
        self.command = "resolve"
        self.crew = crew
        self.role = role
        self.mode = mode
        self.worker = worker
        self.authorized_by = authorized_by
        self.reason = reason
        self.harness = harness
        self.json = as_json
        self.crews_file = crews_file
        self.availability_file = availability_file
        self.events_file = events_file
        self.no_event = no_event
        self.positionals = list(positionals) if positionals is not None else []


def _try_fast_resolve(argv: list[str]) -> _FastResolveArgs | None:
    """Fast-path parse arguments for resolve.

    Falls back to argparse on unexpected flags or --help.
    """
    positionals: list[str] = []
    crew: str | None = None
    role: str | None = None
    mode = "strict"
    worker: str | None = None
    authorized_by: str | None = None
    reason: str | None = None
    harness = "cli"
    as_json = False
    crews_file: str | None = None
    availability_file: str | None = None
    events_file: str | None = None
    no_event = False

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg in ("-h", "--help"):
            return None
        if arg == "--json":
            as_json = True
            i += 1
            continue
        if arg == "--no-event":
            no_event = True
            i += 1
            continue

        if not arg.startswith("-"):
            positionals.append(arg)
            i += 1
            continue

        if not arg.startswith("--"):
            return None

        opt, has_eq, val = arg.partition("=")
        if has_eq:
            opt_name = opt
            opt_val = val
            step = 1
        else:
            opt_name = arg
            if i + 1 >= n or argv[i + 1].startswith("--"):
                return None
            opt_val = argv[i + 1]
            step = 2

        if opt_name == "--crew":
            crew = opt_val
        elif opt_name == "--role":
            role = opt_val
        elif opt_name == "--mode":
            if opt_val not in RESOLVE_MODES:
                return None
            mode = opt_val
        elif opt_name == "--worker":
            worker = opt_val
        elif opt_name == "--authorized-by":
            authorized_by = opt_val
        elif opt_name == "--reason":
            reason = opt_val
        elif opt_name == "--harness":
            harness = opt_val
        elif opt_name == "--crews-file":
            crews_file = opt_val
        elif opt_name == "--availability-file":
            availability_file = opt_val
        elif opt_name == "--events-file":
            events_file = opt_val
        else:
            return None

        i += step

    if len(positionals) == 2 and crew is None and role is None:
        crew = positionals[0]
        role = positionals[1]
    elif len(positionals) == 0 and crew is not None and role is not None:
        pass
    else:
        return None

    return _FastResolveArgs(
        crew=crew,
        role=role,
        mode=mode,
        worker=worker,
        authorized_by=authorized_by,
        reason=reason,
        harness=harness,
        as_json=as_json,
        crews_file=crews_file,
        availability_file=availability_file,
        events_file=events_file,
        no_event=no_event,
    )


def main(argv: list[str] | None = None) -> None:
    args_list = sys.argv[1:] if argv is None else list(argv)
    if args_list and args_list[0] == "resolve":
        fast_args = _try_fast_resolve(args_list[1:])
        if fast_args is not None:
            sys.exit(_run_resolve(fast_args))

    import argparse

    from lee_llm_router.watchdog import DEFAULT_MAX_MINUTES, DEFAULT_STALL_MINUTES

    parser = argparse.ArgumentParser(
        prog="lee-llm-router",
        description="Lee LLM Router CLI tools",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Validate config file and environment; exit 0 if healthy",
    )
    doctor_parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to config YAML (optional with --crews/--availability)",
    )
    doctor_parser.add_argument(
        "--role",
        metavar="ROLE",
        help="Role to dry-run (default: config.default_role)",
    )
    doctor_parser.add_argument(
        "--crews",
        action="store_true",
        help="Also resolve every worker referenced by every crew",
    )
    doctor_parser.add_argument(
        "--crews-file",
        metavar="PATH",
        default=None,
        help="Path to the crews YAML (default: the Auto-Orch crews file)",
    )
    doctor_parser.add_argument(
        "--availability",
        action="store_true",
        help="Also report the age and size of the availability snapshot",
    )
    doctor_parser.add_argument(
        "--availability-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to the availability snapshot (default: "
            "~/.local/state/lee-llm-router/availability/<host>.json)"
        ),
    )
    doctor_parser.add_argument(
        "--catalog",
        action="store_true",
        help="Also validate and load the six staffing catalog documents",
    )
    doctor_parser.add_argument(
        "--catalog-dir",
        metavar="PATH",
        default=None,
        help=(
            "Directory holding routes.yaml, channels.yaml, terms.yaml, "
            "policy.yaml, classes.yaml, crews.yaml "
            "(default: the repo config/staffing directory)"
        ),
    )
    doctor_parser.set_defaults(func=_run_doctor)

    crews_parser = subparsers.add_parser(
        "crews",
        help="Inspect the Auto-Orch crews file",
    )
    crews_sub = crews_parser.add_subparsers(dest="crews_command", metavar="SUBCOMMAND")
    crews_sub.required = True
    crews_list_parser = crews_sub.add_parser(
        "list",
        help="List crews, their stage workers, and their governed routes",
    )
    crews_list_parser.add_argument(
        "--crews-file",
        metavar="PATH",
        default=None,
        help="Path to the crews YAML (default: the Auto-Orch crews file)",
    )
    crews_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON array instead of plain text",
    )
    crews_list_parser.set_defaults(func=_run_crews_list)

    crews_page_parser = crews_sub.add_parser(
        "page",
        help="Generate a self-contained HTML crew staffing page",
    )
    crews_page_parser.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="Output HTML path; its parent directory must already exist",
    )
    crews_page_parser.add_argument(
        "--crews-file",
        metavar="PATH",
        default=None,
        help="Path to the crews YAML (default: the Auto-Orch crews file)",
    )
    crews_page_parser.add_argument(
        "--availability-file",
        metavar="PATH",
        default=None,
        help="Path to the availability snapshot (default: per-host default)",
    )
    crews_page_parser.add_argument(
        "--benchmark-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to staffing evidence JSON (default: latest "
            "~/projects/ai-workforce-benchmark/exports/staffing-evidence-*.json)"
        ),
    )
    crews_page_parser.add_argument(
        "--events-file",
        metavar="PATH",
        default=None,
        help="Validate this JSONL event ledger without reading the default ledger",
    )
    crews_page_parser.set_defaults(func=_run_crews_page)

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Resolve which worker runs a crew's stage, and record the event",
    )
    resolve_parser.add_argument(
        "positionals",
        nargs="*",
        metavar="CREW ROLE",
        help="Crew name and role stage as positionals (e.g. resolve CREW ROLE)",
    )
    resolve_parser.add_argument(
        "--crew",
        default=None,
        metavar="NAME",
        help="Crew name",
    )
    resolve_parser.add_argument(
        "--role",
        default=None,
        metavar="STAGE",
        help="Cognitive stage name (envision, ideate, reconsider, score, author)",
    )
    resolve_parser.add_argument(
        "--mode",
        choices=RESOLVE_MODES,
        default="strict",
        help="Resolution mode (default: strict)",
    )
    resolve_parser.add_argument(
        "--worker",
        metavar="ID",
        default=None,
        help="Worker id to bind to (bind mode only)",
    )
    resolve_parser.add_argument(
        "--authorized-by",
        metavar="WHO",
        default=None,
        help="Who authorized the bind (bind mode only)",
    )
    resolve_parser.add_argument(
        "--reason",
        metavar="WHY",
        default=None,
        help="Why the bind was authorized (bind mode only)",
    )
    resolve_parser.add_argument(
        "--harness",
        metavar="TAG",
        default="cli",
        help="Calling harness tag recorded in the event (default: cli)",
    )
    resolve_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON object instead of plain text",
    )
    resolve_parser.add_argument(
        "--crews-file",
        metavar="PATH",
        default=None,
        help="Path to the crews YAML (default: the Auto-Orch crews file)",
    )
    resolve_parser.add_argument(
        "--availability-file",
        metavar="PATH",
        default=None,
        help="Path to the availability snapshot (default: per-host default)",
    )
    resolve_parser.add_argument(
        "--events-file",
        metavar="PATH",
        default=None,
        help="Path to the event ledger (default: per-host default)",
    )
    resolve_parser.add_argument(
        "--no-event",
        action="store_true",
        help="Do not append an event (dry runs, shim self-tests)",
    )
    resolve_parser.set_defaults(func=_run_resolve)

    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="Resolve, run the harness, supervise with the stall watchdog",
    )
    dispatch_parser.add_argument(
        "--crew",
        required=True,
        metavar="NAME",
        help="Crew name",
    )
    dispatch_parser.add_argument(
        "--role",
        required=True,
        metavar="STAGE",
        help="Cognitive stage name (envision, ideate, reconsider, score, author)",
    )
    dispatch_parser.add_argument(
        "--mode",
        choices=RESOLVE_MODES,
        default="strict",
        help="Resolution mode (default: strict)",
    )
    dispatch_parser.add_argument(
        "--worker",
        metavar="ID",
        default=None,
        help="Worker id to bind to (bind mode only)",
    )
    dispatch_parser.add_argument(
        "--authorized-by",
        metavar="WHO",
        default=None,
        help="Who authorized the bind (bind mode only)",
    )
    dispatch_parser.add_argument(
        "--reason",
        metavar="WHY",
        default=None,
        help="Why the bind was authorized (bind mode only)",
    )
    dispatch_parser.add_argument(
        "--harness",
        metavar="TAG",
        default="cli",
        help="Calling harness tag recorded in the event (default: cli)",
    )
    dispatch_parser.add_argument(
        "--prompt-file",
        metavar="PATH",
        default=None,
        help="Path to prompt file",
    )
    dispatch_parser.add_argument(
        "--prompt",
        metavar="TEXT",
        default=None,
        help="Prompt text",
    )
    dispatch_parser.add_argument(
        "--stall-minutes",
        type=float,
        default=DEFAULT_STALL_MINUTES,
        metavar="N",
        help=(
            f"Minutes of silence before flagging a stall "
            f"(default: {DEFAULT_STALL_MINUTES})"
        ),
    )
    dispatch_parser.add_argument(
        "--max-minutes",
        type=float,
        default=DEFAULT_MAX_MINUTES,
        metavar="N",
        help=(
            f"Wall-clock ceiling in minutes before killing child "
            f"(default: {DEFAULT_MAX_MINUTES})"
        ),
    )
    dispatch_parser.add_argument(
        "--watch-dir",
        action="extend",
        nargs="+",
        default=[],
        metavar="PATH",
        help="Directory to watch for file activity (repeatable)",
    )
    dispatch_parser.add_argument(
        "--crews-file",
        metavar="PATH",
        default=None,
        help="Path to the crews YAML (default: the Auto-Orch crews file)",
    )
    dispatch_parser.add_argument(
        "--availability-file",
        metavar="PATH",
        default=None,
        help="Path to the availability snapshot (default: per-host default)",
    )
    dispatch_parser.add_argument(
        "--events-file",
        metavar="PATH",
        default=None,
        help="Path to the event ledger (default: per-host default)",
    )
    dispatch_parser.add_argument(
        "--no-event",
        action="store_true",
        help="Do not append an event",
    )
    dispatch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolution and command without running",
    )
    dispatch_parser.set_defaults(func=_run_dispatch)

    shims_parser = subparsers.add_parser(
        "shims",
        help="Manage harness command shims (install, diff)",
    )
    shims_sub = shims_parser.add_subparsers(dest="shims_command", metavar="SUBCOMMAND")
    shims_sub.required = False
    shims_parser.set_defaults(func=_run_shims_no_subcommand)

    shims_install_parser = shims_sub.add_parser(
        "install",
        help="Install harness shims (--dry-run or --apply)",
    )
    shims_install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions and rendered shim contents without writing",
    )
    shims_install_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write shims to their target paths",
    )
    shims_install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files whose marker/hash does not match",
    )
    shims_install_parser.add_argument(
        "--harness",
        action="append",
        default=None,
        metavar="TAG",
        help="Limit to named harness (claude-code, codex, omp, opencode; repeatable)",
    )
    shims_install_parser.add_argument(
        "--project",
        default=None,
        metavar="PATH",
        help="Project directory for omp shim (default: cwd)",
    )
    shims_install_parser.set_defaults(func=_run_shims_install)

    shims_diff_parser = shims_sub.add_parser(
        "diff",
        help="Show diff between installed shims and rendered templates",
    )
    shims_diff_parser.add_argument(
        "--harness",
        action="append",
        default=None,
        metavar="TAG",
        help="Limit to named harness (claude-code, codex, omp, opencode; repeatable)",
    )
    shims_diff_parser.add_argument(
        "--project",
        default=None,
        metavar="PATH",
        help="Project directory for omp shim (default: cwd)",
    )
    shims_diff_parser.set_defaults(func=_run_shims_diff)

    catalog_parser = subparsers.add_parser(
        "catalog",
        help="Inspect the staffing catalog",
    )
    catalog_sub = catalog_parser.add_subparsers(
        dest="catalog_command", metavar="SUBCOMMAND"
    )
    catalog_sub.required = False
    catalog_parser.set_defaults(func=_run_catalog_no_subcommand)

    catalog_explain_parser = catalog_sub.add_parser(
        "explain",
        help="Report every route's eligibility for a class, ordered by marginal price",
    )
    catalog_explain_parser.add_argument(
        "--role",
        required=True,
        metavar="ROLE",
        help="Class role (impl, plan, review, judge, prose)",
    )
    catalog_explain_parser.add_argument(
        "--class",
        required=True,
        dest="class_string",
        metavar="CLASS",
        help=(
            "Canonical five-segment class string "
            "role/oracle_type/domain_tags/size_band/language "
            "(e.g. impl/deterministic/none/s/python)"
        ),
    )
    catalog_explain_parser.add_argument(
        "--at",
        default=None,
        metavar="DATE",
        help="ISO date (YYYY-MM-DD) for dated terms (default: today)",
    )
    catalog_explain_parser.add_argument(
        "--availability-file",
        metavar="PATH",
        default=None,
        help="Path to the availability snapshot (default: per-host default)",
    )
    catalog_explain_parser.add_argument(
        "--catalog-dir",
        metavar="PATH",
        default=None,
        help=(
            "Directory holding the six staffing catalog YAML documents "
            "(default: the repo config/staffing directory)"
        ),
    )
    catalog_explain_parser.add_argument(
        "--author-route",
        metavar="ROUTE_ID",
        default=None,
        help=(
            "Author route id for review/judge independence: exclude that "
            "route and every candidate whose model family equals the "
            "author's (reason 'independence'). Without it, independence is "
            "not evaluated (absent-input disclosure only). Unknown ids fail "
            "closed (exit 3)."
        ),
    )
    catalog_explain_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON object instead of a plain-text table",
    )
    catalog_explain_parser.set_defaults(func=_run_catalog_explain)

    run_parser = subparsers.add_parser(
        "run",
        help="Select, dispatch, and record one eligible staffing attempt",
    )
    run_parser.add_argument(
        "--role",
        required=True,
        metavar="ROLE",
        help="Class role (impl, plan, review, judge, prose); always required",
    )
    run_parser.add_argument(
        "--class",
        required=True,
        dest="class_string",
        metavar="CLASS",
        help=(
            "Canonical five-segment class string "
            "role/oracle_type/domain_tags/size_band/language "
            "(e.g. impl/deterministic/none/s/python); always required"
        ),
    )
    run_parser.add_argument(
        "--packet",
        required=True,
        metavar="FILE",
        help="Path to the packet file whose text is dispatched verbatim",
    )
    run_parser.add_argument(
        "--route",
        default=None,
        metavar="ROUTE_ID",
        help=(
            "Explicit route id: selection basis 'explicit'; the route must "
            "be eligible under the same role/class path as catalog explain "
            "(an excluded route exits 3 and launches nothing). Without it, "
            "the first eligible route in catalog explain marginal-price "
            "order is selected (basis 'explain_cheapest_eligible')"
        ),
    )
    run_parser.add_argument(
        "--supervisor-route",
        default=None,
        dest="supervisor_route",
        metavar="ROUTE_ID",
        help=(
            "Optional caller attestation of its own supervisor route "
            "(P1-4 ruling 3): the id must name a known, active, currently "
            "usable catalog route identity (unknown/inactive/exhausted ids "
            "exit 3 and launch nothing), but the worker's role/class "
            "capability policy is never imposed on the attested supervisor "
            "identity. When the attested run dispatches, the oracle passes, "
            "and every evidence gate holds, verified_success is true; "
            "otherwise verified_success_reason names the exact gap"
        ),
    )
    run_parser.add_argument(
        "--author-route",
        default=None,
        dest="author_route",
        metavar="ROUTE_ID",
        help=(
            "Author route id forwarded to the same catalog explain "
            "eligibility path: for a review/judge class the author route "
            "and every candidate whose model family equals the author's are "
            "excluded (reason 'independence'); an unknown id fails closed "
            "(exit 3). Without it, independence is not evaluated"
        ),
    )
    run_parser.add_argument(
        "--oracle",
        default=None,
        metavar="CMD",
        help=(
            "Optional verification command; parsed with shlex and run once "
            "without a shell after the worker"
        ),
    )
    run_parser.add_argument(
        "--workdir",
        default=None,
        metavar="DIR",
        help="Child and oracle working directory (must exist; default: inherit)",
    )
    run_parser.add_argument(
        "--parent",
        default=None,
        metavar="ATTEMPT_ID",
        help=(
            "Parent attempt id for an escalation-linked run; must be "
            "supplied together with --escalation-reason; recorded on the attempt"
        ),
    )
    run_parser.add_argument(
        "--escalation-reason",
        default=None,
        dest="escalation_reason",
        metavar="R",
        help=(
            "Escalation reason paired with --parent; both or neither; "
            "recorded on the attempt"
        ),
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="S",
        help=(
            "Wall-clock ceiling in seconds (default: the dispatch "
            "boundary's standard ceiling)"
        ),
    )
    run_parser.add_argument(
        "--at",
        default=None,
        metavar="DATE",
        help="ISO date (YYYY-MM-DD) for dated terms (default: today)",
    )
    run_parser.add_argument(
        "--availability-file",
        metavar="PATH",
        default=None,
        help="Path to the availability snapshot (default: per-host default)",
    )
    run_parser.add_argument(
        "--catalog-dir",
        metavar="PATH",
        default=None,
        help=(
            "Directory holding the six staffing catalog YAML documents "
            "(default: the repo config/staffing directory)"
        ),
    )
    run_parser.add_argument(
        "--openrouter-snapshot",
        metavar="PATH",
        default=None,
        help="Injectable pinned OpenRouter snapshot path (testing override)",
    )
    run_parser.add_argument(
        "--rate-table",
        metavar="PATH",
        default=None,
        help="Injectable agent-orch rate-table path (testing override)",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary object instead of plain text",
    )
    run_parser.set_defaults(func=_run_run)

    evidence_parser = subparsers.add_parser(
        "evidence",
        help="Inspect staffing evidence",
    )
    evidence_sub = evidence_parser.add_subparsers(
        dest="evidence_command", metavar="SUBCOMMAND"
    )
    evidence_sub.required = True
    evidence_rollup_parser = evidence_sub.add_parser(
        "rollup",
        help="Aggregate validated attempt records by route and class",
    )
    evidence_rollup_parser.set_defaults(func=_run_evidence_rollup)
    evidence_import_parser = evidence_sub.add_parser(
        "import",
        help="Import benchmark or recent Agent-Orch evidence into the attempt ledger",
    )
    evidence_sources = evidence_import_parser.add_mutually_exclusive_group(
        required=True
    )
    evidence_sources.add_argument(
        "--benchmark",
        default=None,
        metavar="PATH",
        help="Path to the benchmark v6 staffing-evidence sidecar",
    )
    evidence_sources.add_argument(
        "--agent-orch",
        dest="agent_orch",
        default=None,
        metavar="PATH",
        help=(
            "Agent-Orch projects directory, *-agent-orch-runs directory, "
            "or one run.json fixture"
        ),
    )
    evidence_import_parser.add_argument(
        "--csv",
        default=None,
        metavar="PATH",
        help="Override source CSV path (must match the sidecar SHA-256)",
    )
    evidence_import_parser.set_defaults(func=_run_evidence_import)

    template_parser = subparsers.add_parser(
        "template",
        help="Print example config YAML to stdout",
    )
    template_parser.set_defaults(func=_run_template)

    trace_parser = subparsers.add_parser(
        "trace",
        help="Show recent trace summaries",
    )
    trace_parser.add_argument(
        "--last",
        type=int,
        default=10,
        metavar="N",
        help="Number of traces to show (default: 10)",
    )
    trace_parser.add_argument(
        "--dir",
        metavar="DIR",
        default=None,
        help="Trace directory (default: .lee-llm-router/traces)",
    )
    trace_parser.set_defaults(func=_run_trace)

    export_parser = subparsers.add_parser(
        "export-source",
        help="Export the package as a vendorable source snapshot",
    )
    export_parser.add_argument(
        "--dest",
        required=True,
        metavar="PATH",
        help="Destination directory for the vendored lee_llm_router package",
    )
    export_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite a non-empty destination directory",
    )
    export_parser.set_defaults(func=_run_export_source)

    args = parser.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
