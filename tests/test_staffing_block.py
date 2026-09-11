"""Focused tests for the pure staffing-block renderers (P2-4)."""

from __future__ import annotations

import pytest

from lee_llm_router.staffing.block import (
    AUTHORITY_POLICY,
    MODE_AUTO,
    STAFFING_BLOCK_JSON_KEYS,
    build_auto_block,
    render_json,
    render_text,
)

# ---------------------------------------------------------------------------
# Fixtures: already-computed caller facts, exactly as accepted modules emit
# ---------------------------------------------------------------------------


def row(
    route,
    *,
    channel="openrouter",
    headroom=None,
    badge=None,
    eligible=True,
    reasons=(),
):
    """An eligibility row (the accepted EligibilityRow mapping shape)."""
    return {
        "route_id": route,
        "model": f"model-for-{route}",
        "channel": channel,
        "eligible": eligible,
        "reasons": list(reasons),
        "availability_health": "healthy",
        "availability_badge": badge,
        "availability_headroom": headroom,
        "pricing": None,
    }


def ladder_available(argmin="r1", escalation=("r1", "r2"), routes=("r1", "r2")):
    return {
        "rungs": [
            {"route": route, "E": 0.0123456 + index}
            for index, route in enumerate(routes)
        ],
        "argmin_start": argmin,
        "escalation": list(escalation),
        "expected_cost_status": "available",
        "unavailable_reasons": [],
    }


def ladder_unavailable(reasons, routes=("r1", "r2"), escalation=None):
    return {
        "rungs": [{"route": route, "E": "unavailable"} for route in routes],
        "argmin_start": routes[0],
        "escalation": list(escalation or routes),
        "expected_cost_status": "unavailable",
        "unavailable_reasons": list(reasons),
    }


def evidence(level="drop_size_band", n=5, k=3, low=False, prior_n=2, posterior_n=3):
    return {
        "level": level,
        "n": n,
        "k": k,
        "estimate": (k + 1) / (n + 2),
        "low_evidence": low,
        "prior_n": prior_n,
        "posterior_n": posterior_n,
    }


# ---------------------------------------------------------------------------
# Computable auto block
# ---------------------------------------------------------------------------


def test_computable_auto_block_golden_text():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[
            row("r1", headroom=0.42, badge="ON TRACK"),
            row("r2", headroom=0.9, badge="COLD"),
        ],
        evidence_by_route={"r1": evidence(), "r2": evidence()},
        proof_status_by_route={"r1": "proven", "r2": "proven"},
        ladder_result=ladder_available(),
        supervisor_route="r2",
        review_route="r2",
        review_eligible=True,
        review_independence_evaluated=True,
        human_escalation_cost_usd=5.00,
    )
    text = render_text(block)
    assert text == "\n".join(
        [
            "staff auto impl impl/deterministic/none/s/python (authority: policy)",
            "Supervisor: r2 (channel openrouter, headroom 0.9, badge COLD, "
            "eligible, proven)",
            "Workers:",
            "- r1 (channel openrouter, headroom 0.42, badge ON TRACK, "
            "eligible, proven)",
            "- r2 (channel openrouter, headroom 0.9, badge COLD, eligible, proven)",
            "Reason: accepted 3/5 comparable (drop_size_band), prior 2 benchmark, "
            "posterior 3 production, estimate 0.571429",
            "Expected cost: $0.0123 (argmin r1)",
            "Escalation: r1 -> r2 -> human ($5.0000 policy terminal, beyond the "
            "never-automatic boundary)",
            "Never-automatic (the boundary automatic escalation never crosses; "
            "bind only with --authorized-by lee): none",
            "Review: r2 (eligible, independent of r1)",
        ]
    )


