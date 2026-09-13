"""Focused P5-1 tests for ``evidence_report.build_evidence_report``.

Every test constructs scratch attempt records (no provider, no real router
state) and verifies the enriched aggregation. Tests cover:

- A class with cost data available (both list and marginal reported)
- A class with missing cost object (reported ``unavailable`` with reason)
- An escalation chain (parent/child linked via ``parent_attempt_id``)
- A channel inside its reserve floor vs one outside it
- Filtering by month (records outside the month are excluded)
- Reviewer fallback detection from selection.excluded
- Route change recommendations
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lee_llm_router.staffing.evidence_report import (
    CHANNEL_IDS,
    build_evidence_report,
    render_evidence_report,
)
from lee_llm_router.staffing.rollup import MINIMUM_SAMPLE_SIZE

# Re-use the repo's committed catalog (channels, routes, policy)
REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"

# ---------------------------------------------------------------------------
# Helpers to build scratch records
# ---------------------------------------------------------------------------

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / "attempt-record-router-run-unavailable.json"
)

_RECORD_COUNTER = 0


def _next_attempt_id() -> str:
    global _RECORD_COUNTER
    _RECORD_COUNTER += 1
    return f"test-evidence-{_RECORD_COUNTER:04d}"


def _record(
    *,
    route_id: str = "codex-gpt-5-6-sol-low-openai-sub",
    class_key: str = "impl/deterministic/none/s/python",
    captured_at: str = "2026-09-15T12:00:00Z",
    verified_success: bool = True,
    verdict: str = "pass",
    parent_attempt_id: str | None = None,
    escalation_reason: str | None = None,
    cost_usd_list: float | None = 0.05,
    cost_usd_marginal: float | None = 0.03,
    role: str | None = None,
    selection: dict | None = None,
    attempt_id: str | None = None,
    failure_class: str | None = None,
) -> dict:
    """Make a schema-valid scratch attempt record with controlled cost/escalation.

    Built from the committed ``attempt-record-router-run-unavailable.json`` fixture
    shape (the same base ``test_staffing_rollup.py`` uses) rather than from scratch,
    so every required field (``router_event``, ``provenance.source_refs``,
    ``selection``) is present and ``usage.source``/``supervisor_route`` satisfy the
    schema's closed vocabularies and conditional gates (P1-4 ruling 3: a
    ``verified_success: true`` record requires a real ``supervisor_route`` object and
    forbids ``verified_success_reason``; a ``verified_success: false`` record with an
    attested ``supervisor_route`` requires a truthful ``verified_success_reason``).
    """
    aid = attempt_id or _next_attempt_id()
    parts = class_key.split("/")
    class_record = {
        "class_key": class_key,
        "role": parts[0] if len(parts) > 0 else "impl",
        "oracle_type": parts[1] if len(parts) > 1 else "deterministic",
        "domain_tags": [],
        "size_band": parts[3] if len(parts) > 3 else "s",
        "language": parts[4] if len(parts) > 4 else "python",
    }
    if role is not None:
        class_record["role"] = role

    record: dict = {
        "schema_version": 2,
        "attempt_id": aid,
        "record_kind": "router_run",
        "packet_id": "test-packet",
        "parent_attempt_id": parent_attempt_id,
        "escalation_reason": escalation_reason,
        "captured_at": captured_at,
        "verified_success": verified_success,
        "route": {
            "model": "test-model",
            "effort": "low",
            "harness": "codex",
            "channel": "openai-sub",
            "provider": "openai",
        },
        "supervisor_route": {
            "model": "test-supervisor-model",
            "effort": "high",
            "harness": "cli",
            "channel": "anthropic-sub",
            "provider": "anthropic",
        },
        "class_record": class_record,
        "verdict": verdict,
        "failure_class": failure_class,
        "oracle_cmd": "test-oracle --check",
        "usage": {
            "basis": "provider_reported",
            "source": "pi --mode json events",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        },
        "wall_clock_ms": 500,
        "selection": (
            selection
            if selection is not None
            else {
                "basis": "explicit",
                "reason": f"explicit --route {route_id} eligible for {class_key}",
                "explain_ref": f"catalog explain --role impl --class {class_key}",
                "excluded": [],
            }
        ),
        "router_event": {
            "ts": captured_at,
            "host": "test-host",
            "harness": "cli",
            "crew": "run",
            "role": class_record["role"],
            "mode": "strict",
            "worker_id": route_id,
            "provider": "test-provider",
            "model": "test-model",
            "effort": "low",
            "channel": "openai-sub",
            "headroom": "healthy",
            "reason": "test fixture",
            "authorized_by": None,
            "route_id": route_id,
            "snapshot_observed_at": captured_at,
            "snapshot_stale": False,
        },
        "provenance": {
            "source": "router-run",
            "recorded_by": "test",
            "source_refs": ["tests/test_staffing_evidence_report.py"],
        },
    }
    if verified_success:
        record["failure_class"] = None
    else:
        record["verified_success_reason"] = "oracle_not_passed"

    if cost_usd_list is not None and cost_usd_marginal is not None:
        record["cost"] = {
            "basis": ["list", "marginal"],
            "usd_list": cost_usd_list,
            "usd_marginal": cost_usd_marginal,
        }
    elif cost_usd_list is None and cost_usd_marginal is None:
        record["cost"] = {"basis": ["unavailable"]}

    return record


# ---------------------------------------------------------------------------
# Cost data available (both list and marginal)
# ---------------------------------------------------------------------------


def test_cost_available(tmp_path, monkeypatch) -> None:
    """A class with cost data available reports both list and marginal."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    # Two records with the same route/class, both with cost
    append_attempt(
        _record(
            route_id="route-a",
            class_key="impl/deterministic/none/s/python",
            cost_usd_list=0.10,
            cost_usd_marginal=0.06,
        ),
        path=ledger,
    )
    append_attempt(
        _record(
            route_id="route-a",
            class_key="impl/deterministic/none/s/python",
            cost_usd_list=0.20,
            cost_usd_marginal=0.12,
        ),
        path=ledger,
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    classes = report["classes"]
    assert len(classes) == 1
    row = classes[0]
    assert row["route_id"] == "route-a"
    assert row["class_key"] == "impl/deterministic/none/s/python"
    assert row["attempts"] == 2
    assert row["verified_pass"] == 2
    cost = row["cost_per_verified_success"]
    assert "unavailable" not in cost
    assert cost["usd_list"] == pytest.approx(0.15)  # (0.10 + 0.20) / 2
    assert cost["usd_marginal"] == pytest.approx(0.09)  # (0.06 + 0.12) / 2


# ---------------------------------------------------------------------------
# Missing cost object -> unavailable
# ---------------------------------------------------------------------------


def test_cost_missing_reports_unavailable(tmp_path, monkeypatch) -> None:
    """A class where verified attempts lack cost reports unavailable with reason."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    # Three records, two verified. One has cost, one does not.
    append_attempt(
        _record(
            route_id="route-b",
            class_key="impl/deterministic/none/s/python",
            cost_usd_list=0.05,
            cost_usd_marginal=0.03,
            attempt_id="has-cost",
        ),
        path=ledger,
    )
    append_attempt(
        _record(
            route_id="route-b",
            class_key="impl/deterministic/none/s/python",
            cost_usd_list=None,
            cost_usd_marginal=None,  # triggers cost = {"basis": ["unavailable"]}
            attempt_id="no-cost",
        ),
        path=ledger,
    )
    # Third record, not verified (so not counted in cost)
    append_attempt(
        _record(
            route_id="route-b",
            class_key="impl/deterministic/none/s/python",
            verified_success=False,
            verdict="fail",
            cost_usd_list=None,
            cost_usd_marginal=None,
            attempt_id="fail-record",
        ),
        path=ledger,
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    classes = report["classes"]
    assert len(classes) >= 1
    row = next(c for c in classes if c["route_id"] == "route-b")
    assert row["attempts"] == 3
    assert row["verified_pass"] == 2  # two verified successes
    cost = row["cost_per_verified_success"]
    assert "unavailable" in cost
    assert "1 of 2 verified attempts have no usable cost record" in cost["unavailable"]


# ---------------------------------------------------------------------------
# Escalation chain
# ---------------------------------------------------------------------------


def test_escalation_chain(tmp_path, monkeypatch) -> None:
    """Records with parent_attempt_id are counted as escalations with reason."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    # Parent record (failed, with failure_class)
    append_attempt(
        _record(
            route_id="route-c",
            class_key="impl/deterministic/none/s/python",
            verified_success=False,
            verdict="fail",
            failure_class="capability_rejected",
            cost_usd_list=0.05,
            cost_usd_marginal=0.03,
            attempt_id="parent-001",
        ),
        path=ledger,
    )
    # Child record (escalation)
    append_attempt(
        _record(
            route_id="route-c",
            class_key="impl/deterministic/none/s/python",
            parent_attempt_id="parent-001",
            escalation_reason="parent failed: capability_rejected",
            cost_usd_list=0.10,
            cost_usd_marginal=0.06,
            attempt_id="child-001",
        ),
        path=ledger,
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    classes = report["classes"]
    row = next(c for c in classes if c["route_id"] == "route-c")
    assert row["escalations"] == 1
    assert len(row["escalation_details"]) == 1
    esc = row["escalation_details"][0]
    assert esc["parent_attempt_id"] == "parent-001"
    assert esc["escalation_reason"] == "parent failed: capability_rejected"


def test_escalation_reason_from_parent_failure(tmp_path, monkeypatch) -> None:
    """The reported escalation_reason is read verbatim from the child record.

    The schema requires ``escalation_reason`` whenever ``parent_attempt_id`` is
    set (an escalation requires both), so there is no schema-valid record for
    evidence_report to "derive" a reason from — it only ever reports the
    recorded field, joined to the parent for its failure_class context.
    """
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    # Parent record
    append_attempt(
        _record(
            route_id="route-c",
            class_key="impl/deterministic/none/s/python",
            verified_success=False,
            verdict="fail",
            failure_class="platform_timeout",
            cost_usd_list=0.05,
            cost_usd_marginal=0.03,
            attempt_id="parent-002",
        ),
        path=ledger,
    )
    # Child record (escalation), its own recorded reason
    append_attempt(
        _record(
            route_id="route-c",
            class_key="impl/deterministic/none/s/python",
            parent_attempt_id="parent-002",
            escalation_reason="parent failed: platform_timeout",
            cost_usd_list=0.10,
            cost_usd_marginal=0.06,
            attempt_id="child-002",
        ),
        path=ledger,
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    classes = report["classes"]
    row = next(c for c in classes if c["route_id"] == "route-c")
    assert row["escalations"] == 1
    esc = row["escalation_details"][0]
    assert esc["parent_attempt_id"] == "parent-002"
    assert esc["escalation_reason"] is not None


# ---------------------------------------------------------------------------
# Reviewer fallback
# ---------------------------------------------------------------------------


def test_reviewer_fallback_detected(tmp_path, monkeypatch) -> None:
    """Review/judge role with independence exclusion in selection.excluded."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    append_attempt(
        _record(
            route_id="route-d",
            class_key="review/judge/none/xs/markdown",
            role="review",
            selection={
                "basis": "explain_cheapest_eligible",
                "reason": "fell back to next eligible after independence exclusion",
                "explain_ref": (
                    "catalog explain --role review --class "
                    "review/judge/none/xs/markdown"
                ),
                "excluded": [
                    {
                        "route_id": "author-route",
                        "reason": "independence: author route excluded for review role",
                    }
                ],
            },
            cost_usd_list=0.08,
            cost_usd_marginal=0.04,
        ),
        path=ledger,
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    classes = report["classes"]
    row = next(c for c in classes if c["route_id"] == "route-d")
    rf = row["reviewer_fallbacks"]
    assert rf["count"] == 0
    assert rf["undecidable"] == 1
    assert rf["unavailable_reason"] == (
        "selection.excluded records independence exclusions without explain order; "
        "fallback cannot be read from the record"
    )


_FALLBACK_REASON = (
    "selection.excluded records independence exclusions without explain order; "
    "fallback cannot be read from the record"
)
_NO_SELECTION_REASON = (
    "record carries no selection object; fallback cannot be read from the record"
)


@pytest.mark.parametrize(
    ("case_id", "selection", "no_selection", "expected_rf"),
    [
        (
            "explicit-ind",
            {
                "basis": "explicit",
                "reason": "explicit --route chosen",
                "explain_ref": "ref",
                "excluded": [{"route_id": "author", "reason": "independence"}],
            },
            False,
            {"count": 0, "undecidable": 0, "unavailable_reason": None},
        ),
        (
            "explain-clean",
            {
                "basis": "explain_cheapest_eligible",
                "reason": "cheapest",
                "explain_ref": "ref",
                "excluded": [{"route_id": "other", "reason": "never_automatic"}],
            },
            False,
            {"count": 0, "undecidable": 0, "unavailable_reason": None},
        ),
        (
            "explain-ind",
            {
                "basis": "explain_cheapest_eligible",
                "reason": "fallback",
                "explain_ref": "ref",
                "excluded": [{"route_id": "author", "reason": "independence"}],
            },
            False,
            {"count": 0, "undecidable": 1, "unavailable_reason": _FALLBACK_REASON},
        ),
        (
            "no-sel",
            None,
            True,
            {
                "count": 0,
                "undecidable": 1,
                "unavailable_reason": _NO_SELECTION_REASON,
            },
        ),
    ],
)
def test_reviewer_fallback_truth_rules(
    monkeypatch, case_id, selection, no_selection, expected_rf
) -> None:
    """Evaluate reviewer fallback truth rules across basis and exclusion states."""
    rec = _record(
        route_id=f"route-{case_id}",
        class_key="review/judge/none/xs/markdown",
        role="review",
        selection=selection,
    )
    if no_selection:
        rec.pop("selection", None)
    monkeypatch.setattr(
        "lee_llm_router.staffing.evidence_report.read_attempts",
        lambda p: [rec],
    )
    report = build_evidence_report("2026-09", catalog_dir=str(REPO_CONFIG_DIR))
    row = next(c for c in report["classes"] if c["route_id"] == f"route-{case_id}")
    assert row["reviewer_fallbacks"] == expected_rf


def test_render_evidence_report_reviewer_fallbacks_both_states() -> None:
    """Renderer outputs 'reviewer_fallbacks: 0' when 0/0, and formatted
    string otherwise.
    """
    reason = (
        "selection.excluded records independence exclusions without explain order; "
        "fallback cannot be read from the record"
    )
    report_clean = {
        "report_for": "2026-09",
        "classes": [
            {
                "route_id": "route-1",
                "class_key": "review/judge/none/xs/markdown",
                "attempts": 1,
                "verified_pass": 1,
                "pass_rate": 1.0,
                "comparison_eligible": False,
                "cost_per_verified_success": {"usd_list": 0.05, "usd_marginal": 0.02},
                "tokens_per_verified_success": {},
                "escalations": 0,
                "escalation_details": [],
                "reviewer_fallbacks": {
                    "count": 0,
                    "undecidable": 0,
                    "unavailable_reason": None,
                },
            }
        ],
        "channels": [],
        "route_changes": [],
    }
    text_clean = render_evidence_report(report_clean)
    assert "  reviewer_fallbacks: 0" in text_clean
    assert "undecidable" not in text_clean

    report_undecidable = {
        "report_for": "2026-09",
        "classes": [
            {
                "route_id": "route-2",
                "class_key": "review/judge/none/xs/markdown",
                "attempts": 1,
                "verified_pass": 1,
                "pass_rate": 1.0,
                "comparison_eligible": False,
                "cost_per_verified_success": {"usd_list": 0.05, "usd_marginal": 0.02},
                "tokens_per_verified_success": {},
                "escalations": 0,
                "escalation_details": [],
                "reviewer_fallbacks": {
                    "count": 0,
                    "undecidable": 1,
                    "unavailable_reason": reason,
                },
            }
        ],
        "channels": [],
        "route_changes": [],
    }
    text_undecidable = render_evidence_report(report_undecidable)
    assert f"  reviewer_fallbacks: 0 (+1 undecidable: {reason})" in text_undecidable


def test_reviewer_fallbacks_json_shape(tmp_path, monkeypatch) -> None:
    """The JSON output presents reviewer_fallbacks as an object with
    count, undecidable, unavailable_reason.
    """
    from lee_llm_router.staffing.json_int import dump_json
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    append_attempt(
        _record(
            route_id="route-json",
            class_key="review/judge/none/xs/markdown",
            role="review",
            selection={
                "basis": "explain_cheapest_eligible",
                "reason": "fallback",
                "explain_ref": "ref",
                "excluded": [{"route_id": "author", "reason": "independence"}],
            },
        ),
        path=ledger,
    )

    report = build_evidence_report("2026-09", catalog_dir=str(REPO_CONFIG_DIR))
    raw_json = dump_json(report)
    parsed = json.loads(raw_json)
    row = next(c for c in parsed["classes"] if c["route_id"] == "route-json")
    assert isinstance(row["reviewer_fallbacks"], dict)
    rf = row["reviewer_fallbacks"]
    assert set(rf.keys()) == {"count", "undecidable", "unavailable_reason"}
    assert isinstance(rf["count"], int)
    assert isinstance(rf["undecidable"], int)
    assert isinstance(rf["unavailable_reason"], str)
    assert rf["count"] == 0
    assert rf["undecidable"] == 1


# ---------------------------------------------------------------------------
# Channel headroom: inside vs outside reserve
# ---------------------------------------------------------------------------


def test_channel_headroom_inside_and_outside_reserve(tmp_path) -> None:
    """Channels inside their reserve floor are reported as inside."""
    # Write a minimal availability snapshot
    av_file = tmp_path / "availability.json"
    av_file.write_text(
        json.dumps(
            {
                "host": "test-host",
                "observed_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S+00:00"
                ),
                "subscriptions": [
                    {
                        "provider": "OpenAI/Codex",
                        "bucket": "Weekly limit",
                        "status": "ON TRACK",
                        "used_pct": 10.0,
                        "remaining_pct": 90.0,
                        "pace_ratio": 1.0,
                        "pace_ratio_infinite": False,
                        "resets_at": "2026-10-01T12:00:00+00:00",
                        "resets_in_hours": 72.0,
                    },
                    {
                        "provider": "Anthropic/Claude",
                        "bucket": "Monthly limit",
                        "status": "TOO FAST",
                        "used_pct": 95.0,
                        "remaining_pct": 5.0,
                        "pace_ratio": 2.5,
                        "pace_ratio_infinite": False,
                        "resets_at": "2026-10-01T12:00:00+00:00",
                        "resets_in_hours": 72.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
        availability_file=str(av_file),
    )
    channels = report["channels"]

    openai = next(c for c in channels if c["channel_id"] == "openai-sub")
    # remaining_fraction 0.90, reserve default 0.10 -> outside reserve
    assert openai["remaining_fraction"] is not None
    assert openai["reserve_fraction"] == 0.10
    assert openai["inside_reserve"] is False

    anthropic = next(c for c in channels if c["channel_id"] == "anthropic-sub")
    # remaining_fraction 0.05, reserve 0.10 -> inside reserve
    assert anthropic["remaining_fraction"] is not None
    assert anthropic["reserve_fraction"] == 0.10
    assert anthropic["inside_reserve"] is True


# ---------------------------------------------------------------------------
# Month filtering
# ---------------------------------------------------------------------------


def test_month_filtering_excludes_outside_month(tmp_path, monkeypatch) -> None:
    """Records outside the requested month are excluded."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    # Record in September
    append_attempt(
        _record(
            route_id="route-e",
            class_key="impl/deterministic/none/s/python",
            captured_at="2026-09-15T12:00:00Z",
        ),
        path=ledger,
    )
    # Record in October
    append_attempt(
        _record(
            route_id="route-e",
            class_key="impl/deterministic/none/s/python",
            captured_at="2026-10-01T00:00:01Z",
        ),
        path=ledger,
    )
    # Record in August
    append_attempt(
        _record(
            route_id="route-e",
            class_key="impl/deterministic/none/s/python",
            captured_at="2026-08-31T23:59:59Z",
        ),
        path=ledger,
    )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    row = next(c for c in report["classes"] if c["route_id"] == "route-e")
    assert row["attempts"] == 1  # only September record counts


# ---------------------------------------------------------------------------
# Empty month produces valid report
# ---------------------------------------------------------------------------


def test_empty_month_produces_valid_report() -> None:
    """A month with no records produces a valid report with zero groups."""
    report = build_evidence_report(
        "2030-01",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    assert report["report_for"] == "2030-01"
    assert len(report["classes"]) == 0
    # Channels and route_changes should still be present
    assert isinstance(report["channels"], list)
    assert isinstance(report["route_changes"], list)


# ---------------------------------------------------------------------------
# Render text mode
# ---------------------------------------------------------------------------


def test_render_evidence_report_text() -> None:
    """Text rendering returns a non-empty string with report_for."""
    report = {
        "report_for": "2026-09",
        "classes": [],
        "channels": [
            {
                "channel_id": "openai-sub",
                "remaining_fraction": 0.90,
                "reserve_fraction": 0.10,
                "inside_reserve": False,
                "availability": "outside reserve",
            }
        ],
        "route_changes": [],
    }
    text = render_evidence_report(report)
    assert "Evidence report" in text
    assert "2026-09" in text
    assert "openai-sub" in text


def _render_group_for_test(
    route_id: str | None, class_key: str, attempt_id: str
) -> dict:
    """Build the minimum complete group accepted by the text renderer."""
    return {
        "route_id": route_id,
        "class_key": class_key,
        "source_ledger": "test-ledger.jsonl",
        "source_attempt_ids": [attempt_id],
        "attempts": 1,
        "verified_pass": 1,
        "pass_rate": 1.0,
        "comparison_eligible": False,
        "cost_per_verified_success": {"usd_list": 0.1, "usd_marginal": 0.05},
        "tokens_per_verified_success": {},
        "escalations": 0,
        "escalation_details": [],
        "reviewer_fallbacks": 0,
    }


def test_render_evidence_report_separates_unrouted_legacy_groups() -> None:
    """Routed groups render first while preserving each group's line format."""
    legacy = _render_group_for_test(None, "legacy-class", "legacy-1")
    routed = _render_group_for_test("route-a", "routed-class", "routed-1")
    text = render_evidence_report(
        {"report_for": "2026-09", "classes": [legacy, routed], "route_changes": []}
    )

    classes_heading = text.index("Classes (1 groups):")
    routed_group = text.index("  route: route-a")
    legacy_heading = text.index(
        "Unrouted legacy groups (1 groups, no router route recorded):"
    )
    legacy_group = text.index("  route: (none)")
    assert classes_heading < routed_group < legacy_heading < legacy_group
    assert (
        "  class: routed-class\n"
        "  source: 1 attempts from test-ledger.jsonl (routed-1)" in text
    )
    assert (
        "  class: legacy-class\n"
        "  source: 1 attempts from test-ledger.jsonl (legacy-1)" in text
    )


def test_render_evidence_report_omits_empty_unrouted_legacy_section() -> None:
    """Reports without legacy groups do not print the legacy heading."""
    routed = _render_group_for_test("route-a", "routed-class", "routed-1")
    text = render_evidence_report(
        {"report_for": "2026-09", "classes": [routed], "route_changes": []}
    )

    assert "Classes (1 groups):" in text
    assert "Unrouted legacy groups" not in text


def test_build_evidence_report_classes_json_is_unchanged_for_legacy_groups(
    monkeypatch,
) -> None:
    """The dict path keeps its existing order and group fields."""
    routed = _record(
        route_id="route-json", class_key="routed-json", attempt_id="routed-json-1"
    )
    legacy = _record(route_id=None, class_key="legacy-json", attempt_id="legacy-json-1")
    monkeypatch.setattr(
        "lee_llm_router.staffing.evidence_report.read_attempts",
        lambda _path: [routed, legacy],
    )

    report = build_evidence_report("2026-09", catalog_dir=str(REPO_CONFIG_DIR))
    classes = report["classes"]
    assert [(group["route_id"], group["class_key"]) for group in classes] == [
        (None, "legacy-json"),
        ("route-json", "routed-json"),
    ]
    expected_fields = [
        "route_id",
        "class_key",
        "source_ledger",
        "source_attempt_ids",
        "attempts",
        "verified_pass",
        "pass_rate",
        "comparison_eligible",
        "cost_per_verified_success",
        "tokens_per_verified_success",
        "escalations",
        "escalation_details",
        "reviewer_fallbacks",
    ]
    assert [list(group) for group in classes] == [expected_fields, expected_fields]
    assert classes[0]["source_attempt_ids"] == ["legacy-json-1"]
    assert classes[1]["source_attempt_ids"] == ["routed-json-1"]


# ---------------------------------------------------------------------------
# Route change recommendations
# ---------------------------------------------------------------------------


def test_route_change_recommendation(tmp_path, monkeypatch) -> None:
    """When a class has >=2 comparison-eligible routes, recommends cheapest."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    CLASS = "impl/deterministic/none/s/python"

    # Route A: 5 attempts, 5 passes, cost 0.10/0.06
    for i in range(5):
        append_attempt(
            _record(
                route_id="route-cheap",
                class_key=CLASS,
                cost_usd_list=0.10,
                cost_usd_marginal=0.06,
            ),
            path=ledger,
        )
    # Route B: 5 attempts, 4 passes (0.8 pass rate), cost 0.05/0.03 (cheaper)
    for i in range(5):
        append_attempt(
            _record(
                route_id="route-cheaper",
                class_key=CLASS,
                cost_usd_list=0.05,
                cost_usd_marginal=0.03,
                verified_success=(i < 4),  # 4 passes, 1 fail
            ),
            path=ledger,
        )

    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    changes = report["route_changes"]
    assert len(changes) >= 1
    match = [c for c in changes if c["class_key"] == CLASS]
    assert len(match) >= 1
    # Should recommend route-cheaper (cheaper marginal)
    assert match[0]["recommended_route_id"] == "route-cheaper"
    assert "pass_rate=" in match[0]["evidence"]


# ---------------------------------------------------------------------------
# All seven channels are reported
# ---------------------------------------------------------------------------


def test_all_seven_channels_reported(tmp_path) -> None:
    """No availability snapshot reports all 7 channels with availability info."""
    report = build_evidence_report(
        "2026-09",
        catalog_dir=str(REPO_CONFIG_DIR),
    )
    channels = report["channels"]
    channel_ids = {ch["channel_id"] for ch in channels}
    for cid in CHANNEL_IDS:
        assert cid in channel_ids, f"Missing channel: {cid}"
    assert len(channels) == len(CHANNEL_IDS)


# ---------------------------------------------------------------------------
# Source rows: source_attempt_ids and source_ledger
# ---------------------------------------------------------------------------


def test_source_rows_and_text_rendering(tmp_path, monkeypatch) -> None:
    """Source rows carry attempt_ids in ledger order and render source line."""
    from lee_llm_router.staffing.ledger import (
        ATTEMPTS_FILE_ENV_VAR,
        append_attempt,
        read_attempts,
    )

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    append_attempt(_record(route_id="route-x", attempt_id="aid-1"), path=ledger)
    append_attempt(_record(route_id="route-x", attempt_id="aid-2"), path=ledger)
    for i in range(1, 5):
        append_attempt(
            _record(route_id="route-y", attempt_id=f"aid-10{i}"), path=ledger
        )

    rec_no_id = _record(route_id="route-z")
    rec_no_id.pop("attempt_id", None)
    real_read = read_attempts(ledger)
    monkeypatch.setattr(
        "lee_llm_router.staffing.evidence_report.read_attempts",
        lambda p: real_read + [rec_no_id],
    )

    report = build_evidence_report("2026-09", catalog_dir=str(REPO_CONFIG_DIR))
    by_route = {c["route_id"]: c for c in report["classes"]}
    assert by_route["route-x"]["source_attempt_ids"] == ["aid-1", "aid-2"]
    assert by_route["route-y"]["source_attempt_ids"] == [
        f"aid-10{i}" for i in range(1, 5)
    ]
    assert by_route["route-z"]["source_attempt_ids"] == ["<no attempt_id>"]
    assert by_route["route-x"]["source_ledger"] == str(ledger)

    text = render_evidence_report(report)
    assert f"  source: 2 attempts from {ledger} (aid-1, aid-2)" in text
    assert (
        f"  source: 4 attempts from {ledger} (aid-101, aid-102, aid-103, +1 more)"
        in text
    )
    assert f"  source: 1 attempts from {ledger} (<no attempt_id>)" in text


# ---------------------------------------------------------------------------
# Route change not recommended reason strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("routes_data", "expected_reason"),
    [
        ([(1, 1.0, 0.05, 0.02)], "fewer than 2 routes with evidence"),
        (
            [(5, 1.0, 0.05, 0.02), (4, 1.0, 0.05, 0.02)],
            f"fewer than 2 comparison-eligible routes (n>={MINIMUM_SAMPLE_SIZE})",
        ),
        (
            [(5, 1.0, 0.05, 0.02), (5, 0.6, 0.05, 0.02)],
            "fewer than 2 routes at pass_rate>=0.8",
        ),
        (
            [(5, 1.0, 0.05, 0.02), (5, 1.0, None, None)],
            "fewer than 2 routes with a usable marginal cost",
        ),
        (
            [(5, 1.0, 0.05, 0.02), (5, 1.0, 0.10, 0.05)],
            "cheapest route already first",
        ),
    ],
)
def test_route_changes_not_recommended_reasons(
    tmp_path, monkeypatch, routes_data, expected_reason
) -> None:
    """Each not-recommended condition produces the exact required reason string."""
    from lee_llm_router.staffing.ledger import ATTEMPTS_FILE_ENV_VAR, append_attempt

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(ledger))
    ledger.write_text("", encoding="utf-8")

    CLASS = "impl/deterministic/none/s/python"
    for idx, (n, pr, clist, cmarg) in enumerate(routes_data, start=1):
        passes = round(n * pr)
        for i in range(n):
            append_attempt(
                _record(
                    route_id=f"route-{idx}",
                    class_key=CLASS,
                    cost_usd_list=clist,
                    cost_usd_marginal=cmarg,
                    verified_success=(i < passes),
                ),
                path=ledger,
            )

    report = build_evidence_report("2026-09", catalog_dir=str(REPO_CONFIG_DIR))
    assert report["route_changes"] == []
    match = [
        nr for nr in report["route_changes_not_recommended"] if nr["class_key"] == CLASS
    ]
    assert len(match) == 1
    assert match[0]["reason"] == expected_reason


def test_render_evidence_report_recommended_changes_both_states() -> None:
    """The Recommended route changes section is always printed in both states."""
    # State 1: empty recommendations -> prints 'none' with reason counts
    report_empty = {
        "report_for": "2026-09",
        "route_changes": [],
        "route_changes_not_recommended": [
            {"class_key": "class-c", "reason": "fewer than 2 routes with evidence"},
            {"class_key": "class-a", "reason": "fewer than 2 routes with evidence"},
            {"class_key": "class-b", "reason": "cheapest route already first"},
        ],
    }
    text_empty = render_evidence_report(report_empty)
    assert "Recommended route changes: none" in text_empty
    idx_ev = text_empty.index("2 classes: fewer than 2 routes with evidence")
    idx_ch = text_empty.index("1 classes: cheapest route already first")
    assert idx_ev < idx_ch

    # State 2: non-empty recommendations -> prints section with recommendation
    report_nonempty = {
        "report_for": "2026-09",
        "route_changes": [
            {
                "class_key": "impl/deterministic/none/s/python",
                "recommended_route_id": "route-cheaper",
                "evidence": "route-cheaper: n=5, pass_rate=1.0, mean_marginal=0.0200",
            }
        ],
    }
    text_nonempty = render_evidence_report(report_nonempty)
    assert "Recommended route changes:" in text_nonempty
    assert "Recommended route changes: none" not in text_nonempty
    assert "  recommended: route-cheaper" in text_nonempty


def test_reviewer_fallbacks_no_selection_reason_is_distinct() -> None:
    """A review record without a selection object is undecidable for its own
    reason, not the independence-without-order reason (Chief, P5-1c review).
    """
    from lee_llm_router.staffing.evidence_report import (
        _REVIEWER_FALLBACK_NO_SELECTION_REASON,
        _REVIEWER_FALLBACK_UNAVAILABLE_REASON,
        _reviewer_fallbacks,
    )

    no_selection = {"class_record": {"role": "review"}}
    result = _reviewer_fallbacks([no_selection])
    assert result == {
        "count": 0,
        "undecidable": 1,
        "unavailable_reason": _REVIEWER_FALLBACK_NO_SELECTION_REASON,
    }
    independence = {
        "class_record": {"role": "judge"},
        "selection": {
            "basis": "explain_cheapest_eligible",
            "excluded": [{"route_id": "r", "reason": "independence"}],
        },
    }
    both = _reviewer_fallbacks([no_selection, independence])
    assert both["undecidable"] == 2
    assert _REVIEWER_FALLBACK_NO_SELECTION_REASON in both["unavailable_reason"]
    assert _REVIEWER_FALLBACK_UNAVAILABLE_REASON in both["unavailable_reason"]
