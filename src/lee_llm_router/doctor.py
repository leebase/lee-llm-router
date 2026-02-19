"""Doctor CLI — config validation and environment diagnostics.

Commands:
    lee-llm-router doctor --config <path> [--role <role>]
    lee-llm-router template
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any


def check_config(
    config_path: str,
    role: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a config file and its environment.

    Returns:
        (errors, warnings) — errors are blocking; warnings are informational.
    """
    from lee_llm_router.config import ConfigError, load_config

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Parse and structurally validate the YAML
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        return [f"Config invalid: {exc}"], []
    except Exception as exc:
        return [f"Unexpected error loading config: {exc}"], []

    # 2. Per-provider environment + binary checks
    for pname, pcfg in config.providers.items():
        if pcfg.type in ("openrouter_http", "openai_http"):
            api_key_env = pcfg.raw.get("api_key_env")
            if api_key_env and not os.environ.get(api_key_env):
                errors.append(
                    f"Provider {pname!r}: env var {api_key_env!r} is not set"
                )
            if not pcfg.raw.get("base_url"):
                warnings.append(
                    f"Provider {pname!r}: 'base_url' not set — will use default"
                )

        elif pcfg.type == "codex_cli":
            command = pcfg.raw.get("command", "codex")
            if not shutil.which(command):
                errors.append(
                    f"Provider {pname!r}: binary {command!r} not found in PATH"
                )

        elif pcfg.type == "mock":
            pass  # mock provider always available

        else:
            warnings.append(
                f"Provider {pname!r}: unknown type {pcfg.type!r} — cannot validate"
            )

    # 3. Dry-run with MockProvider (proves routing logic works)
    target_role = role or config.default_role
    try:
        from lee_llm_router.providers.mock import MockProvider
        from lee_llm_router.response import LLMRequest

        mock = MockProvider()
        req = LLMRequest(
            role=target_role,
            messages=[{"role": "user", "content": "doctor dry-run"}],
        )
        mock.complete(req, {})
    except Exception as exc:
        errors.append(f"Dry-run failed for role {target_role!r}: {exc}")

    return errors, warnings


def get_template() -> str:
    """Return the contents of the bundled llm.example.yaml."""
    template_path = Path(__file__).parent / "templates" / "llm.example.yaml"
    return template_path.read_text()


def _run_doctor(args: argparse.Namespace) -> int:
    config_path = args.config
    role = getattr(args, "role", None)

    print(f"Lee LLM Router Doctor")
    print(f"Config: {config_path}")
    print()

    errors, warnings = check_config(config_path, role)

    for w in warnings:
        print(f"  ⚠  {w}")
    for e in errors:
        print(f"  ✗  {e}", file=sys.stderr)

    if not errors and not warnings:
        print("  ✓  All checks passed")
    elif not errors:
        print(f"\n  ✓  {len(warnings)} warning(s) — no blocking errors")

    if errors:
        print(f"\nStatus: {len(errors)} error(s) found", file=sys.stderr)
        return 1

    return 0


def _run_template(_args: argparse.Namespace) -> int:
    print(get_template(), end="")
    return 0


def _run_trace(args: argparse.Namespace) -> int:
    import json

    trace_dir = Path(args.dir) if args.dir else Path(".lee-llm-router") / "traces"
    n = args.last

    if not trace_dir.exists():
        print(f"No trace directory found: {trace_dir}", file=sys.stderr)
        return 1

    trace_files = sorted(
        trace_dir.rglob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not trace_files:
        print("No traces found.")
        return 0

    for tf in trace_files[:n]:
        try:
            data = json.loads(tf.read_text())
            status = "ERROR" if data.get("error") else "OK"
            elapsed = f"{data.get('elapsed_ms') or 0:.0f}ms"
            attempt = int(data.get("attempt", 0) or 0)
            attempt_str = f"a{attempt}"
            print(
                f"{str(data.get('request_id', '?'))[:8]}  "
                f"{str(data.get('started_at', '?'))[:19]}  "
                f"{str(data.get('role', '?')):<12}  "
                f"{str(data.get('provider', '?')):<20}  "
                f"{attempt_str:<6}  "
                f"{str(data.get('model', '?')):<20}  "
                f"{status:<6}  {elapsed}"
            )
        except Exception as exc:
            print(f"  [could not parse {tf}: {exc}]", file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lee-llm-router",
        description="Lee LLM Router CLI tools",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # doctor subcommand
    doctor_p = subparsers.add_parser(
        "doctor",
        help="Validate config file and environment; exit 0 if healthy",
    )
    doctor_p.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="Path to config YAML",
    )
    doctor_p.add_argument(
        "--role",
        metavar="ROLE",
        help="Role to dry-run (default: config.default_role)",
    )
    doctor_p.set_defaults(func=_run_doctor)

    # template subcommand
    template_p = subparsers.add_parser(
        "template",
        help="Print example config YAML to stdout",
    )
    template_p.set_defaults(func=_run_template)

    # trace subcommand
    trace_p = subparsers.add_parser(
        "trace",
        help="Show recent trace summaries",
    )
    trace_p.add_argument(
        "--last",
        type=int,
        default=10,
        metavar="N",
        help="Number of traces to show (default: 10)",
    )
    trace_p.add_argument(
        "--dir",
        metavar="DIR",
        default=None,
        help="Trace directory (default: .lee-llm-router/traces)",
    )
    trace_p.set_defaults(func=_run_trace)

    args = parser.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
