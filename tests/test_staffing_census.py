"""Tests for the P3-4 live run registry and census (D213 ruling 4).

Contract under test (``docs/staffing/phase3-contracts.md`` §D213 rulings,
ruling 4): a run registers pid, route, packet id, owned paths, and start
under the state directory; an intersecting live run is refused; ``census``
lists live rows and cleans stale pids with a note; parallel work is
permitted only for disjoint owned paths.

All registry operations here are deterministic: fake pids and fake process
identities are injected through the census module's seams
(``_PID_ALIVE``/``_PROCESS_IDENTITY``), every registry directory is a
scratch ``tmp_path`` directory, and concurrency is exercised with real
threads against the real ``flock`` boundary so check-and-register
serialization is the committed behavior, not a test double.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from lee_llm_router.providers.base import LLMRouterError
from lee_llm_router.staffing import census
from lee_llm_router.staffing.census import (
    ProcessIdentity,
    RegistryConflictError,
    RunRegistryError,
    census_registry,
    deregister_run,
    normalize_owned_path,
    normalize_owned_paths,
    paths_intersect,
    register_run,
)


class FakeProcesses:
    """Deterministic fake process table behind the census identity seams.

    ``start_times`` maps a pid to the start time the seams report for it;
    a pid listed in ``dead`` reports as not alive with no identity, which
    is exactly how census sees an exited process.
    """

    def __init__(self) -> None:
        self.start_times: dict[int, int] = {}
        self.dead: set[int] = set()

    def alive(self, pid: int) -> bool:
        return isinstance(pid, int) and pid > 0 and pid not in self.dead

    def identity(self, pid: int) -> ProcessIdentity | None:
        if not self.alive(pid):
            return None
        return ProcessIdentity(
            kind="linux_start_time", start_time=self.start_times.get(pid, 1000 + pid)
        )


@pytest.fixture
def fake_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeProcesses:
    """Wire every census liveness/identity read to one fake process table."""
    fake = FakeProcesses()
    monkeypatch.setattr(census, "_PID_ALIVE", fake.alive)
    monkeypatch.setattr(census, "_PROCESS_IDENTITY", fake.identity)
    return fake


@pytest.fixture
def registry_dir(tmp_path: Path) -> Path:
    """Scratch per-host registry directory (explicitly passed, no env)."""
    return tmp_path / "registry"


def _register(
    registry_dir: Path,
    *,
    pid: int,
    owned: list[str],
    route_id: str = "route-a",
    packet_id: str = "sha256:packet",
) -> census.RunRegistryRecord:
    """Register one run; the identity comes from the fake process seams."""
    return register_run(
        route_id=route_id,
        packet_id=packet_id,
        owned_paths=owned,
        pid=pid,
        registry_dir=registry_dir,
    )


# ---------------------------------------------------------------------------
# Owned-path normalization and intersection
# ---------------------------------------------------------------------------


def test_normalize_owned_paths_resolves_relative_against_workdir(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    normalized = normalize_owned_paths(
        ["src/a.py", "src/a.py", f"{workdir}/src/b.py"], workdir=workdir
    )
    assert normalized == (
        os.path.realpath(str(workdir / "src/a.py")),
        os.path.realpath(str(workdir / "src/b.py")),
    )


def test_normalize_owned_path_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert normalize_owned_paths(["x.py"]) == (
        os.path.realpath(str(tmp_path / "x.py")),
    )


def test_normalize_owned_path_resolves_existing_symlink_prefix(tmp_path):
    # Real directory plus a symlink pointing at it: both spellings must
    # normalize equal, because the prefix exists and is safe to resolve.
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(real, link)
    assert normalize_owned_paths([str(link / "f.py"), str(real / "f.py")]) == (
        os.path.realpath(str(real / "f.py")),
    )


def test_normalize_owned_path_keeps_nonexistent_tail_lexical(tmp_path):
    # A nonexistent target is never followed: the tail is only normalized
    # lexically on top of the deepest existing prefix.
    base = tmp_path / "base"
    base.mkdir()
    normalized = normalize_owned_path(str(base / "missing/../out.py"))
    assert normalized == os.path.realpath(str(base / "out.py"))


def test_normalize_owned_paths_refuses_empty_and_blank():
    with pytest.raises(RunRegistryError) as empty:
        normalize_owned_paths([])
    assert "cannot prove disjointness" in str(empty.value)
    with pytest.raises(RunRegistryError):
        normalize_owned_paths(["   "])


def test_paths_intersect_equality_ancestor_descendant():
    assert paths_intersect("/a/b", "/a/b")
    assert paths_intersect("/a/b", "/a/b/c.py")  # ancestor of file
    assert paths_intersect("/a/b/c.py", "/a/b")  # descendant of dir
    assert paths_intersect("/a/b", "/a/b/c/d")
    assert not paths_intersect("/a/b", "/a/bc")  # component boundary
    assert not paths_intersect("/a/b/one.py", "/a/b/two.py")
    assert not paths_intersect("/a/b", "/x/y")


# ---------------------------------------------------------------------------
# Registration, census listing, stale cleanup, pid reuse
# ---------------------------------------------------------------------------


def test_register_run_writes_record_census_lists_it(registry_dir, fake_processes):
    record = _register(registry_dir, pid=4242, owned=["/work/one"])
    assert record.pid == 4242
    assert record.owned_paths == ("/work/one",)
    assert record.route_id == "route-a"
    assert record.packet_id == "sha256:packet"
    assert record.path is not None and record.path.is_file()
    payload = json_loads(record.path)
    assert payload["record_kind"] == "run_registry"
    assert payload["identity"] == {
        "kind": "linux_start_time",
        "start_time": 1000 + 4242,
    }
    assert payload["started_at"]

    result = census_registry(registry_dir=registry_dir)
    assert [r.pid for r in result.live] == [4242]
    assert result.cleaned == ()
    assert result.live[0].owned_paths == ("/work/one",)


def json_loads(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def test_register_run_refuses_empty_owned_paths(registry_dir, fake_processes):
    with pytest.raises(RunRegistryError):
        register_run(
            route_id="route-a",
            packet_id="sha256:packet",
            owned_paths=[],
            pid=4242,
            registry_dir=registry_dir,
        )
    assert not any(registry_dir.glob("*.json"))


def test_register_run_refuses_intersecting_live_run(registry_dir, fake_processes):
    _register(registry_dir, pid=1001, owned=["/work/tree"])
    for candidate in ("/work/tree", "/work/tree/inner.py", "/work"):
        with pytest.raises(RegistryConflictError) as exc:
            register_run(
                route_id="route-b",
                packet_id="sha256:other",
                owned_paths=[candidate, "/elsewhere"],
                pid=1002,
                registry_dir=registry_dir,
            )
        conflict = exc.value.conflicts[0]
        assert conflict[0] == 1001
        if candidate != "/work":
            assert candidate in conflict[3]
        # The refusing run never registers: exactly one record remains.
        assert len(list(registry_dir.glob("*.json"))) == 1


def test_register_run_accepts_disjoint_runs(registry_dir, fake_processes):
    _register(registry_dir, pid=1001, owned=["/work/tree"])
    record = register_run(
        route_id="route-b",
        packet_id="sha256:other",
        owned_paths=["/work/other-tree", "/elsewhere"],
        pid=1002,
        registry_dir=registry_dir,
    )
    assert record.pid == 1002
    result = census_registry(registry_dir=registry_dir)
    assert sorted(r.pid for r in result.live) == [1001, 1002]
    assert result.cleaned == ()


def test_census_cleans_stale_pid_record_with_note(registry_dir, fake_processes):
    record = _register(registry_dir, pid=4242, owned=["/work/one"])
    # Prove the process incarnation is gone: the pid no longer exists.
    fake_processes.dead.add(4242)
    result = census_registry(registry_dir=registry_dir)
    assert result.live == ()
    assert len(result.cleaned) == 1
    assert result.cleaned[0].record.registry_id == record.registry_id
    assert "no longer exists" in result.cleaned[0].reason
    assert not record.path.exists()


def test_census_detects_pid_reuse_by_start_time(registry_dir, fake_processes):
    record = _register(registry_dir, pid=4242, owned=["/work/one"])
    # The pid exists again but belongs to a new incarnation: the start time
    # now reported for that pid differs from the recorded one, so the record
    # is stale even though the pid is alive.
    fake_processes.start_times[4242] = 999
    result = census_registry(registry_dir=registry_dir)
    assert result.live == ()
    assert len(result.cleaned) == 1
    assert "reused" in result.cleaned[0].reason
    assert not record.path.exists()


def test_census_keeps_record_when_start_time_cannot_be_verified(
    registry_dir, monkeypatch, fake_processes
):
    record = _register(registry_dir, pid=4242, owned=["/work/one"])
    # Conservative portable fallback: when no start-time evidence can be
    # read for the still-existing pid, the record is kept, not deleted.
    monkeypatch.setattr(census, "_PROCESS_IDENTITY", lambda pid: None)
    result = census_registry(registry_dir=registry_dir)
    assert [r.registry_id for r in result.live] == [record.registry_id]
    assert result.cleaned == ()


def test_census_never_deletes_replacement_record(registry_dir, fake_processes):
    # pid 4242's first incarnation registered a record; the pid was then
    # reused by a new incarnation whose own run registered a replacement
    # record. Census must clean exactly the stale record and keep the
    # replacement one.
    stale = _register(registry_dir, pid=4242, owned=["/work/one"])
    fake_processes.start_times[4242] = 999
    replacement = _register(registry_dir, pid=4242, owned=["/work/two"])
    assert stale.path != replacement.path

    result = census_registry(registry_dir=registry_dir)
    assert [r.registry_id for r in result.live] == [replacement.registry_id]
    # The replacement's atomic registration already purged the stale
    # incarnation under the same lock; census must retain the replacement.
    assert result.cleaned == ()
    assert stale.path is not None and not stale.path.exists()
    assert replacement.path is not None and replacement.path.exists()


def test_fallback_lock_never_takes_over_a_fresh_holder(
    monkeypatch, registry_dir, fake_processes
):
    monkeypatch.setattr(census, "_fcntl", None)
    monkeypatch.setattr(census, "_LOCK_TIMEOUT_SECONDS", 0.0)
    lock_path = registry_dir.parent / f"{registry_dir.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999\n", encoding="ascii")

    with pytest.raises(RunRegistryError, match="still live"):
        _register(registry_dir, pid=4242, owned=["/work/one"])

    assert lock_path.exists()


def test_fallback_lock_takes_over_only_a_provably_stale_holder(
    monkeypatch, registry_dir, fake_processes
):
    monkeypatch.setattr(census, "_fcntl", None)
    monkeypatch.setattr(census, "_LOCK_TIMEOUT_SECONDS", 0.0)
    lock_path = registry_dir.parent / f"{registry_dir.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999\n", encoding="ascii")
    stale = time.time() - census._LOCK_FALLBACK_STALE_SECONDS - 1
    os.utime(lock_path, (stale, stale))

    record = _register(registry_dir, pid=4242, owned=["/work/one"])

    assert record.path is not None and record.path.exists()
    assert not lock_path.exists()


def test_deregister_removes_own_record_only(registry_dir, fake_processes):
    first = _register(registry_dir, pid=1001, owned=["/work/one"])
    second = _register(registry_dir, pid=1002, owned=["/work/two"])
    assert deregister_run(first) is None
    assert not first.path.exists()
    assert second.path.exists()
    result = census_registry(registry_dir=registry_dir)
    assert [r.pid for r in result.live] == [1002]
    # Deregistering again (or a record already gone) is a no-op, not an error.
    assert deregister_run(first) is None
    assert deregister_run(None) is None


def test_register_rejects_invalid_pid(registry_dir, fake_processes):
    for bad_pid in (0, -3, "4242"):
        with pytest.raises(RunRegistryError):
            register_run(
                route_id="route-a",
                packet_id="sha256:p",
                owned_paths=["/work"],
                pid=bad_pid,  # type: ignore[arg-type]
                registry_dir=registry_dir,
            )


def test_corrupt_registry_record_fails_closed(registry_dir, fake_processes):
    _register(registry_dir, pid=1001, owned=["/work/one"])
    corrupt = registry_dir / "9999-corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(RunRegistryError):
        census_registry(registry_dir=registry_dir)
    corrupt.unlink()
    result = census_registry(registry_dir=registry_dir)
    assert [r.pid for r in result.live] == [1001]


def test_census_on_missing_directory_is_empty(tmp_path, fake_processes):
    result = census_registry(registry_dir=tmp_path / "does-not-exist")
    assert result.live == ()
    assert result.cleaned == ()


# ---------------------------------------------------------------------------
# Deterministic concurrent registry operations (real flock boundary)
# ---------------------------------------------------------------------------


def _spawn_and_join(count: int, target) -> None:
    threads = [threading.Thread(target=target, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()


def test_concurrent_intersecting_registers_admit_exactly_one(tmp_path, fake_processes):
    # Every thread registers the SAME owned path against the same real
    # flock-serialized registry: the check-and-register steps cannot
    # interleave, so exactly one thread may win.
    registry_dir = tmp_path / "registry"
    count = 8
    barrier = threading.Barrier(count)
    counts_lock = threading.Lock()
    admitted = [0]
    refused = [0]

    def worker(_index: int) -> None:
        barrier.wait(timeout=30)
        try:
            register_run(
                route_id="route-same",
                packet_id="sha256:same",
                owned_paths=["/work/shared-tree"],
                pid=os.getpid(),
                registry_dir=registry_dir,
            )
            with counts_lock:
                admitted[0] += 1
        except RegistryConflictError:
            with counts_lock:
                refused[0] += 1

    _spawn_and_join(count, lambda i: worker(i))
    assert (admitted[0], refused[0]) == (1, count - 1)
    result = census_registry(registry_dir=registry_dir)
    assert len(result.live) == 1
    assert result.live[0].owned_paths == ("/work/shared-tree",)


def test_concurrent_disjoint_registers_all_succeed(tmp_path, fake_processes):
    registry_dir = tmp_path / "registry"
    count = 8
    barrier = threading.Barrier(count)
    failures: list[BaseException] = []
    failures_lock = threading.Lock()

    def worker(index: int) -> None:
        barrier.wait(timeout=30)
        try:
            register_run(
                route_id=f"route-{index}",
                packet_id=f"sha256:{index}",
                owned_paths=[f"/work/tree-{index}"],
                pid=10_000 + index,
                registry_dir=registry_dir,
            )
        except BaseException as exc:  # noqa: BLE001 - recorded for assertion
            with failures_lock:
                failures.append(exc)

    _spawn_and_join(count, worker)
    assert failures == []
    result = census_registry(registry_dir=registry_dir)
    assert sorted(r.pid for r in result.live) == list(range(10_000, 10_000 + count))


def test_concurrent_census_and_register_never_lose_a_record(tmp_path, fake_processes):
    # Census passes concurrent with registrations must never delete a record
    # for a genuinely live pid: the flock serializes cleanup against every
    # check-and-register, and live identities are never cleaned.
    registry_dir = tmp_path / "registry"
    count = 6
    barrier = threading.Barrier(count)
    failures: list[BaseException] = []
    failures_lock = threading.Lock()

    def register_worker(index: int) -> None:
        barrier.wait(timeout=30)
        try:
            register_run(
                route_id=f"route-{index}",
                packet_id=f"sha256:{index}",
                owned_paths=[f"/work/tree-{index}"],
                pid=10_000 + index,
                registry_dir=registry_dir,
            )
        except BaseException as exc:  # noqa: BLE001 - recorded for assertion
            with failures_lock:
                failures.append(exc)

    def census_worker() -> None:
        for _ in range(20):
            try:
                census_registry(registry_dir=registry_dir)
            except BaseException as exc:  # noqa: BLE001 - recorded for assertion
                with failures_lock:
                    failures.append(exc)

    threads = [
        threading.Thread(target=register_worker, args=(i,)) for i in range(count)
    ]
    census_thread = threading.Thread(target=census_worker)
    for thread in threads:
        thread.start()
    census_thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    census_thread.join(timeout=30)
    assert failures == []
    result = census_registry(registry_dir=registry_dir)
    assert sorted(r.pid for r in result.live) == list(range(10_000, 10_000 + count))


def test_registry_errors_chain_into_llm_router_error():
    assert issubclass(RunRegistryError, LLMRouterError)
    assert issubclass(RegistryConflictError, RunRegistryError)