def test_unavailable_auto_block_golden_text():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[
            row("r-unproven"),
            row("r-proven"),
        ],
        evidence_by_route={
            "r-proven": evidence(
                level="none", n=0, k=0, low=True, prior_n=0, posterior_n=0
            )
        },
        proof_status_by_route={"r-proven": "proven"},
        ladder_result=ladder_unavailable(
            ["demand or marginal pricing unavailable"],
            routes=("r-proven", "r-unproven"),
            escalation=("r-proven", "r-unproven"),
        ),
        human_escalation_cost_usd=5.00,
    )
    text = render_text(block)
    assert text == "\n".join(
        [
            "staff auto impl impl/deterministic/none/s/python (authority: policy)",
            "Supervisor: unavailable (no supervisor route supplied)",
            "Workers:",
            "- r-unproven (channel openrouter, headroom unknown, badge "
            "unknown, eligible, unproven)",
            "- r-proven (channel openrouter, headroom unknown, badge "
            "unknown, eligible, proven)",
            "Reason: accepted 0/0 comparable (none), prior 0 benchmark, "
            "posterior 0 production, low evidence",
            "Expected cost: unavailable (demand or marginal pricing unavailable)",
            "Escalation: r-proven -> r-unproven -> human ($5.0000 policy terminal, "
            "beyond the never-automatic boundary)",
            "Never-automatic (the boundary automatic escalation never crosses; "
            "bind only with --authorized-by lee): none",
            "Unproven (auto never selects an unproven route while a proven "
            "eligible one exists): r-unproven",
            "Review: unavailable (no independent review route supplied)",
        ]
    )


def test_no_comparable_evidence_never_shows_estimate():
    block = build_auto_block(
        role="review",
        class_key="review/judge/none/s/python",
        eligibility_rows=[row("r1")],
        evidence_by_route={
            "r1": evidence(level="none", n=0, k=0, low=True, prior_n=0, posterior_n=0)
        },
        proof_status_by_route={"r1": "proven"},
        ladder_result=ladder_available(argmin="r1", escalation=("r1",)),
    )
    payload = render_json(block)
    text = render_text(block)
    assert "estimate" not in payload["reason"]
    assert "estimate" not in text
    assert "accepted 0/0 comparable (none)" in text
    # The estimate is disclosed only with k/n and a comparable level.
    comparable = evidence()
    block2 = build_auto_block(
        role="review",
        class_key="review/judge/none/s/python",
        eligibility_rows=[row("r1")],
        evidence_by_route={"r1": comparable},
        ladder_result=ladder_available(),
    )
    shown = render_json(block2)
    assert shown["reason"]["estimate"] == comparable["estimate"]
    assert "estimate" in render_text(block2)


def test_reason_carries_prior_and_posterior_counts_in_text_and_json():
    """Finding 6 regression: the reason carries the benchmark-prior and
    production-posterior counts, and text and JSON stay in parity."""
    for prior_n, posterior_n in [(5, 0), (0, 5), (2, 3), (0, 0)]:
        block = build_auto_block(
            role="impl",
            class_key="impl/deterministic/none/s/python",
            eligibility_rows=[row("r1")],
            evidence_by_route={
                "r1": evidence(prior_n=prior_n, posterior_n=posterior_n)
            },
            ladder_result=ladder_available(),
        )
        payload = render_json(block)
        text = render_text(block)

        assert payload["reason"]["prior_n"] == prior_n
        assert payload["reason"]["posterior_n"] == posterior_n
        assert f"prior {prior_n} benchmark" in text
        assert f"posterior {posterior_n} production" in text
        # The mixed split is rendered with both counts even at the extremes:
        # an all-prior or all-posterior join never hides the other bucket.
        assert (
            f"accepted 3/5 comparable (drop_size_band), prior {prior_n} "
            f"benchmark, posterior {posterior_n} production" in text
        )


def test_reason_counts_follow_the_evidence_join_summary():
    join_summary = {
        "level": "drop_size_band",
        "n": 5,
        "k": 3,
        "estimate": 4 / 7,
        "low_evidence": False,
        "prior_n": 4,
        "posterior_n": 1,
    }
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r1")],
        evidence_by_route={"r1": join_summary},
        ladder_result=ladder_available(),
    )
    payload = render_json(block)
    assert payload["reason"]["prior_n"] == 4
    assert payload["reason"]["posterior_n"] == 1
    assert (
        "Reason: accepted 3/5 comparable (drop_size_band), prior 4 benchmark, "
        "posterior 1 production, estimate 0.571429" in render_text(block)
    )


# ---------------------------------------------------------------------------
# Optional supervisor
# ---------------------------------------------------------------------------


