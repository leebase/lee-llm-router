"""Tests for the complete P1-5 ``run`` command and v2 attempt append.

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
import shlex
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import pytest
import yaml

import lee_llm_router.staffing.run as run_module
from lee_llm_router.availability import load_availability
from lee_llm_router.doctor import main as cli_main
from lee_llm_router.providers.antigravity_cli import AGY_USAGE_SOURCE
from lee_llm_router.providers.omp_cli import OMP_USAGE_SOURCE
from lee_llm_router.providers.opencode_cli import OPENCODE_USAGE_SOURCE
from lee_llm_router.staffing import load_staffing_catalog
from lee_llm_router.staffing.catalog import Route as StaffingRoute
from lee_llm_router.staffing.census import (
    ProcessIdentity,
    census_registry,
    register_run,
)
from lee_llm_router.staffing.json_int import int_from_decimal, int_to_decimal
from lee_llm_router.staffing.run import (
    Resolution,
    _usage_for_harness,
    build_dispatch_command,
    dispatch_route,
    run_supervised_dispatch,
    select_route,
    validate_attempt_metadata,
)

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
AGY_RECEIPT_STDOUT = json.dumps(
    {
        "conversation_id": "recorded-conversation",
        "status": "SUCCESS",
        "response": "done",
        "error": "",
        "duration_seconds": 1.25,
        "num_turns": 1,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 25,
            "thinking_tokens": 10,
            "cache_read_tokens": 50,
            "total_tokens": 125,
        },
    }
)
OPENCODE_RECEIPT_STDOUT = json.dumps(
    {
        "type": "step_finish",
        "part": {
            "tokens": {
                "input": 100,
                "output": 25,
                "reasoning": 5,
                "cache": {"read": 40, "write": 3},
            },
            "cost": 0.01,
        },
    }
)
OMP_RECEIPT_STDOUT = json.dumps(
    {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "model": "openai/gpt-5.2",
            "usage": {
                "input": 100,
                "output": 20,
                "cacheRead": 5,
                "cacheWrite": 2,
                "totalTokens": 127,
            },
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

    Every stateful path is scratch-only; successful dispatches append only to
    the attempt ledger and pre-dispatch refusals create neither file. The
    live-run registry (P3-4) is likewise redirected to a scratch per-test
    directory so no CLI test can touch real user state.
    """
    events = tmp_path / "events.jsonl"
    attempts = tmp_path / "attempts.jsonl"
    registry = tmp_path / "run-registry"
    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(events))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(attempts))
    monkeypatch.setenv("LEE_LLM_ROUTER_RUN_REGISTRY_DIR", str(registry))
    monkeypatch.setenv("LEE_LLM_ROUTER_ARTIFACTS_DIR", str(artifacts))
    return {
        "events": events,
        "attempts": attempts,
        "registry": registry,
        "artifacts": artifacts,
    }


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
        if isinstance(spec, BaseException):
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
    instance: str | None = None,
    supervisor_route: str | None = None,
    workdir: Path | None = None,
    parent: str | None = None,
    escalation_reason: str | None = None,
    timeout: float | None = None,
    owned_paths: Sequence[str] | None = None,
    extra: Sequence[str] = (),
    launcher: LaunchRecorder | SequencedLaunchRecorder | None = None,
    clock: AdvancingClock | None = None,
    json_output: bool = True,
) -> tuple[int | None, Any]:
    """Invoke ``doctor.main(["run", ...])`` with fakes and capture output.

    ``--role`` and ``--class`` are always supplied (the corrected contract
    makes them mandatory); ``route`` selects the optional explicit route,
    ``instance`` selects the optional explicit channel instance, and
    ``supervisor_route`` supplies the optional caller attestation. The fake
    subprocess boundary is always patched, so no invocation can
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
    if instance is not None:
        argv += ["--instance", instance]
    if supervisor_route is not None:
        argv += ["--supervisor-route", supervisor_route]
    if workdir is not None:
        argv += ["--workdir", str(workdir)]
    if parent is not None:
        argv += ["--parent", parent]
    if escalation_reason is not None:
        argv += ["--escalation-reason", escalation_reason]
    if timeout is not None:
        argv += ["--timeout", str(timeout)]
    # P3-4: every run registers its owned paths; the packet file is the
    # deterministic default owned path for tests that do not care.
    for owned in owned_paths if owned_paths is not None else [str(packet_path)]:
        argv += ["--owned-paths", str(owned)]
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
    *,
    role: str = IMPL_ROLE,
    class_string: str = IMPL_CLASS,
    author_route: str | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """First eligible route id and excluded summaries from ``catalog explain``."""
    argv = [
        "catalog",
        "explain",
        "--role",
        role,
        "--class",
        class_string,
        "--at",
        "2026-09-15",
        "--catalog-dir",
        str(catalog_dir),
        "--availability-file",
        str(snapshot_path),
        "--json",
    ]
    if author_route is not None:
        argv += ["--author-route", author_route]
    with pytest.raises(SystemExit) as exc_info:
        cli_main(argv)
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


def _assert_output_matches_single_append(
    captured: Any, scratch_state: dict[str, Path]
) -> dict[str, Any]:
    """Return the JSON output after proving it is the sole ledger object."""
    payload = json.loads(captured.out)
    lines = scratch_state["attempts"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == payload
    return payload


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
        "provider": payload["router_event"]["provider"],
        "channel_instance": route.channel,
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
        "provider": payload["router_event"]["provider"],
        "channel_instance": "openai-sub",
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
    assert not scratch_state["attempts"].exists()


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
    assert not scratch_state["attempts"].exists()


@pytest.mark.parametrize(
    ("supervisor_route", "retire_catalog"),
    [
        ("no-such-supervisor-route", False),
        (CODEX_ROUTE, True),
    ],
    ids=["unknown", "inactive"],
)
def test_run_invalid_supervisor_route_exits_3_before_worker(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    supervisor_route,
    retire_catalog,
):
    """Unknown, inactive, and ineligible attestations fail before launch."""
    if retire_catalog:
        routes_path = catalog_dir / "routes.yaml"
        data = yaml.safe_load(routes_path.read_text(encoding="utf-8"))
        for route in data["routes"]:
            if route["route_id"] == supervisor_route:
                route["status"] = "retired"
        routes_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        supervisor_route=supervisor_route,
        launcher=launcher,
    )

    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    if supervisor_route == "no-such-supervisor-route":
        assert "does not match any route_id" in captured.err
    elif retire_catalog:
        assert "is not active" in captured.err
    else:  # pragma: no cover - parametrization covers unknown and inactive
        raise AssertionError("unexpected parametrization")


def test_run_supervisor_attestation_is_identity_not_capability(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Astra final-review finding 5 reproducer: role/class policy never applies.

    Chief answer 4 authorizes identity attestation. An eligible GLM
    implementation selection must not become a refusal when its caller
    attests ``agy-gemini-3-1-pro-gemini-sub``, even though Gemini Pro is
    role-scoped (coding denied) for the worker class: attesting one's own
    route is not performing the worker's task. The attested identity is
    recorded verbatim and the run dispatches exactly once.
    """
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        supervisor_route="agy-gemini-3-1-pro-gemini-sub",
        launcher=launcher,
    )

    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.processes) == 1
    catalog = load_staffing_catalog(catalog_dir)
    attested = next(
        r
        for r in catalog.routes.routes
        if r.route_id == "agy-gemini-3-1-pro-gemini-sub"
    )
    assert payload["supervisor_route"] == {
        "model": attested.model,
        "effort": attested.effort,
        "harness": attested.harness,
        "channel": attested.channel,
        "provider": "antigravity_cli",
    }
    # Truthful verification: attested, dispatched, but no oracle ran.
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "oracle_not_passed"


def test_select_route_supervisor_attestation_is_identity_not_capability(
    catalog_dir, snapshot
):
    """Direct selection: role_scoped exclusion is not imposed on the identity."""
    catalog = load_staffing_catalog(catalog_dir)
    availability = load_availability(snapshot)
    outcome = select_route(
        catalog,
        availability,
        role="impl",
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=PI_ROUTE,
        supervisor_route_id="agy-gemini-3-1-pro-gemini-sub",
    )
    assert outcome.route.route_id == PI_ROUTE
    assert outcome.supervisor_route == {
        "model": "gemini-3.1-pro",
        "effort": None,
        "harness": "agy",
        "channel": "gemini-sub",
        "provider": "antigravity_cli",
    }


def test_run_supervisor_attestation_still_refuses_nonclass_governed_reasons(
    monkeypatch, capsys, catalog_dir, tmp_path, packet, scratch_state
):
    """Non-role/class governed exclusions still refuse an attestation.

    Unknown and inactive identities refuse (existing parametrized test);
    this adds the availability branch: a route whose channel headroom is
    unknown is not currently usable, and that refusal is governed identity
    validation, never worker capability policy.
    """
    snapshot = _write_snapshot(tmp_path / "nodata.json", codex=("NO DATA", 0))
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        supervisor_route=CODEX_ROUTE,
        launcher=launcher,
    )

    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    assert "currently usable route identity" in captured.err
    assert "channel unknown" in captured.err


def test_run_supervisor_attestation_never_automatic_is_identity_exempt(
    monkeypatch, capsys, catalog_dir, tmp_path, snapshot, packet, scratch_state
):
    """D223: never_automatic governs worker selection, not supervisor identity.

    A Fable supervisor attests fine on a healthy anthropic channel; the same
    identity is still refused when its channel is exhausted, and that refusal
    names the availability reason, never never_automatic.
    """
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        supervisor_route=FABLE_ROUTE,
        launcher=launcher,
    )
    assert code == 0, captured.err
    assert len(launcher.processes) == 1
    payload = json.loads(captured.out)
    assert payload["supervisor_route"]["model"] == "claude-fable-5-1"
    assert payload["verified_success_reason"] != "supervisor_route_unattested"

    exhausted = _write_snapshot(tmp_path / "exhausted.json", anthropic=("HOT", 0))
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=exhausted,
        packet_path=packet,
        supervisor_route=FABLE_ROUTE,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "currently usable route identity" in captured.err
    assert "channel exhausted" in captured.err
    assert "never_automatic" not in captured.err


# ---------------------------------------------------------------------------
# 2b. Author route (review/judge independence, Astra finding 4)
# ---------------------------------------------------------------------------


REVIEW_CLASS = "review/judge/none/s/python"
REVIEW_ROLE = "review"


def test_run_author_route_excludes_author_and_same_family(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Astra final-review finding 4 reproducer: run enforces independence.

    The explicit GLM selection succeeds without author context, and with
    that same route as ``--author-route`` the run refuses (exit 3) with the
    exact ``independence`` explain reason — the same fail-closed evaluation
    ``catalog explain`` performs.
    """
    # Without the author route the explicit GLM review route is eligible.
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        role=REVIEW_ROLE,
        class_string=REVIEW_CLASS,
        route=PI_ROUTE,
        launcher=launcher,
    )
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["selection"]["basis"] == "explicit"
    assert not any(
        entry["reason"] == "independence" for entry in payload["selection"]["excluded"]
    )
    assert len(launcher.processes) == 1
    ledger_lines_before = len(
        scratch_state["attempts"].read_text(encoding="utf-8").splitlines()
    )

    # Supplying that same route as the author context fails closed exactly
    # as ``catalog explain --author-route`` does: nothing launches, nothing
    # appends.
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        role=REVIEW_ROLE,
        class_string=REVIEW_CLASS,
        route=PI_ROUTE,
        launcher=launcher,
        extra=("--author-route", PI_ROUTE),
    )
    assert code == 3
    assert launcher.processes == []
    ledger_lines_after = len(
        scratch_state["attempts"].read_text(encoding="utf-8").splitlines()
    )
    assert ledger_lines_after == ledger_lines_before
    assert "not eligible" in captured.err
    assert "independence" in captured.err


def test_run_author_route_selection_excludes_author_and_preserves_explain(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Role/class review selection with an author keeps the explain evidence."""
    expected_id, expected_excluded = _explain_first_eligible(
        capsys,
        catalog_dir,
        snapshot,
        role=REVIEW_ROLE,
        class_string=REVIEW_CLASS,
        author_route=PI_ROUTE,
    )
    assert expected_id != PI_ROUTE
    assert (PI_ROUTE, "independence") in expected_excluded

    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        role=REVIEW_ROLE,
        class_string=REVIEW_CLASS,
        launcher=launcher,
        extra=("--author-route", PI_ROUTE),
    )
    assert code == 0
    payload = json.loads(captured.out)
    selection = payload["selection"]
    assert selection["basis"] == "explain_cheapest_eligible"
    assert sorted(
        (entry["route_id"], entry["reason"]) for entry in selection["excluded"]
    ) == sorted(expected_excluded)
    assert payload["route"]["model"] == _route_record(catalog_dir, expected_id).model
    assert len(launcher.processes) == 1


def test_run_unknown_author_route_fails_closed_before_worker(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """An unknown ``--author-route`` fails closed like ``catalog explain``."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
        extra=("--author-route", "no-such-author-route"),
    )
    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    assert "does not match any route_id" in captured.err


def test_run_author_route_not_applicable_outside_review_judge(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """For non-review/judge roles the author route adds no exclusion."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
        extra=("--author-route", PI_ROUTE),
    )
    assert code == 0
    payload = json.loads(captured.out)
    assert all(
        entry["reason"] != "independence" for entry in payload["selection"]["excluded"]
    )


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
    assert not scratch_state["attempts"].exists()


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
    """A supplied link is recorded, while run still launches only one worker."""
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.processes) == 1
    assert payload["parent_attempt_id"] == "attempt-123"
    assert payload["escalation_reason"] == "review rejected the attempt"
    assert not scratch_state["events"].exists()


@pytest.mark.parametrize(
    ("parent", "escalation_reason"),
    [
        ("bad parent", "non_convergence"),
        ("attempt-123", ""),
        ("", "non_convergence"),
    ],
    ids=["parent_pattern", "empty_reason", "empty_parent"],
)
def test_run_invalid_parent_metadata_refuses_before_worker(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    parent,
    escalation_reason,
):
    """Astra final-review finding 6: metadata validates before any launch.

    The committed reproducer (``--parent 'bad parent'
    --escalation-reason non_convergence``) previously dispatched the worker
    and only then failed schema validation, dropping the completed worker.
    Now the caller-controlled record metadata is validated before dispatch:
    exit-3 refusal, nothing launched, nothing appended.
    """
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        parent=parent,
        escalation_reason=escalation_reason,
        launcher=launcher,
    )

    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    if parent == "bad parent":
        assert "parent_attempt_id" in captured.err
        assert "bad parent" in captured.err
    elif parent == "":
        assert "parent_attempt_id" in captured.err
    else:
        assert "escalation_reason" in captured.err


