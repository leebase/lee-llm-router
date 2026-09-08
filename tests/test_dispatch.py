"""Tests for :mod:`lee_llm_router.dispatch` and ``doctor dispatch`` CLI.

All tests here use synthetic crews YAML, synthetic availability snapshots,
fake processes, and fake clocks. No real provider binary is ever executed.
"""

import io
import json
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Sequence

import pytest

from lee_llm_router import doctor
from lee_llm_router.dispatch import build_argv, run_dispatch
from lee_llm_router.events import read_events
from lee_llm_router.resolver import Resolution

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

EFFORT_KEYS = {"CODEX": "REASONING_EFFORT"}

WORKERS: dict[str, tuple[str, str, str, str | None]] = {
    "codex_sol_high": ("CODEX", "/x/bin/codex", "gpt-5.6-sol", "high"),
    "codex_luna_max": ("CODEX", "/x/bin/codex", "gpt-5.6-luna", "max"),
    "claude_opus5_high": ("CLAUDE", "/x/bin/claude", "claude-opus-5", "high"),
    "claude_sonnet5_high": ("CLAUDE", "/x/bin/claude", "claude-sonnet-5", "high"),
    "antigravity_gemini38_flash_high": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.8-flash-high",
        "high",
    ),
    "antigravity_gemini31_pro": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.1-pro",
        "high",
    ),
    "antigravity_bad_effort": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.8-flash-high",
        "xhigh",
    ),
    "omp_glm_flash": ("OMP", "/x/bin/omp", "glm-5.3-flash", None),
}


def worker_command(prefix: str, binary: str, model: str, effort: str | None) -> str:
    """Render a crews-file command template for a synthetic worker."""
    parts = [
        "/usr/bin/env",
        f"{prefix}_STAGE_WORKER_BINARY={binary}",
        f"{prefix}_STAGE_WORKER_MODEL={model}",
    ]
    if effort is not None:
        key = EFFORT_KEYS.get(prefix, "EFFORT")
        parts.append(f"{prefix}_STAGE_WORKER_{key}={effort}")
    parts.append("python3 /x/stage_worker.py {stage}")
    return " ".join(parts)


CREWS_BLOCK = """
crews:
  dispatch-crew:
    description: Test crew for dispatch.
    stages:
      envision: [codex_sol_high]
      ideate: [omp_glm_flash]
      reconsider: [antigravity_gemini38_flash_high]
      score: [antigravity_gemini31_pro]
      author: [antigravity_gemini31_pro, codex_sol_high]
"""


def crews_yaml() -> str:
    """Render the synthetic crews file."""
    lines = ["version: 1", "", "workers:"]
    for worker_id, spec in WORKERS.items():
        lines.append(f"  {worker_id}:")
        lines.append(f'    command: "{worker_command(*spec)}"')
        lines.append("    timeout_seconds: 600")
    lines.extend(CREWS_BLOCK.splitlines())
    return "\n".join(lines) + "\n"


def _entry(
    provider: str,
    bucket: str,
    status: str,
    remaining_pct: float,
    *,
    resets_at: str | None = None,
    pace_ratio: float | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "provider": provider,
        "bucket": bucket,
        "status": status,
        "remaining_pct": remaining_pct,
    }
    if resets_at is not None:
        entry["resets_at"] = resets_at
    if pace_ratio is not None:
        entry["pace_ratio"] = pace_ratio
    return entry


def openai(status: str, remaining_pct: float, **kwargs: Any) -> dict[str, Any]:
    return _entry("OpenAI/Codex", "Weekly limit", status, remaining_pct, **kwargs)


def openrouter(status: str, remaining_pct: float, **kwargs: Any) -> dict[str, Any]:
    return _entry("OpenRouter", "Credits", status, remaining_pct, **kwargs)


def gemini(status: str, remaining_pct: float, **kwargs: Any) -> dict[str, Any]:
    return _entry("Gemini/agy", "Gemini models daily", status, remaining_pct, **kwargs)


