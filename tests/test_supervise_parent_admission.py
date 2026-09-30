"""Actual CLI admission with deterministic fake providers, not LLM behavior."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from lee_llm_router.doctor import main
from lee_llm_router.shims import HARNESS_TAGS, render_target
from lee_llm_router.staffing.unit_admission import (
    UnitAdmissionError,
    execution_identity,
    finish_start,
    reserve_start,
)
from tests.test_staffing_run import (  # reuse scratch-only existing run facilities
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


def decision() -> dict:
    return {
        "version": 1,
        "unit_id": "parent",
        "previous": None,
        "completed_starts": 0,
        "limits": {},
        "gaps": [
            {
                "id": "recall",
                "proposition": "actual owner approves and recalls saved item",
                "source": "frozen DoD R1",
                "state": "OPEN",
                "next_falsifier": "recall fails in consuming journey",
                "history": [{"state": "OPEN", "reason": "frozen DoD"}],
            },
            {
                "id": "review-gate",
                "kind": "independent_review",
                "proposition": "independent review covers final material candidate",
                "source": "frozen DoD review",
                "state": "OPEN",
                "next_falsifier": "blocking defects in final material source",
                "history": [{"state": "OPEN", "reason": "frozen required review"}],
            },
        ],
        "assessments": [],
        "dispatch": {
            "targets": ["recall"],
            "method": "routed-no-approval",
            "capability": "noninteractive routed harness",
            "hypothesis": "can expose owner approval",
            "proposition": "approval and recall are observable",
            "oracle": "finite approval/recall journey",
            "falsifier": "approval cannot be exposed",
            "alternatives": "authorized interactive harness if routed lacks approval",
            "why": "establish actual consuming requirement",
            "revision": "candidate-1",
            "phase": "author",
            "repair_round": 0,
        },
    }


def advance(value: dict, *, moved: bool = False, denied: bool = False) -> dict:
    result = copy.deepcopy(value)
    result["previous"] = hashlib.sha256(
        json.dumps(value, sort_keys=True).encode()
    ).hexdigest()
    result["completed_starts"] += 1
    result["assessments"].append(
        {
            "start": result["completed_starts"],
            "advanced": moved,
            "denied": denied,
            "evidence": (
                "inspected journey transcript; approval unavailable"
                if not moved
                else "observed approval/recall setup; full recall remains unproved"
            ),
        }
    )
    if value["dispatch"]["phase"] in {"review", "final_review"}:
        result["assessments"][-1]["review_outcome"] = "blocking"
    return result


def reserve(tmp_path: Path, value: dict) -> int:
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    return reserve_start(
        str(tmp_path / "STATE.jsonl"),
        str(path),
        "parent",
        route="changed-worker-route",
        packet_id="changed-packet",
        timeout=10,
        role="review" if "review" in value["dispatch"]["phase"] else "impl",
        author_route="independent-author",
        execution=execution_identity(),
    )


def finish(tmp_path: Path, number: int, accounted: bool = True) -> None:
    finish_start(
        str(tmp_path / "STATE.jsonl"),
        "parent",
        number,
        (
            {"wall_clock_ms": 1000, "usage": {"basis": ["unavailable"]}}
            if accounted
            else None
        ),
    )


def test_waste_survives_worker_packet_route_and_finding_renames(tmp_path):
    value = decision()
    for finding in ("new-review-id-1", "new-review-id-2"):
        number = reserve(tmp_path, value)
        finish(tmp_path, number)
        value = advance(value)
        value["dispatch"]["revision"] = finding
    with pytest.raises(UnitAdmissionError, match="two nonadvancing"):
        reserve(tmp_path, value)
    value["dispatch"]["method"] = "renamed-worker-method"
    with pytest.raises(UnitAdmissionError, match="causally unchanged"):
        reserve(tmp_path, value)


def test_definitive_denial_zero_retry_authorized_interactive_alternative(tmp_path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    value = advance(value, denied=True)
    with pytest.raises(UnitAdmissionError, match="definitive denial"):
        reserve(tmp_path, value)
    value["dispatch"].update(
        method="interactive-approved",
        capability="explicit grant A7: interactive harness",
        hypothesis="exposes required owner approval",
    )
    finish(tmp_path, reserve(tmp_path, value))
    value = advance(value, moved=True)
    assert value["gaps"][0]["state"] == "OPEN"  # intermediate evidence only
    assert reserve(tmp_path, value) == 3


def test_waiver_resume_retains_release_gate_and_method_history(tmp_path):
    value = decision()
    waived = copy.deepcopy(value["gaps"][0])
    waived.update(
        id="progression",
        proposition="progression pilot",
        source="DoD R2",
        state="WAIVED",
        evidence="Lee waiver",
        revision="waiver-1",
        observed_at="2026-09-29",
        authority={
            "source": "Lee conversation",
            "scope": "progression only",
            "conditions": "release human gate retained",
        },
    )
    value["gaps"].append(waived)
    finish(tmp_path, reserve(tmp_path, value))
    resumed = advance(value)
    resumed["dispatch"]["targets"] = ["progression"]
    with pytest.raises(UnitAdmissionError, match="open parent gap"):
        reserve(tmp_path, resumed)
    resumed["gaps"][2]["state"] = "OPEN"
    resumed["gaps"][2]["history"].append({"state": "OPEN", "reason": "stale reviewer"})
    with pytest.raises(UnitAdmissionError, match="governing authority"):
        reserve(tmp_path, resumed)
    resumed = advance(value)
    assert reserve(tmp_path, resumed) == 2
    assert resumed["gaps"][0]["state"] == "OPEN"


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda d: d.update(completed_starts=0), "start count"),
        (lambda d: d.update(previous=None), "stale/resetting"),
        (lambda d: d.update(assessments=[]), "assessment"),
        (lambda d: d.update(gaps=[]), "acceptance ledger"),
        (lambda d: d["dispatch"].update(repair_round=3), "repair allowance"),
        (lambda d: d["dispatch"].update(falsifier=""), "falsifier"),
    ],
)
def test_parent_resets_and_empty_dispatch_rejected(tmp_path, mutation, reason):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    resumed = advance(value, moved=True)
    mutation(resumed)
    with pytest.raises(UnitAdmissionError, match=reason):
        reserve(tmp_path, resumed)


@pytest.mark.parametrize("finish_it", [False, True])
def test_unaccounted_crash_or_missing_ledger_blocks_resume(tmp_path, finish_it):
    value = decision()
    number = reserve(tmp_path, value)
    if finish_it:
        finish(tmp_path, number, accounted=False)
    with pytest.raises(UnitAdmissionError, match="unaccounted"):
        reserve(tmp_path, advance(value))


def test_productive_two_rounds_final_review_and_no_third_round(tmp_path):
    value = decision()
    for phase, round_number in (
        ("author", 0),
        ("review", 0),
        ("repair", 1),
        ("review", 1),
        ("repair", 2),
        ("final_review", 2),
    ):
        value["dispatch"].update(
            phase=phase,
            repair_round=round_number,
            targets=["review-gate"] if "review" in phase else ["recall"],
        )
        finish(tmp_path, reserve(tmp_path, value))
        value = advance(value, moved=True)
    value["dispatch"].update(phase="repair", repair_round=2)
    with pytest.raises(UnitAdmissionError, match="final review ended"):
        reserve(tmp_path, value)


@pytest.mark.parametrize(
    "limit",
    [
        {"starts": 0, "authority": "test user cap"},
        {"seconds": 9, "authority": "test user cap"},
        {"starts": 1, "reserve_starts": 1, "authority": "test user cap"},
    ],
)
def test_actual_run_admission_before_fake_provider_launch(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path, limit
):
    value = decision()
    value["limits"] = limit
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        launcher=launcher,
        extra=[
            "--unit-id",
            "parent",
            "--unit-state",
            str(tmp_path / "STATE.jsonl"),
            "--unit-decision",
            str(path),
        ],
    )
    assert code == 3
    assert "parent admission refused" in captured.err
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()


def test_actual_run_persists_and_refuses_child_counter_reset(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    value = decision()
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    launcher = LaunchRecorder()
    flags = [
        "--unit-id",
        "parent",
        "--unit-state",
        str(tmp_path / "STATE.jsonl"),
        "--unit-decision",
        str(path),
    ]
    _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        launcher=launcher,
        extra=flags,
    )
    assert len(launcher.processes) == 1
    events = [
        json.loads(line) for line in (tmp_path / "STATE.jsonl").read_text().splitlines()
    ]
    assert events[-1]["accounted"] is True
    packet.write_text("renamed child packet body")
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        launcher=launcher,
        extra=flags,
    )
    assert code == 3 and "stale/resetting" in captured.err
    assert launcher.processes == []


@pytest.mark.parametrize("count,action", [(0, "repair_same_route"), (1, "escalate")])
def test_actual_next_action_count(tmp_path, capsys, count, action):
    path = tmp_path / "failure.json"
    path.write_text('{"failure_class":"capability_rejected"}')
    with pytest.raises(SystemExit) as result:
        main(["next-action", "--input", str(path), "--repair-count", str(count)])
    assert result.value.code == 0
    assert json.loads(capsys.readouterr().out)["next_action"] == action


def test_all_supported_candidate_shims_render(tmp_path):
    for harness in HARNESS_TAGS:
        target = render_target(
            harness,
            home=tmp_path / "home",
            project=tmp_path / "project",
            command="supervise",
        )
        target.path.parent.mkdir(parents=True, exist_ok=True)
        target.path.write_text(target.content)
        assert "--repair-count <completed-same-route-repairs>" in target.content
        assert "keep fixing and independently re-reviewing until" not in target.content
        assert "superseding contract 2026-09-29" in target.content
        assert "same release blocker survives two consecutive" in target.content


# Full diagnosis matrix: inject the supervisor's proposed decision, then exercise
# actual CLI admission. This validates mechanical boundaries and fixture traces;
# it does not pretend the fixtures autonomously make an LLM choose these actions.
SCENARIOS = [
    ("unique_moved_plan", 0, False, False, None),
    ("failed_capability_repair", 1, False, True, None),
    ("recoverable_consuming_config", 1, False, True, None),
    ("denial_sufficient_permitted_evidence", 1, True, True, None),
    ("denial_no_sufficient_alternative", 1, True, False, "definitive denial"),
    ("stale_waived_progression", 1, False, False, "open parent gap"),
    ("file_churn_flat_acceptance", 2, False, False, "two nonadvancing"),
    ("alternating_fresh_blockers", 2, False, False, "two nonadvancing"),
    ("unrelated_review_hardening", 0, False, False, "target gaps"),
    ("green_leaves_failed_parent_journey", 1, False, True, None),
    ("child_reset_exhausted_envelope", 1, False, False, "starts exhausted"),
    ("two_productive_repair_rounds", 2, False, False, None),
    ("changed_product_promise_requires_Lee", 0, False, False, "target gaps"),
]


@pytest.mark.parametrize("name,prior_count,denied,change,refusal", SCENARIOS)
def test_diagnosis_matrix_actual_cli_mechanics(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    tmp_path,
    name,
    prior_count,
    denied,
    change,
    refusal,
):
    value = decision()
    if name == "child_reset_exhausted_envelope":
        value["limits"] = {"starts": 1, "authority": "explicit fixture cap"}
    if name == "stale_waived_progression":
        value["gaps"][0].update(
            state="WAIVED",
            evidence="human waiver transcript",
            revision="waiver-v1",
            observed_at="2026-09-29",
            authority={
                "source": "Lee",
                "scope": "progression",
                "conditions": "release gate retained",
            },
        )
        # Prior dispatch advances a separate still-required parent release gate.
        value["gaps"].append(
            dict(
                decision()["gaps"][0],
                id="release",
                proposition="release human acceptance",
            )
        )
        value["dispatch"]["targets"] = ["release"]
    for prior_index in range(prior_count):
        if name == "two_productive_repair_rounds" and prior_index == 1:
            value["dispatch"].update(phase="review", targets=["review-gate"])
        finish(tmp_path, reserve(tmp_path, value))
        value = advance(
            value, moved=name == "two_productive_repair_rounds", denied=denied
        )
    if change:
        value["dispatch"].update(
            method="authorized-alternative",
            capability="verified permitted capability grant",
            hypothesis="distinct consuming state/capability repair",
        )
    if name == "stale_waived_progression":
        value["dispatch"]["targets"] = ["recall"]
    if name in {"unrelated_review_hardening", "changed_product_promise_requires_Lee"}:
        value["dispatch"]["targets"] = []
    if name == "two_productive_repair_rounds":
        value["dispatch"].update(phase="repair", repair_round=1, targets=["recall"])
    if name == "unique_moved_plan":
        moved = tmp_path / "unique-verified-plan.md"
        packet.rename(moved)
        packet = moved  # unique source inspection, not invented plan contents
    packet.write_text(f"scenario={name}; bounded target approval/recall journey")
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        launcher=launcher,
        extra=[
            "--unit-id",
            "parent",
            "--unit-state",
            str(tmp_path / "STATE.jsonl"),
            "--unit-decision",
            str(path),
        ],
    )
    if refusal:
        assert code == 3 and refusal in captured.err
        assert launcher.processes == []
    else:
        assert len(launcher.processes) == 1
        # Empty fake work is governed incomplete even when admission succeeds.
        assert code == 3
        assert json.loads(captured.out)["verified_success"] is False
        assert value["gaps"][0]["state"] != "PROVED"


def test_actual_parent_cannot_move_journal_to_reset_counters(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    value = decision()
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    for filename in ("STATE.jsonl", "new-child-STATE.jsonl"):
        packet.write_text(f"bounded packet {filename}")
        launcher = LaunchRecorder()
        code, captured = _run_cli(
            monkeypatch,
            capsys,
            catalog_dir=catalog_dir,
            snapshot_path=snapshot,
            packet_path=packet,
            route=PI_ROUTE,
            timeout=10,
            launcher=launcher,
            extra=[
                "--unit-id",
                "parent",
                "--unit-state",
                str(tmp_path / filename),
                "--unit-decision",
                str(path),
            ],
        )
        if filename.startswith("new"):
            assert code == 3 and "path cannot reset" in captured.err
            assert launcher.processes == []
        else:
            assert len(launcher.processes) == 1


def test_reconcile_actual_missing_append_then_resume_without_reset(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    import lee_llm_router.staffing.ledger as ledger

    original = ledger.append_attempt
    preserved = []

    def failed_append(record):
        preserved.append(record)
        raise OSError("injected ledger append failure")

    monkeypatch.setattr(ledger, "append_attempt", failed_append)
    value = decision()
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    flags = [
        "--unit-id",
        "parent",
        "--unit-state",
        str(tmp_path / "STATE.jsonl"),
        "--unit-decision",
        str(path),
    ]
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        extra=flags,
    )
    assert code == 3 and "could not be appended" in captured.err
    monkeypatch.setattr(ledger, "append_attempt", original)
    original(preserved[0])  # actual retained v2 evidence, no invented usage
    value = advance(value)
    value["reconcile"] = [
        {
            "start": 1,
            "attempt_id": preserved[0]["attempt_id"],
            "evidence": "inspected retained actual command/record",
        }
    ]
    path.write_text(json.dumps(value))
    packet.write_text("distinct bounded recovery packet")
    launcher = LaunchRecorder()
    _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        extra=flags,
        launcher=launcher,
    )
    assert len(launcher.processes) == 1
    events = [
        json.loads(line) for line in (tmp_path / "STATE.jsonl").read_text().splitlines()
    ]
    assert any(e["kind"] == "reconcile" for e in events)
    assert [e["start"] for e in events if e["kind"] == "start"] == [1, 2]


def test_new_gap_id_cannot_reset_method_or_widen_scope(tmp_path):
    value = decision()
    for _ in range(2):
        finish(tmp_path, reserve(tmp_path, value))
        value = advance(value)
    value["gaps"].append(dict(value["gaps"][0], id="recall-r2"))
    value["dispatch"]["targets"] = ["recall-r2"]
    with pytest.raises(UnitAdmissionError, match="gap set frozen"):
        reserve(tmp_path, value)


def test_duplicate_proposition_refused_at_inception(tmp_path):
    value = decision()
    value["gaps"].append(dict(value["gaps"][0], id="recall-r2"))
    with pytest.raises(UnitAdmissionError, match="duplicate gap"):
        reserve(tmp_path, value)


def test_denied_capability_cannot_retry_with_method_and_hypothesis_rename(tmp_path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    value = advance(value, denied=True)
    value["dispatch"].update(
        method="routed-v2", hypothesis="new words same denied harness"
    )
    with pytest.raises(UnitAdmissionError, match="definitive denial"):
        reserve(tmp_path, value)


def phase_step(tmp_path, value, phase, round_number):
    value["dispatch"].update(
        phase=phase,
        repair_round=round_number,
        targets=["review-gate"] if "review" in phase else ["recall"],
    )
    finish(tmp_path, reserve(tmp_path, value))
    return advance(value, moved=True)


def test_exact_review_repair_round_one_cycle_refused(tmp_path):
    value = decision()
    for phase, round_number in [
        ("author", 0),
        ("review", 0),
        ("repair", 1),
        ("review", 1),
    ]:
        value = phase_step(tmp_path, value, phase, round_number)
    value["dispatch"].update(phase="repair", repair_round=1, targets=["recall"])
    with pytest.raises(UnitAdmissionError, match="next directed round"):
        reserve(tmp_path, value)
    # The actual second directed round remains authorized.
    value["dispatch"]["repair_round"] = 2
    assert reserve(tmp_path, value) == 5


@pytest.mark.parametrize("phase", ["review", "diagnose", "author"])
def test_no_infinite_review_diagnosis_or_author_restart_after_round_two(
    tmp_path, phase
):
    value = decision()
    for previous_phase, round_number in [
        ("author", 0),
        ("review", 0),
        ("repair", 1),
        ("review", 1),
        ("repair", 2),
    ]:
        value = phase_step(tmp_path, value, previous_phase, round_number)
    value["dispatch"].update(
        phase=phase,
        repair_round=2,
        targets=["review-gate"] if phase == "review" else ["recall"],
    )
    with pytest.raises(UnitAdmissionError):
        reserve(tmp_path, value)


def test_multiple_packets_in_one_active_round_then_review(tmp_path):
    value = decision()
    for phase, round_number in [
        ("author", 0),
        ("review", 0),
        ("repair", 1),
        ("repair", 1),
        ("review", 1),
    ]:
        value = phase_step(tmp_path, value, phase, round_number)
    assert value["completed_starts"] == 5


def test_review_gap_required_upfront_and_final_dispatch_after_proof(tmp_path):
    value = decision()
    missing = copy.deepcopy(value)
    missing["gaps"].pop()
    with pytest.raises(UnitAdmissionError, match="frozen at inception"):
        reserve(tmp_path, missing)
    for phase, round_number in [("author", 0), ("review", 0), ("repair", 1)]:
        value = phase_step(tmp_path, value, phase, round_number)
    value["gaps"][0].update(
        state="PROVED",
        evidence="actual recall passed",
        revision="candidate-2",
        observed_at="2026-09-29",
    )
    value["gaps"][0]["history"].append({"state": "PROVED", "reason": "actual journey"})
    value["dispatch"].update(
        phase="final_review", repair_round=1, targets=["review-gate"]
    )
    assert reserve(tmp_path, value) == 4


def test_unchanged_initial_review_needs_no_duplicate(tmp_path):
    value = decision()
    for phase in ["author", "review"]:
        value = phase_step(tmp_path, value, phase, 0)
    value["dispatch"].update(phase="final_review", targets=["review-gate"])
    with pytest.raises(UnitAdmissionError, match="no duplicate review"):
        reserve(tmp_path, value)
    # Closure is supervisor work, no extra provider start is owed.


def test_multitarget_movement_does_not_reset_failed_target(tmp_path):
    value = decision()
    value["dispatch"]["targets"] = ["recall", "review-gate"]
    for _ in range(2):
        finish(tmp_path, reserve(tmp_path, value))
        value = advance(value, moved=True)
        value["assessments"][-1]["advanced_targets"] = ["review-gate"]
    value["dispatch"]["targets"] = ["recall"]
    with pytest.raises(UnitAdmissionError, match="two nonadvancing"):
        reserve(tmp_path, value)


def test_actual_dispatch_exception_recovers_alternative_then_required_review(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    from lee_llm_router.staffing import run

    original = run.dispatch_route

    def denied_dispatch(*args, **kwargs):
        raise run.RunDispatchError("injected before attempt construction")

    monkeypatch.setattr(run, "dispatch_route", denied_dispatch)
    value = decision()
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    flags = [
        "--unit-id",
        "parent",
        "--unit-state",
        str(tmp_path / "STATE.jsonl"),
        "--unit-decision",
        str(path),
    ]
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        extra=flags,
    )
    assert code == 3 and "dispatch failed" in captured.err
    assert not scratch_state["attempts"].exists()
    value = advance(value, denied=True)
    value["reconcile"] = [
        {
            "start": 1,
            "evidence": "actual dispatcher error + registry + process inspection",
        }
    ]
    value["dispatch"].update(
        method="interactive",
        capability="already authorized interactive",
        hypothesis="different permitted path",
    )
    path.write_text(json.dumps(value))
    packet.write_text("distinct permitted recovery")
    monkeypatch.setattr(run, "dispatch_route", original)
    launcher = LaunchRecorder()
    _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        extra=flags,
        launcher=launcher,
    )
    assert len(launcher.processes) == 1
    events = [
        json.loads(line) for line in (tmp_path / "STATE.jsonl").read_text().splitlines()
    ]
    recovered = next(e for e in events if e["kind"] == "reconcile")
    assert recovered["accounted"] and recovered["attempt"] is None
    assert (
        recovered["seconds"] >= 0
        and recovered["usage"] == recovered["outcome"] == "unknown"
    )
    value = advance(value, moved=True)
    value.pop("reconcile")
    # Independent review remains a dispatchable frozen gap.
    value = phase_step(tmp_path, value, "review", 0)
    value = phase_step(tmp_path, value, "repair", 1)
    value["dispatch"].update(
        phase="final_review", repair_round=1, targets=["review-gate"]
    )
    assert reserve(tmp_path, value) == 5


def test_interrupted_controller_requires_shutdown_before_recovery(
    tmp_path, monkeypatch
):
    import lee_llm_router.staffing.unit_admission as admission

    value = decision()
    reserve(tmp_path, value)  # Simulate no finish after interruption.
    value = advance(value)
    value["reconcile"] = [{"start": 1, "evidence": "retained crash logs"}]
    with pytest.raises(UnitAdmissionError, match="controller remains live"):
        reserve(tmp_path, value)
    controller_pid = admission.os.getpid()
    real_process_record = admission._linux_process_record
    monkeypatch.setattr(
        admission,
        "_linux_process_record",
        lambda pid: None if pid == controller_pid else real_process_record(pid),
    )
    monkeypatch.setattr(admission, "pid_alive", lambda pid: False)
    assert reserve(tmp_path, value) == 2
    events = [
        json.loads(line) for line in (tmp_path / "STATE.jsonl").read_text().splitlines()
    ]
    assert next(e for e in events if e["kind"] == "reconcile")["time_basis"].startswith(
        "conservative"
    )


def test_failed_review_execution_has_one_finite_recovery(tmp_path):
    value = decision()
    value = phase_step(tmp_path, value, "author", 0)
    value["dispatch"].update(phase="review", targets=["review-gate"])
    for _ in range(2):
        number = reserve(tmp_path, value)
        finish(tmp_path, number, accounted=False)
        value = advance(value, moved=True)
        value["assessments"][-1]["review_outcome"] = "incomplete"
        value["reconcile"] = [
            {
                "start": number,
                "evidence": "retained exception, registry cleanup, no worker",
            }
        ]
    with pytest.raises(UnitAdmissionError, match="recovery exhausted"):
        reserve(tmp_path, value)


def test_recovery_refuses_marked_worker_even_after_controller_finish(
    tmp_path, monkeypatch
):
    import lee_llm_router.staffing.unit_admission as admission

    value = decision()
    finish(tmp_path, reserve(tmp_path, value), accounted=False)
    events = [
        json.loads(line) for line in (tmp_path / "STATE.jsonl").read_text().splitlines()
    ]
    identity = events[0]["execution"]
    proc = tmp_path / "proc"
    (proc / "123").mkdir(parents=True)
    (proc / "123" / "environ").write_bytes(
        f"{admission.WORKER_ENV}={identity['marker']}".encode()
    )
    real_path = Path
    monkeypatch.setattr(
        admission, "Path", lambda p: proc if p == "/proc" else real_path(p)
    )
    value = advance(value)
    value["reconcile"] = [
        {"start": 1, "evidence": "controller ended; worker inspected"}
    ]
    with pytest.raises(UnitAdmissionError, match="worker remains live"):
        reserve(tmp_path, value)
    (proc / "123" / "environ").write_bytes(b"")
    assert reserve(tmp_path, value) == 2


def test_actual_run_interrupted_parent_append_reconciles_without_v2(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, tmp_path
):
    import lee_llm_router.staffing.unit_admission as admission
    from lee_llm_router.staffing import run

    def failed_dispatch(*args, **kwargs):
        raise run.RunDispatchError("no v2 record can be built")

    def failed_finish(*args, **kwargs):
        raise OSError("interrupted accounting append")

    monkeypatch.setattr(run, "dispatch_route", failed_dispatch)
    monkeypatch.setattr(admission, "finish_start", failed_finish)
    value = decision()
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(value))
    _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=PI_ROUTE,
        timeout=10,
        extra=[
            "--unit-id",
            "parent",
            "--unit-state",
            str(tmp_path / "STATE.jsonl"),
            "--unit-decision",
            str(path),
        ],
    )
    assert not scratch_state["attempts"].exists()
    value = advance(value)
    value["reconcile"] = [
        {
            "start": 1,
            "evidence": "actual interrupted append and retained dispatcher log",
        }
    ]
    # The original controller must first have ended; inject its observed absence.
    controller_pid = admission.os.getpid()
    real_process_record = admission._linux_process_record
    monkeypatch.setattr(
        admission,
        "_linux_process_record",
        lambda pid: None if pid == controller_pid else real_process_record(pid),
    )
    monkeypatch.setattr(admission, "pid_alive", lambda pid: False)
    assert reserve(tmp_path, value) == 2


def test_recovery_conservative_time_enforces_actual_supplied_cap(tmp_path):
    value = decision()
    value["limits"] = {"seconds": 10, "authority": "actual fixture cap"}
    finish(tmp_path, reserve(tmp_path, value), accounted=False)
    value = advance(value)
    value["reconcile"] = [{"start": 1, "evidence": "failure retained; no live workers"}]
    with pytest.raises(UnitAdmissionError, match="time exhausted"):
        reserve(tmp_path, value)


def test_normalized_actual_timestamps_and_route_attribution(tmp_path, monkeypatch):
    import lee_llm_router.staffing.unit_admission as admission

    value = decision()
    finish(tmp_path, reserve(tmp_path, value), accounted=False)
    path = tmp_path / "STATE.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    # Same instant with different formats must compare equal, not lexically.
    events[0]["reserved_at"] = "2026-09-29T00:00:00.000000+00:00"
    events[0]["execution"]["route_record"] = {"model": "expected"}
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    assert admission._time("2026-09-29T00:00:00Z") == admission._time(
        events[0]["reserved_at"]
    )
    record = {
        "attempt_id": "retained",
        "packet_id": "changed-packet",
        "captured_at": "2026-09-29T00:00:00Z",
        "route": {"model": "wrong"},
        "wall_clock_ms": 1500,
    }
    monkeypatch.setattr(admission, "read_attempts", lambda p: [record])
    value = advance(value)
    value["reconcile"] = [
        {"start": 1, "attempt_id": "retained", "evidence": "actual retained record"}
    ]
    with pytest.raises(UnitAdmissionError, match="matching persisted"):
        reserve(tmp_path, value)
    record["route"]["model"] = "expected"
    assert reserve(tmp_path, value) == 2
    recovered = next(
        json.loads(line)
        for line in path.read_text().splitlines()
        if json.loads(line).get("kind") == "reconcile"
    )
    assert recovered["seconds"] == 1.5


def test_incomplete_final_review_record_allows_one_recovery(tmp_path):
    value = decision()
    for phase, round_number in [("author", 0), ("review", 0), ("repair", 1)]:
        value = phase_step(tmp_path, value, phase, round_number)
    for _ in range(2):
        value["dispatch"].update(
            phase="final_review", repair_round=1, targets=["review-gate"]
        )
        finish(tmp_path, reserve(tmp_path, value))
        value = advance(value, moved=True)
        value["assessments"][-1]["review_outcome"] = "incomplete"
    with pytest.raises(UnitAdmissionError, match="recovery exhausted"):
        reserve(tmp_path, value)


@pytest.mark.parametrize(
    ("start_ticks", "refusal"),
    [
        (339, None),  # Chief's older non-dumpable Linux process snapshot.
        (1000, "created at or after original controller"),
        (1001, "created at or after original controller"),
        (None, "missing or unknown process creation identity"),
        ("malformed", "missing or unknown process creation identity"),
        ("unreadable", "missing or unknown process creation identity"),
    ],
)
def test_unreadable_environment_requires_older_creation_identity(
    tmp_path, monkeypatch, start_ticks, refusal
):
    import lee_llm_router.staffing.unit_admission as admission
    from lee_llm_router.staffing import run

    proc = tmp_path / "proc"
    entry = proc / "387"
    entry.mkdir(parents=True)
    if start_ticks is not None:
        # Real Linux stat shape, including a command name with ')' and spaces.
        fields = ["S", "1"] + ["0"] * 17 + [str(start_ticks)]
        (entry / "stat").write_text(
            "387 (non-dumpable agent) name) " + " ".join(fields)
        )
    real_path = Path
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text

    def mapped_path(path):
        if str(path) == "/proc" or str(path).startswith("/proc/387/"):
            return proc / str(path).removeprefix("/proc").lstrip("/")
        return real_path(path)

    def unreadable(path):
        if path == entry / "environ":
            raise PermissionError("non-dumpable same-user process")
        return real_read_bytes(path)

    def stat_text(path, *args, **kwargs):
        if path == entry / "stat" and start_ticks == "unreadable":
            raise PermissionError("unreadable process stat")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", stat_text)
    monkeypatch.setattr(admission, "Path", mapped_path)
    monkeypatch.setattr(run, "Path", mapped_path)
    monkeypatch.setattr(Path, "read_bytes", unreadable)
    identity = admission.execution_identity()
    identity["start_time"] = 1000
    pending = {"execution": identity}
    finish = {"controller_finished_at": "retained finish"}
    if refusal:
        with pytest.raises(UnitAdmissionError, match=refusal):
            admission._stopped(pending, finish)
    else:
        admission._stopped(pending, finish)


@pytest.mark.parametrize("creation", [None, "1000", -1, True])
def test_shutdown_refuses_unknown_controller_creation_identity(monkeypatch, creation):
    import lee_llm_router.staffing.unit_admission as admission

    identity = admission.execution_identity()
    identity["start_time"] = creation
    with pytest.raises(UnitAdmissionError, match="controller creation identity"):
        admission._stopped(
            {"execution": identity}, {"controller_finished_at": "retained finish"}
        )
    identity.pop("start_time")
    with pytest.raises(UnitAdmissionError, match="controller creation identity"):
        admission._stopped(
            {"execution": identity}, {"controller_finished_at": "retained finish"}
        )


def test_shutdown_refuses_actual_live_process_with_matching_environment(monkeypatch):
    import os

    import lee_llm_router.staffing.unit_admission as admission

    # Use an existing inherited environment entry as the marker fixture so the
    # real /proc scan observes a live process without launching any new worker.
    identity = admission.execution_identity()
    assert admission.pid_alive(identity["pid"])
    env = Path(f"/proc/{os.getpid()}/environ").read_bytes().split(b"\0")
    key, value = next(item.split(b"=", 1) for item in env if b"=" in item)
    monkeypatch.setattr(admission, "WORKER_ENV", key.decode())
    identity["marker"] = value.decode()
    with pytest.raises(UnitAdmissionError, match="worker remains live"):
        admission._stopped(
            {"execution": identity}, {"controller_finished_at": "retained finish"}
        )