def test_validate_attempt_metadata_rules() -> None:
    """The pre-launch validator enforces exactly the committed v2 rules."""
    from lee_llm_router.staffing.run import RunSelectionError

    # A valid escalation link and a generated-style attempt id both pass.
    validate_attempt_metadata(
        parent_attempt_id="p1-5b-attempt-2-20260910",
        escalation_reason="non_convergence",
        attempt_id="router-run-abc123",
    )
    # No metadata at all passes.
    validate_attempt_metadata()
    for kwargs in (
        {"parent_attempt_id": "p1-x"},  # unpaired parent
        {"escalation_reason": "non_convergence"},  # unpaired reason
        {"parent_attempt_id": "bad parent", "escalation_reason": "r"},
        {"parent_attempt_id": "p1-x", "escalation_reason": ""},
        {"attempt_id": "bad id"},
        {"attempt_id": ""},
    ):
        with pytest.raises(RunSelectionError) as exc_info:
            validate_attempt_metadata(**kwargs)
        assert exc_info.value.kind == "invalid_metadata"
        assert exc_info.value.exit_code == 3


def _prior_redispatch_attempt(
    *,
    attempt_id: str = "attempt-1",
    packet_id: str = "sha256:packet",
    route_id: str = CODEX_ROUTE,
    failure_class: str | None = "platform_timeout",
    kill_reason: str = "stall",
    ceiling_minutes: str = "10",
) -> dict[str, Any]:
    """Return the attempt fields needed by the pure re-dispatch decision."""
    return {
        "attempt_id": attempt_id,
        "packet_id": packet_id,
        "failure_class": failure_class,
        "router_event": {"route_id": route_id},
        "provenance": {
            "notes": [
                f"dispatch kill: {kill_reason} after 60 s "
                f"(stall 1 min, progress 2 min, ceiling {ceiling_minutes} min)"
            ]
        },
    }


@pytest.mark.parametrize("kill_reason", ["stall", "no_progress"])
def test_unchanged_redispatch_refuses_progress_kill(kill_reason: str) -> None:
    refusal = run_module.unchanged_redispatch_refusal(
        [_prior_redispatch_attempt(kill_reason=kill_reason)],
        "sha256:packet",
        CODEX_ROUTE,
        600.0,
        None,
    )

    assert refusal == (
        "refused — unchanged re-dispatch of sha256:packet on "
        f"{CODEX_ROUTE} after a {kill_reason} kill (attempt attempt-1); "
        "change the packet, lower --timeout below 10 min, or escalate with "
        "--parent/--escalation-reason"
    )


@pytest.mark.parametrize(
    "attempts,timeout,parent",
    [
        ([_prior_redispatch_attempt(kill_reason="ceiling")], 600.0, None),
        ([_prior_redispatch_attempt(failure_class="spec_rejected")], 600.0, None),
        ([_prior_redispatch_attempt(route_id=PI_ROUTE)], 600.0, None),
        ([_prior_redispatch_attempt()], 599.9, None),
        # The CLI guarantees that a parent is paired with an escalation reason.
        ([_prior_redispatch_attempt()], 600.0, "attempt-1"),
        ([], 600.0, None),
        (
            [
                _prior_redispatch_attempt(attempt_id="older-stall"),
                _prior_redispatch_attempt(
                    attempt_id="latest-success", failure_class=None
                ),
            ],
            600.0,
            None,
        ),
    ],
    ids=[
        "ceiling",
        "other-failure",
        "other-route",
        "smaller-timeout",
        "parent",
        "empty",
        "latest",
    ],
)
def test_unchanged_redispatch_allows_exceptions(
    attempts: list[dict[str, Any]], timeout: float, parent: str | None
) -> None:
    refusal = run_module.unchanged_redispatch_refusal(
        attempts, "sha256:packet", CODEX_ROUTE, timeout, parent
    )

    assert refusal is None


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
    assert argv[argv.index("--mode") + 1] == "json"
    assert "--provider" in argv
    assert argv[argv.index("--provider") + 1] == "openrouter"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "z-ai/glm-5.3-flash"
    # P1-8: governed impl dispatch grants the explicit bounded editing
    # allowlist (no bash); JSON mode is retained for usage capture.
    assert "--tools" in argv
    tools = argv[argv.index("--tools") + 1]
    assert tools == "read,edit,write,grep,find,ls"
    assert "bash" not in tools
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
    assert payload["router_event"]["route_id"] == PI_ROUTE
    assert "exit_code=0, timed_out=False" in payload["provenance"]["notes"][0]
    _assert_output_matches_single_append(captured, scratch_state)
    assert payload["wall_clock_ms"] >= 0


