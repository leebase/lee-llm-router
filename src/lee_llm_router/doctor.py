"""Doctor CLI - config validation, environment diagnostics, and source export.

Commands:
    lee-llm-router doctor --config <path> [--role <role>] [--crews]
                          [--availability]
    lee-llm-router crews list [--crews-file <path>] [--json]
    lee-llm-router template
    lee-llm-router trace --last N
    lee-llm-router export-source --dest <path> [--force]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = ".lee_llm_router_export.json"


def check_config(
    config_path: str,
    role: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a config file and its environment.

    Returns:
        (errors, warnings) - errors are blocking; warnings are informational.
    """
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
    template_path = Path(__file__).parent / "templates" / "llm.example.yaml"
    return template_path.read_text(encoding="utf-8")


def export_source(dest: str | Path, force: bool = False) -> dict[str, str | None]:
    """Export the package tree as a vendorable source snapshot."""
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
    worker is reported even when no crew stage references it. A worker whose
    resolved model is forbidden (see
    :func:`lee_llm_router.crews.is_forbidden`) is reported as a warning rather
    than an error: the crews file is Auto-Orch's, not ours, and it currently
    declares such a worker.

    Args:
        crews_file: Explicit crews file path, or None to use the default.

    Returns:
        ``(errors, warnings, crew_count, resolved_worker_count,
        total_worker_count)``.
    """
    from lee_llm_router.crews import (
        CrewsConfigError,
        is_forbidden,
        load_crews,
        resolve_worker,
    )

    try:
        crews_config = load_crews(crews_file)
    except CrewsConfigError as exc:
        return [f"Crews invalid: {exc}"], [], 0, 0, 0

    errors: list[str] = []
    warnings: list[str] = []
    resolved: set[str] = set()

    for worker_id, worker in crews_config.workers.items():
        try:
            resolved_worker = resolve_worker(worker)
        except CrewsConfigError as exc:
            errors.append(f"Worker {worker_id!r}: {exc}")
            continue
        resolved.add(worker_id)
        if is_forbidden(resolved_worker.model):
            warnings.append(
                f"Worker {worker_id!r} resolves to forbidden model "
                f"{resolved_worker.model!r}; the resolver must never choose it"
            )

    for crew in crews_config.crews.values():
        for stage in crew.stages.values():
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


def _run_doctor(args: argparse.Namespace) -> int:
    config_path = args.config
    role = getattr(args, "role", None)

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
            f"{len(crew_warnings)} forbidden-model warning(s)"
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
        print("doctor requires --config (or --crews / --availability)", file=sys.stderr)
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


def main(argv: list[str] | None = None) -> None:
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
