"""Tests for the P1-5a ``run`` command (doctor.py ``_run_run`` + staffing.run).

Contract under test is the Chief's corrected D209 syntax
(``docs/staffing/chief-answers-p1-1.md``): ``run --role R --class C --packet
FILE [--route ID] [--workdir DIR] [--parent ATTEMPT_ID --escalation-reason R]
[--timeout S] [--json]`` — role and class are always required and drive
eligibility; an optional explicit route must be eligible under the same
role/class path.

All tests use a scratch copy of the committed catalog, a scratch availability
snapshot, a synthetic packet, and fake subprocesses/clocks injected through
the run module's boundaries. No real provider binary is ever executed and no
real prompt is ever dispatched; scratch state goes through explicit file
paths and the ledger/events env overrides only.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import pytest
import yaml

from lee_llm_router.doctor import main as cli_main
from lee_llm_router.staffing import load_staffing_catalog

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"

IMPL_CLASS = "impl/deterministic/none/s/python"
IMPL_ROLE = "impl"

#: Explicit-route fixtures: each is eligible under the healthy snapshot.
CODEX_ROUTE = "codex-gpt-5-6-sol-low-openai-sub"
LUNA_ROUTE = "pi-gpt-5-6-luna-xhigh-openai-sub"
PI_ROUTE = "pi-z-ai-glm-5-3-flash-openrouter"
CLAUDE_ROUTE = "claude-claude-sonnet-5-high-anthropic-sub"
#: Explicit-route fixture that is always excluded (never_automatic + exhausted).
FABLE_ROUTE = "claude-claude-fable-5-1-high-anthropic-sub"

PACKET_TEXT = "scratch packet body: summarize the fixture input for the test."

#: Synthetic usage stdout payloads (no real prompts; capture-parser fixtures).
PI_EVENT_STDOUT = json.dumps(
    {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "model": "z-ai/glm-5.3-flash",
            "usage": {"input": 10, "output": 20, "cacheRead": 0, "cacheWrite": 0},
            "totalTokens": 30,
        },
    }
)
CODEX_RECEIPT_STDOUT = json.dumps(
    {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 7}}
)
CLAUDE_RESULT_STDOUT = json.dumps(
    {
        "type": "result",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 4,
            "cache_read_input_tokens": 2,
        },
    }
)

USAGE_KEYS = {
    "basis",
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "total_tokens",
}
PROVIDER_REPORTED_KEYS = USAGE_KEYS | {"source"}


# ---------------------------------------------------------------------------
# Scratch fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    """Scratch catalog: the committed six documents, nothing else."""
    dest = tmp_path / "catalog"
    shutil.copytree(
        REPO_CONFIG_DIR,
        dest,
        ignore=shutil.ignore_patterns("schema", "pricing", "__pycache__"),
    )
    return dest


@pytest.fixture
def retired_catalog_dir(tmp_path: Path) -> Path:
    """Scratch catalog with every route retired: nothing is ever eligible."""
    dest = tmp_path / "catalog-retired"
    shutil.copytree(
        REPO_CONFIG_DIR,
        dest,
        ignore=shutil.ignore_patterns("schema", "pricing", "__pycache__"),
    )
    routes_path = dest / "routes.yaml"
    data = yaml.safe_load(routes_path.read_text(encoding="utf-8"))
    for route in data["routes"]:
        route["status"] = "retired"
    routes_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return dest


def _write_snapshot(
    path: Path,
    *,
    codex: tuple[str, int] | None = ("ON TRACK", 80),
    anthropic: tuple[str, int] | None = ("COLD", 90),
    gemini: tuple[str, int] | None = ("ON TRACK", 60),
    opencode: tuple[str, int] | None = ("ON TRACK", 50),
) -> Path:
    """Write a fresh scratch availability snapshot file and return its path."""
    subscriptions = []
    for provider, bucket, value in (
        ("OpenAI/Codex", "Weekly limit", codex),
        ("Anthropic/Claude", "Current session", anthropic),
        ("Gemini/agy", "Gemini models", gemini),
        ("OpenCode/Go", "Weekly", opencode),
    ):
        if value is not None:
            subscriptions.append(
                {
                    "provider": provider,
                    "bucket": bucket,
                    "status": value[0],
                    "remaining_pct": value[1],
                }
            )
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload = {
        "host": "run-test",
        "observed_at": observed_at.isoformat(),
        "subscriptions": subscriptions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    """Healthy scratch availability snapshot (every subscription has headroom)."""
    return _write_snapshot(tmp_path / "availability.json")


@pytest.fixture
def packet(tmp_path: Path) -> Path:
    path = tmp_path / "packet.md"
    path.write_text(PACKET_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def scratch_state(monkeypatch, tmp_path):
    """Point every stateful ledger/env override at scratch paths.

    P1-5a must not append to any ledger, so these files must not exist
    after any run.
    """
    events = tmp_path / "events.jsonl"
    attempts = tmp_path / "attempts.jsonl"
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(events))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(attempts))
    return {"events": events, "attempts": attempts}


# ---------------------------------------------------------------------------
# Fake subprocess boundary
# ---------------------------------------------------------------------------


class FakeStdin:
    """Buffer simulating child stdin pipe."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, b: bytes | str) -> int:
        if isinstance(b, str):
            b = b.encode("utf-8")
        self.data.extend(b)
        return len(b)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakePipeStream:
    """Pipe-backed stream conforming to the real Popen stdout/stderr surface."""

    def __init__(self, chunks: Sequence[bytes] = ()) -> None:
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        os.set_blocking(self._w, False)
        self._chunks = list(chunks)
        self._closed = False

    def fileno(self) -> int:
        return self._r

    def read(self, n: int = 65536) -> bytes | None:
        try:
            chunk = os.read(self._r, n)
        except BlockingIOError:
            chunk = None
        if not chunk and self._chunks:
            os.write(self._w, self._chunks.pop(0))
            try:
                chunk = os.read(self._r, n)
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