def test_run_pi_huge_counter_persists_completed_worker(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A completed Pi worker with a 4301-digit counter still appends once."""
    counter = 2 * (9 * 10**4299)
    receipt = (
        '{"type":"message_end","message":{"role":"assistant",'
        '"model":"z-ai/glm-5.3-flash","usage":{"input":'
        f"{int_to_decimal(counter)}"
        ',"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":'
        f"{int_to_decimal(counter)}"
        "}}}"
    )
    launcher = LaunchRecorder(chunks=[(receipt + "\n").encode("utf-8")])

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
    payload = json.loads(captured.out, parse_int=int_from_decimal)
    assert payload["usage"]["input_tokens"] == counter
    assert payload["usage"]["total_tokens"] == counter
    assert payload["cost"] == {"basis": ["unavailable"]}
    raw = scratch_state["attempts"].read_text(encoding="utf-8")
    assert raw == captured.out
    assert int_to_decimal(counter) in raw
    assert json.loads(raw, parse_int=int_from_decimal) == payload


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
    # P1-8: writable sandbox + git-repo-check skip so the headless worker
    # can edit its scoped file in a non-git scratch workdir.
    assert argv[3] == "-s"
    assert argv[4] == "workspace-write"
    assert "--skip-git-repo-check" in argv
    # No dangerous bypass flag is ever emitted.
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert "--yolo" not in argv
    assert "--full-auto" not in argv
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
    assert payload["router_event"]["route_id"] == CODEX_ROUTE
    assert "exit_code=0, timed_out=False" in payload["provenance"]["notes"][0]
    _assert_output_matches_single_append(captured, scratch_state)


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
    # P1-8: governed noninteractive editing flags, prompt still final.
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "bypassPermissions" not in argv
    assert "--dangerously-skip-permissions" not in argv
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
    # Astra final-review finding 2: the receipt reports no totalTokens and
    # no cache-creation count, so the total is never manufactured as
    # input + output + cache read; it stays unknown.
    assert usage["total_tokens"] is None


def test_build_dispatch_command_pi_governed_edit_tools_retain_json_mode() -> None:
    """P1-8 regression: governed Pi dispatch edits with bounded tools, JSON kept.

    Reproduces the live defect where a Pi impl ``run`` exited 0 but made no
    edit twice: the governed config now carries an explicit bounded editing
    tool allowlist (no bash) while ``--mode json`` usage capture is
    retained and the prompt stays the final argv element.
    """
    route = StaffingRoute(
        route_id="pi-edit-fixture",
        model="z-ai/glm-5.3-flash",
        effort=None,
        harness="pi",
        channel="openrouter",
        dispatch_template="pi {prompt}",
        usage_capture="pi_json",
        status="active",
    )
    argv = build_dispatch_command(route)
    assert argv[0] == "pi"
    assert argv[argv.index("--mode") + 1] == "json"
    assert "--tools" in argv
    tools = argv[argv.index("--tools") + 1]
    assert tools == "read,edit,write,grep,find,ls"
    assert "bash" not in tools
    assert "--provider" in argv
    assert argv[argv.index("--provider") + 1] == "openrouter"
    assert argv[-1] == "{prompt}"


def test_build_dispatch_command_codex_governed_sandbox_flags() -> None:
    """P1-8 regression: governed Codex dispatch gains its sandbox flags.

    Reproduces the live failure where ``codex exec`` in a non-git scratch
    workdir exited 1 in ~0.5s with empty stdout: the governed config now
    appends ``-s workspace-write --skip-git-repo-check`` immediately after
    the forced ``--json`` capture flag, with no dangerous bypass flag and
    the prompt still the final argv element.
    """
    route = StaffingRoute(
        route_id="codex-edit-fixture",
        model="gpt-5.6-sol",
        effort="low",
        harness="codex",
        channel="openai-sub",
        dispatch_template="codex exec {prompt}",
        usage_capture="codex_jsonl",
        status="active",
    )
    argv = build_dispatch_command(route)
    assert argv[:5] == ["codex", "exec", "--json", "-s", "workspace-write"]
    assert "--skip-git-repo-check" in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert "--yolo" not in argv
    assert "--full-auto" not in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "gpt-5.6-sol"
    assert argv[-1] == "{prompt}"


def test_build_dispatch_command_claude_governed_permission_flags() -> None:
    """P1-8 regression: governed Claude dispatch accepts edits noninteractively.

    Reproduces the live failure where an eligible Claude impl ``run`` in a
    scratch workdir exited 1 in ~6s with empty stream-json stdout, made no
    edit, and failed the oracle: the governed argv now carries the
    documented safe permission flags ``--permission-mode acceptEdits``
    plus ``--permission-prompts none`` while the stream-json usage capture
    pair, the model/effort flags, and the trailing ``{prompt}`` placeholder
    are all retained. No bypass flag is ever emitted.
    """
    route = StaffingRoute(
        route_id="claude-edit-fixture",
        model="claude-sonnet-5",
        effort="high",
        harness="claude",
        channel="anthropic-sub",
        dispatch_template="claude {prompt}",
        usage_capture="claude_stream_json",
        status="active",
    )
    argv = build_dispatch_command(route)
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert argv.index("--permission-mode") < argv.index("--permission-prompts")
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"
    assert "--effort" in argv
    assert argv[argv.index("--effort") + 1] == "high"
    for forbidden in (
        "bypassPermissions",
        "--permission-mode=bypassPermissions",
        "--dangerously-skip-permissions",
    ):
        assert forbidden not in argv
    assert argv[-1] == "{prompt}"


def test_build_dispatch_command_agy_governed_json_flag() -> None:
    """Astra blocker 3: agy dispatch carries the accepted governed JSON flags.

    Reproduces the finding where ``build_dispatch_command`` built an empty
    configuration for the agy harness, so the worker emitted text instead
    of the JSON receipt the accepted P1-4d parser captures. The argv now
    applies ``AGY_GOVERNED_CONFIG`` (``--output-format json``) with the
    route's model and effort, and the prompt stays the final element.
    """
    route = StaffingRoute(
        route_id="agy-fixture",
        model="gemini-3.8-flash",
        effort="medium",
        harness="agy",
        channel="gemini-sub",
        dispatch_template="agy {prompt}",
        usage_capture="agy_json",
        status="active",
    )
    argv = build_dispatch_command(route)
    assert argv[0] == "agy"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "gemini-3.8-flash"
    assert argv[argv.index("--effort") + 1] == "medium"
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    # The prompt placeholder stays the final element after the JSON flags.
    assert argv[-2:] == ["-p", "{prompt}"]
    assert argv.index("--output-format") < argv.index("-p")
    # agy print mode defaults to a 5m0s wait; the governed command must
    from lee_llm_router.watchdog import DEFAULT_MAX_MINUTES

    # carry the run ceiling so the watchdog bounds the worker, not agy.
    assert argv[argv.index("--print-timeout") + 1] == (
        f"{int(DEFAULT_MAX_MINUTES * 60)}s"
    )
    assert argv.index("--print-timeout") < argv.index("-p")
    bounded = build_dispatch_command(route, timeout_seconds=2400)
    assert bounded[bounded.index("--print-timeout") + 1] == "2400s"


def test_build_dispatch_command_opencode_governed_json_flag() -> None:
    """Astra blocker 3: OpenCode dispatch carries the governed ``--format json``.

    Reproduces the finding where the OpenCode harness got an empty config
    and the accepted P1-4e parser never received the JSON usage event. The
    argv now applies ``OPENCODE_GOVERNED_CONFIG`` (``--format json``) with
    the route's model, prompt placeholder still final.
    """
    route = StaffingRoute(
        route_id="opencode-fixture",
        model="opencode-go/deepseek-v4-flash",
        effort=None,
        harness="opencode",
        channel="opencode-go",
        dispatch_template="opencode run {prompt}",
        usage_capture="opencode_json",
        status="active",
    )
    argv = build_dispatch_command(route)
    assert argv[0] == "opencode"
    assert argv[1] == "run"
    assert argv[argv.index("-m") + 1] == "opencode-go/deepseek-v4-flash"
    assert "--format" in argv
    assert argv[argv.index("--format") + 1] == "json"
    # OpenCode exposes no effort flag; no effort argv is ever emitted.
    assert "--effort" not in argv
    assert argv[-1] == "{prompt}"
    assert argv.index("--format") < len(argv) - 2


def test_build_dispatch_command_omp_governed_json_mode() -> None:
    """Astra blocker 3: OMP dispatch carries the governed ``--mode json``.

    Reproduces the finding where the OMP harness got an empty config, so
    the legacy text default ran and the accepted P1-4f parser never saw
    the JSON event stream. The argv now applies ``OMP_GOVERNED_CONFIG``
    (``--mode json``) with the route's model; omp exposes no effort flag.
    """
    route = StaffingRoute(
        route_id="omp-fixture",
        model="openai/gpt-5.2",
        effort="low",
        harness="omp",
        channel="openrouter",
        dispatch_template="omp {prompt}",
        usage_capture="omp_json",
        status="active",
    )
    argv = build_dispatch_command(route)
    assert argv[0] == "omp"
    assert argv[1] == "-p"
    assert "--mode" in argv
    assert argv[argv.index("--mode") + 1] == "json"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "openai/gpt-5.2"
    assert "--effort" not in argv


def _assert_unavailable_usage(usage: dict[str, Any], reason_fragment: str) -> None:
    assert set(usage) == USAGE_KEYS | {"unavailable_reason"}
    assert usage["basis"] == "unavailable"
    assert reason_fragment in usage["unavailable_reason"]
    assert usage["input_tokens"] is None
    assert usage["output_tokens"] is None
    assert usage["cached_input_tokens"] is None
    assert usage["reasoning_tokens"] is None
    assert usage["total_tokens"] is None


def test_usage_for_harness_agy_valid_and_missing_receipt() -> None:
    """Astra blocker 3: agy usage flows through the accepted P1-4d parser.

    A valid ``agy -p --output-format json`` receipt yields provider-reported
    counters with the exact Phase 1 taxonomy source; output without a
    terminal usage receipt records unavailable with null counters — never
    zeros or estimates.
    """
    usage = _usage_for_harness("agy", AGY_RECEIPT_STDOUT)
    assert set(usage) == PROVIDER_REPORTED_KEYS | {"cache_write_tokens"}
    assert usage["source"] == AGY_USAGE_SOURCE
    assert AGY_USAGE_SOURCE == "agy -p usage line (agent-orch worker.py)"
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 25
    assert usage["cached_input_tokens"] == 50
    assert usage["reasoning_tokens"] == 10
    assert usage["total_tokens"] == 125

    missing = _usage_for_harness("agy", "worker printed plain text only")
    _assert_unavailable_usage(missing, "agy -p output")


def test_usage_for_harness_opencode_valid_and_missing_usage() -> None:
    """Astra blocker 3: OpenCode usage flows through the accepted P1-4e parser.

    A valid ``opencode run --format json`` step_finish event yields
    provider-reported counters with the exact Phase 1 taxonomy source;
    output without a step_finish usage event records unavailable with null
    counters.
    """
    usage = _usage_for_harness("opencode", OPENCODE_RECEIPT_STDOUT)
    assert set(usage) == PROVIDER_REPORTED_KEYS | {"cache_write_tokens"}
    assert usage["source"] == OPENCODE_USAGE_SOURCE
    assert OPENCODE_USAGE_SOURCE == "opencode run JSON usage event"
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 25
    assert usage["cached_input_tokens"] == 40
    assert usage["reasoning_tokens"] == 5
    # OpenCode reports no native total; it is derived only from the
    # reported input/output/reasoning components, cache kept separate.
    assert usage["total_tokens"] == 130

    missing = _usage_for_harness(
        "opencode", json.dumps({"type": "text", "part": {"text": "hi"}})
    )
    _assert_unavailable_usage(missing, "no step_finish usage event")


def test_usage_for_harness_omp_valid_and_missing_usage() -> None:
    """Astra blocker 3: OMP usage flows through the accepted P1-4f parser.

    A valid ``omp -p --mode json`` message_end event yields
    provider-reported counters with the exact Phase 1 taxonomy source;
    output without an assistant terminal event records unavailable with
    null counters.
    """
    usage = _usage_for_harness("omp", OMP_RECEIPT_STDOUT)
    assert set(usage) == PROVIDER_REPORTED_KEYS
    assert usage["source"] == OMP_USAGE_SOURCE
    assert OMP_USAGE_SOURCE == "omp -p --mode json events"
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 20
    assert usage["cached_input_tokens"] == 5
    assert usage["reasoning_tokens"] is None
    # cacheWrite contributes to the reported total but has no v2 field.
    assert usage["total_tokens"] == 127

    missing = _usage_for_harness(
        "omp", json.dumps({"type": "message_end", "message": {"role": "user"}})
    )
    _assert_unavailable_usage(missing, "no assistant message_end events")


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
    assert payload["failure_class"] == "platform_timeout"
    assert "exit_code=124, timed_out=True" in payload["provenance"]["notes"][0]
    assert payload["wall_clock_ms"] > 0
    _assert_output_matches_single_append(captured, scratch_state)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_worker_ceiling_kill_terminates_whole_process_group(tmp_path) -> None:
    """Astra P2-10 finding 1 regression: the ceiling kill kills descendants.

    A real worker is launched through the default real ``subprocess.Popen``
    in its own session/process group, spawns a ``sleep`` descendant, and
    hits a short wall-clock ceiling. The dispatch returns 124 and the
    descendant process is gone — not just the immediate shell. PID reuse is
    avoided by polling for the descendant's exact pid to become unreferencable
    and by confirming ``/proc`` no longer lists it.
    """
    pid_file = tmp_path / "descendant.pid"
    pgid_file = tmp_path / "worker.pgid"
    script = (
        "sleep 300 & echo $! > {pid}; "
        "ps -o pgid= -p $$ > {pgid} 2>/dev/null; "
        "wait"
    ).format(pid=shlex.quote(str(pid_file)), pgid=shlex.quote(str(pgid_file)))
    resolution = Resolution(
        worker_id="process-group-regression",
        dispatch_command=["/bin/sh", "-c", script],
        prompt_delivery="argv",
    )

    code = run_supervised_dispatch(
        resolution,
        "unused-prompt",
        max_minutes=2.0 / 60.0,  # 2-second wall-clock ceiling
        popen=subprocess.Popen,
        clock=time.monotonic,
        sleep=time.sleep,
        poll_seconds=0.05,
        sink=lambda _chunk: None,
        err_sink=lambda _chunk: None,
    )

    assert code == 124
    descendant_pid = int(pid_file.read_text())
    # The worker ran as a session/group leader, so it was killable as a
    # group. When ``ps`` is available, verify its pgid was not the test
    # runner's own group.
    if pgid_file.exists() and pgid_file.read_text().strip():
        worker_pgid = int(pgid_file.read_text())
        assert worker_pgid != os.getpgid(0)

    # The descendant must be gone: poll its exact pid until unreferencable,
    # then confirm /proc agrees (guards against zombie or PID-reuse reads).
    gone_deadline = time.monotonic() + 10.0
    while time.monotonic() < gone_deadline:
        try:
            os.kill(descendant_pid, 0)
        except ProcessLookupError:
            break
        except PermissionError:
            time.sleep(0.05)
        else:
            time.sleep(0.05)
    else:
        pytest.fail(f"descendant {descendant_pid} survived the worker ceiling kill")
    assert not Path(f"/proc/{descendant_pid}").exists()


@pytest.mark.skipif(
    not (os.name == "posix" and sys.platform.startswith("linux")),
    reason="recursive process-tree discovery uses Linux /proc",
)
def test_worker_ceiling_kill_terminates_escaped_recursive_descendants(
    tmp_path,
) -> None:
    """A new-session child and its child die at the worker's ceiling.

    Process-group-only cleanup does not touch ``detached`` or ``grandchild``:
    the former calls ``start_new_session=True`` and the latter inherits its
    new session. The recorded start times make the post-kill assertion robust
    against PID reuse, and the ``finally`` block prevents a failed regression
    from leaking real processes into the test runner.
    """
    pid_file = tmp_path / "escaped-descendants.txt"
    worker_pgid_file = tmp_path / "worker-pgid"
    child_code = (
        "import os, pathlib, subprocess, sys, time\n"
        f"grandchild = subprocess.Popen([{sys.executable!r}, '-c', "
        "'import time; time.sleep(300)'])\n"
        "def start_time(pid):\n"
        "    return pathlib.Path('/proc/' + str(pid) + '/stat').read_text()"
        ".rsplit(')', 1)[1].split()[19]\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(\n"
        "    ' '.join((str(os.getpid()), str(os.getsid(0)), str(grandchild.pid), "
        "start_time(os.getpid()), start_time(grandchild.pid)))\n"
        ")\n"
        "time.sleep(300)\n"
    )
    worker_code = (
        "import os, pathlib, subprocess, sys, time\n"
        f"pathlib.Path({str(worker_pgid_file)!r}).write_text(str(os.getpgrp()))\n"
        "subprocess.Popen("
        f"[{sys.executable!r}, '-c', {child_code!r}], "
        "start_new_session=True)\n"
        "time.sleep(300)\n"
    )
    resolution = Resolution(
        worker_id="escaped-process-tree-regression",
        dispatch_command=[sys.executable, "-c", worker_code],
        prompt_delivery="argv",
    )

    try:
        code = run_supervised_dispatch(
            resolution,
            "unused-prompt",
            max_minutes=2.0 / 60.0,
            popen=subprocess.Popen,
            clock=time.monotonic,
            sleep=time.sleep,
            poll_seconds=0.05,
            sink=lambda _chunk: None,
            err_sink=lambda _chunk: None,
        )
        assert code == 124
        detached_pid, detached_sid, grandchild_pid, detached_start, grandchild_start = (
            pid_file.read_text().split()
        )
        assert int(detached_sid) != int(worker_pgid_file.read_text())
        for pid_text, start_time in (
            (detached_pid, detached_start),
            (grandchild_pid, grandchild_start),
        ):
            pid = int(pid_text)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    stat = Path(f"/proc/{pid}/stat").read_text()
                except FileNotFoundError:
                    break
                current_start = stat.rsplit(")", 1)[1].split()[19]
                if current_start != start_time:
                    break  # The original process is gone; the PID was reused.
                time.sleep(0.05)
            else:
                pytest.fail(f"escaped descendant {pid} survived the ceiling kill")
    finally:
        # Cleanup is identity-checked so a reused PID cannot kill an unrelated
        # test process if this regression fails before its assertions finish.
        if pid_file.exists():
            fields = pid_file.read_text().split()
            for pid_text, start_time in (
                (fields[0], fields[3]),
                (fields[2], fields[4]),
            ):
                pid = int(pid_text)
                try:
                    stat = Path(f"/proc/{pid}/stat").read_text()
                    current_start = stat.rsplit(")", 1)[1].split()[19]
                except FileNotFoundError:
                    continue
                if current_start == start_time:
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass


@pytest.mark.skipif(
    not (os.name == "posix" and sys.platform.startswith("linux")),
    reason="inherited provenance discovery uses Linux /proc",
)
def test_worker_ceiling_kills_reparented_orphan_after_ancestry_disappears(
    tmp_path: Path,
) -> None:
    """Astra High reproducer: kill a reparented, new-session grandchild.

    The worker launches a short-lived intermediate Python process. That
    process launches a sleeping grandchild with ``start_new_session=True``
    and redirected standard streams, then exits. The worker confirms that the
    grandchild is sleeping under pid 1 and remains alive until its two-second
    ceiling. At cleanup no live PPID chain connects the orphan to the worker,
    so process-group-only or timeout-time ancestry discovery cannot find it.
    """
    observation_file = tmp_path / "reparented-grandchild.txt"
    grandchild_file = tmp_path / "grandchild-identity.txt"
    intermediate_code = (
        "import pathlib, subprocess, sys\n"
        "grandchild = subprocess.Popen("
        f"[{sys.executable!r}, '-c', 'import time; time.sleep(300)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, start_new_session=True)\n"
        f"stat = pathlib.Path('/proc/' + str(grandchild.pid) + '/stat')"
        ".read_text().rsplit(')', 1)[1].split()\n"
        f"pathlib.Path({str(grandchild_file)!r}).write_text("
        "f'{grandchild.pid} {stat[19]}')\n"
    )
    worker_code = (
        "import pathlib, subprocess, sys, time\n"
        f"intermediate = subprocess.Popen([{sys.executable!r}, '-c', "
        f"{intermediate_code!r}])\n"
        "intermediate.wait()\n"
        f"identity = pathlib.Path({str(grandchild_file)!r}).read_text()\n"
        "pid_text, start_time = identity.split()\n"
        "pid = int(pid_text)\n"
        "for _ in range(200):\n"
        "    stat = pathlib.Path('/proc/' + pid_text + '/stat').read_text()"
        ".rsplit(')', 1)[1].split()\n"
        "    if stat[0] == 'S' and int(stat[1]) == 1:\n"
        f"        pathlib.Path({str(observation_file)!r}).write_text("
        "f'{pid} {start_time} {intermediate.pid} {stat[0]} {stat[1]}')\n"
        "        break\n"
        "    time.sleep(0.005)\n"
        "else:\n"
        "    raise RuntimeError('grandchild did not become a sleeping orphan')\n"
        "time.sleep(300)\n"
    )
    resolution = Resolution(
        worker_id="reparented-orphan-regression",
        dispatch_command=[sys.executable, "-c", worker_code],
        prompt_delivery="argv",
    )

    identity: tuple[int, str] | None = None
    try:
        code = run_supervised_dispatch(
            resolution,
            "unused-prompt",
            max_minutes=2.0 / 60.0,
            popen=subprocess.Popen,
            clock=time.monotonic,
            sleep=time.sleep,
            poll_seconds=0.05,
            sink=lambda _chunk: None,
            err_sink=lambda _chunk: None,
        )

        assert code == 124
        pid_text, start_time, intermediate_pid, state, ppid = (
            observation_file.read_text().split()
        )
        identity = (int(pid_text), start_time)
        assert state == "S"
        assert int(ppid) == 1
        assert not Path(f"/proc/{intermediate_pid}").exists()

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                stat = Path(f"/proc/{pid_text}/stat").read_text()
            except FileNotFoundError:
                break
            if stat.rsplit(")", 1)[1].split()[19] != start_time:
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"reparented grandchild {pid_text} survived the ceiling kill")
    finally:
        # Identity-check emergency cleanup: a failing regression must not leak
        # the real sleeper or risk killing a process that reused its PID.
        if identity is None and grandchild_file.exists():
            pid_text, start_time = grandchild_file.read_text().split()
            identity = (int(pid_text), start_time)
        if identity is not None:
            pid, start_time = identity
            try:
                stat = Path(f"/proc/{pid}/stat").read_text()
            except FileNotFoundError:
                pass
            else:
                if stat.rsplit(")", 1)[1].split()[19] == start_time:
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass


def test_fake_worker_launch_gets_no_process_group_flag() -> None:
    """Injected fake Popens stay untouched: no POSIX-only flag, no wrapping."""
    launcher = LaunchRecorder(never_exits=True)
    resolution = Resolution(
        worker_id="fake-boundary",
        dispatch_command=["fake-worker", "{prompt}"],
        prompt_delivery="argv",
    )
    clock = AdvancingClock(step=60.0)

    code = run_supervised_dispatch(
        resolution,
        "prompt-text",
        popen=launcher,
        clock=clock,
        sleep=lambda _s: None,
        poll_seconds=0.05,
        sink=lambda _chunk: None,
        err_sink=lambda _chunk: None,
    )

    assert code == 124
    proc = launcher.processes[0]
    assert isinstance(proc, FakeProcess)  # never wrapped in a group proxy
    assert "start_new_session" not in proc.popen_kwargs
    assert "env" not in proc.popen_kwargs


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


def test_run_launches_once_and_appends_exactly_one_matching_record(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Success path has one child, one valid line, and output agreement."""
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["schema_version"] == 2
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


def test_run_record_carries_duration_and_dispatch_provenance_without_streams(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """The strict v2 record carries duration and compact dispatch evidence."""
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
    assert "dispatch" not in payload
    assert CODEX_RECEIPT_STDOUT not in json.dumps(payload)
    assert stderr_line.decode("utf-8") not in json.dumps(payload)
    assert isinstance(payload["wall_clock_ms"], int)
    assert set(payload["usage"]) == PROVIDER_REPORTED_KEYS
    _assert_output_matches_single_append(captured, scratch_state)


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
    assert payload["verdict"] == "unverified"
    assert payload["oracle_cmd"] is None
    assert payload["verified_success"] is False
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
    assert payload["verdict"] == "pass"
    assert payload["oracle_cmd"] == "oracle --label 'hello world'"
    assert payload["failure_class"] is None
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "supervisor_route_unattested"
    assert "supervisor_route" not in payload
    assert (
        "exit_code=0, timed_out=False, error=none" in payload["provenance"]["notes"][-1]
    )
    assert len(launcher.calls) == 2
    assert launcher.calls[0][1]["cwd"] == str(workdir)
    assert launcher.calls[1][1]["cwd"] == str(workdir)
    assert launcher.calls[0][1]["shell"] is False
    assert launcher.calls[1][1]["shell"] is False
    assert launcher.calls[1][0] == ["oracle", "--label", "hello world"]


def test_run_attested_pass_sets_verified_success_and_records_supervisor_route(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A complete attested pass is verified and records catalog route evidence."""
    launcher = SequencedLaunchRecorder(
        [_worker_spec(), {"chunks": [b"oracle passed\n"], "exit_code": 0}]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        supervisor_route=CODEX_ROUTE,
        launcher=launcher,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    supervisor = _route_record(catalog_dir, CODEX_ROUTE)
    assert payload["supervisor_route"] == {
        "model": supervisor.model,
        "effort": supervisor.effort,
        "harness": supervisor.harness,
        "channel": supervisor.channel,
        "provider": "codex_cli",
    }
    assert payload["verified_success"] is True
    assert "verified_success_reason" not in payload
    assert len(launcher.calls) == 2


def test_run_subscription_unpriced_model_still_verifies_true(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """P3-7 answer 2: a subscription channel's unpriceable model must not
    withhold verification from an otherwise complete attested pass.

    ``agy-gemini-3-8-flash-high-gemini-sub`` is a real committed
    ``gemini-sub`` (subscription) route whose model id is an internal
    effort-tiered encoding with no row in the pinned OpenRouter snapshot or
    the agent-orch rate table, so its cost is permanently ``unavailable``
    ("selected route has no dated price") — this reproduces the acceptance
    defect where a passing, attested attempt on this route was recorded
    ``verified_success: false — evidence_incomplete`` purely because a
    subscription channel's list-equivalent cost could not be computed.
    """
    launcher = SequencedLaunchRecorder(
        [
            {"chunks": [(AGY_RECEIPT_STDOUT + "\n").encode("utf-8")], "exit_code": 0},
            {"chunks": [b"oracle passed\n"], "exit_code": 0},
        ]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route="agy-gemini-3-8-flash-high-gemini-sub",
        supervisor_route=CODEX_ROUTE,
        launcher=launcher,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["route"]["channel"] == "gemini-sub"
    assert payload["usage"]["basis"] == "provider_reported"
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert payload["verified_success"] is True
    assert "verified_success_reason" not in payload


def test_verified_success_reason_subscription_exempts_unavailable_cost() -> None:
    """Direct gate test: subscription-channel unavailable cost verifies true."""
    from lee_llm_router.staffing.run import DispatchOutcome, _verified_success_reason

    dispatch = DispatchOutcome(
        argv=("agy",),
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={},
    )
    record = {
        "supervisor_route": {
            "model": "gpt-5.6-sol",
            "effort": "low",
            "harness": "codex",
            "channel": "openai-sub",
        },
        "route": {
            "model": "gemini-3.8-flash-high",
            "effort": "high",
            "harness": "agy",
            "channel": "gemini-sub",
        },
        "class_record": {"role": "impl"},
        "oracle_cmd": "pytest -q",
        "failure_class": None,
        "wall_clock_ms": 1000,
    }
    usage = {"basis": "provider_reported", "input_tokens": 10, "output_tokens": 2}
    cost = {"basis": ["unavailable"]}

    assert (
        _verified_success_reason(dispatch, "pass", record, usage, cost, "subscription")
        is None
    )


@pytest.mark.parametrize("channel_kind", ["metered", "local", None])
def test_verified_success_reason_non_subscription_still_requires_cost(
    channel_kind: str | None,
) -> None:
    """Only a channel positively known to be 'subscription' is exempt.

    A metered channel's unavailable cost is real missing spend evidence; an
    unrecognised or ``local`` channel fails closed the same way — never
    guessed into the exemption.
    """
    from lee_llm_router.staffing.run import DispatchOutcome, _verified_success_reason

    dispatch = DispatchOutcome(
        argv=("pi",),
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={},
    )
    record = {
        "supervisor_route": {
            "model": "gpt-5.6-sol",
            "effort": "low",
            "harness": "codex",
            "channel": "openai-sub",
        },
        "route": {
            "model": "z-ai/glm-5.3-flash",
            "effort": None,
            "harness": "pi",
            "channel": "openrouter",
        },
        "class_record": {"role": "impl"},
        "oracle_cmd": "pytest -q",
        "failure_class": None,
        "wall_clock_ms": 1000,
    }
    usage = {"basis": "provider_reported", "input_tokens": 10, "output_tokens": 2}
    cost = {"basis": ["unavailable"]}

    assert (
        _verified_success_reason(dispatch, "pass", record, usage, cost, channel_kind)
        == "evidence_incomplete"
    )


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
        supervisor_route=CODEX_ROUTE,
        launcher=launcher,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 0
    payload = json.loads(captured.out)
    assert payload["verdict"] == "fail"
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "oracle_not_passed"
    assert payload["oracle_cmd"] == "oracle --check"
    assert payload["failure_class"] == "spec_rejected"
    assert (
        "exit_code=9, timed_out=False, error=none" in payload["provenance"]["notes"][-1]
    )
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
        supervisor_route=CODEX_ROUTE,
        launcher=launcher,
        extra=("--oracle", "oracle"),
    )

    assert code == 7
    payload = json.loads(captured.out)
    assert payload["verdict"] == "pass"
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "worker_dispatch_failed"
    assert "exit_code=7, timed_out=False" in payload["provenance"]["notes"][0]
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
    payload = json.loads(captured.out)
    assert payload["verdict"] == "fail"
    assert payload["failure_class"] == "platform_timeout"
    assert (
        "exit_code=124, timed_out=True, error=none"
        in payload["provenance"]["notes"][-1]
    )
    assert len(launcher.calls) == 2
    assert launcher.processes[1].killed is True


def test_run_deleted_workdir_after_worker_persists_one_attempt(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """A workdir race after the worker never drops the completed worker.

    Astra final-review finding 6 reproducer: the oracle cannot be set up
    after the worker completed (workdir deleted between the two
    boundaries). Exactly one schema-valid attempt is persisted preserving
    the worker evidence and the oracle failure, with a truthful verdict,
    failure class, and verified_success, and the governed failure is
    returned (exit 3). The oracle never launches.
    """
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
    # Exactly one ledger record and it is the only stdout object.
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["record_kind"] == "router_run"
    # Worker evidence preserved verbatim.
    assert payload["usage"]["basis"] == "provider_reported"
    assert payload["usage"]["input_tokens"] == 10
    assert payload["usage"]["output_tokens"] == 20
    assert payload["usage"]["total_tokens"] == 30
    # Oracle failure preserved as failed evidence with its error.
    assert payload["verdict"] == "fail"
    assert payload["failure_class"] == "platform_env"
    assert payload["oracle_cmd"] == "oracle --check"
    assert "workdir is not a directory" in payload["provenance"]["notes"][-1]
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "supervisor_route_unattested"
    assert payload["selection"]["basis"] == "explicit"


def test_run_attested_oracle_setup_failure_reason_is_oracle_not_passed(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """Attested run with an oracle setup failure names the oracle gap.

    The truthful verified_success precedence holds on the governed failure
    path too: attested, dispatched, but the oracle verdict is not pass.
    """
    workdir = tmp_path / "attested-deleted-after-worker"
    workdir.mkdir()
    launcher = WorkdirDeletingLaunchRecorder(workdir)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=LUNA_ROUTE,
        supervisor_route=CODEX_ROUTE,
        workdir=workdir,
        launcher=launcher,
        extra=("--oracle", "oracle --check"),
    )

    assert code == 3
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["supervisor_route"]["model"] == "gpt-5.6-sol"
    assert payload["verdict"] == "fail"
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "oracle_not_passed"


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
    payload = json.loads(captured.out)
    assert payload["verdict"] == "fail"
    assert payload["failure_class"] == "platform_env"
    assert (
        "launch failure: FileNotFoundError: oracle missing"
        in payload["provenance"]["notes"][-1]
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


# ---------------------------------------------------------------------------
# 11. P1-5b2 canonical record, cost, and append
# ---------------------------------------------------------------------------


def test_run_packet_id_is_content_addressed_not_a_path(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """The top-level packet id identifies exact text, independent of location."""
    from lee_llm_router.staffing.run import packet_id_for_text

    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode()])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["packet_id"] == packet_id_for_text(PACKET_TEXT)
    assert payload["packet_id"].startswith("sha256:")
    assert str(packet) not in payload["packet_id"]


def test_run_unknown_codex_cache_split_withholds_numeric_cost(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Codex input/output without a cached split cannot be priced as uncached."""
    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode()])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["cost"] == {"basis": ["unavailable"]}
    # The missing cache split remains null; it is never treated as all
    # uncached input.
    assert payload["usage"]["cached_input_tokens"] is None
    assert payload["usage"]["reasoning_tokens"] is None


@pytest.mark.parametrize(
    ("worker_stdout", "reason_fragment"),
    [
        ("", "output was empty"),
        (
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 12},
                }
            ),
            "missing or had invalid required",
        ),
    ],
    ids=["unavailable", "insufficient-required-usage"],
)
def test_run_unavailable_or_insufficient_usage_has_no_cost_figures(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    worker_stdout,
    reason_fragment,
):
    """Unknown required quantities produce unavailable cost, never figures."""
    chunks = [(worker_stdout + "\n").encode()] if worker_stdout else []
    launcher = LaunchRecorder(chunks=chunks)
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["usage"]["basis"] == "unavailable"
    assert reason_fragment in payload["usage"]["unavailable_reason"]
    assert payload["cost"] == {"basis": ["unavailable"]}


