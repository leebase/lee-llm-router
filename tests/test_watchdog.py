"""Tests for :mod:`lee_llm_router.watchdog`.

Everything here is deterministic: a hand-rolled fake clock stands in for wall
time and a hand-rolled fake ``Popen``-alike stands in for a real subprocess.
No test sleeps for real, so the whole file must run in well under a second.
"""

from __future__ import annotations

from lee_llm_router.watchdog import (
    ActivitySignature,
    StallReport,
    StallWatchdog,
    Verdict,
    run_supervised,
    scan_watch_dirs,
)


class FakeClock:
    """A clock whose value only changes when the test tells it to."""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


class FakePopen:
    """A ``popen_like`` stand-in with fully scripted exit behaviour."""

    def __init__(self, *, exit_code: int | None = None, wait_result: int = 0) -> None:
        self._exit_code = exit_code
        self._wait_result = wait_result
        self.killed = False
        self.wait_calls: list[float] = []

    def poll(self) -> int | None:
        return self._exit_code

    def set_exit_code(self, code: int) -> None:
        self._exit_code = code

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float) -> int:
        self.wait_calls.append(timeout)
        return self._wait_result


# ---------------------------------------------------------------------------
# ActivitySignature
# ---------------------------------------------------------------------------


def test_activity_signature_equality_means_no_activity():
    a = ActivitySignature(output_bytes=10, watch_signature=(("f", 1, 2),))
    b = ActivitySignature(output_bytes=10, watch_signature=(("f", 1, 2),))
    c = ActivitySignature(output_bytes=11, watch_signature=(("f", 1, 2),))
    assert a == b
    assert a != c


# ---------------------------------------------------------------------------
# scan_watch_dirs
# ---------------------------------------------------------------------------


def test_scan_watch_dirs_missing_directory_returns_empty():
    assert scan_watch_dirs([]) == ()


