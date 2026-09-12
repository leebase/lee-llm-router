"""Focused P2-5a staffing-service tests.

All catalog and availability inputs are local fixtures.  Attempt evidence and
bind ledgers use injected mappings and pytest scratch paths; no provider is
prompted and no real router state is touched.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lee_llm_router.availability import parse_availability
from lee_llm_router.events import EVENT_FIELDS, read_events
from lee_llm_router.staffing.catalog import load_staffing_catalog
from lee_llm_router.staffing.eligibility import resolve_route_family
from lee_llm_router.staffing.staff import (
    BIND_AUTHORIZED_BY,
    StaffServiceError,
    render_staff_json,
    render_staff_text,
    staff,
)

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
AT = "2026-09-15"
CLASS_KEY = "impl/deterministic/none/s/python"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

SOL_LOW = "codex-gpt-5-6-sol-low-openai-sub"
SOL_HIGH = "codex-gpt-5-6-sol-high-openai-sub"
FABLE = "claude-claude-fable-5-1-high-anthropic-sub"
GEMINI_PRO = "agy-gemini-3-1-pro-gemini-sub"
GLM_OPENROUTER = "pi-z-ai-glm-5-3-flash-openrouter"
MIMO = "opencode-opencode-go-mimo-v2-5-opencode-go"


def _snapshot(*, openai_status: str = "ON TRACK", openai_pct: int = 80):
    return parse_availability(
        {
            "host": "staff-test",
            "observed_at": "2026-09-09T11:59:00+00:00",
            "subscriptions": [
                {
                    "provider": "OpenAI/Codex",
                    "bucket": "Weekly limit",
                    "status": openai_status,
                    "remaining_pct": openai_pct,
                },
                {
                    "provider": "Anthropic/Claude",
                    "bucket": "Current session",
                    "status": "ON TRACK",
                    "remaining_pct": 80,
                },
                {
                    "provider": "Gemini/agy",
                    "bucket": "Gemini models",
                    "status": "ON TRACK",
                    "remaining_pct": 80,
                },
                {
                    "provider": "OpenCode/Go",
                    "bucket": "Weekly",
                    "status": "ON TRACK",
                    "remaining_pct": 80,
                },
            ],
        },
        now=NOW,
    )


@pytest.fixture(scope="module")
def catalog():
    return load_staffing_catalog(REPO_CONFIG_DIR)


@pytest.fixture(scope="module")
def availability():
    return _snapshot()


def _auto(catalog, availability, **kwargs):
    arguments = {
        "mode": "auto",
        "role": "impl",
        "class_key": CLASS_KEY,
        "at_date": AT,
        "rollup": {"groups": []},
    }
    arguments.update(kwargs)
    return staff(catalog, availability, **arguments)


def _router_record(
    route_id: str,
    *,
    class_key: str = CLASS_KEY,
    usage_basis: str = "observed",
    verified_success: bool = False,
):
    """The placements consumed by proof and evidence; no provider data."""
    return {
        "record_kind": "router_run",
        "router_event": {"route_id": route_id},
        "class_record": {"class_key": class_key},
        "usage": {"basis": usage_basis},
        "verified_success": verified_success,
    }


def _worker(payload: dict, route_id: str) -> dict:
    return next(row for row in payload["workers"] if row["route_id"] == route_id)


# ---------------------------------------------------------------------------
# Available-arithmetic composition helpers (D211 rulings 1–4 all satisfied)
# ---------------------------------------------------------------------------


def _unproven_record(route_id: str, class_key: str = CLASS_KEY) -> dict:
    """Evidence without proof: usage unknown, no verified success."""
    return {
        "record_kind": "router_run",
        "router_event": {"route_id": route_id},
        "class_record": {"class_key": class_key},
        "usage": {"basis": "unknown"},
    }


def _supervisor_records(n: int = 5, class_key: str = CLASS_KEY) -> list[dict]:
    """Rows attesting one supervisor route with known marginal costs."""
    return [
        {
            "record_kind": "router_run",
            "router_event": {"route_id": GLM_OPENROUTER},
            "class_record": {"class_key": class_key},
            "usage": {"basis": "unknown"},
            "supervisor_route": GLM_OPENROUTER,
            "cost": {"usd_marginal": 0.01},
        }
        for _ in range(n)
    ]


def _known_demand_rollup(catalog, class_key: str = CLASS_KEY) -> dict:
    """A rollup group with usable token medians for every catalog route."""
    return {
        "groups": [
            {
                "route_id": route.route_id,
                "class_key": class_key,
                "token_medians": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "cached_input_tokens": None,
                    "reasoning_tokens": None,
                    "total_tokens": 1100,
                },
                "wall_clock_median_ms": 5000,
            }
            for route in catalog.routes.routes
        ]
    }


def _available_arithmetic(catalog, availability, **kwargs):
    """An auto composition where the ladder arithmetic is fully available."""
    records = _supervisor_records() + [
        _unproven_record(route.route_id) for route in catalog.routes.routes
    ]
    # Observed usage makes the route proven for the proof boundary, while the
    # unsuccessful outcome keeps its ladder probability low enough that the
    # pure arithmetic argmin remains a different, unproven route.
    records.append(_router_record(SOL_HIGH))
    return _auto(
        catalog,
        availability,
        rollup=_known_demand_rollup(catalog),
        attempt_records=records,
        **kwargs,
    )


def test_auto_is_proof_first_when_expected_cost_is_unavailable(
    catalog, availability
) -> None:
    baseline = _auto(catalog, availability)
    assert baseline.payload["selected_route"] != SOL_HIGH

    result = _auto(
        catalog,
        availability,
        attempt_records=[_router_record(SOL_HIGH)],
    )

    assert result.mode == "auto"
    assert result.payload["authority"] == "policy"
    assert result.payload["expected_cost"]["status"] == "unavailable"
    assert result.payload["selected_route"] == SOL_HIGH
    assert _worker(result.payload, SOL_HIGH)["proof_status"] == "proven"
    assert any(
        worker["eligible"] and worker["proof_status"] == "unproven"
        for worker in result.payload["workers"]
    )
    assert "auto never selects an unproven route" in result.text


def test_auto_exposes_every_phase_zero_exclusion(catalog) -> None:
    openrouter_locked = replace(
        catalog,
        channels=replace(
            catalog.channels,
            channels=tuple(
                (
                    replace(channel, harness_lock=("omp",))
                    if channel.channel_id == "openrouter"
                    else channel
                )
                for channel in catalog.channels.channels
            ),
        ),
        terms=replace(
            catalog.terms,
            terms=tuple(
                term for term in catalog.terms.terms if term.channel_ref != "openrouter"
            ),
        ),
    )
    result = _auto(
        openrouter_locked,
        _snapshot(openai_status="HOT", openai_pct=0),
    )

    assert len(result.payload["workers"]) == len(catalog.routes.routes)
    assert "channel exhausted" in _worker(result.payload, SOL_LOW)["reasons"]
    assert "never_automatic" in _worker(result.payload, FABLE)["reasons"]
    assert any(
        reason.startswith("role_scoped: coding denied")
        for reason in _worker(result.payload, GEMINI_PRO)["reasons"]
    )
    openrouter_reasons = _worker(result.payload, GLM_OPENROUTER)["reasons"]
    assert "harness 'pi' not in channel 'openrouter' harness_lock" in openrouter_reasons
    assert any("terms unavailable" in reason for reason in openrouter_reasons)
    mimo_reasons = _worker(result.payload, MIMO)["reasons"]
    assert "route status unpriced" in mimo_reasons
    assert "pricing unavailable" in mimo_reasons
    assert FABLE in result.payload["never_automatic"]
    assert FABLE not in result.payload["escalation"]


def test_auto_honors_the_requested_terms_date(catalog, availability) -> None:
    before = _auto(catalog, availability, at_date="2026-09-08")
    effective = _auto(catalog, availability, at_date="2026-09-09")

    assert before.at_date == "2026-09-08"
    assert before.payload["selected_route"] is None
    assert all(
        any("terms unavailable at 2026-09-08" in reason for reason in row["reasons"])
        for row in before.payload["workers"]
    )
    assert effective.payload["selected_route"] is not None
    assert any(row["eligible"] for row in effective.payload["workers"])


def test_auto_unknown_evidence_and_demand_are_explicit(catalog, availability) -> None:
    no_evidence = _auto(catalog, availability)
    assert no_evidence.payload["reason"] == {
        "level": "none",
        "n": 0,
        "k": 0,
        "prior_n": 0,
        "posterior_n": 0,
        "low_evidence": True,
    }
    assert "evidence unavailable" in no_evidence.payload["expected_cost"]["reasons"]

    known_evidence = _auto(
        catalog,
        availability,
        attempt_records=[_router_record(SOL_HIGH)],
    )
    assert known_evidence.payload["reason"]["level"] == "exact"
    assert known_evidence.payload["reason"]["n"] == 1
    assert "estimate" in known_evidence.payload["reason"]
    assert "demand or marginal pricing unavailable" in (
        known_evidence.payload["expected_cost"]["reasons"]
    )


def test_auto_computes_an_independent_review_route(catalog, availability) -> None:
    result = _auto(
        catalog,
        availability,
        attempt_records=[_router_record(SOL_HIGH)],
    )
    review = result.payload["review"]

    assert result.payload["selected_route"] == SOL_HIGH
    assert review["route_id"] is not None
    assert review["eligible"] is True
    assert review["independence_evaluated"] is True
    assert review["independence_reference"] == SOL_HIGH
    by_id = {route.route_id: route for route in catalog.routes.routes}
    selected_family, _ = resolve_route_family(by_id[result.payload["selected_route"]])
    review_family, _ = resolve_route_family(by_id[review["route_id"]])
    assert review_family != selected_family
    assert f"independent of {SOL_HIGH}" in result.text


def test_auto_proof_first_override_reconciles_cost_and_escalation(
    catalog, availability, monkeypatch
) -> None:
    """Finding 3 regression: with arithmetic available, proof-first may
    override the pure argmin; the block's expected cost and escalation
    suffix must then belong to the actual selected route."""
    staff_module = importlib.import_module("lee_llm_router.staffing.staff")
    ladder_order = []

    def available_ladder(rungs, **_kwargs):
        routes = [rung.route for rung in rungs]
        argmin = next(route for route in routes if route != SOL_HIGH)
        ordered = [argmin, SOL_HIGH] + [
            route for route in routes if route not in (argmin, SOL_HIGH)
        ]
        ladder_order.extend(ordered)
        return {
            "rungs": [
                {"route": route, "E": 0.01 + index / 100}
                for index, route in enumerate(ordered)
            ],
            "argmin_start": argmin,
            "escalation": ordered,
            "expected_cost_status": "available",
            "unavailable_reasons": [],
        }

    monkeypatch.setattr(staff_module, "calculate_ladder", available_ladder)
    result = _auto(
        catalog,
        availability,
        attempt_records=[_router_record(SOL_HIGH)],
    )
    payload = result.payload

    assert payload["expected_cost"]["status"] == "available"
    argmin = payload["expected_cost"]["argmin_route"]
    selected = payload["selected_route"]
    assert selected != argmin
    assert _worker(payload, argmin)["proof_status"] == "unproven"
    assert _worker(payload, selected)["proof_status"] == "proven"

    # The published figure is the selected route's own expected cost, and the
    # escalation chain is the eligible-rung suffix starting at the selected
    # route — not the rejected argmin's suffix.
    assert payload["escalation"] == ladder_order[ladder_order.index(selected) :]
    assert payload["escalation"][0] == selected
    assert argmin not in payload["escalation"][: payload["escalation"].index(selected)]
    assert payload["expected_cost"]["usd"] > 0
    assert f"(selected {selected}; ladder argmin {argmin})" in result.text
    assert "auto never selects an unproven route" in result.text


def test_auto_explicit_author_review_is_truthful_and_excludes_selected(
    catalog, availability
) -> None:
    """Finding 2 regression: with an explicit author reference, the review
    disclosure names that reference (not the selected worker), and the
    reviewed worker's route and family are excluded even though the naive
    cheapest reviewer would have been the selected worker itself."""
    by_id = {route.route_id: route for route in catalog.routes.routes}
    result = _auto(
        catalog,
        availability,
        author_route_id=GLM_OPENROUTER,
        attempt_records=[_router_record(SOL_HIGH)],
    )
    review = result.payload["review"]

    assert result.payload["selected_route"] == SOL_HIGH
    assert review["independence_evaluated"] is True
    assert review["independence_reference"] == GLM_OPENROUTER
    assert review["route_id"] is not None
    assert review["route_id"] != SOL_HIGH
    selected_family, _ = resolve_route_family(by_id[SOL_HIGH])
    author_family, _ = resolve_route_family(by_id[GLM_OPENROUTER])
    review_family, _ = resolve_route_family(by_id[review["route_id"]])
    assert review_family not in (selected_family, author_family)
    assert f"independent of author {GLM_OPENROUTER}" in result.text
    assert f"selected {SOL_HIGH} also excluded" in result.text


def test_auto_explicit_author_review_never_picks_the_selected_worker(
    catalog, availability
) -> None:
    """Fail closed: the naive marginal-price reviewer for this composition is
    the selected worker itself; the selected route and its family are always
    excluded from the review choice too."""
    deepseek = "opencode-opencode-go-deepseek-v4-flash-opencode-go"
    result = _auto(
        catalog,
        availability,
        author_route_id=GLM_OPENROUTER,
        attempt_records=[_router_record(deepseek)],
    )
    review = result.payload["review"]

    assert result.payload["selected_route"] == deepseek
    assert review["independence_reference"] == GLM_OPENROUTER
    assert review["route_id"] != deepseek
    by_id = {route.route_id: route for route in catalog.routes.routes}
    selected_family, _ = resolve_route_family(by_id[deepseek])
    review_family, _ = resolve_route_family(by_id[review["route_id"]])
    assert review_family != selected_family


def test_auto_unknown_author_route_fails_closed(catalog, availability) -> None:
    with pytest.raises(StaffServiceError) as excinfo:
        _auto(catalog, availability, author_route_id="not-in-catalog")
    assert "author_route_id" in str(excinfo.value)


def test_auto_renderers_are_stable_and_equivalent(catalog, availability) -> None:
    first = _auto(catalog, availability)
    second = _auto(catalog, availability)

    assert first == second
    assert render_staff_json(first) == first.payload
    assert render_staff_text(first) == first.text
    assert json.dumps(first.payload, separators=(",", ":")) == json.dumps(
        second.payload, separators=(",", ":")
    )


@pytest.mark.parametrize("crew_id", ["sol-low-glm-pi", "luna-sol"])
def test_saved_interactive_crews_render_exact_catalog_routes(
    catalog, availability, crew_id: str
) -> None:
    crew = next(entry for entry in catalog.crews.crews if entry.crew_id == crew_id)
    result = staff(catalog, availability, mode="crew", crew_id=crew_id)

    assert result.payload["crew_id"] == crew.crew_id
    assert result.payload["kind"] == crew.kind == "interactive"
    assert result.payload["authority"] == crew.authority
    assert result.payload["governed_ref"] == crew.governed_ref
    assert result.payload["supervisor_route"] == crew.supervisor_route
    assert result.payload["worker_routes"] == {
        role: list(routes) for role, routes in crew.worker_routes.items()
    }
    assert result.payload["reviewer_route"] == crew.reviewer_route
    assert result.payload["escalation_ladder"] == list(crew.escalation_ladder)
    assert result.payload["evidence_ref"] == crew.evidence_ref
    assert result.event is None


def test_bind_ordinary_route_appends_exactly_one_event(
    catalog, availability, tmp_path: Path
) -> None:
    path = tmp_path / "events" / "bind.jsonl"
    result = staff(
        catalog,
        availability,
        mode="bind",
        role="impl",
        class_key=CLASS_KEY,
        at_date=AT,
        bind_route=SOL_LOW,
        authorized_by="chief",
        reason="Lee requested the ordinary route",
        events_path=path,
        now="2026-09-15T12:00:00+00:00",
    )

    events = read_events(path)
    assert len(events) == 1
    assert events[0] == result.event == result.payload["event"]
    assert tuple(events[0]) == EVENT_FIELDS
    assert events[0]["mode"] == "bind"
    assert events[0]["route_id"] == SOL_LOW
    assert events[0]["authorized_by"] == "chief"
    assert result.payload["never_automatic"] is False


def test_bind_never_automatic_refuses_non_lee_without_writing(
    catalog, availability, tmp_path: Path
) -> None:
    path = tmp_path / "refused.jsonl"
    with pytest.raises(StaffServiceError) as excinfo:
        staff(
            catalog,
            availability,
            mode="bind",
            role="impl",
            class_key=CLASS_KEY,
            at_date=AT,
            bind_route=FABLE,
            authorized_by="Lee",
            reason="wrongly capitalized authority",
            events_path=path,
        )

    assert excinfo.value.kind == "never_automatic"
    assert not path.exists()


def test_bind_never_automatic_accepts_exact_lee_once(
    catalog, availability, tmp_path: Path
) -> None:
    path = tmp_path / "accepted.jsonl"
    result = staff(
        catalog,
        availability,
        mode="bind",
        role="impl",
        class_key=CLASS_KEY,
        at_date=AT,
        bind_route=FABLE,
        authorized_by=BIND_AUTHORIZED_BY,
        reason="explicit Lee exception",
        events_path=path,
        now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert result.payload["never_automatic"] is True
    assert result.event["authorized_by"] == "lee"
    assert len(path.read_text().splitlines()) == 1
    assert len(read_events(path)) == 1


@pytest.mark.parametrize(
    ("kwargs", "kind"),
    [
        ({"mode": "automatic"}, "invalid_mode"),
        ({"mode": 1}, "invalid_mode"),
        ({"mode": "auto", "at_date": "2026-02-30"}, "invalid_date"),
        ({"mode": "auto", "class_key": "plan/judge/none/s/python"}, "invalid_class"),
        ({"mode": "crew", "crew_id": "missing"}, "unknown_crew"),
        ({"mode": "crew", "crew_id": "auto"}, "reserved_auto_crew"),
        (
            {"mode": "crew", "crew_id": "luna-sol", "reason": "unused"},
            "invalid_arguments",
        ),
        ({"mode": "bind", "bind_route": "missing"}, "unknown_route"),
        ({"mode": "bind", "bind_route": SOL_LOW, "reason": None}, "invalid_arguments"),
        (
            {"mode": "bind", "bind_route": SOL_LOW, "snapshot_stale": "no"},
            "invalid_arguments",
        ),
    ],
)
def test_invalid_modes_routes_and_arguments_fail_closed(
    catalog, availability, kwargs: dict, kind: str
) -> None:
    arguments = {
        "role": "impl",
        "class_key": CLASS_KEY,
        "at_date": AT,
        "authorized_by": "chief",
        "reason": "test",
    }
    arguments.update(kwargs)
    if arguments["mode"] == "auto":
        arguments.pop("authorized_by")
        arguments.pop("reason")
    elif arguments["mode"] == "crew":
        arguments.pop("authorized_by")
        if kwargs.get("reason") is None:
            arguments.pop("reason")
    with pytest.raises(StaffServiceError) as excinfo:
        staff(catalog, availability, **arguments)
    assert excinfo.value.kind == kind


@pytest.mark.parametrize(
    "override",
    [
        {"bind_route": "not-in-catalog"},
        {"bind_route": FABLE, "authorized_by": "chief"},
        {"bind_route": SOL_LOW, "reason": ""},
        {"bind_route": SOL_LOW, "at_date": "15-09-2026"},
        {"bind_route": SOL_LOW, "attempt_records": []},
    ],
)
def test_bind_validation_failures_never_create_a_ledger(
    catalog, availability, tmp_path: Path, override: dict
) -> None:
    path = tmp_path / "must-not-exist.jsonl"
    arguments = {
        "mode": "bind",
        "role": "impl",
        "class_key": CLASS_KEY,
        "at_date": AT,
        "bind_route": SOL_LOW,
        "authorized_by": "chief",
        "reason": "valid reason",
        "events_path": path,
    }
    arguments.update(override)

    with pytest.raises(StaffServiceError):
        staff(catalog, availability, **arguments)
    assert not path.exists()


# ---------------------------------------------------------------------------
# D216 subscription-channel reserve: auto ladder skips reserved channels;
# bind refuses without --authorized-by lee and succeeds with it.
# ---------------------------------------------------------------------------

_SONNET_HIGH = "claude-claude-sonnet-5-high-anthropic-sub"
_FABLE = "claude-claude-fable-5-1-high-anthropic-sub"


def _snapshot_reserved(openai_pct: int = 7, anthropic_pct: int = 8):
    """Both subscription channels below the 0.10 default reserve."""
    return parse_availability(
        {
            "host": "staff-test",
            "observed_at": "2026-09-09T11:59:00+00:00",
            "subscriptions": [
                {
                    "provider": "OpenAI/Codex",
                    "bucket": "Weekly limit",
                    "status": "ON TRACK",
                    "remaining_pct": openai_pct,
                },
                {
                    "provider": "Anthropic/Claude",
                    "bucket": "Current session",
                    "status": "ON TRACK",
                    "remaining_pct": anthropic_pct,
                },
                {
                    "provider": "Gemini/agy",
                    "bucket": "Gemini models",
                    "status": "ON TRACK",
                    "remaining_pct": 8,
                },
                {
                    "provider": "OpenCode/Go",
                    "bucket": "Weekly",
                    "status": "ON TRACK",
                    "remaining_pct": 8,
                },
            ],
        },
        now=NOW,
    )


@pytest.fixture
def reserved_availability():
    return _snapshot_reserved(openai_pct=7, anthropic_pct=8)


def test_auto_ladder_skips_reserved_channel_to_cheapest_metered(
    catalog, reserved_availability
) -> None:
    """With both subscriptions reserved, the cheapest metered route is
    selected (z-ai glm-5.3-flash on openrouter)."""
    result = _auto(catalog, reserved_availability)
    payload = result.payload
    selected = payload["selected_route"]
    # The cheapest metered route is GLM on openrouter.
    assert (
        selected == GLM_OPENROUTER
    ), f"expected cheapest metered route {GLM_OPENROUTER}, got {selected}"
    for worker in payload["workers"]:
        route_id = worker["route_id"]
        if worker["channel"] in (
            "openai-sub",
            "anthropic-sub",
            "gemini-sub",
            "opencode-go",
        ):
            assert (
                any(r.startswith("reserve:") for r in worker["reasons"])
                or worker["eligible"] is False
            ), f"subscription route {route_id} should be excluded by reserve"
    assert selected == GLM_OPENROUTER
    assert f"- {GLM_OPENROUTER} " in result.text and "eligible" in result.text


def test_bind_reserved_channel_refuses_non_lee_without_writing(
    catalog, reserved_availability, tmp_path: Path
) -> None:
    """A reserved channel's route binds only with --authorized-by lee."""
    path = tmp_path / "reserved-refused.jsonl"
    with pytest.raises(StaffServiceError) as excinfo:
        staff(
            catalog,
            reserved_availability,
            mode="bind",
            role="impl",
            class_key=CLASS_KEY,
            at_date=AT,
            bind_route=SOL_LOW,
            authorized_by="chief",
            reason="bypass reserve",
            events_path=path,
        )

    assert excinfo.value.kind == "reserve"
    assert not path.exists()


