"""Replay fixture integrity and pure next-action contract tests (P2-7).

The five replay facts below are copied verbatim from the authoritative
"Five replay facts" table in ``docs/staffing/phase2-contracts.md``
(D211 ruling 7). They are fixed trace-derived inputs; tests compare
``expected_action`` exactly and never reinterpret or invent facts.

These five fixed facts exercise ``platform_*``/``spec_rejected``/
``unaccounted_spend`` outcomes; none requires capability context, so no
capability-context field appears in the fixtures.

The ``next_action`` mapping under test is the pure mapping quoted in D211
ruling 6: ``platform_*`` -> ``retry_same_route_after_platform_repair``;
``spec_rejected`` -> ``return_to_planner``; first ``capability_rejected``
-> ``repair_same_route``, second -> ``escalate``; ``unaccounted_spend``
-> ``reconcile_then_retry``; unknown -> ``supervisor_judgment``. It never
dispatches. The implementation is owned by P2-6
(``lee_llm_router.staffing.next_action``); if that module is temporarily
absent, the contract test skips with an explicit dependency reason while
the fixture integrity tests still run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "replay"

# Authoritative copy of the D211 "Five replay facts" table
# (docs/staffing/phase2-contracts.md). Do not edit facts here; edit the
# contracts doc first, then mirror.
REPLAY_FACTS: tuple[dict[str, str], ...] = (
    {
        "case_id": "linux-sniffcopy-a24aa58959fe",
        "class_key": "impl/deterministic/infra-env/m/c",
        "oracle_type": "deterministic",
        "failure_class": "platform_timeout",
        "expected_action": "retry_same_route_after_platform_repair",
    },
    {
        "case_id": "linux-jsoncarve-35-cycle-loop",
        "class_key": "plan/judge/authority/l/yaml-config",
        "oracle_type": "judge",
        "failure_class": "spec_rejected",
        "expected_action": "return_to_planner",
    },
    {
        "case_id": "snowflake-elt-478250b5f6a1",
        "class_key": "impl/deterministic/ui-browser/m/mixed",
        "oracle_type": "deterministic",
        "failure_class": "platform_env",
        "expected_action": "retry_same_route_after_platform_repair",
    },
    {
        "case_id": "revenue-e3fbeb9f3c4c",
        "class_key": "impl/judge/authority/s/markdown",
        "oracle_type": "judge",
        "failure_class": "unaccounted_spend",
        "expected_action": "reconcile_then_retry",
    },
    {
        "case_id": "job-search-starburst-exit-143",
        "class_key": "impl/human/none/s/mixed",
        "oracle_type": "human",
        "failure_class": "platform_env",
        "expected_action": "retry_same_route_after_platform_repair",
    },
)

FIXTURE_KEYS = frozenset(
    {"case_id", "class_key", "oracle_type", "failure_class", "expected_action"}
)
ORACLE_TYPES = frozenset({"deterministic", "judge", "human"})
NEXT_ACTION_ACTIONS = frozenset(
    {
        "retry_same_route_after_platform_repair",
        "return_to_planner",
        "repair_same_route",
        "escalate",
        "reconcile_then_retry",
        "supervisor_judgment",
    }
)


def _load_fixture(case_id: str) -> dict[str, str]:
    path = FIXTURES_DIR / f"{case_id}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _param_id(fact: dict[str, str]) -> str:
    return fact["case_id"]


# ---------------------------------------------------------------------------
# Schema and fact integrity (no production dependency)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_fixture_exists_one_per_traced_case(fact: dict[str, str]) -> None:
    """Exactly one JSON fixture exists per traced case, named by case id."""
    path = FIXTURES_DIR / f"{fact['case_id']}.json"
    assert path.is_file(), f"missing replay fixture: {path}"


def test_no_extra_replay_fixtures() -> None:
    """The replay fixture directory holds exactly the five traced cases."""
    expected = {f"{fact['case_id']}.json" for fact in REPLAY_FACTS}
    actual = {p.name for p in FIXTURES_DIR.glob("*.json")}
    assert actual == expected


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_fixture_schema_exact_keys(fact: dict[str, str]) -> None:
    """Each fixture carries exactly the five contract fields, all strings."""
    data = _load_fixture(fact["case_id"])
    assert set(data) == FIXTURE_KEYS
    assert all(isinstance(value, str) and value for value in data.values())


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_fixture_facts_match_contracts_table(fact: dict[str, str]) -> None:
    """Fixture facts equal the authoritative table copy, field by field."""
    data = _load_fixture(fact["case_id"])
    assert data["case_id"] == fact["case_id"]
    assert data["class_key"] == fact["class_key"]
    assert data["oracle_type"] == fact["oracle_type"]
    assert data["failure_class"] == fact["failure_class"]
    assert data["expected_action"] == fact["expected_action"]


def test_case_ids_unique() -> None:
    """One fixture per traced case: case ids are unique across fixtures."""
    ids = [fact["case_id"] for fact in REPLAY_FACTS]
    assert len(ids) == len(set(ids)) == 5


# ---------------------------------------------------------------------------
# Canonical class keys (grammar from staffing.catalog.canonical_class_key)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_class_key_is_canonical_five_part(fact: dict[str, str]) -> None:
    """class_key is lowercase with five ``/``-separated segments.

    Grammar: ``role/oracle_type/domain_tags/size_band/language``; the
    domain-tags segment is the deduplicated tag set sorted ascending by
    codepoint and ``+``-joined, with the empty set rendered ``none``.
    """
    class_key = fact["class_key"]
    assert class_key == class_key.lower()
    segments = class_key.split("/")
    assert len(segments) == 5, f"{class_key!r} is not five-part"
    role, oracle_segment, tags_segment, size_band, language = segments
    assert role and oracle_segment and size_band and language
    assert all(part and part == part.lower() for part in segments)
    # Empty tag set renders as the literal ``none``, never an empty segment.
    if tags_segment == "none":
        pass
    else:
        tags = tags_segment.split("+")
        assert tags == sorted(set(tags)), f"tags in {class_key!r} not canonical"
        assert "" not in tags


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_class_key_oracle_segment_matches_oracle_type(fact: dict[str, str]) -> None:
    """The oracle segment of the key is the fixture's ``oracle_type``."""
    oracle_segment = fact["class_key"].split("/")[1]
    assert oracle_segment == fact["oracle_type"]


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_oracle_type_in_known_taxonomy(fact: dict[str, str]) -> None:
    """``oracle_type`` is one of deterministic | judge | human."""
    assert fact["oracle_type"] in ORACLE_TYPES


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_expected_action_in_next_action_vocabulary(fact: dict[str, str]) -> None:
    """``expected_action`` is a value the ruling-6 mapping can emit."""
    assert fact["expected_action"] in NEXT_ACTION_ACTIONS


# ---------------------------------------------------------------------------
# Pure next_action contract (D211 ruling 6) — owned by P2-6
# ---------------------------------------------------------------------------


try:  # P2-6 delivers this module concurrently; absence is a reportable state.
    from lee_llm_router.staffing.next_action import next_action
except ImportError:  # pragma: no cover - depends on P2-6 landing
    next_action = None


@pytest.mark.parametrize("fact", REPLAY_FACTS, ids=_param_id)
def test_expected_action_matches_pure_next_action(fact: dict[str, str]) -> None:
    """The pure mapping returns exactly the fixture's ``expected_action``.

    Capability context is intentionally absent: none of these five fixed
    facts is a ``capability_rejected`` outcome, so the call passes only
    ``failure_class``.
    """
    if next_action is None:
        pytest.skip(
            "dependency pending: lee_llm_router.staffing.next_action (P2-6) "
            "not importable yet; fixture integrity tests still assert the "
            "quoted ruling-6 mapping via expected_action"
        )
    result = next_action(failure_class=fact["failure_class"])
    assert result == fact["expected_action"]