def test_run_invalid_final_record_writes_no_ledger_line(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """The committed ledger validation refuses a malformed candidate pre-write."""
    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode()])
    monkeypatch.setattr(
        "lee_llm_router.staffing.run.build_attempt_record",
        lambda *_args, **_kwargs: {"schema_version": 2},
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

    assert code == 3
    assert "attempt record could not be appended" in captured.err
    assert "attempt-record v2 schema validation" in captured.err
    assert not scratch_state["attempts"].exists()
    assert len(launcher.processes) == 1


def test_run_calls_committed_append_once(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """One completed attempt crosses the committed append boundary once."""
    from lee_llm_router.staffing import ledger

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)
    launcher = LaunchRecorder(chunks=[(CODEX_RECEIPT_STDOUT + "\n").encode()])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert calls == [payload]


# ---------------------------------------------------------------------------
# P1-5 / Astra cache-pricing regression tests
# ---------------------------------------------------------------------------


def test_attempt_cost_glm_cache_pricing_regression(catalog_dir) -> None:
    """GLM cache pricing regression: recorded usage bills cache tokens additively."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import SelectionOutcome, _attempt_cost

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == PI_ROUTE)
    # z-ai/glm-5.3-flash (2026-09-11 snapshot, D218): prompt=0.00000015,
    # completion=0.0000005, cache=0.00000003
    pricing = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.00000015,
        replacement_output_usd_per_token=0.0000005,
        marginal_input_usd_per_token=0.00000015,
        marginal_output_usd_per_token=0.0000005,
        source="openrouter-snapshot:z-ai/glm-5.3-flash",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test GLM route",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )

    # Finding reproducer: input=4501, output=457, cached=5440, reasoning=193
    recorded_usage = {
        "basis": "provider_reported",
        "source": "pi --mode json events",
        "input_tokens": 4501,
        "output_tokens": 457,
        "cached_input_tokens": 5440,
        "reasoning_tokens": 193,
        "total_tokens": 10398,
    }

    cost, note = _attempt_cost(outcome, recorded_usage)
    assert cost["basis"] == ["list", "marginal"]
    # 2026-09-11 snapshot rates (D218, doubled since 2026-09-09): 0.00106685
    # including cache (was 0.000533425 under the superseded snapshot).
    assert cost["usd_list"] == pytest.approx(0.00106685)
    assert cost["usd_marginal"] == pytest.approx(0.00106685)
    assert "cache" in note


def test_attempt_cost_sol_cache_pricing_regression(catalog_dir) -> None:
    """Sol cache pricing: cached tokens are an input subset at cache rate."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import SelectionOutcome, _attempt_cost

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    # gpt-5.6-sol: input=4.0/1M, output=20.0/1M, cache=0.40/1M.
    pricing = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.000004,
        replacement_output_usd_per_token=0.000020,
        marginal_input_usd_per_token=0.000004,
        marginal_output_usd_per_token=0.000020,
        source="rate-table:gpt-5.6-sol",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test Sol route",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )

    # Finding reproducer: input=59282, output=360, cached=51584, reasoning=18
    # uncached input = 59282 - 51584 = 7698
    # list cost = 7698 * 0.000004 + 51584 * 0.0000004 + 360 * 0.000020 = 0.0586256
    recorded_usage = {
        "basis": "provider_reported",
        "source": "codex exec --json usage",
        "input_tokens": 59282,
        "output_tokens": 360,
        "cached_input_tokens": 51584,
        "reasoning_tokens": 18,
        "total_tokens": 59642,
    }

    cost, note = _attempt_cost(outcome, recorded_usage)
    assert cost["basis"] == ["list", "marginal"]
    # Currently was 0.244328; must be 0.0586256 because cached is a subset
    assert cost["usd_list"] == pytest.approx(0.0586256)
    assert cost["usd_marginal"] == pytest.approx(0.0586256)
    assert "cache" in note

    # Also test with marginal multiplier 0.25 (ON TRACK)
    pricing_on_track = EligibilityPrice(
        badge="ON TRACK",
        multiplier=0.25,
        replacement_input_usd_per_token=0.000004,
        replacement_output_usd_per_token=0.000020,
        marginal_input_usd_per_token=0.000001,
        marginal_output_usd_per_token=0.000005,
        source="rate-table:gpt-5.6-sol",
    )
    outcome_on_track = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test Sol route on track",
        explain_ref="explain",
        excluded=(),
        pricing=pricing_on_track,
    )
    cost_ot, _ = _attempt_cost(outcome_on_track, recorded_usage)
    assert cost_ot["usd_list"] == pytest.approx(0.0586256)
    assert cost_ot["usd_marginal"] == pytest.approx(0.0586256 * 0.25)