def snap_json(*entries: dict[str, Any], observed_at: datetime | None = None) -> str:
    payload = {
        "observed_at": (observed_at or NOW).isoformat(),
        "host": "testhost",
        "subscriptions": list(entries),
    }
    return json.dumps(payload, indent=2)


HEALTHY = ("ON TRACK", 90.0)


@pytest.fixture
def test_env(tmp_path):
    """Set up crews.yaml, availability.json, and events.jsonl paths."""
    crews_file = tmp_path / "crews.yaml"
    crews_file.write_text(crews_yaml(), encoding="utf-8")

    snapshot_file = tmp_path / "availability.json"
    snapshot_file.write_text(
        snap_json(openai(*HEALTHY), openrouter(*HEALTHY), gemini(*HEALTHY)),
        encoding="utf-8",
    )

    events_file = tmp_path / "events.jsonl"
    return crews_file, snapshot_file, events_file


class FakeClock:
    """Controllable monotonic clock."""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


class FakePipeStream:
    """Pipe-backed stream conforming to real Popen.stdout/stderr."""

    def __init__(self, chunks: Sequence[bytes] = ()) -> None:
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        os.set_blocking(self._w, False)
        self._chunks: list[bytes] = []
        for c in chunks:
            if not c:
                continue
            for i in range(0, len(c), 65536):
                self._chunks.append(c[i : i + 65536])
        self._closed = False
        self._stream = open(self._r, "rb", buffering=0)

    def fileno(self) -> int:
        return self._stream.fileno()

    def read(self, n: int = 65536) -> bytes | None:
        try:
            chunk = self._stream.read(n)
        except BlockingIOError:
            chunk = None
        if not chunk and self._chunks:
            c = self._chunks.pop(0)
            os.write(self._w, c)
            try:
                chunk = self._stream.read(n)
            except BlockingIOError:
                chunk = None
        if not chunk and not self._chunks and not self._closed:
            try:
                os.close(self._w)
            except OSError:
                pass
            self._closed = True
        return chunk if chunk else None

    def close(self) -> None:
        if not self._closed:
            try:
                os.close(self._w)
            except OSError:
                pass
            self._closed = True
        try:
            self._stream.close()
        except OSError:
            pass


