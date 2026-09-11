"""Harness shims generation and management.

Provides templated command shims for Claude Code, Codex, OMP, and OpenCode.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Sequence

ENV_SHIM_HOME = "LEE_LLM_ROUTER_SHIM_HOME"

HARNESS_TAGS: tuple[str, ...] = ("claude-code", "codex", "omp", "opencode")

HARNESS_FORMS: dict[str, str] = {
    "claude-code": "Claude Code slash command",
    "codex": "Codex custom prompt",
    "omp": "OMP prompt template",
    "opencode": "OpenCode command file",
}

HARNESS_FRONTMATTER_EXTRA: dict[str, str] = {
    "claude-code": (
        "argument-hint: auto|NAME\n" "allowed-tools: Bash(lee-llm-router:*)\n"
    ),
    "codex": "argument-hint: auto|NAME\n",
    "omp": "argument-hint: auto|NAME\n",
    "opencode": "",
}

MARKER_RE = re.compile(
    r"^<!-- lee-llm-router shim v1 sha256=([0-9a-fA-F]{64}) -->(\r?\n)?",
    re.MULTILINE,
)


class ShimError(Exception):
    """Base exception for shims operations."""


class ShimUsageError(ShimError):
    """Usage error for shims operations (maps to exit 3)."""


@dataclass(frozen=True)
class ShimTarget:
    """Rendered target information for a harness shim."""

    harness: str
    path: Path
    form: str
    content: str
    body: str
    frontmatter: str
    marker_line: str
    marker_hash: str
    body_below_marker: str


Target = ShimTarget


def resolve_home(home: Path | str | None = None) -> Path:
    """Resolve the target home directory."""
    if home is not None:
        return Path(home).resolve()
    env_home = os.environ.get(ENV_SHIM_HOME)
    if env_home:
        return Path(env_home).resolve()
    return Path.home().resolve()


def resolve_project(project: Path | str | None = None) -> Path:
    """Resolve the target project directory (for omp)."""
    if project is not None:
        return Path(project).resolve()
    return Path.cwd().resolve()


def normalize_harnesses(harnesses: Sequence[str] | str | None) -> list[str]:
    """Normalize and validate harness tags."""
    if harnesses is None:
        return list(HARNESS_TAGS)
    if isinstance(harnesses, str):
        harnesses = [harnesses]
    result: list[str] = []
    for item in harnesses:
        for tag in item.split(","):
            tag = tag.strip()
            if not tag:
                continue
            if tag not in HARNESS_TAGS:
                raise ShimUsageError(
                    f"unknown harness {tag!r} (known: {', '.join(HARNESS_TAGS)})"
                )
            if tag not in result:
                result.append(tag)
    return result


def target_path_for_harness(
    harness: str,
    project: Path | str | None = None,
    home: Path | str | None = None,
) -> Path:
    """Return the absolute installation target path for a harness."""
    h = resolve_home(home)
    p = resolve_project(project)
    if harness == "claude-code":
        return h / ".claude" / "commands" / "crew.md"
    elif harness == "codex":
        return h / ".codex" / "prompts" / "crew.md"
    elif harness == "omp":
        return p / ".omp" / "prompts" / "crew.md"
    elif harness == "opencode":
        return h / ".config" / "opencode" / "command" / "crew.md"
    else:
        raise ShimUsageError(
            f"unknown harness {harness!r} (known: {', '.join(HARNESS_TAGS)})"
        )


def load_template() -> str:
    """Load the raw template text from package data."""
    try:
        import importlib.resources as pkg_resources

        return (
            pkg_resources.files("lee_llm_router")
            .joinpath("templates/shims/crew.md.tmpl")
            .read_text(encoding="utf-8")
        )
    except Exception:
        tmpl_path = Path(__file__).parent / "templates" / "shims" / "crew.md.tmpl"
        return tmpl_path.read_text(encoding="utf-8")


def render_target(
    harness: str,
    project: Path | str | None = None,
    home: Path | str | None = None,
) -> ShimTarget:
    """Render the full target object for a given harness."""
    if harness not in HARNESS_TAGS:
        raise ShimUsageError(
            f"unknown harness {harness!r} (known: {', '.join(HARNESS_TAGS)})"
        )

    raw_tmpl = load_template()
    marker_placeholder = "<!-- lee-llm-router shim v1 sha256={marker_hash} -->"
    idx = raw_tmpl.find(marker_placeholder)
    if idx == -1:
        raise ShimError(
            f"Marker line placeholder not found in template: {marker_placeholder}"
        )

    prefix = raw_tmpl[:idx]
    rest = raw_tmpl[idx + len(marker_placeholder) :]
    if rest.startswith("\r\n"):
        body_tmpl = rest[2:]
    elif rest.startswith("\n"):
        body_tmpl = rest[1:]
    else:
        body_tmpl = rest

    body_below = body_tmpl.replace("{harness}", harness)
    marker_hash = hashlib.sha256(body_below.encode("utf-8")).hexdigest()
    marker_line = f"<!-- lee-llm-router shim v1 sha256={marker_hash} -->"
    extra = HARNESS_FRONTMATTER_EXTRA.get(harness, "")
    frontmatter = prefix.replace("{frontmatter_extra}", extra)

    content = f"{frontmatter}{marker_line}\n{body_below}"
    body = f"{marker_line}\n{body_below}"
    path = target_path_for_harness(harness, project=project, home=home)
    form = HARNESS_FORMS[harness]

    return ShimTarget(
        harness=harness,
        path=path,
        form=form,
        content=content,
        body=body,
        frontmatter=frontmatter,
        marker_line=marker_line,
        marker_hash=marker_hash,
        body_below_marker=body_below,
    )


def render_shim(harness: str) -> str:
    """Render the full shim file content for a harness."""
    return render_target(harness).content


def render_body(harness: str) -> str:
    """Render the shim body (marker line + body below) for a harness."""
    return render_target(harness).body


def render_body_below(harness: str) -> str:
    """Render the shim body below the marker line for a harness."""
    return render_target(harness).body_below_marker


render = render_shim


def get_targets(
    project: Path | str | None = None,
    home: Path | str | None = None,
    harnesses: Sequence[str] | str | None = None,
) -> list[ShimTarget]:
    """Return rendered targets for the selected harnesses."""
    tag_list = normalize_harnesses(harnesses)
    return [render_target(h, project=project, home=home) for h in tag_list]


get_shims = get_targets


def inspect_target(target: ShimTarget) -> str:
    """Inspect an existing target path and return the action to take.

    Returns one of:
        - 'create'
        - 'update'
        - 'unchanged'
        - 'refuse: not generated by lee-llm-router'
    """
    if not target.path.exists():
        return "create"
    try:
        existing = target.path.read_text(encoding="utf-8")
    except OSError:
        return "refuse: not generated by lee-llm-router"

    if existing == target.content:
        return "unchanged"

    m = MARKER_RE.search(existing)
    if not m:
        return "refuse: not generated by lee-llm-router"

    recorded_hash = m.group(1).lower()
    body_below = existing[m.end() :]
    actual_hash = hashlib.sha256(body_below.encode("utf-8")).hexdigest()
    if actual_hash != recorded_hash:
        return "refuse: not generated by lee-llm-router"

    return "update"


def install_shims(
    dry_run: bool = False,
    apply: bool = False,
    force: bool = False,
    harnesses: Sequence[str] | str | None = None,
    project: Path | str | None = None,
    home: Path | str | None = None,
) -> int:
    """Install shims for the selected harnesses.

    Returns 0 on success, 1 on refusal, 3 on usage error.
    """
    if (dry_run and apply) or (not dry_run and not apply):
        raise ShimUsageError("exactly one of --dry-run or --apply is required")

    targets = get_targets(project=project, home=home, harnesses=harnesses)

    if dry_run:
        for target in targets:
            action = inspect_target(target)
            print(f"target: {target.path}")
            print(f"action: {action}")
            print(target.content, end="" if target.content.endswith("\n") else "\n")
        return 0

    any_refused = False
    for target in targets:
        action = inspect_target(target)
        if action == "unchanged":
            print(f"unchanged: {target.path}")
        elif action == "create":
            target.path.parent.mkdir(parents=True, exist_ok=True)
            target.path.write_text(target.content, encoding="utf-8")
            print(f"create: {target.path}")
        elif action == "update":
            target.path.parent.mkdir(parents=True, exist_ok=True)
            target.path.write_text(target.content, encoding="utf-8")
            print(f"update: {target.path}")
        elif action == "refuse: not generated by lee-llm-router":
            if force:
                target.path.parent.mkdir(parents=True, exist_ok=True)
                target.path.write_text(target.content, encoding="utf-8")
                print(f"update: {target.path}")
            else:
                print(
                    f"refuse: not generated by lee-llm-router: {target.path}",
                    file=sys.stderr,
                )
                any_refused = True

    return 1 if any_refused else 0


def diff_shims(
    harnesses: Sequence[str] | str | None = None,
    project: Path | str | None = None,
    home: Path | str | None = None,
) -> int:
    """Show unified diff between installed shims and rendered templates.

    Returns 0 if no drift and none missing, 1 if drift or missing.
    """
    targets = get_targets(project=project, home=home, harnesses=harnesses)
    has_drift = False
    for target in targets:
        if not target.path.exists():
            print(f"missing: {target.path}")
            has_drift = True
            continue
        existing = target.path.read_text(encoding="utf-8")
        if existing == target.content:
            continue
        has_drift = True
        diff = difflib.unified_diff(
            existing.splitlines(keepends=True),
            target.content.splitlines(keepends=True),
            fromfile=str(target.path),
            tofile=f"{target.path} (rendered)",
        )
        sys.stdout.writelines(diff)
    return 1 if has_drift else 0