def test_scan_watch_dirs_nonexistent_dir_does_not_raise(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert scan_watch_dirs([missing]) == ()


def test_scan_watch_dirs_two_files_sorted_and_detects_change(tmp_path):
    (tmp_path / "b.txt").write_text("hello")
    (tmp_path / "a.txt").write_text("hi")

    first = scan_watch_dirs([tmp_path])
    assert len(first) == 2
    # Sorted by relative path: "a.txt" sorts before "b.txt".
    assert first[0][0] == "a.txt"
    assert first[1][0] == "b.txt"

    # Touching one file with a new size changes the signature.
    (tmp_path / "b.txt").write_text("hello, much longer now")
    second = scan_watch_dirs([tmp_path])
    assert second != first
    assert len(second) == 2


# ---------------------------------------------------------------------------
# StallWatchdog.observe — silence / stall boundary
# ---------------------------------------------------------------------------


def test_silence_static_stalls_at_exactly_stall_seconds():
    clock = FakeClock(0.0)
    wd = StallWatchdog(stall_seconds=5.0, max_seconds=1000.0, clock=clock)

    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE  # first tick

    clock.advance(5.0)
    assert wd.observe(output_bytes_total=0) is Verdict.STALLED
    assert wd.stalled is True


def test_silence_static_just_under_threshold_continues():
    clock = FakeClock(0.0)
    wd = StallWatchdog(stall_seconds=5.0, max_seconds=1000.0, clock=clock)

    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE

    clock.advance(4.999)
    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE
    assert wd.stalled is False


def test_watch_dir_change_resets_stall_timer(tmp_path):
    log_file = tmp_path / "out.log"
    log_file.write_text("a")

    clock = FakeClock(0.0)
    wd = StallWatchdog(
        stall_seconds=5.0, max_seconds=1000.0, clock=clock, watch_dirs=[tmp_path]
    )
    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE  # t=0, baseline

    clock.advance(4.0)  # t=4, one second shy of stalling
    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE

    # The file changes size — activity, timer resets.
    log_file.write_text("a much longer line of output")
    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE
    assert wd.last_activity_at == 4.0

    clock.advance(4.0)  # t=8; without the reset this would already be stalled
    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE

    clock.advance(1.0)  # t=9, 5s silent since the reset at t=4
    assert wd.observe(output_bytes_total=0) is Verdict.STALLED


def test_output_growth_with_static_files_continues_despite_long_gap():
    clock = FakeClock(0.0)
    wd = StallWatchdog(stall_seconds=5.0, max_seconds=1000.0, clock=clock)

    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE

    clock.advance(50.0)  # far past stall_seconds
    verdict = wd.observe(output_bytes_total=100)  # but bytes grew this tick
    assert verdict is Verdict.CONTINUE
    assert wd.stalled is False


def test_on_stall_fires_once_per_episode_then_again_after_recovery():
    reports: list[StallReport] = []
    clock = FakeClock(0.0)
    wd = StallWatchdog(
        stall_seconds=3.0,
        max_seconds=1000.0,
        clock=clock,
        on_stall=reports.append,
    )

    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE  # t=0

    clock.advance(3.0)
    assert wd.observe(output_bytes_total=0) is Verdict.STALLED  # first stall
    assert len(reports) == 1
    assert reports[0].output_bytes_total == 0

    clock.advance(1.0)
    assert wd.observe(output_bytes_total=0) is Verdict.STALLED  # still stalled
    assert len(reports) == 1  # no re-fire

    # Activity resumes.
    clock.advance(0.1)
    assert wd.observe(output_bytes_total=10) is Verdict.CONTINUE
    assert len(reports) == 1

    # A fresh stall episode begins.
    clock.advance(3.0)
    assert wd.observe(output_bytes_total=10) is Verdict.STALLED
    assert len(reports) == 2


# ---------------------------------------------------------------------------
# StallWatchdog.observe — ceiling
# ---------------------------------------------------------------------------


def test_ceiling_reached_while_active_kills_not_continues():
    clock = FakeClock(0.0)
    wd = StallWatchdog(stall_seconds=1000.0, max_seconds=5.0, clock=clock)

    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE  # t=0
    clock.advance(1.0)
    assert wd.observe(output_bytes_total=1) is Verdict.CONTINUE  # t=1, active

    clock.advance(4.0)  # t=5: ceiling
    verdict = wd.observe(output_bytes_total=2)  # still active this tick
    assert verdict is Verdict.KILLED


def test_ceiling_reached_while_stalled_kills_not_stalled():
    clock = FakeClock(0.0)
    wd = StallWatchdog(stall_seconds=2.0, max_seconds=5.0, clock=clock)

    assert wd.observe(output_bytes_total=0) is Verdict.CONTINUE  # t=0
    clock.advance(2.0)
    assert wd.observe(output_bytes_total=0) is Verdict.STALLED  # t=2

    clock.advance(3.0)  # t=5: ceiling, while still silent
    verdict = wd.observe(output_bytes_total=0)
    assert verdict is Verdict.KILLED


# ---------------------------------------------------------------------------
# run_supervised
# ---------------------------------------------------------------------------


def test_run_supervised_never_exits_is_killed_at_ceiling():
    clock = FakeClock(0.0)
    watchdog = StallWatchdog(stall_seconds=1000.0, max_seconds=5.0, clock=clock)
    popen = FakePopen(exit_code=None, wait_result=-9)

    result = run_supervised(
        popen,
        watchdog,
        poll_seconds=1.0,
        sleep=clock.advance,
        read_chunk=lambda: b"",
    )

    assert result.killed is True
    assert result.exit_code == -9
    assert popen.killed is True


def test_run_supervised_stalls_then_recovers_and_exits_cleanly():
    clock = FakeClock(0.0)
    watchdog = StallWatchdog(stall_seconds=3.0, max_seconds=1000.0, clock=clock)
    popen = FakePopen(exit_code=None)

    # Three silent ticks (enough to cross stall_seconds=3 at poll_seconds=1),
    # then a chunk of real output, then the process reports exit 0.
    chunks = [b"", b"", b"", b"", b"data"]
    call_count = {"n": 0}

    def read_chunk():
        n = call_count["n"]
        call_count["n"] += 1
        if n < len(chunks):
            return chunks[n]
        return b""

    def poll():
        # Exit only once the "data" chunk has been consumed.
        return 0 if call_count["n"] >= 5 else None

    popen.poll = poll  # type: ignore[assignment]

    sunk: list[bytes] = []
    result = run_supervised(
        popen,
        watchdog,
        poll_seconds=1.0,
        sleep=clock.advance,
        read_chunk=read_chunk,
        sink=sunk.append,
    )

    assert result.stalled is True
    assert result.killed is False
    assert result.exit_code == 0
    assert sunk == [b"data"]
    assert result.output_bytes_total == len(b"data")
