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
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import pytest
import yaml

from lee_llm_router.availability import load_availability
from lee_llm_router.doctor import main as cli_main
from lee_llm_router.providers.antigravity_cli import AGY_USAGE_SOURCE
from lee_llm_router.providers.omp_cli import OMP_USAGE_SOURCE
from lee_llm_router.providers.opencode_cli import OPENCODE_USAGE_SOURCE
from lee_llm_router.staffing import load_staffing_catalog
from lee_llm_router.staffing.catalog import Route as StaffingRoute
from lee_llm_router.staffing.run import (
    _usage_for_harness,
    build_dispatch_command,
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
    the attempt ledger and pre-dispatch refusals create neither file.
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
    supervisor_route: str | None = None,
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
    makes them mandatory); ``route`` selects the optional explicit route and
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
        (FABLE_ROUTE, False),
        (CODEX_ROUTE, True),
    ],
    ids=["unknown", "ineligible", "inactive"],
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
    else:
        # Astra final-review finding 5: the attestation validates the
        # identity, so role/class capability policy never applies — but
        # every other governed reason (never_automatic here) still refuses.
        assert "currently usable route identity" in captured.err
        assert "never_automatic" in captured.err
        assert "role_scoped" not in captured.err


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
    # z-ai/glm-5.3-flash: prompt=0.000000075, completion=0.00000025, cache=0.000000015
    pricing = EligibilityPrice(
        badge="NO DATA",
        multiplier=1.0,
        replacement_input_usd_per_token=0.000000075,
        replacement_output_usd_per_token=0.00000025,
        marginal_input_usd_per_token=0.000000075,
        marginal_output_usd_per_token=0.00000025,
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
    # Currently was 0.000451825 (omitting cache); must be 0.000533425 including cache
    assert cost["usd_list"] == pytest.approx(0.000533425)
    assert cost["usd_marginal"] == pytest.approx(0.000533425)
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
    assert payload_glm["cost"]["usd_list"] == pytest.approx(0.000533425)
    assert payload_glm["cost"]["usd_marginal"] == pytest.approx(0.000533425)
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