def test_optional_supervisor_absent_and_present():
    base = dict(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r1"), row("sup")],
        evidence_by_route={"r1": evidence()},
        ladder_result=ladder_available(),
    )
    absent = build_auto_block(**base)
    assert "Supervisor: unavailable (no supervisor route supplied)" in render_text(
        absent
    )
    assert render_json(absent)["supervisor"] is None

    present = build_auto_block(
        **base,
        supervisor_route="sup",
        proof_status_by_route={"sup": "proven"},
    )
    assert (
        "Supervisor: sup (channel openrouter, headroom unknown, badge unknown, "
        "eligible, proven)" in render_text(present)
    )
    assert render_json(present)["supervisor"]["route_id"] == "sup"


def test_supervisor_route_must_be_a_supplied_row():
    with pytest.raises(ValueError, match="not-a-row"):
        build_auto_block(
            role="impl",
            class_key="impl/deterministic/none/s/python",
            eligibility_rows=[row("r1")],
            supervisor_route="not-a-row",
        )


# ---------------------------------------------------------------------------
# Independent reviewer selection / exclusion
# ---------------------------------------------------------------------------


def test_independent_reviewer_selected_with_author_route():
    block = build_auto_block(
        role="review",
        class_key="review/judge/none/s/python",
        eligibility_rows=[
            row("author"),
            row("reviewer", reasons=(), eligible=True),
        ],
        evidence_by_route={"author": evidence()},
        proof_status_by_route={"author": "proven", "reviewer": "proven"},
        ladder_result=ladder_available(argmin="author", escalation=("author",)),
        review_route="reviewer",
        review_independence_evaluated=True,
    )
    text = render_text(block)
    assert "Review: reviewer (eligible, independent of author)" in text
    payload = render_json(block)
    assert payload["review"] == {
        "route_id": "reviewer",
        "eligible": True,
        "reason": None,
        "independence_evaluated": True,
        "independence_reference": "author",
    }


def test_independent_reviewer_excluded_reports_exact_reason():
    block = build_auto_block(
        role="review",
        class_key="review/judge/none/s/python",
        eligibility_rows=[
            row("author"),
            row("same-family", eligible=False, reasons=("independence",)),
        ],
        evidence_by_route={"author": evidence()},
        ladder_result=ladder_available(argmin="author", escalation=("author",)),
        review_route="same-family",
        review_independence_evaluated=True,
    )
    text = render_text(block)
    assert "Review: same-family (excluded (independence), not independent)" in text
    payload = render_json(block)
    assert payload["review"]["eligible"] is False
    assert payload["review"]["reason"] == "independence"


def test_independence_not_evaluated_disclosure():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r1"), row("r2")],
        ladder_result=ladder_available(),
        review_route="r2",
    )
    assert "independence not evaluated (no --author-route)" in render_text(block)
    assert render_json(block)["review"]["independence_evaluated"] is False
    assert render_json(block)["review"]["independence_reference"] is None


def test_explicit_author_reference_disclosed_with_selected_excluded():
    """An explicit author reference is disclosed verbatim, and the reviewed
    worker is disclosed as excluded too — the block never claims independence
    from the selected worker when the reference was a different route."""
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("worker"), row("reviewer")],
        ladder_result=ladder_available(argmin="worker", escalation=("worker",)),
        selected_route="worker",
        review_route="reviewer",
        review_eligible=True,
        review_independence_evaluated=True,
        review_independence_reference="author",
    )
    text = render_text(block)
    assert (
        "Review: reviewer (eligible, independent of author author; "
        "selected worker also excluded)"
    ) in text
    assert render_json(block)["review"]["independence_reference"] == "author"


# ---------------------------------------------------------------------------
# Headroom and badge facts
# ---------------------------------------------------------------------------


def test_headroom_and_badges_render_and_parity():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[
            row("h1", headroom=0.25, badge="ON TRACK"),
            row("h2", headroom=None, badge=None),
            row(
                "h3",
                headroom=0.0,
                badge="COLD",
                eligible=False,
                reasons=("channel exhausted",),
            ),
        ],
        ladder_result=ladder_available(argmin="h1", escalation=("h1",)),
    )
    text = render_text(block)
    assert (
        "- h1 (channel openrouter, headroom 0.25, badge ON TRACK, eligible, unproven)"
        in text
    )
    assert (
        "- h2 (channel openrouter, headroom unknown, badge unknown, eligible, unproven)"
        in text
    )
    assert (
        "- h3 (channel openrouter, headroom 0, badge COLD, excluded: channel "
        "exhausted, unproven)" in text
    )
    payload = render_json(block)
    headrooms = {
        worker["route_id"]: worker["headroom"] for worker in payload["workers"]
    }
    assert headrooms == {"h1": 0.25, "h2": None, "h3": 0.0}