def test_attempt_cost_edge_case_null_cached_count(catalog_dir) -> None:
    """Null cached count computes cost from input/output without fabricating zeroes."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import SelectionOutcome, _attempt_cost

    catalog = load_staffing_catalog(catalog_dir)
    route_sol = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    pricing_sol = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.000004,
        replacement_output_usd_per_token=0.000020,
        marginal_input_usd_per_token=0.000004,
        marginal_output_usd_per_token=0.000020,
        source="rate-table:gpt-5.6-sol",
    )
    outcome_sol = SelectionOutcome(
        route=route_sol,
        basis="explicit",
        reason="test Sol route",
        explain_ref="explain",
        excluded=(),
        pricing=pricing_sol,
    )
    # An absent cached-input split is not evidence that the whole input was
    # uncached, so the Codex cost is unavailable.
    cost, note = _attempt_cost(
        outcome_sol,
        {
            "basis": "provider_reported",
            "input_tokens": 59282,
            "output_tokens": 360,
            "cached_input_tokens": None,
        },
    )
    assert cost == {"basis": ["unavailable"]}
    assert "cached_input_tokens is unknown" in note

    # A source-reported zero split is a valid known-component branch.
    known_cost, _ = _attempt_cost(
        outcome_sol,
        {
            "basis": "provider_reported",
            "input_tokens": 59282,
            "output_tokens": 360,
            "cached_input_tokens": 0,
            "total_tokens": 59642,
        },
    )
    assert known_cost["basis"] == ["list", "marginal"]
    assert known_cost["usd_list"] == pytest.approx(0.244328)

    # GLM with cached None
    route_glm = next(r for r in catalog.routes.routes if r.route_id == PI_ROUTE)
    pricing_glm = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.000000075,
        replacement_output_usd_per_token=0.00000025,
        marginal_input_usd_per_token=0.000000075,
        marginal_output_usd_per_token=0.00000025,
        source="openrouter-snapshot:z-ai/glm-5.3-flash",
    )
    outcome_glm = SelectionOutcome(
        route=route_glm,
        basis="explicit",
        reason="test GLM route",
        explain_ref="explain",
        excluded=(),
        pricing=pricing_glm,
    )
    cost_glm, _ = _attempt_cost(
        outcome_glm,
        {
            "basis": "provider_reported",
            "input_tokens": 4501,
            "output_tokens": 457,
            "cached_input_tokens": None,
            # Pi's authoritative total includes the cache components; with
            # the total reported and a zero remainder over the represented
            # components, cache-write is arithmetically zero and cost stays
            # known without fabricating a cached zero.
            "total_tokens": 4958,
        },
    )
    assert cost_glm["basis"] == ["list", "marginal"]
    assert cost_glm["usd_list"] == pytest.approx(0.000451825)


def test_astra_billing_reproducers_fail_closed_or_bill_known_components() -> None:
    """Residual Astra cost reproducers never drop billable components."""
    from types import SimpleNamespace as Namespace

    from lee_llm_router.staffing.run import _attempt_cost

    pricing = Namespace(
        replacement_input_usd_per_token=1e-6,
        replacement_output_usd_per_token=2e-6,
        marginal_input_usd_per_token=1e-6,
        marginal_output_usd_per_token=2e-6,
        multiplier=1,
    )

    def selected(harness: str) -> Namespace:
        return Namespace(
            route=Namespace(harness=harness, model="fixture-model"),
            pricing=pricing,
            cache_replacement_usd_per_token=0.1e-6,
            cache_marginal_usd_per_token=0.1e-6,
            cache_rates_checked=True,
        )

    codex_usage = _usage_for_harness(
        "codex",
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
        ),
    )
    codex_cost, codex_note = _attempt_cost(selected("codex"), codex_usage)
    assert codex_cost == {"basis": ["unavailable"]}
    assert "cached_input_tokens is unknown" in codex_note

    agy_usage = _usage_for_harness(
        "agy",
        json.dumps(
            {
                "status": "SUCCESS",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 100,
                },
            }
        ),
    )
    assert agy_usage["cache_write_tokens"] == 100
    agy_cost, agy_note = _attempt_cost(selected("agy"), agy_usage)
    assert agy_cost == {"basis": ["unavailable"]}
    assert "cache_write_tokens has no selected dated price" in agy_note

    opencode_usage = _usage_for_harness(
        "opencode",
        json.dumps(
            {
                "type": "step_finish",
                "part": {
                    "tokens": {
                        "input": 10,
                        "output": 2,
                        "reasoning": 100,
                        "cache": {"read": 0, "write": 0},
                    }
                },
            }
        ),
    )
    assert opencode_usage["reasoning_tokens"] == 100
    assert opencode_usage["cache_write_tokens"] == 0
    opencode_cost, _ = _attempt_cost(selected("opencode"), opencode_usage)
    assert opencode_cost["basis"] == ["list", "marginal"]
    assert opencode_cost["usd_list"] == pytest.approx(0.000214)

    # Known zero cache components remain billable; no zero is fabricated for
    # the Codex split or agy cache write.
    codex_known = dict(codex_usage, cached_input_tokens=0)
    known_codex_cost, _ = _attempt_cost(selected("codex"), codex_known)
    assert known_codex_cost["usd_list"] == pytest.approx(0.000014)

    agy_known_usage = dict(agy_usage, cache_write_tokens=0)
    known_agy_cost, _ = _attempt_cost(selected("agy"), agy_known_usage)
    assert known_agy_cost["usd_list"] == pytest.approx(0.000014)


def test_attempt_cost_edge_case_unavailable_price_evidence(catalog_dir) -> None:
    """Missing cache evidence fails closed when reported cache is used."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import SelectionOutcome, _attempt_cost

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == PI_ROUTE)

    # 1. Route has no pricing at all
    outcome_no_price = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="no price",
        explain_ref="explain",
        excluded=(),
        pricing=None,
    )
    cost, note = _attempt_cost(
        outcome_no_price,
        {
            "basis": "provider_reported",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_input_tokens": 20,
        },
    )
    assert cost == {"basis": ["unavailable"]}
    assert "no dated price" in note

    # 2. Pricing source lists a model with no cache price in OpenRouter snapshot
    # tencent/hy-mt2-1.8b has prompt/completion but NO input_cache_read
    pricing_unpriced_cache = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.000000044,
        replacement_output_usd_per_token=0.000000177,
        marginal_input_usd_per_token=0.000000044,
        marginal_output_usd_per_token=0.000000177,
        source="openrouter-snapshot:tencent/hy-mt2-1.8b",
    )
    outcome_unpriced = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="unpriced cache",
        explain_ref="explain",
        excluded=(),
        pricing=pricing_unpriced_cache,
    )
    cost, note = _attempt_cost(
        outcome_unpriced,
        {
            "basis": "provider_reported",
            "input_tokens": 1000,
            "output_tokens": 200,
            "cached_input_tokens": 500,
            # Pi's total includes the cache components; a zero remainder
            # lets the cache-price gate be reached.
            "total_tokens": 1700,
        },
    )
    assert cost == {"basis": ["unavailable"]}
    assert "cache price is unavailable" in note

    # 3. But if cached_input_tokens is 0, missing cache price does not block calculation
    cost_zero, _ = _attempt_cost(
        outcome_unpriced,
        {
            "basis": "provider_reported",
            "input_tokens": 1000,
            "output_tokens": 200,
            "cached_input_tokens": 0,
            "total_tokens": 1200,
        },
    )
    assert cost_zero["basis"] == ["list", "marginal"]
    assert cost_zero["usd_list"] == pytest.approx(
        1000 * 0.000000044 + 200 * 0.000000177
    )


def test_attempt_cost_edge_case_invalid_relationship(catalog_dir) -> None:
    """Invalid relationships and cached counter types fail closed."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import SelectionOutcome, _attempt_cost

    catalog = load_staffing_catalog(catalog_dir)
    route_sol = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    pricing_sol = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.000004,
        replacement_output_usd_per_token=0.000020,
        marginal_input_usd_per_token=0.000004,
        marginal_output_usd_per_token=0.000020,
        source="rate-table:gpt-5.6-sol",
    )
    outcome_sol = SelectionOutcome(
        route=route_sol,
        basis="explicit",
        reason="test Sol route",
        explain_ref="explain",
        excluded=(),
        pricing=pricing_sol,
    )

    # 1. Codex subset contradiction: cached > input
    cost, note = _attempt_cost(
        outcome_sol,
        {
            "basis": "provider_reported",
            "source": "codex exec --json usage",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_input_tokens": 150,
        },
    )
    assert cost == {"basis": ["unavailable"]}
    assert "cached_input_tokens contradicts input_tokens" in note

    # 2. Negative cached tokens
    cost_neg, note_neg = _attempt_cost(
        outcome_sol,
        {
            "basis": "provider_reported",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_input_tokens": -1,
        },
    )
    assert cost_neg == {"basis": ["unavailable"]}
    assert "cached_input_tokens is invalid" in note_neg

    # 3. Non-integer cached tokens (bool)
    cost_bool, note_bool = _attempt_cost(
        outcome_sol,
        {
            "basis": "provider_reported",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_input_tokens": True,
        },
    )
    assert cost_bool == {"basis": ["unavailable"]}
    assert "cached_input_tokens is invalid" in note_bool


def test_run_cli_cache_pricing_end_to_end(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
) -> None:
    """CLI end-to-end with fake subprocess applies cache accounting for Sol and GLM."""
    # 1. Codex Sol run with recorded cache usage
    sol_receipt = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 59282,
                "output_tokens": 360,
                "cached_input_tokens": 51584,
                "reasoning_output_tokens": 18,
                "total_tokens": 59642,
            },
        }
    )
    launcher_sol = LaunchRecorder(chunks=[(sol_receipt + "\n").encode()])
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        launcher=launcher_sol,
    )
    assert code == 0
    payload_sol = _assert_output_matches_single_append(captured, scratch_state)
    assert payload_sol["cost"]["basis"] == ["list", "marginal"]
    assert payload_sol["cost"]["usd_list"] == pytest.approx(0.0586256)
    # The healthy snapshot has openai-sub at "ON TRACK" (multiplier 0.25)
    assert payload_sol["cost"]["usd_marginal"] == pytest.approx(0.0586256 * 0.25)
    assert payload_sol["usage"]["cached_input_tokens"] == 51584
    assert payload_sol["usage"]["reasoning_tokens"] == 18

    # Clear attempts ledger for next run
    scratch_state["attempts"].unlink()

    # 2. Pi GLM run with recorded cache usage
    glm_receipt = json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "model": "z-ai/glm-5.3-flash",
                "usage": {
                    "input": 4501,
                    "output": 457,
                    "cacheRead": 5440,
                    "cacheWrite": 0,
                    "reasoning": 193,
                },
                "totalTokens": 10398,
            },
        }
    )
    launcher_glm = LaunchRecorder(chunks=[(glm_receipt + "\n").encode()])
    code_glm, captured_glm = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        launcher=launcher_glm,
    )
    assert code_glm == 0
    payload_glm = _assert_output_matches_single_append(captured_glm, scratch_state)
    assert payload_glm["cost"]["basis"] == ["list", "marginal"]
    # 2026-09-11 snapshot rates (D218, doubled since 2026-09-09).
    assert payload_glm["cost"]["usd_list"] == pytest.approx(0.00106685)
    assert payload_glm["cost"]["usd_marginal"] == pytest.approx(0.00106685)
    assert payload_glm["usage"]["cached_input_tokens"] == 5440
    assert payload_glm["usage"]["reasoning_tokens"] == 193


# ---------------------------------------------------------------------------
# Astra contract blocker: worker usage capture exceptions must not drop
# the completed worker from the attempt ledger
# ---------------------------------------------------------------------------


def test_run_worker_usage_capture_exception_appends_attempt_with_unavailable_usage(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A completed worker must never disappear from the ledger because capture raises.

    Quoted reproducer: when usage capture raises after the worker completes,
    CLI exits 3 and the ledger append spy sees zero calls.
    Fixed: build and append exactly one truthful router_run record with usage
    basis unavailable, null token counters, diagnostic preserved in
    unavailable_reason, cost unavailable, and verified_success false.
    """
    from lee_llm_router.staffing import ledger

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)

    # Contradictory total_tokens causes capture_codex_usage to raise LLMRouterError
    contradictory_stdout = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 10,  # contradicts 100 + 50 = 150
            },
        }
    )
    launcher = LaunchRecorder(chunks=[(contradictory_stdout + "\n").encode("utf-8")])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(calls) == 1
    assert calls[0] == payload

    # Truthful attempt record checks
    assert payload["record_kind"] == "router_run"
    assert payload["route"]["harness"] == "codex"
    assert payload["usage"]["basis"] == "unavailable"
    assert payload["usage"]["input_tokens"] is None
    assert payload["usage"]["output_tokens"] is None
    assert payload["usage"]["cached_input_tokens"] is None
    assert payload["usage"]["reasoning_tokens"] is None
    assert payload["usage"]["total_tokens"] is None
    assert "source" not in payload["usage"]
    assert (
        "usage capture failed for harness 'codex'"
        in payload["usage"]["unavailable_reason"]
    )
    assert "total_tokens contradicts" in payload["usage"]["unavailable_reason"]
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "supervisor_route_unattested"