class FakeProcess:
    """Fake child process conforming to the real Popen surface."""

    def __init__(
        self,
        argv: list[str],
        chunks: Sequence[bytes] = (),
        stderr_chunks: Sequence[bytes] = (),
        exit_code: int = 0,
        never_exits: bool = False,
        **kwargs: Any,
    ) -> None:
        self.argv = list(argv)
        self.popen_kwargs = kwargs
        self.stdin = FakeStdin()
        self.stdout = FakePipeStream(chunks)
        self.stderr = FakePipeStream(stderr_chunks)
        self._exit_code = exit_code
        self._never_exits = never_exits
        self.killed = False

    def poll(self) -> int | None:
        if self._never_exits:
            return None
        return self._exit_code

    def kill(self) -> None:
        self.killed = True
        self.stdout.close()
        self.stderr.close()

    def wait(self, timeout: float = 0.0) -> int:
        return -9 if self.killed else self._exit_code


class LaunchRecorder:
    """Fake Popen that records every constructed child process."""

    def __init__(
        self,
        *,
        chunks: Sequence[bytes] = (),
        stderr_chunks: Sequence[bytes] = (),
        exit_code: int = 0,
        never_exits: bool = False,
    ) -> None:
        self.processes: list[FakeProcess] = []
        self._chunks = list(chunks)
        self._stderr_chunks = list(stderr_chunks)
        self._exit_code = exit_code
        self._never_exits = never_exits

    def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
        proc = FakeProcess(
            argv,
            chunks=self._chunks,
            stderr_chunks=self._stderr_chunks,
            exit_code=self._exit_code,
            never_exits=self._never_exits,
            **kwargs,
        )
        self.processes.append(proc)
        return proc


class SequencedLaunchRecorder:
    """Fake Popen with a distinct worker and oracle outcome."""

    def __init__(self, specs: Sequence[dict[str, Any] | Exception]) -> None:
        self.specs = list(specs)
        self.processes: list[FakeProcess] = []
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
        self.calls.append((list(argv), dict(kwargs)))
        spec = self.specs[len(self.processes)]
        if isinstance(spec, Exception):
            raise spec
        proc = FakeProcess(argv, **spec, **kwargs)
        self.processes.append(proc)
        return proc


