"""Native expansion smoke tests for all five harnesses (D224-1).

Tests are marked with @pytest.mark.native and skipped unless
LEE_LLM_ROUTER_NATIVE_SMOKE=1 is set in the environment.

Each test creates a temporary isolated home/project, installs a throwaway
prompt template `argecho.md` with body:
    Reply with one line and nothing else: ARGS=<$ARGUMENTS>
and frontmatter matching that harness's shim format. It then invokes the
harness non-interactively with arguments and verifies the expansion.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

pytestmark = [
    pytest.mark.native,
    pytest.mark.skipif(
        os.environ.get("LEE_LLM_ROUTER_NATIVE_SMOKE") != "1",
        reason="Native expansion smokes require LEE_LLM_ROUTER_NATIVE_SMOKE=1",
    ),
]

TIMEOUT_SECONDS = 120
ARGECHO_BODY = "Reply with one line and nothing else: ARGS=<$ARGUMENTS>\n"
EXPECTED_ARG_TOKEN = "/tmp/plan-x.md auto"


@pytest.fixture(autouse=True)
def plan_x_file():
    """Ensure /tmp/plan-x.md exists so models checking file existence find it."""
    path = pathlib.Path("/tmp/plan-x.md")
    created = False
    if not path.exists():
        path.write_text("# Plan X\n", encoding="utf-8")
        created = True
    try:
        yield path
    finally:
        if created and path.exists():
            try:
                path.unlink()
            except OSError:
                pass


def test_native_smoke_claude(tmp_path):
    """Claude Code expands slash commands non-interactively via -p."""
    temp_home = tmp_path / "home"
    cmd_dir = temp_home / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "argecho.md").write_text(
        "---\n"
        "description: Echo arguments\n"
        "argument-hint: auto|NAME\n"
        "allowed-tools: Bash(lee-llm-router:*)\n"
        "---\n" + ARGECHO_BODY,
        encoding="utf-8",
    )

    real_claude = pathlib.Path.home() / ".claude"
    for f in [".credentials.json", "settings.json"]:
        if (real_claude / f).exists():
            os.symlink(real_claude / f, temp_home / ".claude" / f)

    env = os.environ.copy()
    env["HOME"] = str(temp_home)

    cmd = [
        "claude",
        "--model",
        "claude-haiku-4-5-20251001",
        "-p",
        f"/argecho {EXPECTED_ARG_TOKEN}",
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert (
        proc.returncode == 0
    ), f"Claude failed with exit {proc.returncode}: {proc.stderr}"
    assert (
        f"ARGS=<{EXPECTED_ARG_TOKEN}>" in proc.stdout
        or f"ARGS={EXPECTED_ARG_TOKEN}" in proc.stdout
    ), f"Unexpected Claude reply: {proc.stdout!r}"


def test_native_smoke_codex(tmp_path):
    """Codex expands custom prompts non-interactively via exec /prompts:name."""
    temp_home = tmp_path / "home"
    codex_home = temp_home / ".codex"
    cmd_dir = codex_home / "prompts"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "argecho.md").write_text(
        "---\n"
        "description: Echo arguments\n"
        "argument-hint: auto|NAME\n"
        "---\n" + ARGECHO_BODY,
        encoding="utf-8",
    )

    real_codex = pathlib.Path.home() / ".codex"
    for f in ["auth.json", "config.toml"]:
        if (real_codex / f).exists():
            os.symlink(real_codex / f, codex_home / f)

    env = os.environ.copy()
    env["HOME"] = str(temp_home)
    env["CODEX_HOME"] = str(codex_home)

    cmd = [
        "codex",
        "exec",
        f"/prompts:argecho {EXPECTED_ARG_TOKEN}",
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert (
        proc.returncode == 0
    ), f"Codex failed with exit {proc.returncode}: {proc.stderr}"
    assert (
        f"ARGS=<{EXPECTED_ARG_TOKEN}>" in proc.stdout
        or f"ARGS={EXPECTED_ARG_TOKEN}" in proc.stdout
    ), f"Unexpected Codex reply: {proc.stdout!r}"


def test_native_smoke_omp(tmp_path):
    """OMP expands prompt templates non-interactively via -p."""
    temp_proj = tmp_path / "project"
    cmd_dir = temp_proj / ".omp" / "prompts"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "argecho.md").write_text(
        "---\n"
        "description: Echo arguments\n"
        "argument-hint: auto|NAME\n"
        "---\n" + ARGECHO_BODY,
        encoding="utf-8",
    )

    cmd = [
        "omp",
        "-p",
        f"/argecho {EXPECTED_ARG_TOKEN}",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(temp_proj),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert (
        proc.returncode == 0
    ), f"OMP failed with exit {proc.returncode}: {proc.stderr}"
    assert (
        f"ARGS=<{EXPECTED_ARG_TOKEN}>" in proc.stdout
        or f"ARGS={EXPECTED_ARG_TOKEN}" in proc.stdout
    ), f"Unexpected OMP reply: {proc.stdout!r}"


def test_native_smoke_pi(tmp_path):
    """Pi expands prompt templates non-interactively via -p."""
    temp_home = tmp_path / "home"
    pi_agent = temp_home / ".pi" / "agent"
    cmd_dir = pi_agent / "prompts"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "argecho.md").write_text(
        "---\n"
        "description: Echo arguments\n"
        "argument-hint: auto|NAME\n"
        "---\n" + ARGECHO_BODY,
        encoding="utf-8",
    )

    real_agent = pathlib.Path.home() / ".pi" / "agent"
    for f in ["auth.json", "models-store.json", "settings.json"]:
        if (real_agent / f).exists():
            os.symlink(real_agent / f, pi_agent / f)

    env = os.environ.copy()
    env["HOME"] = str(temp_home)
    env["PI_CODING_AGENT_DIR"] = str(pi_agent)

    cmd = [
        "pi",
        "-p",
        f"/argecho {EXPECTED_ARG_TOKEN}",
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, f"Pi failed with exit {proc.returncode}: {proc.stderr}"
    assert (
        f"ARGS=<{EXPECTED_ARG_TOKEN}>" in proc.stdout
        or f"ARGS={EXPECTED_ARG_TOKEN}" in proc.stdout
    ), f"Unexpected Pi reply: {proc.stdout!r}"


def test_native_smoke_opencode(tmp_path):
    """OpenCode non-interactive expansion smoke via `run --command`."""
    temp_home = tmp_path / "home"
    cmd_dir = temp_home / ".config" / "opencode" / "command"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "argecho.md").write_text(
        "---\n---\n" + ARGECHO_BODY,
        encoding="utf-8",
    )

    (temp_home / ".local" / "share").mkdir(parents=True)
    os.symlink(
        os.path.expanduser("~/.local/share/opencode"),
        temp_home / ".local" / "share" / "opencode",
    )
    real_cfg = pathlib.Path.home() / ".config" / "opencode"
    for f in ["opencode.jsonc", "tui.json"]:
        if (real_cfg / f).exists():
            os.symlink(real_cfg / f, temp_home / ".config" / "opencode" / f)

    env = os.environ.copy()
    env["HOME"] = str(temp_home)

    # OpenCode's non-interactive form for a command file is
    # `opencode run --command <name> <message>`; the message is the
    # command's $ARGUMENTS (opencode run --help: "--command  the command to
    # run, use message for args"). A positional "/argecho ..." message is
    # plain chat to the agent and does not expand (recorded in
    # docs/staffing/shims-native-smoke.md).
    cmd = [
        "opencode",
        "run",
        "--command",
        "argecho",
        EXPECTED_ARG_TOKEN,
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )

    # Check if positional invocation expanded the template
    # OpenCode substitutes the whole message as one quoted string:
    # observed reply is ARGS=<"/tmp/plan-x.md auto">. The shim templates'
    # parsing rule strips that quote pair; the smoke accepts both forms.
    expanded = (
        f"ARGS=<{EXPECTED_ARG_TOKEN}>" in proc.stdout
        or f'ARGS=<"{EXPECTED_ARG_TOKEN}">' in proc.stdout
        or f"ARGS={EXPECTED_ARG_TOKEN}" in proc.stdout
    )
    assert expanded, (
        "OpenCode --command did not expand $ARGUMENTS; "
        f"exit={proc.returncode}, stdout={proc.stdout.strip()!r}, "
        f"stderr={proc.stderr.strip()[-400:]!r}"
    )
