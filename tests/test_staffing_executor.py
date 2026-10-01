"""Protected transport tests use fake providers and innocuous local children."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lee_llm_router.staffing.executor import ExecutorSpecError, load_executor_spec
from tests.test_staffing_run import (
    PI_EVENT_STDOUT,
    PI_ROUTE,
    LaunchRecorder,
    _run_cli,
)
from tests.test_staffing_run import (
    catalog_dir as catalog_dir,
)
from tests.test_staffing_run import (
    packet as packet,
)
from tests.test_staffing_run import (
    scratch_state as scratch_state,
)
from tests.test_staffing_run import (
    snapshot as snapshot,
)
from tests.test_supervise_parent_admission import decision


def spec_value():
    return dict(
        version=1,
        employee_id="worker-1",
        parent_transaction_id="parent",
        gap_id="recall",
        argv_prefix=[str(Path(sys.executable).resolve()), "literal $HOME; $(false)"],
    )


@pytest.mark.parametrize(
    "change",
    [
        {"extra": True},
        {"version": True},
        {"version": 2},
        {"employee_id": 1},
        {"employee_id": ""},
        {"employee_id": "a" * 257},
        {"gap_id": None},
        {"argv_prefix": "bad"},
        {"argv_prefix": []},
        {"argv_prefix": [1]},
        {"argv_prefix": ["relative"]},
        {"argv_prefix": ["/tmp/../bin/true"]},
        {"argv_prefix": ["x"] * 33},
        {"argv_prefix": ["x" * 4097]},
        {"argv_prefix": ["a\x00"]},
        {"parent_transaction_id": float("nan")},
    ],
)
def test_strict_spec(tmp_path, change):
    value = spec_value() | change
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ExecutorSpecError):
        load_executor_spec(str(path))


def test_symlinks_duplicate_and_shapes(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec_value()))
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ExecutorSpecError):
        load_executor_spec(str(link))
    executable = tmp_path / "exe"
    executable.symlink_to(Path(sys.executable).resolve())
    for raw in (
        "[]",
        "null",
        '{"version":1,"version":1}',
        json.dumps(spec_value() | {"argv_prefix": [str(executable)]}),
        " " * 65537,
    ):
        path.write_text(raw)
        with pytest.raises(ExecutorSpecError):
            load_executor_spec(str(path))


def test_fifo_refused_without_waiting_for_writer(tmp_path):
    fifo = tmp_path / "spec.fifo"
    os.mkfifo(fifo)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from lee_llm_router.staffing.executor import load_executor_spec; "
                "import sys; load_executor_spec(sys.argv[1])"
            ),
            str(fifo),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "executor spec must be a regular file" in result.stderr


@pytest.mark.parametrize(
    "case",
    [
        "accepted",
        "failure",
        "e2big",
        "enoent",
        "employee",
        "parent",
        "gap",
        "closed",
        "unknown",
        "pair",
        "parents",
    ],
)
def test_actual_cli_binding(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path, case
):
    from lee_llm_router import doctor

    monkeypatch.setattr(doctor, "_worker_binding_path", lambda: tmp_path / "absent")
    monkeypatch.delenv("LEE_LLM_ROUTER_PARENT_START", raising=False)
    monkeypatch.setattr(os, "getppid", lambda: 0)
    value = spec_value()
    host = decision()
    if case in {"employee", "parent", "gap"}:
        value[
            {
                "employee": "employee_id",
                "parent": "parent_transaction_id",
                "gap": "gap_id",
            }[case]
        ] = "wrong"
    if case == "closed":
        host["gaps"][0]["state"] = "PROVED"
    if case == "unknown":
        value["grant"] = True
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(value))
    dp = tmp_path / "decision.json"
    dp.write_text(json.dumps(host))
    journal = tmp_path / "STATE.jsonl"
    flags = ["--executor-spec", str(spec)]
    if case != "pair":
        flags += ["--employee-id", "worker-1"]
    if case != "parents":
        flags += [
            "--unit-id",
            "parent",
            "--unit-state",
            str(journal),
            "--unit-decision",
            str(dp),
        ]
    launcher = LaunchRecorder(
        chunks=(
            [(PI_EVENT_STDOUT + '\n{"text":"done"}\n').encode()]
            if case != "failure"
            else []
        ),
        exit_code=7 if case == "failure" else 0,
    )
    launch_calls = []
    native_errno = {"e2big": errno.E2BIG, "enoent": errno.ENOENT}.get(case)

    def failed_popen(*args, **kwargs):
        launch_calls.append(args)
        raise OSError(native_errno, "SECRET prompt credential", "SECRET argv")

    clock_ticks = []

    def clock():
        clock_ticks.append(len(clock_ticks) * 0.25)
        return clock_ticks[-1]

    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        launcher=failed_popen if native_errno else launcher,
        clock=clock if native_errno else None,
        workdir=tmp_path,
        extra=flags,
    )
    if case not in {"accepted", "failure", "e2big", "enoent"}:
        assert code == 3
        assert not launcher.processes
        assert not journal.exists()
        assert not scratch_state["attempts"].exists()
        return
    if native_errno:
        assert code == 127, captured.err
        assert len(launch_calls) == 1
        assert not launcher.processes
        record = json.loads(captured.out)
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        assert [e["kind"] for e in events] == ["start", "finish"]
        assert events[0]["decision"] == host
        assert events[0]["execution"]["attempt_id"] == record["attempt_id"]
        assert events[1]["start"] == events[0]["start"] == 1
        assert events[1]["accounted"] is True
        assert events[1]["attempt"] == record
        assert record["wall_clock_ms"] == int((clock_ticks[-1] - clock_ticks[0]) * 1000)
        assert events[1]["seconds"] == record["wall_clock_ms"] / 1000 > 0
        assert record["usage"]["input_tokens"] is None
        assert record["usage"]["output_tokens"] is None
        assert "unavailable" in record["usage"]["basis"]
        assert "SECRET" not in captured.out + captured.err
        assert record["verified_success"] is False
        assert record["cost"] == {"basis": ["unavailable"]}
        return
    assert code == (7 if case == "failure" else 0), captured.err
    assert len(launcher.processes) == 1
    proc = launcher.processes[0]
    assert proc.argv[:2] == value["argv_prefix"]
    assert proc.popen_kwargs["shell"] is False
    assert proc.popen_kwargs["cwd"] == str(tmp_path)
    assert (
        packet.read_text() in proc.argv
        or proc.stdin.data.decode() == packet.read_text()
    )
    record = json.loads(captured.out)
    note = next(
        n
        for n in record["provenance"]["notes"]
        if n.startswith("protected-executor-v1 ")
    )
    binding = json.loads(note.split(" ", 1)[1])
    assert binding["employee_id"] == "worker-1"
    assert binding["source_sha256"] == hashlib.sha256(spec.read_bytes()).hexdigest()
    assert "literal" not in note
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [e["kind"] for e in events] == ["start", "finish"]
    assert events[0]["decision"] == host
    attempt_id = record["attempt_id"]
    assert attempt_id.startswith("router-run-")
    assert events[0]["execution"]["attempt_id"] == attempt_id
    assert binding["attempt_id"] == attempt_id
    env = proc.popen_kwargs["env"]
    assert {
        key: env[key]
        for key in (
            "LEE_EMPLOYEE_ID",
            "LEE_EMPLOYEE_PARENT_ID",
            "LEE_EMPLOYEE_GAP_ID",
            "LEE_EMPLOYEE_ATTEMPT_ID",
        )
    } == {
        "LEE_EMPLOYEE_ID": "worker-1",
        "LEE_EMPLOYEE_PARENT_ID": "parent",
        "LEE_EMPLOYEE_GAP_ID": "recall",
        "LEE_EMPLOYEE_ATTEMPT_ID": attempt_id,
    }
    assert events[1]["accounted"] and events[1]["attempt"] == record
    if case == "accepted":
        assert record["usage"]["input_tokens"] == 10
    else:
        assert record["usage"]["input_tokens"] is None


def test_real_prefix_preserves_stdin_native_capture(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from lee_llm_router.staffing import run

    python = str(Path(sys.executable).resolve())
    prefix = tmp_path / "prefix.py"
    prefix.write_text("import os, sys\nos.execv(sys.argv[1], sys.argv[1:])\n")
    child = tmp_path / "child.py"
    child.write_text(
        "import sys, os\n"
        "assert sys.stdin.read() == 'literal $(false); $HOME'\n"
        "assert os.environ['EXECUTOR_TEST'] == 'retained'\nprint("
        + repr(PI_EVENT_STDOUT)
        + ")\n"
    )
    monkeypatch.setattr(
        run, "build_dispatch_command", lambda *a, **k: [python, str(child)]
    )
    result = run.dispatch_route(
        SimpleNamespace(harness="pi", route_id="test"),
        "literal $(false); $HOME",
        workdir=tmp_path,
        timeout_seconds=5,
        extra_env={"EXECUTOR_TEST": "retained"},
        trusted_executor_argv_prefix=(python, str(prefix)),
        poll_seconds=0.01,
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == PI_EVENT_STDOUT
    assert result.usage["input_tokens"] == 10


@pytest.mark.parametrize("parent", [None, "fresh", "spoof"])
@pytest.mark.parametrize(
    "marker", ["readonly", "malformed", "dangling", "env", "ancestor"]
)
def test_bound_worker_run_refused(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    tmp_path,
    parent,
    marker,
):
    from lee_llm_router import doctor, staffing

    binding = tmp_path / "binding.json"
    monkeypatch.setattr(doctor, "_worker_binding_path", lambda: binding)
    monkeypatch.delenv("LEE_LLM_ROUTER_PARENT_START", raising=False)
    if marker == "dangling":
        binding.symlink_to(tmp_path / "missing")
    elif marker in {"readonly", "malformed"}:
        binding.write_text("{}" if marker == "readonly" else "not JSON")
        binding.chmod(0o444)
    elif marker == "env":
        monkeypatch.setenv("LEE_LLM_ROUTER_PARENT_START", "")
    else:
        monkeypatch.setattr(os, "getppid", lambda: 900)
        monkeypatch.setattr(sys, "platform", "linux")
        read_bytes, read_text = Path.read_bytes, Path.read_text
        monkeypatch.setattr(
            Path,
            "read_bytes",
            lambda p: (
                b"LEE_LLM_ROUTER_PARENT_START=actual\0"
                if str(p) == "/proc/901/environ"
                else (
                    b"OTHER=value\0" if str(p) == "/proc/900/environ" else read_bytes(p)
                )
            ),
        )
        monkeypatch.setattr(
            Path,
            "read_text",
            lambda p, *a, **kw: (
                "900 (worker name) S 901"
                if str(p) == "/proc/900/stat"
                else read_text(p, *a, **kw)
            ),
        )

    def unexpected_catalog(*args, **kwargs):
        pytest.fail("worker refusal must precede catalog loading")

    monkeypatch.setattr(staffing, "load_staffing_catalog", unexpected_catalog)
    journal = tmp_path / "parent.jsonl"
    flags = (
        []
        if parent is None
        else [
            "--unit-id",
            parent,
            "--unit-state",
            str(journal),
            "--unit-decision",
            str(tmp_path / "untrusted.json"),
        ]
    )
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
        extra=flags,
    )
    assert code == 3
    assert json.loads(captured.out)["kind"] == "worker_bound"
    assert not launcher.processes
    assert not journal.exists()
    assert not scratch_state["attempts"].exists()


def test_actual_legacy_capture_bootstrap_and_nested_refusal(tmp_path):
    """The fixed first capture launch survives; its model descendants do not."""
    import json
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    import pytest

    bwrap = shutil.which("bwrap")
    if not bwrap or not sys.platform.startswith("linux"):
        pytest.skip("requires Linux bwrap PID namespaces")
    source = str(Path(__file__).resolve().parents[1] / "src")
    (tmp_path / "binding.json").write_text(
        json.dumps(
            dict(
                employee_id="architecture-employee",
                task_id="fixture",
            )
        )
    )
    (tmp_path / "router-bootstrap.json").write_text(
        json.dumps(
            dict(version=1, employee_id="architecture-employee", task_id="fixture")
        )
    )
    (tmp_path / "capture.py").write_text(
        'import subprocess,sys\nraise SystemExit(subprocess.call(["/usr/bin/python3","-c",sys.argv[3]]))\n'
    )
    nested = (
        "import sys,json;sys.path.insert(0,"
        + repr(source)
        + ");from lee_llm_router.doctor import _run_worker_bound;print(json.dumps({'nested':_run_worker_bound()}))"
    )
    script = (
        "import sys,os,subprocess,json;sys.path.insert(0,"
        + repr(source)
        + ");from lee_llm_router.doctor import _run_worker_bound;print(json.dumps({'top':_run_worker_bound(),'pid':os.getpid()}));subprocess.run(['/usr/bin/python3','-c',"
        + repr(nested)
        + "])"
    )
    argv = [
        bwrap,
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/run",
        "--unshare-pid",
        "--proc",
        "/proc",
        "--ro-bind",
        str(tmp_path),
        "/run/assignment",
        "--",
        "/usr/bin/python3",
        "/run/assignment/capture.py",
        "/tmp/lee-llm-router",
        "run",
        script,
    ]
    run = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
    observations = [json.loads(line) for line in run.stdout.splitlines()]
    assert {"top": False, "pid": 3} in observations
    assert {"nested": True} in observations
    # Native provider namespaces must never get the legacy bootstrap exception.
    (tmp_path / "router-bootstrap.json").unlink()
    native = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert native.returncode == 0, native.stderr
    assert {"top": True, "pid": 3} in [
        json.loads(line) for line in native.stdout.splitlines()
    ]