class AdvancingClock:
    """Monotonic clock that jumps forward on every read (ceiling tests)."""

    def __init__(self, step: float = 60.0) -> None:
        self.value = 0.0
        self._step = step

    def __call__(self) -> float:
        self.value += self._step
        return self.value


# ---------------------------------------------------------------------------
# CLI invocation helpers
# ---------------------------------------------------------------------------


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    catalog_dir: Path,
    snapshot_path: Path,
    packet_path: Path,
    role: str = IMPL_ROLE,
    class_string: str = IMPL_CLASS,
    route: str | None = None,
    workdir: Path | None = None,
    parent: str | None = None,
    escalation_reason: str | None = None,
    timeout: float | None = None,
    extra: Sequence[str] = (),
    launcher: LaunchRecorder | SequencedLaunchRecorder | None = None,
    clock: AdvancingClock | None = None,
    json_output: bool = True,
) -> tuple[int | None, Any]:
    """Invoke ``doctor.main(["run", ...])`` with fakes and capture output.

    ``--role`` and ``--class`` are always supplied (the corrected contract
    makes them mandatory); ``route`` selects the optional explicit route.
    The fake subprocess boundary is always patched, so no invocation can
    ever reach a real harness binary. Returns ``(exit_code, captured)``;
    the recorder carries every launched fake process.
    """
    if launcher is None:
        launcher = LaunchRecorder()
    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", launcher)
    if clock is not None:
        monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_CLOCK", clock)
        monkeypatch.setattr(
            "lee_llm_router.staffing.run._DEFAULT_SLEEP", lambda _s: None
        )

    argv = [
        "run",
        "--role",
        role,
        "--class",
        class_string,
        "--packet",
        str(packet_path),
        "--catalog-dir",
        str(catalog_dir),
        "--availability-file",
        str(snapshot_path),
        "--at",
        "2026-09-15",
    ]
    if route is not None:
        argv += ["--route", route]
    if workdir is not None:
        argv += ["--workdir", str(workdir)]
    if parent is not None:
        argv += ["--parent", parent]
    if escalation_reason is not None:
        argv += ["--escalation-reason", escalation_reason]
    if timeout is not None:
        argv += ["--timeout", str(timeout)]
    argv += list(extra)
    if json_output:
        argv.append("--json")

    with pytest.raises(SystemExit) as exc_info:
        cli_main(argv)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Traceback" not in combined
    return exc_info.value.code, captured


def _explain_first_eligible(
    capsys: pytest.CaptureFixture[str],
    catalog_dir: Path,
    snapshot_path: Path,
) -> tuple[str, list[tuple[str, str]]]:
    """First eligible route id and excluded summaries from ``catalog explain``."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main(
            [
                "catalog",
                "explain",
                "--role",
                IMPL_ROLE,
                "--class",
                IMPL_CLASS,
                "--at",
                "2026-09-15",
                "--catalog-dir",
                str(catalog_dir),
                "--availability-file",
                str(snapshot_path),
                "--json",
            ]
        )
    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    eligible = [r["route_id"] for r in payload["routes"] if r["eligible"]]
    excluded = [
        (r["route_id"], "; ".join(r["reasons"]))
        for r in payload["routes"]
        if not r["eligible"]
    ]
    assert eligible
    return eligible[0], excluded


def _route_record(catalog_dir: Path, route_id: str) -> Any:
    catalog = load_staffing_catalog(catalog_dir)
    return next(r for r in catalog.routes.routes if r.route_id == route_id)


# ---------------------------------------------------------------------------
# 1. Explain-cheapest selection
# ---------------------------------------------------------------------------


def test_run_explain_cheapest_selects_first_eligible(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """No --route: basis explain_cheapest_eligible, first in explain order."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
    )
    assert code == 0
    payload = json.loads(captured.out)

    expected_id, expected_excluded = _explain_first_eligible(
        capsys, catalog_dir, snapshot
    )
    route = next(
        r
        for r in load_staffing_catalog(catalog_dir).routes.routes
        if r.route_id == expected_id
    )

    assert payload["schema_version"] == 2
    assert payload["record_kind"] == "router_run"
    assert payload["route"] == {
        "model": route.model,
        "effort": route.effort,
        "harness": route.harness,
        "channel": route.channel,
    }
    selection = payload["selection"]
    assert selection["basis"] == "explain_cheapest_eligible"
    assert "marginal-price" in selection["reason"]
    assert "catalog explain" in selection["explain_ref"]
    assert IMPL_CLASS in selection["explain_ref"]
    assert sorted(
        (entry["route_id"], entry["reason"]) for entry in selection["excluded"]
    ) == sorted(expected_excluded)
    assert len(launcher.processes) == 1


