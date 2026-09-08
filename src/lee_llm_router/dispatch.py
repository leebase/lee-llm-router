"""Worker dispatch and supervision with the stall watchdog.

Provides :func:`run_dispatch` to execute a resolved worker command, stream its
stdout/stderr, and supervise progress using :class:`StallWatchdog` and
:func:`run_supervised`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

from lee_llm_router.resolver import PROMPT_PLACEHOLDER, Resolution
from lee_llm_router.watchdog import (
    DEFAULT_MAX_MINUTES,
    DEFAULT_STALL_MINUTES,
    StallReport,
    StallWatchdog,
    run_supervised,
)


def _format_minutes(val: float) -> str:
    """Format minutes nicely for display: whole numbers as integers, else float."""
    r = round(val)
    if abs(val - r) < 0.05:
        return str(int(r))
    return f"{val:g}"


def build_argv(resolution: Resolution, prompt: str) -> list[str]:
    """Build the final child argv from the resolution and prompt.

    If prompt delivery is "argv", replaces the single `{prompt}` placeholder
    with the prompt text. Otherwise, returns a copy of the dispatch command.

    Args:
        resolution: The resolved worker.
        prompt: The prompt text to deliver.

    Returns:
        The argv list to pass to the child process.
    """
    if resolution.prompt_delivery == "argv":
        return [
            prompt if arg == PROMPT_PLACEHOLDER else arg
            for arg in resolution.dispatch_command
        ]
    return list(resolution.dispatch_command)


def run_dispatch(
    resolution: Resolution,
    prompt: str,
    *,
    stall_minutes: float = DEFAULT_STALL_MINUTES,
    max_minutes: float = DEFAULT_MAX_MINUTES,
    watch_dirs: Sequence[Path | str] = (),
    popen: Callable[..., Any] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = 0.5,
    sink: Callable[[bytes], None] | None = None,
    err_sink: Callable[[bytes], None] | None = None,
    read_chunk: Callable[[], bytes | None] | None = None,
    read_err_chunk: Callable[[], bytes | None] | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute a resolved worker harness and supervise it with StallWatchdog.

    Args:
        resolution: Resolved worker metadata.
        prompt: Prompt string to deliver.
        stall_minutes: Minutes of joint silence before flagging a stall.
        max_minutes: Wall-clock ceiling in minutes before killing the child.
        watch_dirs: Directories to monitor for file activity.
        popen: Process spawner callable (injected for tests).
        clock: Monotonic clock callable (injected for tests).
        sleep: Sleep callable (injected for tests).
        poll_seconds: Polling cadence for the watchdog loop.
        sink: Callable receiving child stdout byte chunks (defaults to
            stdout buffer).
        err_sink: Callable receiving child stderr byte chunks (defaults to
            stderr buffer).
        read_chunk: Callable returning child stdout byte chunks (defaults to
            reading child stdout).
        read_err_chunk: Callable returning child stderr byte chunks (defaults to
            reading child stderr).
        stderr: Stream for watchdog warnings and ceiling messages (defaults to
            sys.stderr).

    Returns:
        Exit code: 124 on ceiling timeout, otherwise child exit code.
    """
    argv = build_argv(resolution, prompt)
    target_err = stderr if stderr is not None else sys.stderr

    if sink is not None:
        sink_fn = sink
    else:

        def sink_fn(chunk: bytes) -> None:
            if not chunk:
                return
            stdout_buf = getattr(sys.stdout, "buffer", None)
            if stdout_buf is not None:
                stdout_buf.write(chunk)
                stdout_buf.flush()
            else:
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                sys.stdout.flush()

    if err_sink is not None:
        err_sink_fn = err_sink
    else:

        def err_sink_fn(chunk: bytes) -> None:
            if not chunk:
                return
            target_err_buf = getattr(target_err, "buffer", None)
            if target_err_buf is not None:
                target_err_buf.write(chunk)
                target_err_buf.flush()
            else:
                target_err.write(chunk.decode("utf-8", errors="replace"))
                target_err.flush()

    proc = popen(
        argv,
        stdin=subprocess.PIPE if resolution.prompt_delivery == "stdin" else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdin_thread: threading.Thread | None = None
    if resolution.prompt_delivery == "stdin":
        prompt_bytes = prompt.encode("utf-8") if isinstance(prompt, str) else prompt

        def _feed_stdin() -> None:
            try:
                proc.stdin.write(prompt_bytes)
                proc.stdin.flush()
            except OSError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        stdin_thread = threading.Thread(target=_feed_stdin, daemon=True)
        stdin_thread.start()

    if read_chunk is not None:
        read_stdout_fn = read_chunk
    else:
        os.set_blocking(proc.stdout.fileno(), False)

        def read_stdout_fn() -> bytes | None:
            try:
                chunk = proc.stdout.read(65536)
                return chunk if chunk else None
            except BlockingIOError:
                return None

    if read_err_chunk is not None:
        read_stderr_fn = read_err_chunk
    else:
        os.set_blocking(proc.stderr.fileno(), False)

        def read_stderr_fn() -> bytes | None:
            try:
                chunk = proc.stderr.read(65536)
                return chunk if chunk else None
            except BlockingIOError:
                return None

    def supervised_read() -> bytes | None:
        total = 0

        while True:
            chunk = read_stdout_fn()
            if not chunk:
                break
            sink_fn(chunk)
            total += len(chunk)

        while True:
            chunk = read_stderr_fn()
            if not chunk:
                break
            err_sink_fn(chunk)
            total += len(chunk)

        if total > 0:
            return bytes(total)
        return None

    def on_stall(report: StallReport) -> None:
        n_str = _format_minutes(stall_minutes)
        m_str = _format_minutes(report.elapsed_seconds / 60.0)
        max_str = _format_minutes(max_minutes)
        msg = (
            f"dispatch: no output and no file activity for {n_str} min "
            f"(worker {resolution.worker_id}, elapsed {m_str} min); "
            f"still waiting, ceiling {max_str} min\n"
        )
        target_err.write(msg)
        target_err.flush()

    watch_paths = [Path(p) for p in watch_dirs]
    stall_seconds = float(stall_minutes) * 60.0
    max_seconds = float(max_minutes) * 60.0

    watchdog = StallWatchdog(
        stall_seconds=stall_seconds,
        max_seconds=max_seconds,
        clock=clock,
        watch_dirs=watch_paths,
        on_stall=on_stall,
    )

    try:
        result = run_supervised(
            proc,
            watchdog,
            poll_seconds=poll_seconds,
            sleep=sleep,
            read_chunk=supervised_read,
            sink=lambda _chunk: None,
        )
    finally:
        if stdin_thread is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            stdin_thread.join(timeout=1.0)

    if result.killed:
        max_str = _format_minutes(max_minutes)
        target_err.write(f"dispatch: killed after {max_str} min ceiling\n")
        target_err.flush()
        return 124

    if result.exit_code is not None:
        return result.exit_code
    return 0