def test_bind_reserved_channel_accepts_exact_lee_once(
    catalog, reserved_availability, tmp_path: Path
) -> None:
    """A reserved channel's route binds successfully with --authorized-by lee."""
    path = tmp_path / "reserved-accepted.jsonl"
    result = staff(
        catalog,
        reserved_availability,
        mode="bind",
        role="impl",
        class_key=CLASS_KEY,
        at_date=AT,
        bind_route=SOL_LOW,
        authorized_by=BIND_AUTHORIZED_BY,
        reason="Lee bypasses the subscription reserve",
        events_path=path,
        now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert result.payload["reserved"] is True
    assert result.payload["never_automatic"] is False
    assert result.event["authorized_by"] == "lee"
    assert len(path.read_text().splitlines()) == 1
    assert len(read_events(path)) == 1


def test_bind_reserved_lane_shows_reserve_in_text(
    catalog, reserved_availability, tmp_path: Path
) -> None:
    """The bind text output includes the reserve line."""
    path = tmp_path / "reserved-text.jsonl"
    result = staff(
        catalog,
        reserved_availability,
        mode="bind",
        role="impl",
        class_key=CLASS_KEY,
        at_date=AT,
        bind_route=SOL_LOW,
        authorized_by=BIND_AUTHORIZED_BY,
        reason="Lee bypasses reserve",
        events_path=path,
        now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert "Reserve: yes" in result.text
    assert "bound by lee" in result.text