# ---------------------------------------------------------------------------
# Escalation, never-automatic boundary, and selection
# ---------------------------------------------------------------------------


def test_escalation_stops_at_never_automatic_boundary():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[
            row("r1"),
            row("na", reasons=("never_automatic",)),
        ],
        ladder_result=ladder_available(argmin="r1", escalation=("r1",)),
        human_escalation_cost_usd=5.00,
    )
    text = render_text(block)
    assert (
        "Escalation: r1 -> human ($5.0000 policy terminal, "
        "beyond the never-automatic boundary)" in text
    )
    assert (
        "Never-automatic (the boundary automatic escalation never crosses; "
        "bind only with --authorized-by lee): na" in text
    )
    payload = render_json(block)
    assert payload["never_automatic"] == ["na"]
    assert payload["escalation"] == ["r1"]


def test_selection_prefers_proven_eligible_routes_in_input_order():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("a-unproven"), row("b-proven"), row("c-proven")],
        proof_status_by_route={"b-proven": "proven", "c-proven": "proven"},
        ladder_result=ladder_unavailable(
            ["evidence unavailable"],
            routes=("b-proven", "c-proven", "a-unproven"),
            escalation=("b-proven", "c-proven", "a-unproven"),
        ),
    )
    assert block.selected_route == "b-proven"
    assert render_json(block)["selected_route"] == "b-proven"


def test_ineligible_explicit_or_ladder_selection_is_never_used():
    rows = [row("bad", eligible=False, reasons=("channel exhausted",)), row("good")]
    with pytest.raises(ValueError, match="not an eligible"):
        build_auto_block(
            role="impl",
            class_key="impl/deterministic/none/s/python",
            eligibility_rows=rows,
            selected_route="bad",
        )
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=rows,
        ladder_result=ladder_unavailable(["evidence unavailable"], routes=("bad",)),
    )
    assert block.selected_route == "good"


def test_nonfinite_or_missing_available_cost_becomes_unavailable():
    for value in (float("nan"), float("inf"), None):
        ladder = ladder_available(argmin="r1", escalation=("r1",), routes=("r1",))
        ladder["rungs"][0]["E"] = value
        block = build_auto_block(
            role="impl",
            class_key="impl/deterministic/none/s/python",
            eligibility_rows=[row("r1", headroom=float("nan"))],
            ladder_result=ladder,
        )
        payload = render_json(block)
        assert payload["workers"][0]["headroom"] is None
        assert payload["expected_cost"]["status"] == "unavailable"
        assert payload["expected_cost"]["reasons"] == [
            "argmin expected cost unavailable"
        ]


# ---------------------------------------------------------------------------
# Proof-first override: reconciliation to the actual selected route
# ---------------------------------------------------------------------------


def test_proof_first_override_reconciles_cost_and_escalation_suffix():
    """Proof-first policy may select a rung other than the pure argmin; the
    expected cost and escalation suffix must belong to the selected route,
    with the rejected argmin still disclosed as the ladder argmin."""
    ladder = {
        "rungs": [
            {"route": "r-cheap", "E": 0.005},
            {"route": "r-proven", "E": 0.0123456},
            {"route": "r-last", "E": 0.02},
        ],
        "argmin_start": "r-cheap",
        "escalation": ["r-cheap", "r-proven", "r-last"],
        "expected_cost_status": "available",
        "unavailable_reasons": [],
    }
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r-cheap"), row("r-proven"), row("r-last")],
        proof_status_by_route={"r-proven": "proven"},
        ladder_result=ladder,
        selected_route="r-proven",
    )
    payload = render_json(block)
    assert payload["selected_route"] == "r-proven"
    assert payload["expected_cost"] == {
        "status": "available",
        "usd": 0.0123456,
        "argmin_route": "r-cheap",
    }
    assert payload["escalation"] == ["r-proven", "r-last"]
    assert (
        "Expected cost: $0.0123 (selected r-proven; ladder argmin r-cheap)"
        in render_text(block)
    )


