"""Opt-in parent accounting at the existing run boundary; no dispatch policy.

The supervisor supplies acceptance judgments. This journal enforces continuity,
finite dispatch questions and supplied limits, not the truth of narrative claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from lee_llm_router.staffing.census import pid_alive
from lee_llm_router.staffing.json_int import dump_json, int_from_decimal
from lee_llm_router.staffing.ledger import (
    AttemptLedgerError,
    read_attempts,
    resolve_attempts_path,
    writer_transaction,
)
from lee_llm_router.staffing.run import _linux_process_record


class UnitAdmissionError(ValueError):
    """A versioned parent start lacks reconciled authority or evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UnitAdmissionError(message)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@contextmanager
def _journal(path: Path) -> Iterator[tuple[Any, list[dict[str, Any]]]]:
    # Reuse the existing bounded, crash-released ledger writer lock.
    with writer_transaction(path) as target:
        with target.open("a+", encoding="utf-8") as stream:
            stream.seek(0)
            events = [
                json.loads(line, parse_int=int_from_decimal)
                for line in stream
                if line.strip()
            ]
            _require(all(isinstance(e, dict) for e in events), "invalid parent journal")
            yield stream, events


def _append(stream: Any, event: dict[str, Any]) -> None:
    import os

    stream.seek(0, 2)
    stream.write(dump_json(event) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _validate_rows(rows: Any, old_rows: list[dict[str, Any]]) -> None:
    _require(isinstance(rows, list) and bool(rows), "acceptance ledger required")
    seen = set()
    old = {r["id"]: r for r in old_rows}
    for row in rows:
        _require(isinstance(row, dict), "invalid acceptance row")
        _require(
            _text(row.get("id")) and row["id"] not in seen, "unique gap id required"
        )
        seen.add(row["id"])
        _require(_text(row.get("proposition")), "gap proposition required")
        _require(_text(row.get("source")), "frozen DoD source required")
        _require(
            row.get("state") in {"OPEN", "BLOCKED", "PROVED", "WAIVED", "NOT_REQUIRED"},
            "invalid gap state",
        )
        _require(
            isinstance(row.get("history"), list) and bool(row["history"]),
            "gap history required",
        )
        _require(
            _text(row.get("next_falsifier")), "gap falsifier or closure basis required"
        )
        if row["state"] in {"PROVED", "WAIVED", "NOT_REQUIRED", "BLOCKED"}:
            _require(
                _text(row.get("evidence"))
                and _text(row.get("revision"))
                and _text(row.get("observed_at")),
                "gap evidence/revision/time required",
            )
        if row["state"] in {"WAIVED", "NOT_REQUIRED"}:
            authority = row.get("authority", {})
            _require(
                isinstance(authority, dict)
                and all(
                    _text(authority.get(k)) for k in ("source", "scope", "conditions")
                ),
                "scoped authority required",
            )
        if row["id"] in old:
            previous = old[row["id"]]
            _require(
                row["proposition"] == previous["proposition"]
                and row["source"] == previous["source"]
                and row.get("kind") == previous.get("kind"),
                "frozen proposition cannot reset",
            )
            history = previous["history"]
            _require(
                row["history"][: len(history)] == history,
                "acceptance history cannot reset",
            )
            if row != previous:
                _require(
                    len(row["history"]) > len(history),
                    "transition requires retained history",
                )
            if previous["state"] in {"WAIVED", "NOT_REQUIRED"} and row != previous:
                _require(
                    _text(row.get("governing_authority")),
                    "waiver change requires governing authority",
                )
    _require(set(old) <= seen, "parent gaps cannot disappear")
    _require(
        not old or set(old) == seen,
        "gap set frozen at parent inception; governing scope changes need "
        "attributed authority without renewed counters",
    )
    propositions = [r["proposition"].strip().casefold() for r in rows]
    _require(len(set(propositions)) == len(propositions), "duplicate gap proposition")
    _require(
        any(
            r.get("kind") == "independent_review"
            and (bool(old) or r["state"] == "OPEN")
            for r in rows
        ),
        "required independent-review gap must be frozen at inception",
    )


@contextmanager
def _binding(path: Path, unit_id: str, journal: Path) -> Iterator[tuple[Any, int]]:
    with _journal(path) as (stream, events):
        prior = [e for e in events if e.get("unit_id") == unit_id]
        if prior:
            _require(
                prior[-1]["path"] == str(journal.resolve()),
                "parent journal path cannot reset",
            )
            _require(journal.is_file(), "bound parent journal missing; restore it")
        yield stream, prior[-1]["starts"] if prior else 0


WORKER_ENV = "LEE_LLM_ROUTER_PARENT_START"


def execution_identity() -> dict[str, Any]:
    """Capture local controller identity before an opted-in dispatch."""
    record = _linux_process_record(os.getpid())
    return {
        "host": socket.gethostname(),
        "boot": (
            Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            if Path("/proc/sys/kernel/random/boot_id").exists()
            else None
        ),
        "pid": os.getpid(),
        "start_time": record[1] if record else None,
        "marker": uuid.uuid4().hex,
    }


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None, "accounting timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _stopped(pending: dict[str, Any], finish: dict[str, Any] | None) -> None:
    identity = pending.get("execution")
    _require(
        isinstance(identity, dict),
        "missing retained process identity; inspect retained evidence",
    )
    _require(
        identity["host"] == socket.gethostname(), "reconcile on original execution host"
    )
    _require(
        identity.get("boot") is not None,
        "worker shutdown cannot be reconciled on this platform "
        "from retained process evidence",
    )
    controller_start = identity.get("start_time")
    _require(
        type(controller_start) is int and controller_start >= 0,
        "missing or unknown controller creation identity; cannot prove worker shutdown",
    )
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if boot != identity["boot"]:
        return
    if not finish or not finish.get("controller_finished_at"):
        controller = _linux_process_record(identity["pid"])
        _require(
            (controller is not None and controller[1] != identity["start_time"])
            or not pid_alive(identity["pid"]),
            "original controller remains live",
        )
    marker = f"{WORKER_ENV}={identity['marker']}".encode()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            env = (proc / "environ").read_bytes().split(bytes([0]))
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            process = _linux_process_record(int(proc.name))
            _require(
                process is not None and type(process[1]) is int and process[1] >= 0,
                "cannot prove worker shutdown: unreadable process environment "
                "and missing or unknown process creation identity",
            )
            # An older process cannot inherit this controller's fresh marker.
            # Equal ticks are ambiguous because Linux starttime has finite resolution.
            if process[1] < controller_start:
                continue
            raise UnitAdmissionError(
                "cannot prove worker shutdown: unreadable process environment "
                "created at or after original controller",
            ) from exc
        _require(
            marker not in env,
            "original worker remains live; stop and verify before reconciliation",
        )


def reserve_start(
    journal_path: str,
    decision_path: str,
    unit_id: str,
    *,
    route: str,
    packet_id: str,
    timeout: float,
    role: str,
    author_route: str | None,
    binding_path: str | None = None,
    execution: dict[str, Any] | None = None,
) -> int:
    """Reserve one cumulative start before provider launch.

    Args:
        journal_path: Stable append-only parent WORK/STATE journal path.
        decision_path: Supervisor's version-1 acceptance/decision JSON.
        unit_id: Stable parent identity inherited by every child/resume.
        route: Already selected eligible route, recorded without changing policy.
        packet_id: Packet hash for attribution, never method identity.
        timeout: Finite launch bound in seconds.
        role: Existing router role.
        author_route: Existing independent-review author exclusion.
        binding_path: Stable per-host ledger sidecar binding parent to its journal.
            Defaults beside the explicit journal for standalone callers.

    Returns:
        The reserved start number. Unfinished reservations block later starts.

    Raises:
        UnitAdmissionError: Evidence, accounting, continuity or limits fail.
    """
    try:
        decision = json.loads(Path(decision_path).read_text(encoding="utf-8"))
        _require(isinstance(decision, dict), "decision must be an object")
        _require(
            decision.get("version") == 1
            and decision.get("unit_id") == unit_id
            and _text(unit_id),
            "parent version/identity mismatch",
        )
        _require(_number(timeout) and timeout > 0, "finite positive timeout required")
        binding = (
            Path(binding_path)
            if binding_path
            else Path(journal_path).parent / "unit-bindings.jsonl"
        )
        with (
            _binding(binding, unit_id, Path(journal_path)) as (
                binding_stream,
                bound_starts,
            ),
            _journal(Path(journal_path)) as (stream, events),
        ):
            starts = [e for e in events if e.get("kind") == "start"]
            _require(
                len(starts) >= bound_starts, "parent journal counters cannot reset"
            )
            finishes = {
                e["start"]: e
                for e in events
                if e.get("kind") in {"finish", "reconcile"}
            }
            _require(
                all(e.get("unit_id") == unit_id for e in events),
                "journal belongs to another parent",
            )
            _require(
                decision.get("previous")
                == (_digest(starts[-1]["decision"]) if starts else None),
                "stale/resetting parent decision",
            )
            _require(
                type(decision.get("completed_starts")) is int
                and decision["completed_starts"] == len(starts),
                "parent start count cannot reset",
            )
            reconciliations = decision.get("reconcile", [])
            _require(isinstance(reconciliations, list), "invalid reconciliation")
            for item in reconciliations:
                _require(
                    isinstance(item, dict)
                    and type(item.get("start")) is int
                    and _text(item.get("evidence")),
                    "reconciliation needs start and inspected evidence",
                )
                pending = next((s for s in starts if s["start"] == item["start"]), None)
                _require(pending is not None, "unknown reconciliation start")
                if item["start"] in finishes and finishes[item["start"]]["accounted"]:
                    continue
                _stopped(pending, finishes.get(item["start"]))
                if _text(item.get("attempt_id")):
                    attempts = read_attempts(resolve_attempts_path())
                    record = next(
                        (r for r in attempts if r["attempt_id"] == item["attempt_id"]),
                        None,
                    )
                    _require(
                        record is not None
                        and record.get("packet_id") == pending["packet_id"]
                        and pending["execution"].get("route_record") is not None
                        and all(
                            record.get("route", {}).get(k) == v
                            for k, v in pending["execution"]["route_record"].items()
                        )
                        and _time(record["captured_at"])
                        >= _time(pending["reserved_at"]),
                        "reconciliation requires matching persisted launch evidence",
                    )
                    _require(
                        not any(
                            f.get("attempt", {}).get("attempt_id") == item["attempt_id"]
                            for f in finishes.values()
                            if f.get("attempt")
                        ),
                        "attempt already accounted",
                    )
                    seconds = record["wall_clock_ms"] / 1000
                    basis = "actual persisted attempt"
                else:
                    record = None
                    end = datetime.now(timezone.utc).isoformat()
                    seconds = max(
                        0, (_time(end) - _time(pending["reserved_at"])).total_seconds()
                    )
                    basis = "conservative reservation-to-reconciliation upper bound"
                event = {
                    "kind": "reconcile",
                    "unit_id": unit_id,
                    "start": item["start"],
                    "accounted": True,
                    "seconds": seconds,
                    "attempt": record,
                    "usage": "unknown" if record is None else "see attempt",
                    "outcome": "unknown" if record is None else "see attempt",
                    "time_basis": basis,
                    "evidence": item["evidence"],
                }
                _append(stream, event)
                finishes[item["start"]] = event
            _require(
                all(
                    s["start"] in finishes and finishes[s["start"]]["accounted"]
                    for s in starts
                ),
                "unaccounted parent start; reconcile retained launch evidence first",
            )
            previous = starts[-1]["decision"] if starts else {}
            _validate_rows(decision.get("gaps"), previous.get("gaps", []))
            limits = decision.get("limits", {})
            _require(
                isinstance(limits, dict)
                and set(limits)
                <= {
                    "starts",
                    "seconds",
                    "reserve_starts",
                    "reserve_seconds",
                    "authority",
                },
                "invalid supplied limits",
            )
            _require(
                not starts or limits == previous.get("limits", {}),
                "parent limits cannot reset",
            )
            for key in ("starts", "seconds", "reserve_starts", "reserve_seconds"):
                if key in limits:
                    _require(_number(limits[key]), "invalid limit")
            if limits:
                _require(
                    _text(limits.get("authority")), "supplied limit authority required"
                )
            assessments = decision.get("assessments")
            _require(
                isinstance(assessments, list) and len(assessments) == len(starts),
                "every prior start requires an acceptance assessment",
            )
            old_assessments = previous.get("assessments", [])
            _require(
                assessments[: len(old_assessments)] == old_assessments,
                "method assessment history cannot reset",
            )
            streaks: dict[tuple[str, str], int] = {}
            denied: set[tuple[str, str]] = set()
            for start, assessment in zip(starts, assessments):
                _require(
                    isinstance(assessment, dict)
                    and assessment.get("start") == start["start"]
                    and type(assessment.get("advanced")) is bool
                    and type(assessment.get("denied")) is bool
                    and _text(assessment.get("evidence")),
                    "invalid method assessment",
                )
                dispatch = start["decision"]["dispatch"]
                moved_targets = assessment.get("advanced_targets")
                if moved_targets is not None:
                    _require(
                        isinstance(moved_targets, list)
                        and all(t in dispatch["targets"] for t in moved_targets),
                        "advanced targets must belong to assessed dispatch",
                    )
                if dispatch["phase"] in {"review", "final_review"}:
                    _require(
                        assessment.get("review_outcome")
                        in {"passed", "blocking", "incomplete"},
                        "review outcome evidence required",
                    )
                    _require(
                        assessment["review_outcome"] == "incomplete"
                        or finishes[start["start"]].get("attempt") is not None,
                        "completed review requires actual retained review record",
                    )
                for gap in dispatch["targets"]:
                    key = (gap, dispatch["method"])
                    streaks[key] = (
                        0
                        if gap
                        in assessment.get(
                            "advanced_targets",
                            (
                                dispatch["targets"]
                                if len(dispatch["targets"]) == 1
                                and assessment["advanced"]
                                else []
                            ),
                        )
                        else streaks.get(key, 0) + 1
                    )
                    if assessment["denied"]:
                        denied.add((gap, dispatch["capability"]))
            dispatch = decision.get("dispatch", {})
            _require(isinstance(dispatch, dict), "dispatch question required")
            for key in (
                "method",
                "capability",
                "hypothesis",
                "proposition",
                "oracle",
                "falsifier",
                "alternatives",
                "why",
                "revision",
            ):
                _require(_text(dispatch.get(key)), f"dispatch {key} required")
            targets = dispatch.get("targets")
            _require(
                isinstance(targets, list)
                and bool(targets)
                and all(_text(t) for t in targets),
                "dispatch target gaps required",
            )
            gaps = {g["id"]: g for g in decision["gaps"]}
            _require(
                all(
                    t in gaps and gaps[t]["state"] in {"OPEN", "BLOCKED"}
                    for t in targets
                ),
                "dispatch must advance an open parent gap",
            )
            for target in targets:
                key = (target, dispatch["method"])
                _require(
                    (target, dispatch["capability"]) not in denied,
                    "definitive denial prohibits equivalent retries",
                )
                _require(
                    streaks.get(key, 0) < 2,
                    "two nonadvancing attempts prohibit unchanged method; "
                    "renamed method is causally unchanged",
                )
            # Renaming a method must explain a causal capability/hypothesis change.
            for start in starts:
                prior = start["decision"]["dispatch"]
                if (
                    set(targets) & set(prior["targets"])
                    and prior["method"] != dispatch["method"]
                ):
                    _require(
                        (dispatch["capability"], dispatch["hypothesis"])
                        != (prior["capability"], prior["hypothesis"]),
                        "renamed method is causally unchanged",
                    )
            phase = dispatch.get("phase")
            _require(
                phase in {"author", "diagnose", "repair", "review", "final_review"},
                "invalid transaction phase",
            )
            round_number = dispatch.get("repair_round")
            prior_dispatch = previous.get("dispatch", {})
            prior_round = prior_dispatch.get("repair_round", 0)
            prior_phase = prior_dispatch.get("phase")
            _require(
                type(round_number) is int and 0 <= round_number <= 2,
                "repair allowance cannot reset or exceed two rounds",
            )
            completed = [
                s
                for s, a in zip(starts, assessments)
                if finishes[s["start"]].get("attempt") is not None
                and (
                    s["decision"]["dispatch"]["phase"] not in {"review", "final_review"}
                    or a["review_outcome"] != "incomplete"
                )
            ]
            completed_phases = [s["decision"]["dispatch"]["phase"] for s in completed]
            _require(
                "final_review" not in completed_phases,
                "final review ended this transaction; preserve incomplete disposition",
            )
            _require(
                phase != "author"
                or not any(
                    s["decision"]["dispatch"]["phase"] in {"review", "final_review"}
                    for s in starts
                ),
                "authoring cannot restart after independent review",
            )
            if phase == "repair":
                _require(
                    "review" in completed_phases,
                    "directed repair/final review requires prior independent review",
                )
                last_review = next(
                    s
                    for s in reversed(completed)
                    if s["decision"]["dispatch"]["phase"] == "review"
                )
                expected = last_review["decision"]["dispatch"]["repair_round"] + 1
                _require(
                    round_number == expected and expected <= 2,
                    "repair allowance requires next directed round after review",
                )
            else:
                _require(
                    round_number == prior_round,
                    "repair allowance changes only when starting directed repair",
                )
            if phase == "diagnose" and any(
                p in {"review", "final_review"} for p in completed_phases
            ):
                _require(
                    prior_phase in {"repair", "diagnose"} and prior_round < 2,
                    "diagnosis cannot extend closed review transaction",
                )
            if phase == "review":
                _require(prior_round < 2, "round two requires final review")
                _require(
                    prior_phase not in {"review", "final_review"}
                    or starts[-1] not in completed,
                    "completed review cannot repeat without material repair",
                )
            if phase == "final_review":
                _require(
                    "review" in completed_phases,
                    "directed repair/final review requires prior independent review",
                )
                _require(
                    prior_phase in {"repair", "final_review"},
                    "unchanged initial review already covers final material source; "
                    "no duplicate review",
                )
            if phase in {"review", "final_review"}:
                failed_reviews = [
                    s
                    for s in starts
                    if s["decision"]["dispatch"]["phase"] == phase
                    and s["decision"]["dispatch"]["repair_round"] == round_number
                    and s not in completed
                ]
                _require(
                    len(failed_reviews) < 2,
                    "review execution recovery exhausted; "
                    "preserve incomplete disposition",
                )
                _require(
                    any(gaps[t].get("kind") == "independent_review" for t in targets),
                    "review must target frozen independent-review gap",
                )
            if phase in {"review", "final_review"}:
                _require(
                    role == "review" and _text(author_route),
                    "independent review exclusion required",
                )
            reserve = 0 if phase == "final_review" else limits.get("reserve_starts", 0)
            _require(
                "starts" not in limits or len(starts) + 1 + reserve <= limits["starts"],
                "supplied parent starts exhausted",
            )
            used = sum(f["seconds"] for f in finishes.values())
            reserve_seconds = (
                0 if phase == "final_review" else limits.get("reserve_seconds", 0)
            )
            _require(
                "seconds" not in limits
                or used + timeout + reserve_seconds <= limits["seconds"],
                "supplied parent time exhausted",
            )
            number = len(starts) + 1
            _append(
                stream,
                {
                    "kind": "start",
                    "unit_id": unit_id,
                    "start": number,
                    "route": route,
                    "reserved_at": datetime.now(timezone.utc).isoformat(),
                    "packet_id": packet_id,
                    "decision": decision,
                    "execution": execution,
                },
            )
            _append(
                binding_stream,
                {
                    "unit_id": unit_id,
                    "path": str(Path(journal_path).resolve()),
                    "starts": number,
                },
            )
            return number
    except (
        AttemptLedgerError,
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise UnitAdmissionError(str(exc)) from exc


def finish_start(
    journal_path: str,
    unit_id: str,
    start: int,
    record: dict[str, Any] | None,
) -> None:
    """Persist actual accounting; missing records await shutdown reconciliation.

    Args:
        journal_path: The same stable parent journal used at admission.
        unit_id: The inherited parent identity.
        start: Reservation returned by reserve_start.
        record: Persisted v2 attempt, or None when accounting failed.
    """
    with _journal(Path(journal_path)) as (stream, events):
        _require(
            all(e.get("unit_id") == unit_id for e in events), "parent identity mismatch"
        )
        _require(
            not any(
                e.get("kind") in {"finish", "reconcile"} and e.get("start") == start
                for e in events
            ),
            "duplicate accounting",
        )
        _append(
            stream,
            {
                "kind": "finish",
                "unit_id": unit_id,
                "start": start,
                "accounted": record is not None,
                "seconds": record["wall_clock_ms"] / 1000 if record else None,
                "attempt": record,
                "controller_finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