def test_run_claude_pathological_integer_keeps_completed_worker_record(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A second Claude parse failure must not drop the completed worker."""
    from lee_llm_router.staffing import ledger

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)
    receipt = (
        '{"type":"result","usage":{"input_tokens":'
        + "1" * 5000
        + ',"output_tokens":2}}'
    )
    launcher = LaunchRecorder(chunks=[(receipt + "\n").encode("utf-8")])

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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.processes) == 1
    assert len(calls) == 1
    assert payload["usage"]["basis"] == "unavailable"
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert (
        "usage capture failed for harness 'claude'"
        in payload["usage"]["unavailable_reason"]
    )


def test_run_worker_usage_capture_exception_with_oracle_preserves_oracle_evidence(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """When capture raises, oracle execution and evidence are preserved in ledger."""
    from lee_llm_router.staffing import ledger

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)

    workdir = tmp_path / "workdir"
    workdir.mkdir()

    # Contradictory output causes capture to raise
    contradictory_stdout = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 10,
            },
        }
    )
    launcher = SequencedLaunchRecorder(
        [
            {"chunks": [(contradictory_stdout + "\n").encode("utf-8")], "exit_code": 0},
            {"chunks": [b"oracle passed all assertions\n"], "exit_code": 0},
        ]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        supervisor_route=CODEX_ROUTE,
        workdir=workdir,
        launcher=launcher,
        extra=("--oracle", "pytest -v"),
    )

    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(calls) == 1

    # Both worker and oracle were launched
    assert len(launcher.calls) == 2
    assert launcher.calls[1][0] == ["pytest", "-v"]

    # Oracle evidence preserved
    assert payload["oracle_cmd"] == "pytest -v"
    assert payload["verdict"] == "pass"
    assert (
        "exit_code=0, timed_out=False, error=none" in payload["provenance"]["notes"][-1]
    )

    # Usage and cost are unavailable
    assert payload["usage"]["basis"] == "unavailable"
    assert payload["cost"] == {"basis": ["unavailable"]}

    # Attested + passing oracle + unavailable usage -> evidence_incomplete
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "evidence_incomplete"


def test_run_worker_usage_capture_exception_with_failing_oracle(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """When capture raises and oracle fails, oracle verdict fail takes precedence."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()

    contradictory_stdout = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 10,
            },
        }
    )
    launcher = SequencedLaunchRecorder(
        [
            {"chunks": [(contradictory_stdout + "\n").encode("utf-8")], "exit_code": 0},
            {"chunks": [b"FAILED: 1 test failed\n"], "exit_code": 1},
        ]
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        supervisor_route=CODEX_ROUTE,
        workdir=workdir,
        launcher=launcher,
        extra=("--oracle", "pytest -v"),
    )

    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["verdict"] == "fail"
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "oracle_not_passed"
    assert payload["usage"]["basis"] == "unavailable"
    assert payload["cost"] == {"basis": ["unavailable"]}


def test_run_worker_usage_capture_exception_nonzero_worker_exit(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Nonzero worker exit with capture error records worker_dispatch_failed."""
    from lee_llm_router.staffing import ledger

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)

    contradictory_stdout = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 10,
            },
        }
    )
    launcher = LaunchRecorder(
        chunks=[(contradictory_stdout + "\n").encode("utf-8")],
        exit_code=7,
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        supervisor_route=CODEX_ROUTE,
        launcher=launcher,
    )

    assert code == 7
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(calls) == 1
    assert payload["verified_success"] is False
    assert payload["verified_success_reason"] == "worker_dispatch_failed"
    assert payload["usage"]["basis"] == "unavailable"
    assert payload["cost"] == {"basis": ["unavailable"]}


def test_run_worker_arbitrary_capture_exception_handled(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Arbitrary capture exceptions are recorded as unavailable usage."""
    from lee_llm_router.staffing import ledger
    from lee_llm_router.staffing import run as run_mod

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)

    def exploding_capture(_stdout):
        raise RuntimeError("unexpected parser explosion")

    monkeypatch.setattr(run_mod, "capture_codex_usage", exploding_capture)

    launcher = LaunchRecorder(chunks=[b"some stdout\n"])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(calls) == 1
    assert payload["usage"]["basis"] == "unavailable"
    assert "unexpected parser explosion" in payload["usage"]["unavailable_reason"]
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert payload["verified_success"] is False


def test_pre_dispatch_configuration_error_writes_no_ledger_record(
    monkeypatch, capsys, catalog_dir, snapshot, packet, tmp_path, scratch_state
):
    """Pre-dispatch configuration errors refuse (exit 3) and append no ledger record."""
    from lee_llm_router.staffing import ledger

    calls: list[dict[str, Any]] = []
    real_append = ledger.append_attempt

    def recording_append(record):
        calls.append(record)
        return real_append(record)

    monkeypatch.setattr(ledger, "append_attempt", recording_append)

    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        workdir=tmp_path / "nonexistent-workdir",
        launcher=launcher,
    )

    assert code == 3
    assert launcher.processes == []
    assert len(calls) == 0
    assert not scratch_state["attempts"].exists()
    assert "workdir is not a directory" in captured.err


# ---------------------------------------------------------------------------
# Astra final re-review: contract-blocking findings 1-3
# ---------------------------------------------------------------------------


def test_run_claude_contradictory_cache_total_preserves_worker_with_unavailable_cost(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Finding 1: a Claude total below its known components never bills input/output.

    The exact Astra re-review reproducer receipt — input=10, output=2,
    cache_creation=100, absent cache-read, reported total=12 — previously
    produced one schema-valid record with numeric list=marginal cost that
    silently discarded the cache-write evidence. The contradictory total
    now fails capture closed: the completed worker is still persisted
    exactly once with unavailable usage (the contradiction diagnostic
    preserving the known-component evidence) and unavailable cost.
    """
    receipt = json.dumps(
        {
            "type": "result",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "cache_creation_input_tokens": 100,
                "total_tokens": 12,
            },
        }
    )
    launcher = LaunchRecorder(chunks=[(receipt + "\n").encode("utf-8")])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.processes) == 1
    assert payload["route"]["harness"] == "claude"
    assert payload["usage"]["basis"] == "unavailable"
    assert payload["usage"]["input_tokens"] is None
    assert payload["usage"]["output_tokens"] is None
    assert payload["usage"]["total_tokens"] is None
    assert "is below its known components" in payload["usage"]["unavailable_reason"]
    assert "112" in payload["usage"]["unavailable_reason"]
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert payload["verified_success"] is False


def test_run_claude_model_usage_contradictory_cache_total_is_unavailable_cost(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Finding 1 on the modelUsage path: the contradictory row total fails closed."""
    receipt = json.dumps(
        {
            "type": "result",
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 10,
                    "outputTokens": 2,
                    "cacheCreationInputTokens": 100,
                    "totalTokens": 12,
                }
            },
        }
    )
    launcher = LaunchRecorder(chunks=[(receipt + "\n").encode("utf-8")])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["usage"]["basis"] == "unavailable"
    assert "is below its known components" in payload["usage"]["unavailable_reason"]
    assert payload["cost"] == {"basis": ["unavailable"]}


def test_run_claude_cache_write_total_preserves_evidence_without_numeric_cost(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Valid neighbor: consistent cache-write evidence keeps truthful usage.

    With the authoritative total at the known-component minimum (112 =
    10 + 2 + 100 and an unknown, never-zero cache-read), the record keeps
    the provider-reported tokens including the total that represents the
    cache-write evidence — but the unrepresented remainder fails cost
    closed instead of billing input/output only.
    """
    receipt = json.dumps(
        {
            "type": "result",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "cache_creation_input_tokens": 100,
                "total_tokens": 112,
            },
        }
    )
    launcher = LaunchRecorder(chunks=[(receipt + "\n").encode("utf-8")])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["usage"]["basis"] == "provider_reported"
    assert payload["usage"]["input_tokens"] == 10
    assert payload["usage"]["output_tokens"] == 2
    assert payload["usage"]["total_tokens"] == 112
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert any(
        "total_tokens includes cache-write tokens" in note
        for note in payload["provenance"]["notes"]
    )


def test_run_codex_huge_token_integer_keeps_worker_with_unavailable_cost(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Finding 2: a 10**400 token integer never loses the completed worker.

    The valid JSON integer passes capture as truthful provider-reported
    usage; previously the float price multiplication raised an uncaught
    OverflowError after the worker completed, dropping the attempt. Now
    exactly one schema-valid record persists with truthful usage and
    unavailable cost.
    """
    receipt = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10**400,
                "output_tokens": 2,
                "cached_input_tokens": 0,
            },
        }
    )
    launcher = LaunchRecorder(chunks=[(receipt + "\n").encode("utf-8")])
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.processes) == 1
    assert payload["usage"]["basis"] == "provider_reported"
    assert payload["usage"]["input_tokens"] == 10**400
    assert payload["usage"]["output_tokens"] == 2
    assert payload["usage"]["cached_input_tokens"] == 0
    assert payload["cost"] == {"basis": ["unavailable"]}
    assert any(
        "representable float cost range" in note
        for note in payload["provenance"]["notes"]
    )
    assert payload["verified_success"] is False


class CleanupTimeoutOracleProcess(FakeProcess):
    """Fake oracle that never exits and whose post-kill wait times out."""

    def wait(self, timeout: float = 0.0) -> int:
        if self.killed:
            raise subprocess.TimeoutExpired(cmd=" ".join(self.argv), timeout=timeout)
        return self._exit_code


class CleanupTimeoutLaunchRecorder(SequencedLaunchRecorder):
    """Sequenced recorder whose oracle's post-kill wait raises TimeoutExpired."""

    def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
        self.calls.append((list(argv), dict(kwargs)))
        spec = dict(self.specs[len(self.processes)])
        wait_raises = spec.pop("wait_raises_timeout", False)
        if wait_raises:
            proc: FakeProcess = CleanupTimeoutOracleProcess(argv, **spec, **kwargs)
        else:
            proc = FakeProcess(argv, **spec, **kwargs)
        self.processes.append(proc)
        return proc


def test_run_oracle_cleanup_timeout_expired_preserves_completed_worker(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Finding 3: a post-kill TimeoutExpired never drops the completed worker.

    The oracle exceeds its budget, is killed, and its ``wait`` then raises
    ``subprocess.TimeoutExpired`` — previously uncaught past the completed
    worker. Now the timeout oracle evidence is preserved (exit 124,
    timed_out) and exactly one schema-valid attempt with the governed
    failure status is appended.
    """
    launcher = CleanupTimeoutLaunchRecorder(
        [_worker_spec(), {"never_exits": True, "wait_raises_timeout": True}]
    )
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.calls) == 2
    assert launcher.processes[1].killed is True
    # Worker evidence preserved verbatim.
    assert payload["usage"]["basis"] == "provider_reported"
    assert payload["usage"]["input_tokens"] == 10
    assert payload["usage"]["output_tokens"] == 20
    assert payload["usage"]["total_tokens"] == 30
    # Failed/timeout oracle evidence preserved with the governed status.
    assert payload["verdict"] == "fail"
    assert payload["failure_class"] == "platform_timeout"
    assert payload["oracle_cmd"] == "oracle --check"
    assert (
        "exit_code=124, timed_out=True, error=none"
        in payload["provenance"]["notes"][-1]
    )
    assert payload["verified_success"] is False


def test_run_records_validated_class_derivation_overrides(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    derivation = tmp_path / "derivation.json"
    derivation.write_text(
        json.dumps(
            {
                "class_derivation": {
                    "class": {"class_key": IMPL_CLASS},
                    "override_records": [
                        {"field": "size_band", "derived": "xs", "value": "s"}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        extra=("--class-derivation", str(derivation)),
    )
    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert (
        'class derivation overrides: [{"derived":"xs","field":"size_band",'
        '"value":"s"}]' in payload["provenance"]["notes"]
    )


def test_run_refuses_mismatched_class_derivation_before_launch(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    derivation = tmp_path / "derivation.json"
    derivation.write_text(
        json.dumps(
            {
                "class": {"class_key": "impl/deterministic/none/l/python"},
                "override_records": [],
            }
        ),
        encoding="utf-8",
    )
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        extra=("--class-derivation", str(derivation)),
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    assert "must match --class" in captured.err


# ---------------------------------------------------------------------------
# P3-4: live run registry (--owned-paths, refusal, deregistration)
# ---------------------------------------------------------------------------

FAKE_LIVE_PID = 424242
"""A pid that only exists inside the fake identity seams below."""

FAKE_START_TIME = 777
"""Linux start time recorded by the fake identity seams."""


def _wire_fake_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake process identities: the test process and one fake live pid.

    Every identity read reports the same fake start time, so a registered
    record is consistently judged live; any other pid is dead.
    """
    from lee_llm_router.staffing import census as census_mod

    own_pid = os.getpid()

    def alive(pid: int) -> bool:
        return pid == own_pid or pid == FAKE_LIVE_PID

    def identity(pid: int) -> census_mod.ProcessIdentity:
        return census_mod.ProcessIdentity(
            kind="linux_start_time", start_time=FAKE_START_TIME
        )

    monkeypatch.setattr(census_mod, "_PID_ALIVE", alive)
    monkeypatch.setattr(census_mod, "_PROCESS_IDENTITY", identity)


def _register_fixture_run(registry_dir: Path, owned: Sequence[str]):
    """Pre-register one fake live run for intersection/refusal tests."""
    return register_run(
        route_id=CODEX_ROUTE,
        packet_id="sha256:fixture-run",
        owned_paths=list(owned),
        pid=FAKE_LIVE_PID,
        identity=ProcessIdentity(kind="linux_start_time", start_time=FAKE_START_TIME),
        registry_dir=registry_dir,
    )


def test_run_refuses_intersecting_live_run_and_launches_nothing(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A live run owning the packet's path refuses the second run: exit 3,
    nothing launched, nothing appended, and the live record is untouched."""
    _wire_fake_identity(monkeypatch)
    registry = scratch_state["registry"]
    pre = _register_fixture_run(registry, owned=[str(packet)])
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    assert "intersect" in captured.err
    assert str(FAKE_LIVE_PID) in captured.err
    assert pre.path is not None and pre.path.exists()
    # The live record is still listed after the refusal.
    result = census_registry(registry_dir=registry)
    assert [r.pid for r in result.live] == [FAKE_LIVE_PID]


def test_run_refuses_unchanged_redispatch_after_stall_before_registration(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A repeated packet/route after a stall kill never registers or launches."""
    first_launcher = LaunchRecorder(never_exits=True)
    first_code, _ = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        timeout=600,
        extra=("--stall-minutes", "0.02"),
        launcher=first_launcher,
        clock=AdvancingClock(step=0.5),
    )
    assert first_code == 124
    assert len(first_launcher.processes) == 1
    seeded_ledger = scratch_state["attempts"].read_text(encoding="utf-8")
    assert "dispatch kill: stall" in seeded_ledger
    assert list(scratch_state["registry"].glob("*.json")) == []

    from lee_llm_router.staffing import census as census_module

    def unexpected_registration(**_kwargs: Any) -> None:
        pytest.fail("unchanged re-dispatch reached register_run")

    monkeypatch.setattr(census_module, "register_run", unexpected_registration)
    second_launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        timeout=600,
        extra=("--stall-minutes", "0.02"),
        launcher=second_launcher,
    )

    assert code == 3
    assert second_launcher.processes == []
    assert scratch_state["attempts"].read_text(encoding="utf-8") == seeded_ledger
    assert list(scratch_state["registry"].glob("*.json")) == []
    assert "unchanged re-dispatch" in captured.err
    assert json.loads(captured.out)["kind"] == "unchanged_redispatch"