class FakeStdin:
    """Buffer simulating child stdin pipe."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False
        self._lock = threading.Lock()

    def write(self, b: bytes | str) -> int:
        if isinstance(b, str):
            b = b.encode("utf-8")
        with self._lock:
            self.data.extend(b)
        return len(b)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        with self._lock:
            self.closed = True

    def getvalue(self) -> bytes:
        with self._lock:
            return bytes(self.data)


class FakeProcess:
    """Fake child process conforming to the real Popen surface."""

    def __init__(
        self,
        argv: list[str],
        chunks: Sequence[bytes] = (),
        *,
        stderr_chunks: Sequence[bytes] = (),
        exit_code: int = 0,
        exit_after_ticks: int = 0,
        **_kwargs: Any,
    ) -> None:
        self.argv = list(argv)
        self.chunks = list(chunks)
        self.stdin = FakeStdin()
        self.stdout = FakePipeStream(chunks)
        self.stderr = FakePipeStream(stderr_chunks)
        self._exit_code = exit_code
        self._exit_after_ticks = exit_after_ticks
        self._ticks = 0
        self.killed = False
        self.kill_count = 0
        self.wait_calls: list[float] = []

    def poll(self) -> int | None:
        if self._ticks >= self._exit_after_ticks:
            return self._exit_code
        self._ticks += 1
        return None

    def kill(self) -> None:
        self.killed = True
        self.kill_count += 1
        self.stdout.close()
        self.stderr.close()

    def wait(self, timeout: float = 0.0) -> int:
        self.wait_calls.append(timeout)
        return -9 if self.killed else self._exit_code


# ---------------------------------------------------------------------------
# 1. --dry-run tests
# ---------------------------------------------------------------------------


def test_dry_run_argv_worker(test_env, capsys, monkeypatch):
    """--dry-run prints argv with {prompt} unsubstituted for argv worker, exit 0."""
    crews_file, snapshot_file, events_file = test_env

    constructed = []

    def fake_popen(*args, **kwargs):
        constructed.append(args)
        return FakeProcess(*args)

    monkeypatch.setattr("lee_llm_router.dispatch.run_dispatch", fake_popen)

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
                "--dry-run",
            ]
        )
    assert exc_info.value.code == 0
    assert len(constructed) == 0  # Nothing executed

    out = capsys.readouterr().out
    assert "worker: codex_sol_high" in out
    assert "{prompt}" in out
    assert "event: " in out


def test_dry_run_stdin_worker(test_env, capsys, monkeypatch):
    """--dry-run prints [prompt on stdin] for stdin worker, nothing executed, exit 0."""
    crews_file, snapshot_file, events_file = test_env

    constructed = []

    def fake_popen(*args, **kwargs):
        constructed.append(args)
        return FakeProcess(*args)

    monkeypatch.setattr("lee_llm_router.dispatch.run_dispatch", fake_popen)

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "ideate",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
                "--dry-run",
            ]
        )
    assert exc_info.value.code == 0
    assert len(constructed) == 0  # Nothing executed

    out = capsys.readouterr().out
    assert "worker: omp_glm_flash" in out
    assert "[prompt on stdin]" in out


# ---------------------------------------------------------------------------
# 2. argv worker vs stdin worker delivery
# ---------------------------------------------------------------------------


def test_argv_worker_receives_substituted_prompt(test_env, monkeypatch):
    """argv worker: fake popen receives argv with prompt substituted."""
    crews_file, snapshot_file, events_file = test_env

    created_procs: list[FakeProcess] = []

    def fake_popen(argv, **kwargs):
        proc = FakeProcess(argv, exit_code=0, exit_after_ticks=0)
        created_procs.append(proc)
        return proc

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "write a compiler",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    assert len(created_procs) == 1
    proc = created_procs[0]
    assert "{prompt}" not in proc.argv
    assert "write a compiler" in proc.argv


def test_stdin_worker_receives_prompt_bytes_on_stdin(test_env, monkeypatch):
    """stdin worker: fake receives the prompt bytes on stdin."""
    crews_file, snapshot_file, events_file = test_env

    created_procs: list[FakeProcess] = []

    def fake_popen(argv, **kwargs):
        proc = FakeProcess(argv, exit_code=0, exit_after_ticks=0)
        created_procs.append(proc)
        return proc

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "ideate",
                "--prompt",
                "stdin test prompt",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    assert len(created_procs) == 1
    proc = created_procs[0]
    assert proc.stdin.getvalue() == b"stdin test prompt"
    assert proc.stdin.closed is True


# ---------------------------------------------------------------------------
# 3. Child exit code and streaming chunks
# ---------------------------------------------------------------------------


def test_child_exit_code_and_chunk_streaming(test_env, capsys, monkeypatch):
    """child exits 7 -> exit 7; two chunks forwarded to stdout in order."""
    crews_file, snapshot_file, events_file = test_env

    chunks = [b"First chunk\n", b"Second chunk\n"]

    def fake_popen(argv, **kwargs):
        return FakeProcess(argv, chunks=chunks, exit_code=7, exit_after_ticks=2)

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "stream prompt",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 7
    captured = capsys.readouterr()
    assert captured.out == "First chunk\nSecond chunk\n"


# ---------------------------------------------------------------------------
# 4. Stall detection and recovery
# ---------------------------------------------------------------------------


def test_child_stalls_past_stall_minutes_and_recovers(test_env, capsys, monkeypatch):
    """child quiet past --stall-minutes -> stall line, continues, exit 0."""
    crews_file, snapshot_file, events_file = test_env

    clock = FakeClock(0.0)

    # 4 ticks silent: at 30s per tick, 60s passes -> stall line at t=60s.
    # At tick 3, process exits 0.
    def fake_popen(argv, **kwargs):
        return FakeProcess(argv, chunks=[], exit_code=0, exit_after_ticks=3)

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args,
            **dict(
                kwargs,
                popen=fake_popen,
                clock=clock,
                sleep=lambda _s: clock.advance(30.0),
                poll_seconds=0.5,
            ),
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "stall test",
                "--stall-minutes",
                "1",
                "--max-minutes",
                "120",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    expected_msg = (
        "dispatch: no output and no file activity for 1 min "
        "(worker codex_sol_high, elapsed 1 min); "
        "still waiting, ceiling 120 min"
    )
    assert expected_msg in captured.err


# ---------------------------------------------------------------------------
# 5. Ceiling kill
# ---------------------------------------------------------------------------


def test_child_killed_at_ceiling_exits_124(test_env, capsys, monkeypatch):
    """child never exits -> killed at --max-minutes -> exit 124, kill() called once."""
    crews_file, snapshot_file, events_file = test_env

    clock = FakeClock(0.0)
    created_procs: list[FakeProcess] = []

    def fake_popen(argv, **kwargs):
        proc = FakeProcess(argv, chunks=[], exit_code=0, exit_after_ticks=999999)
        created_procs.append(proc)
        return proc

    # Max minutes = 2 (120s). Advancing 30s per tick -> after 4 ticks ceiling reached.
    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args,
            **dict(
                kwargs,
                popen=fake_popen,
                clock=clock,
                sleep=lambda _s: clock.advance(30.0),
                poll_seconds=0.5,
            ),
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "ceiling test",
                "--stall-minutes",
                "10",
                "--max-minutes",
                "2",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 124
    assert len(created_procs) == 1
    proc = created_procs[0]
    assert proc.killed is True
    assert proc.kill_count == 1
    captured = capsys.readouterr()
    assert "dispatch: killed after 2 min ceiling" in captured.err


# ---------------------------------------------------------------------------
# 6. Prompt usage errors
# ---------------------------------------------------------------------------


def test_both_prompt_and_prompt_file_exits_3(test_env, capsys, tmp_path):
    """both --prompt and --prompt-file -> exit 3."""
    crews_file, snapshot_file, events_file = test_env
    p_file = tmp_path / "prompt.txt"
    p_file.write_text("prompt from file", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "cli prompt",
                "--prompt-file",
                str(p_file),
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "cannot specify both --prompt and --prompt-file" in captured.err


def test_no_prompt_and_stdin_is_tty_exits_3(test_env, capsys, monkeypatch):
    """no prompt and stdin is a TTY (monkeypatch sys.stdin.isatty) -> exit 3."""
    crews_file, snapshot_file, events_file = test_env
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "prompt required" in captured.err


def test_empty_prompt_exits_3(test_env, capsys):
    """Empty prompt -> exit 3."""
    crews_file, snapshot_file, events_file = test_env

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "   ",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "prompt is empty" in captured.err


# ---------------------------------------------------------------------------
# 7. Refusal (forbidden worker)
# ---------------------------------------------------------------------------


def test_refusal_forbidden_worker_exits_3_and_never_constructs_popen(
    test_env, capsys, monkeypatch
):
    """refusal (forbidden worker) -> exit 3 and fake popen was never constructed."""
    crews_file, snapshot_file, events_file = test_env

    constructed = []

    def fake_popen(*args, **kwargs):
        constructed.append(args)
        return FakeProcess(*args)

    monkeypatch.setattr("lee_llm_router.dispatch.run_dispatch", fake_popen)

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "score",  # resolves to antigravity_gemini31_pro (forbidden)
                "--prompt",
                "hello",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 3
    assert len(constructed) == 0
    captured = capsys.readouterr()
    assert "gemini-3.1-pro" in captured.err
    assert "decisions.md D152/D153" in captured.err


# ---------------------------------------------------------------------------
# 8. Event ledger writing: exactly one on success, none on refusal
# ---------------------------------------------------------------------------


def test_event_ledger_written_once_on_success_none_on_refusal(test_env, monkeypatch):
    """exactly one event line written for a successful run; none for a refusal."""
    crews_file, snapshot_file, events_file = test_env

    def fake_popen(argv, **kwargs):
        return FakeProcess(argv, exit_code=0, exit_after_ticks=0)

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    # 1. Refusal run
    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "score",
                "--prompt",
                "hello",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 3
    assert not events_file.exists()

    # 2. Successful run
    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "hello",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    events = read_events(events_file)
    assert len(events) == 1
    assert events[0]["crew"] == "dispatch-crew"
    assert events[0]["role"] == "envision"
    assert events[0]["worker_id"] == "codex_sol_high"


# ---------------------------------------------------------------------------
# 9. Additional prompt sources and direct unit tests
# ---------------------------------------------------------------------------


def test_prompt_from_file(test_env, tmp_path, monkeypatch):
    """Prompt read from --prompt-file."""
    crews_file, snapshot_file, events_file = test_env
    p_file = tmp_path / "prompt.txt"
    p_file.write_text("file prompt content", encoding="utf-8")

    created_procs = []

    def fake_popen(argv, **kwargs):
        proc = FakeProcess(argv, exit_code=0, exit_after_ticks=0)
        created_procs.append(proc)
        return proc

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt-file",
                str(p_file),
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    assert len(created_procs) == 1
    assert "file prompt content" in created_procs[0].argv


def test_prompt_from_stdin(test_env, monkeypatch):
    """Prompt read from stdin when neither flag given and stdin is not a TTY."""
    crews_file, snapshot_file, events_file = test_env

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: "piped stdin content\n")

    created_procs = []

    def fake_popen(argv, **kwargs):
        proc = FakeProcess(argv, exit_code=0, exit_after_ticks=0)
        created_procs.append(proc)
        return proc

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    assert len(created_procs) == 1
    assert "piped stdin content\n" in created_procs[0].argv


def test_build_argv_helper():
    """Unit test build_argv logic."""
    res_argv = Resolution(
        crew="c",
        role="r",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin", "--flag", "{prompt}"],
        prompt_delivery="argv",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )
    assert build_argv(res_argv, "my prompt") == ["bin", "--flag", "my prompt"]

    res_stdin = Resolution(
        crew="c",
        role="r",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin", "--flag"],
        prompt_delivery="stdin",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )
    assert build_argv(res_stdin, "my prompt") == ["bin", "--flag"]


def test_no_event_suppresses_event_ledger_write(test_env, monkeypatch):
    """--no-event flag suppresses appending to the event ledger."""
    crews_file, snapshot_file, events_file = test_env

    def fake_popen(argv, **kwargs):
        return FakeProcess(argv, exit_code=0, exit_after_ticks=0)

    monkeypatch.setattr(
        "lee_llm_router.dispatch.run_dispatch",
        lambda *args, **kwargs: run_dispatch(
            *args, **dict(kwargs, popen=fake_popen, sleep=lambda _s: None)
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "dispatch-crew",
                "--role",
                "envision",
                "--prompt",
                "no event prompt",
                "--no-event",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
            ]
        )
    assert exc_info.value.code == 0
    assert not events_file.exists()


def test_watch_dir_activity_prevents_stall(tmp_path):
    """Activity in watch directory resets stall timer, preventing stall warning."""
    clock = FakeClock(0.0)
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()
    watched_file = watch_dir / "output.log"
    watched_file.write_text("initial", encoding="utf-8")

    proc = FakeProcess(["bin"], chunks=[], exit_code=0, exit_after_ticks=3)

    def sleep_and_touch(_s):
        clock.advance(40.0)
        # Touch watched file with new content to signal activity at t=40 and t=80
        watched_file.write_text(f"activity at {clock.value}", encoding="utf-8")

    err_buf = io.StringIO()
    res = Resolution(
        crew="c",
        role="r",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin"],
        prompt_delivery="argv",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )

    code = run_dispatch(
        res,
        "prompt",
        stall_minutes=1.0,  # 60s
        max_minutes=10.0,
        watch_dirs=[watch_dir],
        popen=lambda *args, **kwargs: proc,
        clock=clock,
        sleep=sleep_and_touch,
        stderr=err_buf,
    )
    assert code == 0
    assert "dispatch: no output and no file activity" not in err_buf.getvalue()


# ---------------------------------------------------------------------------
# 10. Packet P26 Contracts: Stdin Deadlock, Stderr Streaming, Seams, Drain
# ---------------------------------------------------------------------------


def test_contract1_stdin_delivery_300kb_real_cat(capsys):
    """Contract 1: 300 KB prompt delivered to /bin/cat on stdin without deadlock."""
    res = Resolution(
        crew="test-crew",
        role="envision",
        mode="strict",
        worker_id="cat_worker",
        provider="omp_cli",
        model="some-model",
        effort=None,
        channel="openrouter",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="omp:some-model",
        dispatch_command=["/bin/cat"],
        prompt_delivery="stdin",
        worker_command="/bin/cat",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )
    prompt = "A" * 300_000
    exit_code = run_dispatch(res, prompt)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert len(captured.out) == 300_000
    assert captured.out == prompt


def test_contract1_stdin_delivery_fake_process_deadlock_prevention():
    """Contract 1: Fake process emits stdout only after consuming N bytes of stdin."""
    consumed = bytearray()
    chunks = [b"response-chunk\n"]

    class BlockingUntilConsumedStdin:
        def __init__(self) -> None:
            self._lock = threading.Lock()
            self._all_written = threading.Event()
            self.closed = False

        def write(self, b: bytes) -> int:
            with self._lock:
                consumed.extend(b)
                if len(consumed) >= 150_000:
                    self._all_written.set()
            return len(b)

        def flush(self) -> None:
            pass

        def close(self) -> None:
            with self._lock:
                self.closed = True

    class DeadlockTestProcess:
        def __init__(self, argv: list[str], **_kwargs: Any) -> None:
            self.argv = argv
            self.stdin = BlockingUntilConsumedStdin()
            self._r_out, self._w_out = os.pipe()
            self._r_err, self._w_err = os.pipe()
            os.set_blocking(self._r_out, False)
            os.set_blocking(self._w_out, False)
            os.set_blocking(self._r_err, False)
            os.set_blocking(self._w_err, False)
            self.stdout = open(self._r_out, "rb", buffering=0)
            self.stderr = open(self._r_err, "rb", buffering=0)
            self._ticks = 0

        def poll(self) -> int | None:
            if self.stdin._all_written.is_set():
                if chunks:
                    os.write(self._w_out, chunks.pop(0))
                else:
                    try:
                        os.close(self._w_out)
                    except OSError:
                        pass
                if self._ticks >= 1:
                    return 0
                self._ticks += 1
            return None

        def kill(self) -> None:
            pass

        def wait(self, timeout: float = 0.0) -> int:
            return 0

    res = Resolution(
        crew="test-crew",
        role="envision",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin"],
        prompt_delivery="stdin",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )

    out_captured = bytearray()
    clock = FakeClock(0.0)

    exit_code = run_dispatch(
        res,
        "Y" * 150_000,
        popen=lambda argv, **kw: DeadlockTestProcess(argv, **kw),
        clock=clock,
        sleep=lambda _s: clock.advance(1.0),
        sink=lambda c: out_captured.extend(c),
    )
    assert exit_code == 0
    assert bytes(out_captured) == b"response-chunk\n"
    assert len(consumed) == 150_000


def test_contract2_separate_stdout_and_stderr_streaming_fake(capsys):
    """Contract 2: stdout -> parent stdout, stderr -> parent stderr."""
    clock = FakeClock(0.0)
    stdout_chunks = [b"stdout line 1\n", b"stdout line 2\n"]
    stderr_chunks = [b"stderr line 1\n", b"stderr line 2\n"]

    proc = FakeProcess(
        ["bin"],
        chunks=stdout_chunks,
        stderr_chunks=stderr_chunks,
        exit_code=0,
        exit_after_ticks=2,
    )

    res = Resolution(
        crew="c",
        role="r",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin"],
        prompt_delivery="argv",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )

    code = run_dispatch(
        res,
        "prompt",
        popen=lambda *a, **kw: proc,
        clock=clock,
        sleep=lambda _s: clock.advance(1.0),
    )
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == "stdout line 1\nstdout line 2\n"
    assert captured.err == "stderr line 1\nstderr line 2\n"


def test_contract2_separate_stdout_and_stderr_real_bash_scratch_crews(tmp_path, capsys):
    """Contract 2: bash echoes out to stdout, err to stderr, exit 3."""
    script = tmp_path / "echo_bash.sh"
    script.write_text("#!/bin/bash\n/bin/bash -c 'echo out; echo err 1>&2; exit 3'\n")
    script.chmod(0o755)

    cmd_str = (
        f"/usr/bin/env OMP_STAGE_WORKER_BINARY={script} "
        "OMP_STAGE_WORKER_MODEL=some-model python3 x.py {stage}"
    )
    crews_content = f"""version: 1