def test_selected_rung_without_usable_cost_fails_closed():
    ladder = {
        "rungs": [
            {"route": "r-cheap", "E": 0.005},
            {"route": "r-proven", "E": float("nan")},
        ],
        "argmin_start": "r-cheap",
        "escalation": ["r-cheap", "r-proven"],
        "expected_cost_status": "available",
        "unavailable_reasons": [],
    }
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r-cheap"), row("r-proven")],
        proof_status_by_route={"r-proven": "proven"},
        ladder_result=ladder,
        selected_route="r-proven",
    )
    payload = render_json(block)
    assert payload["expected_cost"]["status"] == "unavailable"
    assert payload["expected_cost"]["usd"] is None
    assert payload["expected_cost"]["reasons"] == ["selected expected cost unavailable"]
    assert "Expected cost: unavailable (selected expected cost unavailable)" in (
        render_text(block)
    )


def test_reason_unavailable_when_no_evidence_join():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r1")],
        ladder_result=ladder_available(),
    )
    assert "Reason: unavailable (no evidence join for r1)" in render_text(block)
    assert render_json(block)["reason"] is None


def test_empty_eligibility_rows_make_workers_explicit():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[],
        ladder_result=ladder_available(argmin="r1"),
    )
    text = render_text(block)
    assert "Workers: unavailable (no eligibility rows supplied)" in text
    assert "Reason: unavailable (no eligible route)" in text
    assert block.selected_route is None


# ---------------------------------------------------------------------------
# JSON/text parity
# ---------------------------------------------------------------------------


def test_json_carries_exactly_the_text_facts():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[
            row("r1", headroom=0.42, badge="HOT"),
            row("r2", headroom=0.5, badge="COLD"),
        ],
        evidence_by_route={"r1": evidence(), "r2": evidence()},
        proof_status_by_route={"r1": "proven", "r2": "proven"},
        ladder_result=ladder_available(),
        supervisor_route="r2",
        review_route="r2",
        review_independence_evaluated=True,
        human_escalation_cost_usd=5.00,
    )
    payload = render_json(block)
    text = render_text(block)

    assert list(payload.keys()) == list(STAFFING_BLOCK_JSON_KEYS)
    assert payload["mode"] == MODE_AUTO
    assert payload["authority"] == AUTHORITY_POLICY
    assert payload["role"] == "impl"
    assert payload["class_key"] == "impl/deterministic/none/s/python"

    # Every scalar fact of the JSON appears verbatim in the text.
    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)
        else:
            yield value

    for fact in walk(payload):
        if fact is None:
            continue
        if isinstance(fact, str):
            if fact in ("available", "unavailable"):
                continue
            assert fact in text, fact
        elif isinstance(fact, bool):
            continue
        elif isinstance(fact, int):
            assert str(fact) in text, fact
        elif isinstance(fact, float):
            assert f"{fact:g}" in text or f"{fact:.4f}" in text, fact

    # Structural facts match the block itself.
    assert payload["supervisor"]["route_id"] == "r2"
    assert [worker["route_id"] for worker in payload["workers"]] == ["r1", "r2"]
    assert payload["selected_route"] == "r1"
    assert payload["reason"]["k"] == 3 and payload["reason"]["n"] == 5
    assert payload["expected_cost"]["status"] == "available"
    assert payload["expected_cost"]["usd"] == 0.0123456
    assert payload["expected_cost"]["argmin_route"] == "r1"
    assert payload["escalation"] == ["r1", "r2"]


def test_unavailable_json_facts_match_text():
    block = build_auto_block(
        role="impl",
        class_key="impl/deterministic/none/s/python",
        eligibility_rows=[row("r1")],
        ladder_result=ladder_unavailable(["evidence unavailable"]),
        human_escalation_cost_usd=5.00,
    )
    payload = render_json(block)
    text = render_text(block)
    assert payload["expected_cost"]["status"] == "unavailable"
    assert payload["expected_cost"]["usd"] is None
    assert payload["expected_cost"]["reasons"] == ["evidence unavailable"]
    assert "Expected cost: unavailable (evidence unavailable)" in text
    assert payload["reason"] is None
    assert "Reason: unavailable (no evidence join for r1)" in text