def test_run_accepts_disjoint_live_run(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    """A live run owning a different path does not refuse: the run launches,
    records, and deregisters itself, leaving only the other run live."""
    _wire_fake_identity(monkeypatch)
    registry = scratch_state["registry"]
    _register_fixture_run(registry, owned=[str(tmp_path / "other-tree")])
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
    _assert_output_matches_single_append(captured, scratch_state)
    assert len(launcher.processes) == 1
    result = census_registry(registry_dir=registry)
    assert [r.pid for r in result.live] == [FAKE_LIVE_PID]


def test_run_deregisters_on_failed_dispatch_exit(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A worker exit 1 still appends the truthful record and deregisters."""
    _wire_fake_identity(monkeypatch)
    registry = scratch_state["registry"]
    launcher = LaunchRecorder(exit_code=1)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        launcher=launcher,
    )
    assert code == 1
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["verified_success"] is False
    result = census_registry(registry_dir=registry)
    assert result.live == ()
    assert result.cleaned == ()


def test_run_deregisters_on_ceiling_timeout(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A killed ceiling timeout records the truth and leaves no live row."""
    _wire_fake_identity(monkeypatch)
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
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["failure_class"] == "platform_timeout"
    result = census_registry(registry_dir=scratch_state["registry"])
    assert result.live == ()


@pytest.mark.parametrize(
    "extra_args,chunks,timeout,expected_note",
    [
        (["--stall-minutes", "0.02"], (), 600, "stall"),
        (["--progress-minutes", "0.03"], [b"chunk\n"] * 50, 600, "no_progress"),
        (["--stall-action", "warn", "--stall-minutes", "0.02"], (), 5, "ceiling"),
    ],
)
def test_run_deregisters_on_stall_or_no_progress_kill(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    tmp_path,
    extra_args,
    chunks,
    timeout,
    expected_note,
):
    _wire_fake_identity(monkeypatch)
    owned_file = tmp_path / "target.py"
    owned_file.write_text("# initial\n")
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        timeout=timeout,
        owned_paths=[str(owned_file)],
        extra=extra_args,
        launcher=LaunchRecorder(chunks=chunks, never_exits=True),
        clock=AdvancingClock(step=0.5),
    )
    assert code == 124
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["failure_class"] == "platform_timeout"
    notes = payload["provenance"]["notes"]
    assert any(f"dispatch kill: {expected_note}" in n for n in notes)
    assert census_registry(registry_dir=scratch_state["registry"]).live == ()


def test_run_survives_progress_clock_when_touching_owned_files(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    _wire_fake_identity(monkeypatch)
    owned_file = tmp_path / "target.py"

    class ProgressLauncher(LaunchRecorder):
        ticks = 0

        def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
            proc = super().__call__(argv, **kwargs)

            def poll() -> int | None:
                self.ticks += 1
                owned_file.write_text(f"# tick {self.ticks}\n")
                return 0 if self.ticks >= 4 else None

            proc.poll = poll  # type: ignore[assignment]
            return proc

    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        timeout=600,
        owned_paths=[str(owned_file)],
        extra=["--progress-minutes", "0.03"],
        launcher=ProgressLauncher(chunks=[b"out\n"] * 3),
        clock=AdvancingClock(step=0.5),
    )
    assert code == 0
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["failure_class"] is None
    notes = payload["provenance"]["notes"]
    assert not any("dispatch kill:" in n for n in notes)
    assert census_registry(registry_dir=scratch_state["registry"]).live == ()


def test_run_deregisters_on_popener_exception(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """An exception escaping the launch boundary still deregisters."""
    _wire_fake_identity(monkeypatch)
    launcher = SequencedLaunchRecorder([ValueError("boom")])
    with pytest.raises(ValueError, match="boom"):
        _run_cli(
            monkeypatch,
            capsys,
            catalog_dir=catalog_dir,
            snapshot_path=snapshot,
            packet_path=packet,
            launcher=launcher,
        )
    result = census_registry(registry_dir=scratch_state["registry"])
    assert result.live == ()


def test_run_deregisters_on_interrupt(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """KeyboardInterrupt escaping dispatch still deregisters, unmasked."""
    _wire_fake_identity(monkeypatch)
    launcher = SequencedLaunchRecorder([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        _run_cli(
            monkeypatch,
            capsys,
            catalog_dir=catalog_dir,
            snapshot_path=snapshot,
            packet_path=packet,
            launcher=launcher,
        )
    result = census_registry(registry_dir=scratch_state["registry"])
    assert result.live == ()


def test_run_deregisters_when_oracle_setup_fails_after_worker(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Oracle failure: record persisted, exit 3, no live registry row left."""
    from lee_llm_router.staffing import run as run_mod
    from lee_llm_router.staffing.run import RunDispatchError

    def broken_oracle(*_a: Any, **_k: Any) -> Any:
        raise RunDispatchError("oracle could not start")

    monkeypatch.setattr(run_mod, "run_oracle", broken_oracle)
    _wire_fake_identity(monkeypatch)
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CODEX_ROUTE,
        extra=("--oracle", "true"),
        launcher=launcher,
    )
    assert code == 3
    payload = _assert_output_matches_single_append(captured, scratch_state)
    assert payload["verdict"] == "fail"
    result = census_registry(registry_dir=scratch_state["registry"])
    assert result.live == ()


def test_run_requires_owned_paths_before_launch(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """Missing --owned-paths is an argparse exit 2; nothing runs or records."""
    launcher = LaunchRecorder()
    monkeypatch.setattr("lee_llm_router.staffing.run._DEFAULT_POPEN", launcher)
    argv = [
        "run",
        "--role",
        IMPL_ROLE,
        "--class",
        IMPL_CLASS,
        "--packet",
        str(packet),
        "--catalog-dir",
        str(catalog_dir),
        "--availability-file",
        str(snapshot),
        "--json",
    ]
    with pytest.raises(SystemExit) as exc_info:
        cli_main(argv)
    assert exc_info.value.code == 2
    capsys.readouterr()
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    assert not any(scratch_state["registry"].glob("*.json"))


def test_run_refuses_blank_owned_path_before_launch(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """A blank --owned-paths value is refused with exit 3, launches nothing."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        owned_paths=["   "],
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert "owned paths invalid" in captured.err
    assert not scratch_state["attempts"].exists()
    assert not any(scratch_state["registry"].glob("*.json"))


# ---------------------------------------------------------------------------
# P4-5c: Artifact persistence and judge verdict parsing
# ---------------------------------------------------------------------------


def test_persist_worker_output_writes_files_and_records_dir(
    catalog_dir, snapshot, scratch_state
):
    """1. Successful attempt writes stdout/stderr byte-for-byte and records dir."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    pricing = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="rate-table:gpt-5.6-sol",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )
    stdout_text = "line 1\nline 2\nline 3\n"
    stderr_text = "warning: something\n"
    dispatch = DispatchOutcome(
        argv=("codex", "exec"),
        exit_code=0,
        stdout=stdout_text,
        stderr=stderr_text,
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )
    availability = load_availability(snapshot)
    class_record = {
        "role": "impl",
        "oracle_type": "deterministic",
        "size_band": "s",
        "language": "python",
        "class_key": "impl/deterministic/none/s/python",
    }
    record = build_attempt_record(
        outcome=outcome,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    attempt_id = record["attempt_id"]
    artifacts_root = scratch_state["artifacts"]
    expected_dir = artifacts_root / attempt_id
    assert record["provenance"]["worker_output_dir"] == str(expected_dir)
    assert (expected_dir / "stdout.txt").read_text(encoding="utf-8") == stdout_text
    assert (expected_dir / "stderr.txt").read_text(encoding="utf-8") == stderr_text


def test_judge_verdict_accept_with_json_harness_shape(
    catalog_dir, snapshot, scratch_state
):
    """2. REVIEW VERDICT: ACCEPT embedded in JSON event stream records judge_pass."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == PI_ROUTE)
    pricing = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="openrouter-snapshot:z-ai/glm-5.3-flash",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )
    # Pi/agy JSON event stream: marker embedded in a JSON string field
    # followed by a wire-format newline, not the literal last line.
    stdout_text = (
        '{"type":"message","message":{"role":"assistant",'
        '"content":"Let me review this.\\nREVIEW VERDICT: ACCEPT"}}'
        '\n{"type":"finish","reason":"done"}\n'
    )
    dispatch = DispatchOutcome(
        argv=("pi", "--mode", "json"),
        exit_code=0,
        stdout=stdout_text,
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )
    availability = load_availability(snapshot)
    class_record = {
        "role": "review",
        "oracle_type": "none",
        "size_band": "s",
        "language": "python",
        "class_key": "review/judge/none/s/python",
    }
    record = build_attempt_record(
        outcome=outcome,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    assert record["verdict"] == "judge_pass"


def test_judge_verdict_reject_with_json_harness_shape(
    catalog_dir, snapshot, scratch_state
):
    """3. REVIEW VERDICT: REJECT embedded in JSON event stream records judge_fail."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == PI_ROUTE)
    pricing = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="openrouter-snapshot:z-ai/glm-5.3-flash",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )
    stdout_text = (
        '{"type":"message","message":{"role":"assistant",'
        '"content":"This needs fixing.\\nREVIEW VERDICT: REJECT"}}'
        '\n{"type":"finish","reason":"done"}\n'
    )
    dispatch = DispatchOutcome(
        argv=("pi", "--mode", "json"),
        exit_code=0,
        stdout=stdout_text,
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )
    availability = load_availability(snapshot)
    class_record = {
        "role": "judge",
        "oracle_type": "none",
        "size_band": "s",
        "language": "python",
        "class_key": "review/judge/none/s/python",
    }
    record = build_attempt_record(
        outcome=outcome,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    assert record["verdict"] == "judge_fail"


def test_judge_verdict_no_marker_falls_back_to_oracle(
    catalog_dir, snapshot, scratch_state
):
    """4. No marker in review stdout: verdict stays as plain oracle-derived value."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == PI_ROUTE)
    pricing = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="openrouter-snapshot:z-ai/glm-5.3-flash",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )
    stdout_text = (
        '{"type":"message","message":{"role":"assistant",'
        '"content":"Everything looks good."}}'
        '\n{"type":"finish","reason":"done"}\n'
    )
    dispatch = DispatchOutcome(
        argv=("pi", "--mode", "json"),
        exit_code=0,
        stdout=stdout_text,
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )
    availability = load_availability(snapshot)
    class_record = {
        "role": "review",
        "oracle_type": "none",
        "size_band": "s",
        "language": "python",
        "class_key": "review/judge/none/s/python",
    }
    record = build_attempt_record(
        outcome=outcome,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    # No marker found → verdict stays as _oracle_verdict(None) = "unverified"
    assert record["verdict"] == "unverified"


def test_judge_verdict_non_review_role_unaffected_by_marker(
    catalog_dir, snapshot, scratch_state
):
    """5. Non-review/judge role unaffected even when stdout contains the marker."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    pricing = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="rate-table:gpt-5.6-sol",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )
    # Impl worker's stdout incidentally contains the marker text.
    stdout_text = (
        "I implemented the feature. The reviewer said\n"
        "REVIEW VERDICT: ACCEPT but that's just context.\n"
    )
    dispatch = DispatchOutcome(
        argv=("codex", "exec"),
        exit_code=0,
        stdout=stdout_text,
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )
    availability = load_availability(snapshot)
    class_record = {
        "role": "impl",
        "oracle_type": "deterministic",
        "size_band": "s",
        "language": "python",
        "class_key": "impl/deterministic/none/s/python",
    }
    record = build_attempt_record(
        outcome=outcome,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    # Judge verdict is never evaluated for impl → plain oracle-derived
    assert record["verdict"] == "unverified"


def test_artifacts_write_failure_sets_none_dir_and_notes(
    monkeypatch, catalog_dir, snapshot, scratch_state
):
    """6. Artifacts write failure: no raise; worker_output_dir=None; noted."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    pricing = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="rate-table:gpt-5.6-sol",
    )
    outcome = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
    )
    stdout_text = "line 1\n"
    dispatch = DispatchOutcome(
        argv=("codex", "exec"),
        exit_code=0,
        stdout=stdout_text,
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )

    # Point LEE_LLM_ROUTER_ARTIFACTS_DIR at a regular file so mkdir fails
    # with OSError (FileExistsError), which build_attempt_record catches.
    scratch_state["artifacts"].mkdir(parents=True, exist_ok=True)
    bad_path = scratch_state["artifacts"] / "blocker.txt"
    bad_path.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("LEE_LLM_ROUTER_ARTIFACTS_DIR", str(bad_path))

    availability = load_availability(snapshot)
    class_record = {
        "role": "impl",
        "oracle_type": "deterministic",
        "size_band": "s",
        "language": "python",
        "class_key": "impl/deterministic/none/s/python",
    }
    # build_attempt_record must not raise.
    record = build_attempt_record(
        outcome=outcome,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    assert record["provenance"]["worker_output_dir"] is None
    assert any(
        "persistence failed" in note for note in record["provenance"]["notes"]
    ), f"expected persistence failure in notes: {record['provenance']['notes']}"


# ---------------------------------------------------------------------------
# M3-3: run --instance pins an instance; attempt record carries it
# ---------------------------------------------------------------------------

OPENCODE_GO_ROUTE = "pi-glm-5-3-flash-opencode-go"


def _write_opencode_instance_snapshot(
    path: Path,
    instance_a: tuple[str, int] = ("ON TRACK", 10),
    instance_b: tuple[str, int] = ("ON TRACK", 60),
    *,
    codex: tuple[str, int] | None = ("ON TRACK", 80),
    anthropic: tuple[str, int] | None = ("COLD", 90),
    gemini: tuple[str, int] | None = ("ON TRACK", 60),
) -> Path:
    """Write an availability snapshot with explicit opencode-go instances."""
    subscriptions = []
    if codex is not None:
        subscriptions.append(
            {
                "provider": "OpenAI/Codex",
                "bucket": "Weekly limit",
                "status": codex[0],
                "remaining_pct": codex[1],
            }
        )
    if anthropic is not None:
        subscriptions.append(
            {
                "provider": "Anthropic/Claude",
                "bucket": "Current session",
                "status": anthropic[0],
                "remaining_pct": anthropic[1],
            }
        )
    if gemini is not None:
        subscriptions.append(
            {
                "provider": "Gemini/agy",
                "bucket": "Gemini models",
                "status": gemini[0],
                "remaining_pct": gemini[1],
            }
        )
    subscriptions.append(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": instance_a[0],
            "remaining_pct": instance_a[1],
            "instance": "a",
        }
    )
    subscriptions.append(
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": instance_b[0],
            "remaining_pct": instance_b[1],
            "instance": "b",
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


def test_select_route_no_instance_picks_first_eligible_instance(
    catalog_dir: Path, tmp_path: Path
) -> None:
    """(a) Without --instance, the first eligible instance is chosen."""
    snap_b_first = _write_opencode_instance_snapshot(
        tmp_path / "snap_b.json",
        instance_a=("ON TRACK", 10),  # at reserve (10%), ineligible
        instance_b=("ON TRACK", 60),  # eligible
    )
    catalog = load_staffing_catalog(catalog_dir)
    avail_b = load_availability(snap_b_first)

    outcome = select_route(
        catalog,
        avail_b,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=OPENCODE_GO_ROUTE,
        instance_id=None,
    )
    # Instance a is first in channels.yaml supply order, but b has headroom and
    # is eligible; channel_instance resolves to b.
    assert outcome.channel_instance == "b"

    # Symmetrically, when a is clear (75%) and b is exhausted (0%):
    snap_a_first = _write_opencode_instance_snapshot(
        tmp_path / "snap_a.json",
        instance_a=("ON TRACK", 75),
        instance_b=("EXHAUSTED", 0),
    )
    avail_a = load_availability(snap_a_first)
    outcome_a = select_route(
        catalog,
        avail_a,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=OPENCODE_GO_ROUTE,
        instance_id=None,
    )
    assert outcome_a.channel_instance == "a"


def test_select_route_no_instance_non_subscription_channel_resolves_none(
    catalog_dir: Path, snapshot: Path
) -> None:
    """(b) Without --instance, non-subscription channel resolves to None."""
    catalog = load_staffing_catalog(catalog_dir)
    avail = load_availability(snapshot)

    outcome = select_route(
        catalog,
        avail,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=PI_ROUTE,  # openrouter metered channel
        instance_id=None,
    )
    assert outcome.channel_instance is None


def test_select_route_explicit_instance_accepted_when_eligible(
    catalog_dir: Path, tmp_path: Path
) -> None:
    """(c) Explicit --instance naming an eligible instance is accepted."""
    snap = _write_opencode_instance_snapshot(
        tmp_path / "snap.json",
        instance_a=("ON TRACK", 50),
        instance_b=("ON TRACK", 60),
    )
    catalog = load_staffing_catalog(catalog_dir)
    avail = load_availability(snap)

    # b is accepted
    outcome_b = select_route(
        catalog,
        avail,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=OPENCODE_GO_ROUTE,
        instance_id="b",
    )
    assert outcome_b.channel_instance == "b"

    # a is accepted even though b has higher headroom
    outcome_a = select_route(
        catalog,
        avail,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=OPENCODE_GO_ROUTE,
        instance_id="a",
    )
    assert outcome_a.channel_instance == "a"


def test_select_route_ineligible_instance_raises_exit_3_nothing_launched(
    catalog_dir: Path,
    tmp_path: Path,
    packet: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scratch_state: dict[str, Path],
) -> None:
    """(d) --instance naming an ineligible instance exits 3 with no side effects."""
    from lee_llm_router.staffing.run import RunSelectionError

    snap = _write_opencode_instance_snapshot(
        tmp_path / "snap.json",
        instance_a=("ON TRACK", 10),  # at reserve (10%)
        instance_b=("ON TRACK", 60),
    )
    catalog = load_staffing_catalog(catalog_dir)
    avail = load_availability(snap)

    # Unit-level exception check
    with pytest.raises(RunSelectionError) as exc_info:
        select_route(
            catalog,
            avail,
            role=IMPL_ROLE,
            oracle_type="deterministic",
            size_band="s",
            language="python",
            class_key=IMPL_CLASS,
            at_date="2026-09-15",
            route_id=OPENCODE_GO_ROUTE,
            instance_id="a",
        )
    assert exc_info.value.exit_code == 3
    assert exc_info.value.kind == "excluded"
    assert (
        "instance 'a' of route 'pi-glm-5-3-flash-opencode-go' is not eligible"
        in str(exc_info.value)
    )
    assert "reserve: 10% kept in the tank (D216)" in str(exc_info.value)

    # CLI-level check: no dispatch, no registry, no attempts/events recorded
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snap,
        packet_path=packet,
        route=OPENCODE_GO_ROUTE,
        instance="a",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert census_registry(registry_dir=scratch_state["registry"]).live == ()
    assert not scratch_state["attempts"].exists()
    assert not scratch_state["events"].exists()


def test_select_route_unknown_or_disabled_instance_raises_exit_3(
    catalog_dir: Path,
    tmp_path: Path,
    packet: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """(e) --instance naming unknown or disabled instance id exits 3."""
    from lee_llm_router.staffing.run import RunSelectionError

    snap = _write_opencode_instance_snapshot(
        tmp_path / "snap.json",
        instance_a=("ON TRACK", 60),
        instance_b=("ON TRACK", 60),
    )
    catalog = load_staffing_catalog(catalog_dir)
    avail = load_availability(snap)

    # Unknown instance
    with pytest.raises(RunSelectionError) as exc_info:
        select_route(
            catalog,
            avail,
            role=IMPL_ROLE,
            oracle_type="deterministic",
            size_band="s",
            language="python",
            class_key=IMPL_CLASS,
            at_date="2026-09-15",
            route_id=OPENCODE_GO_ROUTE,
            instance_id="unknown_inst_id",
        )
    assert exc_info.value.exit_code == 3
    assert exc_info.value.kind == "unknown_instance"
    assert "--instance 'unknown_inst_id'" in str(exc_info.value)
    assert "pi-glm-5-3-flash-opencode-go" in str(exc_info.value)

    # Disabled instance in catalog
    channels_path = catalog_dir / "channels.yaml"
    channels_data = yaml.safe_load(channels_path.read_text(encoding="utf-8"))
    for ch in channels_data["channels"]:
        if ch["channel_id"] == "opencode-go":
            for inst in ch["instances"]:
                if inst["instance_id"] == "b":
                    inst["enabled"] = False
    channels_path.write_text(yaml.safe_dump(channels_data), encoding="utf-8")
    catalog_disabled = load_staffing_catalog(catalog_dir)

    with pytest.raises(RunSelectionError) as exc_info:
        select_route(
            catalog_disabled,
            avail,
            role=IMPL_ROLE,
            oracle_type="deterministic",
            size_band="s",
            language="python",
            class_key=IMPL_CLASS,
            at_date="2026-09-15",
            route_id=OPENCODE_GO_ROUTE,
            instance_id="b",
        )
    assert exc_info.value.exit_code == 3
    assert exc_info.value.kind == "unknown_instance"
    assert "--instance 'b'" in str(exc_info.value)
    assert "pi-glm-5-3-flash-opencode-go" in str(exc_info.value)

    # CLI check with unknown instance
    launcher = LaunchRecorder()
    code, _ = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snap,
        packet_path=packet,
        route=OPENCODE_GO_ROUTE,
        instance="unknown_inst_id",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []


def test_select_route_instance_on_channel_without_instance_concept_raises_exit_3(
    catalog_dir: Path,
    snapshot: Path,
    packet: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """(f) --instance on a non-subscription channel exits 3."""
    from lee_llm_router.staffing.run import RunSelectionError

    catalog = load_staffing_catalog(catalog_dir)
    avail = load_availability(snapshot)

    with pytest.raises(RunSelectionError) as exc_info:
        select_route(
            catalog,
            avail,
            role=IMPL_ROLE,
            oracle_type="deterministic",
            size_band="s",
            language="python",
            class_key=IMPL_CLASS,
            at_date="2026-09-15",
            route_id=PI_ROUTE,  # metered openrouter
            instance_id="any-instance",
        )
    assert exc_info.value.exit_code == 3
    assert exc_info.value.kind == "unknown_instance"
    assert "cannot specify --instance 'any-instance'" in str(exc_info.value)
    assert "pi-z-ai-glm-5-3-flash-openrouter" in str(exc_info.value)
    assert "openrouter" in str(exc_info.value)

    # CLI check
    launcher = LaunchRecorder()
    code, _ = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        instance="any-instance",
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []


def test_build_attempt_record_carries_channel_instance(
    catalog_dir: Path, snapshot: Path, scratch_state: dict[str, Path]
) -> None:
    """(g) build_attempt_record carries outcome.channel_instance in both cases."""
    from lee_llm_router.staffing.eligibility import EligibilityPrice
    from lee_llm_router.staffing.run import (
        DispatchOutcome,
        SelectionOutcome,
        build_attempt_record,
    )

    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == CODEX_ROUTE)
    pricing = EligibilityPrice(
        badge="TOO FAST",
        multiplier=1.0,
        replacement_input_usd_per_token=0.0,
        replacement_output_usd_per_token=0.0,
        marginal_input_usd_per_token=0.0,
        marginal_output_usd_per_token=0.0,
        source="rate-table:gpt-5.6-sol",
    )
    dispatch = DispatchOutcome(
        argv=("codex", "exec"),
        exit_code=0,
        stdout="ok\n",
        stderr="",
        duration_seconds=1.0,
        timed_out=False,
        usage={
            "basis": "provider_reported",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )
    availability = load_availability(snapshot)
    class_record = {
        "role": "impl",
        "oracle_type": "deterministic",
        "size_band": "s",
        "language": "python",
        "class_key": "impl/deterministic/none/s/python",
    }

    # Case 1: non-None channel_instance
    outcome_inst = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
        channel_instance="b",
    )
    record_inst = build_attempt_record(
        outcome=outcome_inst,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test1",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    assert record_inst["route"]["channel_instance"] == "b"

    # Case 2: None channel_instance
    outcome_none = SelectionOutcome(
        route=route,
        basis="explicit",
        reason="test",
        explain_ref="explain",
        excluded=(),
        pricing=pricing,
        channel_instance=None,
    )
    record_none = build_attempt_record(
        outcome=outcome_none,
        dispatch=dispatch,
        oracle=None,
        packet_id="sha256:test2",
        class_record=class_record,
        availability=availability,
        at_date=date(2026, 9, 15),
    )
    assert record_none["route"]["channel_instance"] is None


def test_single_instance_channel_resolves_implicit_instance(
    catalog_dir: Path,
    snapshot: Path,
    packet: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Subscription channel with no declared instances resolves implicit id."""
    from lee_llm_router.staffing.run import RunSelectionError

    catalog = load_staffing_catalog(catalog_dir)
    avail = load_availability(snapshot)

    # Without --instance, resolves to implicit instance id ("openai-sub")
    outcome_default = select_route(
        catalog,
        avail,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=CODEX_ROUTE,
        instance_id=None,
    )
    assert outcome_default.channel_instance == "openai-sub"

    # With --instance naming that implicit instance id: accepted
    outcome_pinned = select_route(
        catalog,
        avail,
        role=IMPL_ROLE,
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=CODEX_ROUTE,
        instance_id="openai-sub",
    )
    assert outcome_pinned.channel_instance == "openai-sub"

    # With --instance naming a nonexistent instance on this channel: exit 3
    with pytest.raises(RunSelectionError) as exc_info:
        select_route(
            catalog,
            avail,
            role=IMPL_ROLE,
            oracle_type="deterministic",
            size_band="s",
            language="python",
            class_key=IMPL_CLASS,
            at_date="2026-09-15",
            route_id=CODEX_ROUTE,
            instance_id="nonexistent-inst",
        )
    assert exc_info.value.exit_code == 3
    assert exc_info.value.kind == "unknown_instance"

    # Dispatched via CLI records the implicit instance on the attempt
    launcher = LaunchRecorder(chunks=[CODEX_RECEIPT_STDOUT.encode("utf-8")])
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
    assert payload["route"]["channel_instance"] == "openai-sub"


# ---------------------------------------------------------------------------
# extra_env child-environment merging and provenance coexistence (M4-2)
# ---------------------------------------------------------------------------


def test_dispatch_route_extra_env_merged_into_child_env(
    catalog_dir: Path,
) -> None:
    """extra_env is merged alongside os.environ and passed to popen."""
    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == OPENCODE_GO_ROUTE)

    recorder = LaunchRecorder(chunks=[b"ok\n"])
    dispatch_route(
        route,
        "test prompt",
        popen=recorder,
        extra_env={"HOME": "/fake/staged/home", "TEST_EXTRA_VAR": "val"},
    )
    assert len(recorder.processes) == 1
    proc = recorder.processes[0]
    child_env = proc.popen_kwargs.get("env")
    assert child_env is not None
    assert child_env["HOME"] == "/fake/staged/home"
    assert child_env["TEST_EXTRA_VAR"] == "val"
    # Merged, not replaced: unrelated inherited variables like PATH survive
    assert "PATH" in child_env
    assert child_env["PATH"] == os.environ["PATH"]


def test_dispatch_route_without_extra_env_keeps_env_unset_for_fake_popen(
    catalog_dir: Path,
) -> None:
    """Without extra_env, fake popen receives no 'env' keyword argument."""
    catalog = load_staffing_catalog(catalog_dir)
    route = next(r for r in catalog.routes.routes if r.route_id == OPENCODE_GO_ROUTE)

    recorder = LaunchRecorder(chunks=[b"ok\n"])
    dispatch_route(
        route,
        "test prompt",
        popen=recorder,
        extra_env=None,
    )
    assert len(recorder.processes) == 1
    proc = recorder.processes[0]
    assert "env" not in proc.popen_kwargs


def test_supervised_dispatch_extra_env_and_provenance_coexist() -> None:
    """extra_env and Linux provenance marker coexist without clobbering each other."""
    from lee_llm_router.staffing.run import (
        _WORKER_PROVENANCE_ENV,
        Resolution,
        run_supervised_dispatch,
    )

    recorded_kwargs: dict[str, Any] = {}

    def fake_real_popen(child_argv: list[str], **kwargs: Any) -> FakeProcess:
        recorded_kwargs.update(kwargs)
        return FakeProcess(child_argv, exit_code=0)

    # Mark fake_real_popen as a real spawner so the posix provenance branch executes
    setattr(fake_real_popen, "_lee_llm_router_real_popen", True)

    resolution = Resolution(
        worker_id="test-worker",
        dispatch_command=["echo", "hi"],
        prompt_delivery="argv",
    )
    code = run_supervised_dispatch(
        resolution,
        "test prompt",
        popen=fake_real_popen,
        extra_env={"HOME": "/fake/staged/home", "CUSTOM_KEY": "val"},
    )
    assert code == 0
    child_env = recorded_kwargs.get("env")
    assert child_env is not None
    assert child_env["HOME"] == "/fake/staged/home"
    assert child_env["CUSTOM_KEY"] == "val"
    assert "PATH" in child_env
    assert child_env["PATH"] == os.environ["PATH"]
    if os.name == "posix" and Path("/proc").is_dir():
        assert _WORKER_PROVENANCE_ENV in child_env
        assert len(child_env[_WORKER_PROVENANCE_ENV]) == 32