def test_run_selection_record_is_explain_evidence_only(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """The selection record carries exactly the four explain-evidence fields."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
    )
    assert code == 0
    payload = json.loads(captured.out)
    selection = payload["selection"]
    assert set(selection) == {"basis", "reason", "explain_ref", "excluded"}
    for entry in selection["excluded"]:
        assert set(entry) == {"route_id", "reason"}
        assert entry["reason"]


# ---------------------------------------------------------------------------
# 2. Explicit route
# ---------------------------------------------------------------------------


def test_run_explicit_eligible_route(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """--route with an eligible route: basis explicit, dispatch happens."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    payload = json.loads(captured.out)
    selection = payload["selection"]
    assert selection["basis"] == "explicit"
    assert CODEX_ROUTE in selection["reason"]
    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    assert payload["route"] == {
        "model": route.model,
        "effort": route.effort,
        "harness": route.harness,
        "channel": route.channel,
    }
    assert len(launcher.processes) == 1


def test_run_explicit_excluded_route_exits_3_and_never_launches(
    monkeypatch, capsys, tmp_path, catalog_dir, packet, scratch_state
):
    """--route naming an ineligible route: exit 3, exact explain reason."""
    snapshot = _write_snapshot(tmp_path / "exhausted.json", anthropic=("HOT", 0))
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=FABLE_ROUTE,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    # The exact explain reasons for the excluded explicit route.
    assert "not eligible" in captured.err
    assert "never_automatic" in captured.err
    assert "channel exhausted" in captured.err


def test_run_unknown_explicit_route_exits_3_and_never_launches(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """--route that matches no catalog route: exit 3, nothing launched."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route="no-such-route-anywhere",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "does not match any route_id" in captured.err


# ---------------------------------------------------------------------------
# 3. No eligible route
# ---------------------------------------------------------------------------


def test_run_no_eligible_route_exits_3_and_never_launches(
    monkeypatch, capsys, retired_catalog_dir, snapshot, packet, scratch_state
):
    """Every route retired: exit 3 refusal, nothing launched."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=retired_catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "no eligible route" in captured.err


# ---------------------------------------------------------------------------
# 4. Required role/class
# ---------------------------------------------------------------------------


def test_run_requires_role_and_class(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Missing --role or --class is an argparse usage error; nothing launches."""
    launcher = LaunchRecorder()  # patched below; must stay empty in all cases
    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", launcher)
    common = [
        "--packet",
        str(packet),
        "--catalog-dir",
        str(catalog_dir),
        "--availability-file",
        str(snapshot),
        "--json",
    ]

    # --class missing.
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["run", "--role", IMPL_ROLE, *common])
    assert exc_info.value.code == 2
    capsys.readouterr()

    # --role missing.
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["run", "--class", IMPL_CLASS, *common])
    assert exc_info.value.code == 2
    capsys.readouterr()

    assert launcher.processes == []


def test_run_role_must_equal_class_role_segment(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A --role that disagrees with the --class role segment is refused."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        role="plan",
        class_string=IMPL_CLASS,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "does not equal the --class role segment" in captured.err


def test_run_rejects_non_canonical_class(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A malformed class string is refused before any launch."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        class_string="impl/deterministic",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "five-segment" in captured.err


# ---------------------------------------------------------------------------
# 5. Parent/escalation pair
# ---------------------------------------------------------------------------


def test_run_rejects_incomplete_parent_escalation_pair(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """--parent without --escalation-reason (or vice versa) refuses: exit 3."""
    for kwargs in (
        {"parent": "attempt-123"},
        {"escalation_reason": "review rejected the attempt"},
    ):
        launcher = LaunchRecorder()
        code, captured = _run_cli(
            monkeypatch,
            capsys,
            catalog_dir=catalog_dir,
            snapshot_path=snapshot,
            packet_path=packet,
            launcher=launcher,
            **kwargs,
        )
        assert code == 3
        assert launcher.processes == []
        assert "--parent and --escalation-reason" in captured.err


def test_run_complete_parent_pair_launches_once_and_does_not_escalate(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A complete pair is parsed and unused: one launch, no escalation state."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        parent="attempt-123",
        escalation_reason="review rejected the attempt",
        launcher=launcher,
    )
    assert code == 0
    payload = json.loads(captured.out)
    assert len(launcher.processes) == 1
    # Parsed but deliberately unused in P1-5a: no escalation field anywhere.
    assert "parent" not in json.dumps(payload).lower()
    assert not scratch_state["attempts"].exists()
    assert not scratch_state["events"].exists()


# ---------------------------------------------------------------------------
# 6. Pi dispatch argv + usage
# ---------------------------------------------------------------------------


def test_run_pi_dispatch_argv_and_usage(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Pi harness: JSON-mode argv through build_command, provider-reported usage."""
    launcher = LaunchRecorder(chunks=[(PI_EVENT_STDOUT + "\n").encode("utf-8")])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    assert len(launcher.processes) == 1
    proc = launcher.processes[0]
    argv = proc.argv
    assert argv[0] == "pi"
    assert "--mode" in argv and "json" in argv
    assert "--provider" in argv
    assert argv[argv.index("--provider") + 1] == "openrouter"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "z-ai/glm-5.3-flash"
    # The packet text is substituted exactly once; no placeholder remains.
    assert argv[-1] == PACKET_TEXT
    assert "{prompt}" not in argv

    payload = json.loads(captured.out)
    usage = payload["usage"]
    assert set(usage) == PROVIDER_REPORTED_KEYS
    assert usage["basis"] == "provider_reported"
    assert usage["source"] == "pi --mode json events"
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 20
    assert usage["cached_input_tokens"] == 0
    assert usage["reasoning_tokens"] is None
    assert usage["total_tokens"] == 30
    assert payload["dispatch"]["exit_code"] == 0
    assert payload["dispatch"]["timed_out"] is False
    assert payload["dispatch"]["stdout"].strip() == PI_EVENT_STDOUT
    assert payload["wall_clock_ms"] >= 0


def test_run_codex_dispatch_argv_and_usage(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Codex harness: forced --json flag, JSONL receipt parsed for usage."""
    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode("utf-8")])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    assert len(launcher.processes) == 1
    argv = launcher.processes[0].argv
    assert argv[0] == "codex"
    assert argv[1] == "exec"
    assert argv[2] == "--json"  # governed capture flag forced right after exec
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "gpt-5.6-sol"
    assert "-c" in argv
    assert "model_reasoning_effort=low" in argv
    assert argv[-1] == PACKET_TEXT
    assert "{prompt}" not in argv

    payload = json.loads(captured.out)
    usage = payload["usage"]
    assert set(usage) == PROVIDER_REPORTED_KEYS
    assert usage["basis"] == "provider_reported"
    assert usage["source"] == "codex exec --json usage"
    assert usage["input_tokens"] == 12
    assert usage["output_tokens"] == 7
    assert usage["total_tokens"] == 19
    assert payload["dispatch"]["exit_code"] == 0


def test_run_claude_governed_capture_argv_and_usage(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Claude reuses the committed governed stream-json capture (already wired)."""
    launcher = LaunchRecorder(chunks=[(CLAUDE_RESULT_STDOUT + "\n").encode("utf-8")])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CLAUDE_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    assert len(launcher.processes) == 1
    argv = launcher.processes[0].argv
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[-1] == PACKET_TEXT

    payload = json.loads(captured.out)
    usage = payload["usage"]
    assert set(usage) == PROVIDER_REPORTED_KEYS
    assert usage["basis"] == "provider_reported"
    assert usage["source"] == "claude -p --output-format stream-json result event"
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 4
    assert usage["cached_input_tokens"] == 2
    assert usage["reasoning_tokens"] is None
    assert usage["total_tokens"] == 16


# ---------------------------------------------------------------------------
# 7. Ceiling timeout
# ---------------------------------------------------------------------------


def test_run_timeout_kills_child_and_reports_124(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A child that never exits is killed at the ceiling: exit 124, timed_out."""
    launcher = LaunchRecorder(never_exits=True)
    clock = AdvancingClock(step=60.0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        timeout=5,
        launcher=launcher,
        clock=clock,
    )
    assert code == 124
    assert len(launcher.processes) == 1
    assert launcher.processes[0].killed is True
    payload = json.loads(captured.out)
    assert payload["dispatch"]["exit_code"] == 124
    assert payload["dispatch"]["timed_out"] is True
    assert payload["dispatch"]["duration_seconds"] > 0


# ---------------------------------------------------------------------------
# 8. Packet and workdir validation
# ---------------------------------------------------------------------------


def test_run_missing_packet_refuses(
    monkeypatch, capsys, catalog_dir, snapshot, tmp_path, scratch_state
):
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=tmp_path / "no-such-packet.md",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "packet file cannot be read" in captured.err


def test_run_empty_packet_refuses(
    monkeypatch, capsys, catalog_dir, snapshot, tmp_path, scratch_state
):
    empty = tmp_path / "empty-packet.md"
    empty.write_text("   \n", encoding="utf-8")
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=empty,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "packet file is empty" in captured.err


def test_run_workdir_validation(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """A nonexistent workdir refuses; a valid one becomes the child's cwd."""
    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode("utf-8")])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        workdir=tmp_path / "missing-dir",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "workdir is not a directory" in captured.err

    workdir = tmp_path / "real-dir"
    workdir.mkdir()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        workdir=workdir,
        launcher=launcher,
    )
    assert code == 0
    # The refused first attempt launched nothing; only the valid run did.
    assert len(launcher.processes) == 1
    assert launcher.processes[0].popen_kwargs.get("cwd") == str(workdir)


# ---------------------------------------------------------------------------
# 9. Exactly one launch, no escalation, no ledger append
# ---------------------------------------------------------------------------


def test_run_launches_exactly_once_and_appends_nothing(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Success path: exactly one child, and no ledger/event file is created."""
    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode("utf-8")])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    assert len(launcher.processes) == 1
    assert not scratch_state["attempts"].exists()
    assert not scratch_state["events"].exists()


def test_run_child_exit_code_propagates(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A failing child propagates its exit code; nothing else is launched."""
    launcher = LaunchRecorder(exit_code=7)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        launcher=launcher,
    )
    assert code == 7
    assert len(launcher.processes) == 1


def test_run_output_carries_streams_and_wallclock(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """The JSON record carries stdout/stderr/exit/wallclock plus schema usage."""
    stderr_line = b"child stderr scratch\n"
    launcher = LaunchRecorder(
        chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode("utf-8")],
        stderr_chunks=[stderr_line],
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    payload = json.loads(captured.out)
    dispatch = payload["dispatch"]
    assert set(dispatch) == {
        "argv",
        "exit_code",
        "timed_out",
        "duration_seconds",
        "stdout",
        "stderr",
    }
    assert dispatch["stdout"].strip() == CODEX_RECEIPT_STDOUT
    assert dispatch["stderr"] == stderr_line.decode("utf-8")
    assert isinstance(dispatch["duration_seconds"], (int, float))
    assert isinstance(payload["wall_clock_ms"], int)
    assert set(payload["usage"]) == PROVIDER_REPORTED_KEYS


# ---------------------------------------------------------------------------
# 10. P1-5b1 oracle and verdict
# ---------------------------------------------------------------------------


def _worker_spec(*, exit_code: int = 0) -> dict[str, Any]:
    """Return a fake worker spec with valid Pi usage evidence."""
    return {
        "chunks": [(PI_EVENT_STDOUT + "\n").encode("utf-8")],
        "exit_code": exit_code,
    }


class WorkdirDeletingProcess(FakeProcess):
    """Fake worker that removes its cwd when it reports completion."""

    def __init__(self, workdir: Path, argv: list[str], **kwargs: Any) -> None:
        self.workdir = workdir
        self._workdir_deleted = False
        super().__init__(argv, **kwargs)

    def poll(self) -> int | None:
        exit_code = super().poll()
        if exit_code is not None and not self._workdir_deleted:
            shutil.rmtree(self.workdir)
            self._workdir_deleted = True
        return exit_code


class WorkdirDeletingLaunchRecorder(SequencedLaunchRecorder):
    """Fake boundary that deletes the workdir after the worker completes."""

    def __init__(self, workdir: Path) -> None:
        super().__init__([_worker_spec()])
        self.workdir = workdir

    def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
        if self.processes:
            raise AssertionError("oracle must not launch after workdir deletion")
        self.calls.append((list(argv), dict(kwargs)))
        spec = self.specs[len(self.processes)]
        if isinstance(spec, Exception):
            raise spec
        process = WorkdirDeletingProcess(self.workdir, argv, **spec, **kwargs)
        self.processes.append(process)
        return process


def test_run_without_oracle_is_unverified_and_launches_only_worker(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A worker success cannot infer a verified success without an oracle."""
    launcher = SequencedLaunchRecorder([_worker_spec()])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        launcher=launcher,
    )

    assert code == 0
    payload = json.loads(captured.out)
    verification = payload["verification"]
    assert set(verification) == {"oracle_type", "verdict", "oracle"}
    assert verification["oracle_type"] == "none"
    assert verification["verdict"] == "unverified"
    assert verification["oracle"] is None
    assert len(launcher.calls) == 1


def test_run_oracle_pass_uses_shlex_argv_workdir_and_no_shell(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """A zero-exit oracle passes with exact argv and the requested cwd."""
    workdir = tmp_path / "oracle-cwd"
    workdir.mkdir()
    launcher = SequencedLaunchRecorder(
        [
            _worker_spec(),
            {"chunks": [b"oracle says okay\n"], "exit_code": 0},
        ]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        workdir=workdir,
        launcher=launcher,
        extra=("--oracle", "oracle --label 'hello world'"),
    )

    assert code == 0
    payload = json.loads(captured.out)
    verification = payload["verification"]
    assert set(verification) == {"oracle_type", "verdict", "oracle"}
    assert verification["oracle_type"] == "command"
    assert verification["verdict"] == "pass"
    evidence = verification["oracle"]
    assert evidence["argv"] == ["oracle", "--label", "hello world"]
    assert evidence["exit_code"] == 0
    assert evidence["stdout"] == "oracle says okay\n"
    assert evidence["stderr"] == ""
    assert evidence["timed_out"] is False
    assert evidence["error"] is None
    assert isinstance(evidence["duration_seconds"], (int, float))
    assert len(launcher.calls) == 2
    assert launcher.calls[0][1]["cwd"] == str(workdir)
    assert launcher.calls[1][1]["cwd"] == str(workdir)
    assert launcher.calls[0][1]["shell"] is False
    assert launcher.calls[1][1]["shell"] is False
    assert launcher.calls[1][0] == ["oracle", "--label", "hello world"]


def test_run_nonzero_oracle_is_fail_with_captured_evidence(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A nonzero oracle is a deterministic failed verification."""
    launcher = SequencedLaunchRecorder(
        [
            _worker_spec(),
            {
                "chunks": [b"oracle output\n"],
                "stderr_chunks": [b"oracle rejected\n"],
                "exit_code": 9,
            },
        ]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        launcher=launcher,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 0
    payload = json.loads(captured.out)
    oracle = payload["verification"]
    assert oracle["verdict"] == "fail"
    assert oracle["oracle"]["exit_code"] == 9
    assert oracle["oracle"]["stdout"] == "oracle output\n"
    assert oracle["oracle"]["stderr"] == "oracle rejected\n"
    assert oracle["oracle"]["timed_out"] is False
    assert oracle["oracle"]["error"] is None
    assert len(launcher.calls) == 2


def test_run_worker_failure_still_runs_oracle_once(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Worker failure does not suppress the separately governed oracle."""
    launcher = SequencedLaunchRecorder([_worker_spec(exit_code=7), {"exit_code": 0}])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        launcher=launcher,
        extra=("--oracle", "oracle"),
    )

    assert code == 7
    payload = json.loads(captured.out)
    assert payload["dispatch"]["exit_code"] == 7
    assert payload["verification"]["verdict"] == "pass"
    assert len(launcher.calls) == 2


def test_run_oracle_timeout_is_fail_and_not_retried(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """An oracle that exceeds the remaining budget is killed exactly once."""
    launcher = SequencedLaunchRecorder([_worker_spec(), {"never_exits": True}])
    clock = AdvancingClock(step=60.0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        timeout=300,
        launcher=launcher,
        clock=clock,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 0
    verification = json.loads(captured.out)["verification"]
    assert verification["verdict"] == "fail"
    assert verification["oracle"]["exit_code"] == 124
    assert verification["oracle"]["timed_out"] is True
    assert verification["oracle"]["error"] is None
    assert len(launcher.calls) == 2
    assert launcher.processes[1].killed is True


def test_run_deleted_workdir_after_worker_is_exit_3_without_oracle_launch(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """A workdir race after the worker is governed as a clear exit-3 failure."""
    workdir = tmp_path / "deleted-after-worker"
    workdir.mkdir()
    launcher = WorkdirDeletingLaunchRecorder(workdir)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        workdir=workdir,
        launcher=launcher,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 3
    assert "run: oracle failed: workdir is not a directory" in captured.err
    assert str(workdir) in captured.err
    assert len(launcher.calls) == 1
    assert json.loads(captured.out) == {
        "error": f"oracle failed: workdir is not a directory: {workdir}",
        "exit_code": 3,
    }


def test_run_oracle_launch_failure_is_fail_with_stable_error(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """An oracle launch error becomes failed evidence and receives no retry."""
    launcher = SequencedLaunchRecorder(
        [_worker_spec(), FileNotFoundError("oracle missing")]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        launcher=launcher,
        extra=("--oracle", "missing-oracle"),
    )

    assert code == 0
    verification = json.loads(captured.out)["verification"]
    assert verification["verdict"] == "fail"
    assert verification["oracle"]["exit_code"] is None
    assert verification["oracle"]["timed_out"] is False
    assert verification["oracle"]["error"] == (
        "launch failure: FileNotFoundError: oracle missing"
    )
    assert len(launcher.calls) == 2


def test_run_malformed_or_empty_oracle_refuses_before_worker(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Both shlex refusal forms launch neither a worker nor an oracle."""
    for command in ("'unterminated", "   "):
        launcher = SequencedLaunchRecorder([])
        code, captured = _run_cli(
            monkeypatch,
            capsys,
            catalog_dir=catalog_dir,
            snapshot_path=snapshot,
            packet_path=packet,
            route=LUNA_ROUTE,
            launcher=launcher,
            extra=("--oracle", command),
        )
        assert code == 3
        assert "oracle command invalid" in captured.err
        assert launcher.calls == []


def test_oracle_default_budget_uses_the_watchdog_default():
    """The oracle default derives from the watchdog's authoritative ceiling."""
    from lee_llm_router.staffing.run import (
        DEFAULT_ORACLE_TIMEOUT_SECONDS,
        oracle_timeout_seconds,
    )
    from lee_llm_router.watchdog import DEFAULT_MAX_MINUTES

    assert DEFAULT_ORACLE_TIMEOUT_SECONDS == DEFAULT_MAX_MINUTES * 60.0
    assert oracle_timeout_seconds(None, 0.0) == DEFAULT_MAX_MINUTES * 60.0


def test_run_plain_summary_includes_verification(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """The plain result exposes the same verdict without captured streams."""
    launcher = SequencedLaunchRecorder([_worker_spec(), {"exit_code": 0}])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        launcher=launcher,
        json_output=False,
        extra=("--oracle", "oracle"),
    )

    assert code == 0
    assert "verification: pass (oracle exit 0)" in captured.out
    assert "oracle output" not in captured.out
    assert len(launcher.calls) == 2