workers:
  bash_worker:
    command: "{cmd_str}"
    timeout_seconds: 60
crews:
  bash-crew:
    description: Bash test crew.
    stages:
      envision: [bash_worker]
"""
    crews_file = tmp_path / "crews.yaml"
    crews_file.write_text(crews_content, encoding="utf-8")

    snapshot_file = tmp_path / "availability.json"
    snapshot_file.write_text(
        snap_json(openai(*HEALTHY), openrouter(*HEALTHY), gemini(*HEALTHY)),
        encoding="utf-8",
    )

    events_file = tmp_path / "events.jsonl"

    with pytest.raises(SystemExit) as exc_info:
        doctor.main(
            [
                "dispatch",
                "--crew",
                "bash-crew",
                "--role",
                "envision",
                "--prompt",
                "test prompt",
                "--crews-file",
                str(crews_file),
                "--availability-file",
                str(snapshot_file),
                "--events-file",
                str(events_file),
                "--no-event",
            ]
        )
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == "out\n"
    assert "err\n" in captured.err


def test_contract3_declared_seams_custom_readers_and_sinks():
    """Contract 3: custom read_chunk, read_err_chunk, sink, err_sink seams."""
    out_received = []
    err_received = []

    def custom_read_chunk():
        if not out_received:
            return b"custom-stdout"
        return None

    def custom_read_err_chunk():
        if not err_received:
            return b"custom-stderr"
        return None

    class MinimalProcess:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self._polled = 0

        def poll(self):
            if self._polled >= 1:
                return 0
            self._polled += 1
            return None

        def kill(self):
            pass

        def wait(self, timeout=0.0):
            return 0

    res = Resolution(
        crew="c",
        role="r",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin"],
        prompt_delivery="argv",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )

    code = run_dispatch(
        res,
        "prompt",
        popen=lambda *a, **kw: MinimalProcess(*a, **kw),
        read_chunk=custom_read_chunk,
        read_err_chunk=custom_read_err_chunk,
        sink=lambda c: out_received.append(c),
        err_sink=lambda c: err_received.append(c),
        sleep=lambda _s: None,
    )
    assert code == 0
    assert out_received == [b"custom-stdout"]
    assert err_received == [b"custom-stderr"]


def test_contract5_final_drain_forwards_all_buffered_output_on_exit():
    """Contract 5: child writes 1 MB then exits; all buffered output forwarded."""
    one_mb = b"Z" * 1_000_000

    proc = FakeProcess(
        ["bin"],
        chunks=[one_mb],
        exit_code=0,
        exit_after_ticks=0,
    )

    res = Resolution(
        crew="c",
        role="r",
        mode="strict",
        worker_id="w",
        provider="p",
        model="m",
        effort=None,
        channel="ch",
        headroom="healthy",
        headroom_remaining_fraction=1.0,
        pace_ratio=None,
        reason="reason",
        authorized_by=None,
        route_id="r:m:e",
        dispatch_command=["bin"],
        prompt_delivery="argv",
        worker_command="cmd",
        snapshot_observed_at=None,
        snapshot_stale=False,
    )

    forwarded = bytearray()
    code = run_dispatch(
        res,
        "prompt",
        popen=lambda *a, **kw: proc,
        sink=lambda c: forwarded.extend(c),
        sleep=lambda _s: None,
    )
    assert code == 0
    assert len(forwarded) == 1_000_000
    assert bytes(forwarded) == one_mb
