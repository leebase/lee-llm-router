"""Tests for bounded host-authorized parent outcome closure guard."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lee_llm_router.staffing.unit_admission import (
    WORKER_ENV,
    UnitAdmissionError,
    close_outcome,
)
from tests.test_supervise_parent_admission import (
    advance,
    checkpoint,
    decision,
    finish,
    reserve,
)


@pytest.fixture(autouse=True)
def _host_context(monkeypatch: pytest.MonkeyPatch) -> None:
    # A worker pytest context inherits the parent-start marker; closure is a
    # host act, so simulate the host unless a test re-asserts worker context.
    monkeypatch.delenv(WORKER_ENV, raising=False)


def _closed_decision(
    base: dict,
    *,
    evidence: str = "recall journey verified in consuming journey",
    revision: str = "candidate-1",
    observed_at: str = "2026-10-01T12:00:00Z",
) -> dict:
    closed = copy.deepcopy(base)
    for gap in closed["gaps"]:
        gap["state"] = "PROVED"
        gap["evidence"] = evidence
        gap["revision"] = revision
        gap["observed_at"] = observed_at
        gap["history"].append({"state": "PROVED", "reason": "verified on host"})
    return closed


def test_outcome_closure_real_append(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    prior_lines = len(journal.read_text().splitlines())

    closing = _closed_decision(advance(value, moved=True))
    event = close_outcome(str(journal), "parent", closing)

    assert event["kind"] == "outcome_closed"
    assert event["unit_id"] == "parent"
    assert event["completed_starts"] == 1
    assert event["cumulative_seconds"] == 1.0
    assert "observed_at" in event
    assert event["decision"] == closing

    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    assert len(lines) == prior_lines + 1
    assert lines[-1] == event


def test_retained75_analogue_starts_numbering_cumulative_seconds(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    value = advance(value, moved=True)
    finish(tmp_path, reserve(tmp_path, value))

    journal = tmp_path / "STATE.jsonl"
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    starts = [e for e in events if e.get("kind") == "start"]
    assert [s["start"] for s in starts] == [1, 2]

    closing = _closed_decision(advance(value, moved=True))
    event = close_outcome(journal, "parent", closing)

    assert event["completed_starts"] == 2
    assert event["cumulative_seconds"] == 2.0
    assert len(closing["assessments"]) == 2


def test_open_and_blocked_gaps_denial_without_append(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    prior_content = journal.read_text()

    # OPEN gap refusal: the recall gap is left exactly as frozen, untouched.
    closing_open = _closed_decision(advance(value, moved=True))
    closing_open["gaps"][0] = copy.deepcopy(value["gaps"][0])
    assert closing_open["gaps"][0]["state"] == "OPEN"
    with pytest.raises(UnitAdmissionError, match="remains OPEN"):
        close_outcome(journal, "parent", closing_open)
    assert journal.read_text() == prior_content

    # BLOCKED gap refusal
    closing_blocked = _closed_decision(advance(value, moved=True))
    closing_blocked["gaps"][0]["state"] = "BLOCKED"
    closing_blocked["gaps"][0]["history"].append(
        {"state": "BLOCKED", "reason": "blocked upstream"}
    )
    with pytest.raises(UnitAdmissionError, match="remains BLOCKED"):
        close_outcome(journal, "parent", closing_blocked)
    assert journal.read_text() == prior_content


def test_missing_review_proof_denial(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    prior_content = journal.read_text()

    # Waived independent review refusal
    closing_waived = _closed_decision(advance(value, moved=True))
    closing_waived["gaps"][1]["state"] = "WAIVED"
    closing_waived["gaps"][1]["authority"] = {
        "source": "waiver-src",
        "scope": "test",
        "conditions": "none",
    }
    closing_waived["gaps"][1]["history"].append(
        {"state": "WAIVED", "reason": "attempted waiver"}
    )
    with pytest.raises(UnitAdmissionError, match="independent review"):
        close_outcome(journal, "parent", closing_waived)
    assert journal.read_text() == prior_content

    # Missing evidence on review gap
    closing_no_evidence = _closed_decision(advance(value, moved=True))
    closing_no_evidence["gaps"][1]["evidence"] = ""
    with pytest.raises(UnitAdmissionError, match="evidence"):
        close_outcome(journal, "parent", closing_no_evidence)
    assert journal.read_text() == prior_content


def test_tampered_counts_gaps_history_assessments(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    value = advance(value, moved=True)
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    prior_content = journal.read_text()

    valid_closing = _closed_decision(advance(value, moved=True))

    # Tampered completed_starts count
    tampered = copy.deepcopy(valid_closing)
    tampered["completed_starts"] = 1
    with pytest.raises(UnitAdmissionError, match="completed_starts mismatch"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content

    # Tampered previous digest
    tampered = copy.deepcopy(valid_closing)
    tampered["previous"] = "0" * 64
    with pytest.raises(UnitAdmissionError, match="stale/resetting parent decision"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content

    # Tampered gap dropped
    tampered = copy.deepcopy(valid_closing)
    tampered["gaps"] = [tampered["gaps"][0]]
    with pytest.raises(UnitAdmissionError, match="parent gaps cannot disappear"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content

    # Tampered gap proposition
    tampered = copy.deepcopy(valid_closing)
    tampered["gaps"][0]["proposition"] = "tampered proposition"
    with pytest.raises(UnitAdmissionError, match="frozen proposition cannot reset"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content

    # Tampered gap history reset
    tampered = copy.deepcopy(valid_closing)
    tampered["gaps"][0]["history"] = [{"state": "PROVED", "reason": "fresh"}]
    with pytest.raises(UnitAdmissionError, match="acceptance history cannot reset"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content

    # Tampered assessments count
    tampered = copy.deepcopy(valid_closing)
    tampered["assessments"].pop()
    with pytest.raises(UnitAdmissionError, match="every completed start requires"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content

    # Tampered assessment history prefix
    tampered = copy.deepcopy(valid_closing)
    tampered["assessments"][0]["evidence"] = "tampered assessment evidence"
    with pytest.raises(UnitAdmissionError, match="assessment history cannot reset"):
        close_outcome(journal, "parent", tampered)
    assert journal.read_text() == prior_content


def test_unaccounted_and_active_finish_denial(tmp_path: Path):
    journal = tmp_path / "STATE.jsonl"

    # Active start (never finished)
    value = decision()
    reserve(tmp_path, value)
    closing = _closed_decision(advance(value, moved=True))
    prior_content = journal.read_text()
    with pytest.raises(UnitAdmissionError, match="unaccounted parent start"):
        close_outcome(journal, "parent", closing)
    assert journal.read_text() == prior_content

    # Unaccounted finish (crashed/record=None) in a distinct parent directory;
    # the existing binding correctly refuses a deleted bound journal.
    other = tmp_path / "second"
    other.mkdir()
    value = decision()
    finish(other, reserve(other, value), accounted=False)
    other_journal = other / "STATE.jsonl"
    prior_content = other_journal.read_text()
    with pytest.raises(UnitAdmissionError, match="unaccounted parent start"):
        close_outcome(other_journal, "parent", _closed_decision(advance(value)))
    assert other_journal.read_text() == prior_content


def test_worker_context_denial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    prior_content = journal.read_text()

    closing = _closed_decision(advance(value, moved=True))
    monkeypatch.setenv(WORKER_ENV, "worker-marker-12345")
    with pytest.raises(UnitAdmissionError, match="worker"):
        close_outcome(journal, "parent", closing)
    assert journal.read_text() == prior_content


def test_reserve_refusal_after_closure_and_idempotence(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"

    closing = _closed_decision(advance(value, moved=True))
    event = close_outcome(journal, "parent", closing)
    assert event["kind"] == "outcome_closed"

    # Further reserve_start under closed parent refused
    next_decision = advance(closing)
    with pytest.raises(UnitAdmissionError, match="already closed"):
        reserve(tmp_path, next_decision)

    # Idempotent re-close rejected without appending duplicate
    prior_lines = len(journal.read_text().splitlines())
    with pytest.raises(UnitAdmissionError, match="already closed"):
        close_outcome(journal, "parent", closing)
    assert len(journal.read_text().splitlines()) == prior_lines


def test_wrong_parent_and_checkpoint_preservation(tmp_path: Path):
    value = decision()
    value["checkpoint"] = checkpoint()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"

    # Wrong parent unit_id
    closing = _closed_decision(advance(value, moved=True))
    with pytest.raises(UnitAdmissionError, match="parent version/identity mismatch"):
        close_outcome(journal, "other-parent", closing)

    # Checkpoint dropped in closing decision
    closing_no_checkpoint = copy.deepcopy(closing)
    del closing_no_checkpoint["checkpoint"]
    with pytest.raises(UnitAdmissionError, match="checkpoint cannot reset"):
        close_outcome(journal, "parent", closing_no_checkpoint)


@pytest.mark.parametrize(
    "field", ["checkpoint_extension", "limits", "workstream", "checkpoint"]
)
def test_protected_fields_denial_at_closure(tmp_path: Path, field: str):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    original_bytes = journal.read_bytes()

    closing = _closed_decision(advance(value, moved=True))
    closing[field] = {"mutated": "evidence"}
    with pytest.raises(UnitAdmissionError, match=f"{field} cannot reset"):
        close_outcome(journal, "parent", closing)
    assert journal.read_bytes() == original_bytes


def test_reconcile_accounted_missing_seconds_denial(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"
    with journal.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "kind": "reconcile",
                    "unit_id": "parent",
                    "start": 1,
                    "accounted": True,
                    "seconds": None,
                    "evidence": "reconciled but elapsed seconds unknown",
                }
            )
            + "\n"
        )
    original_bytes = journal.read_bytes()

    closing = _closed_decision(advance(value, moved=True))
    with pytest.raises(UnitAdmissionError, match="unaccounted parent start"):
        close_outcome(journal, "parent", closing)
    assert journal.read_bytes() == original_bytes


def test_close_outcome_requires_latest_reconciliation_time(tmp_path: Path):
    value = decision()
    finish(tmp_path, reserve(tmp_path, value))
    journal = tmp_path / "STATE.jsonl"

    with journal.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "kind": "reconcile",
                    "unit_id": "parent",
                    "start": 1,
                    "accounted": True,
                    "seconds": 2.125,
                    "evidence": "persisted attempt wall-clock adjustment",
                }
            )
            + "\n"
        )

    closing = _closed_decision(advance(value, moved=True))
    event = close_outcome(journal, "parent", closing)

    assert event["kind"] == "outcome_closed"
    assert event["cumulative_seconds"] == 2.125


def test_sidecar_highwater_lag_journal_is_source_of_truth(tmp_path: Path):
    value = decision()
    start_num = reserve(tmp_path, value)
    binding_file = tmp_path / "unit-bindings.jsonl"
    assert binding_file.is_file()

    records = [
        json.loads(line)
        for line in binding_file.read_text().splitlines()
        if line.strip()
    ]
    assert records[-1]["starts"] == start_num
    records[-1]["starts"] = 0
    binding_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    finish(tmp_path, start_num)
    journal = tmp_path / "STATE.jsonl"

    closing = _closed_decision(advance(value, moved=True))
    event = close_outcome(journal, "parent", closing)

    assert event["kind"] == "outcome_closed"
    assert event["completed_starts"] == 1
    journal_starts = [
        e
        for e in [json.loads(line) for line in journal.read_text().splitlines()]
        if e.get("kind") == "start"
    ]
    assert len(journal_starts) == 1
