"""Tests for the staffing catalog loader/validator (shape boundary only).

Fixtures here are handwritten scratch data; they do not depend on the
not-yet-authored live catalog YAML. No provider prompts are involved.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from lee_llm_router.doctor import main
from lee_llm_router.providers.base import FailureType
from lee_llm_router.staffing import (
    DOCUMENT_ORDER,
    BadgeMultipliers,
    Channel,
    ChannelsCatalog,
    ClassesCatalog,
    Crew,
    CrewsCatalog,
    DenyPredicate,
    PolicyCatalog,
    Route,
    RoutesCatalog,
    StaffingCatalogError,
    TermsCatalog,
    canonical_class_key,
    load_staffing_catalog,
    load_staffing_document,
    validate_class_block,
)
from lee_llm_router.staffing.catalog import (
    DEFAULT_STAGE_WORKER_DIR,
    HARNESS_BINARY_ENV_VAR_PREFIX,
    HARNESS_BINARY_ENV_VAR_SUFFIX,
    HARNESS_BINARY_TOKENS,
    STAGE_WORKER_DIR_ENV_VAR,
    STAGE_WORKER_DIR_TOKEN,
    ChannelInstance,
    CrewSupervisor,
    harness_binary_env_var,
    resolve_dispatch_template,
    resolve_harness_binaries,
    resolve_harness_binary,
    resolve_stage_worker_dir,
)

# ---------------------------------------------------------------------------
# Handwritten valid fixture documents (minimal but schema-valid)
# ---------------------------------------------------------------------------


def routes_doc() -> dict:
    return {
        "routes": [
            {
                "route_id": "route-openrouter-high",
                "model": "acme/large-1",
                "effort": "high",
                "harness": "cli",
                "channel": "chan-sub-a",
                "dispatch_template": "dispatch {prompt}",
                "usage_capture": "native_json",
                "status": "active",
            },
            {
                "route_id": "route-local-fallback",
                "model": "local/small-1",
                "effort": None,
                "harness": "worker",
                "channel": "chan-local",
                "dispatch_template": "dispatch {prompt}",
                "usage_capture": "none",
                "status": "active",
            },
        ]
    }


def channels_doc() -> dict:
    return {
        "channels": [
            {
                "channel_id": "chan-sub-a",
                "kind": "subscription",
                "fee_usd_month": [
                    {"effective_from": "2026-01-01", "value": 200},
                    {"effective_from": "2026-06-01", "value": "unknown"},
                ],
                "windows": ["weekly", "rolling-5h"],
                "harness_lock": ["cli"],
                "replacement_price_ref": "pricing/openrouter-20260909.json",
            },
            {
                "channel_id": "chan-local",
                "kind": "local",
                "fee_usd_month": [{"effective_from": "2026-01-01", "value": 0}],
                "windows": [],
                "harness_lock": [],
                "replacement_price_ref": "pricing/local.md",
            },
        ]
    }


def terms_doc() -> dict:
    return {
        "terms": [
            {
                "channel_ref": "chan-sub-a",
                "kind": "subscription",
                "effective_from": "2026-01-01",
                "fee_usd_month": 200,
                "source": "scratch fixture terms",
                "decision_price_ref": "pricing/decision-a",
                "reporting_price_ref": "pricing/reporting-a",
            }
        ],
        "badge_multipliers": {
            "COLD": 0.8,
            "USE IT": 1.0,
            "ON TRACK": 1.0,
            "HOT": 1.2,
            "TOO FAST": 1.5,
            "NO DATA": 1.0,
        },
    }


def policy_doc() -> dict:
    return {
        "never_automatic": [
            {
                "model_ref": "acme/large-1",
                "effort": "max",
                "decision": "Never used without an explicit non-automatic decision.",
                "source": "scratch fixture policy",
            }
        ],
        "role_scoped": [
            {
                "model_ref": "acme/large-1",
                "allowed_role_classes": ["role-class-a"],
                "denied_role_classes": ["role-class-b"],
                "decision": "Model-to-roles scoping only.",
                "source": "scratch fixture policy",
            }
        ],
        "role_class": [
            {
                "role_ref": "impl",
                "role_class": "role-class-a",
                "decision": "Governance classification only.",
                "source": "scratch fixture policy",
            }
        ],
        "role_floors": [
            {
                "role_ref": "review",
                "floor": "floor-alpha",
                "effective_from": "2026-01-01",
                "decision": "Archived tier-policy floor.",
                "source": "scratch fixture policy",
            }
        ],
        "reviewer_independence": [
            {
                "reviewer_ref": "reviewer-1",
                "fresh_eyes_mode": "fresh-eyes-preferred",
                "decision": "Fresh eyes preferred.",
                "source": "scratch fixture policy",
            }
        ],
        "spend_caps": [
            {
                "cap": 50,
                "unit": "usd-month",
                "scope": "global",
                "decision": "Hard cap.",
                "source": "scratch fixture policy",
            }
        ],
        "crew_ordering_rule": {
            "decision": (
                "Within a role's array, order by marginal price at "
                "authoring time with prepaid-first as the tie-break; a "
                "human may pin otherwise with a stated reason."
            ),
            "source": "scratch fixture crew_ordering_rule D215",
        },
        "reserve_fraction": {
            "default": 0.10,
            "overrides": [
                {"channel_id": "anthropic-sub", "reserve_fraction": 0.10},
                {"channel_id": "gemini-sub", "reserve_fraction": 0.10},
            ],
        },
        "human_escalation_cost_usd": 5.00,
    }


def classes_doc() -> dict:
    return {
        "taxonomy_version": "fixture-taxonomy-1",
        "key_grammar": "role/oracle_type/domain_tags/size_band/language",
        "canonical_encoding": {
            "segment_separator": "/",
            "tag_separator": "+",
            "tag_order": "ascending codepoint",
            "tag_dedup": True,
            "empty_tags_segment": "none",
            "notes": "Component fields are authoritative; key equality is loader work.",
        },
        "value_sets": {
            "role": ["impl", "plan", "review", "judge", "prose"],
            "oracle_type": ["deterministic", "judge", "human", "none"],
            "domain_tags": [
                "persistence",
                "concurrency",
                "security",
                "authority",
                "ui-browser",
                "data-schema",
                "infra-env",
            ],
            "size_band": ["xs", "s", "m", "l"],
            "language": [
                "python",
                "typescript",
                "shell",
                "c",
                "go",
                "sql",
                "yaml-config",
                "markdown",
                "mixed",
            ],
        },
        "cheap_trial_rule": {
            "rule_name": "dont_cheap_trial",
            "default": "allow_cheap_trial",
            "deny_conditions": [
                {
                    "when": {
                        "field": "oracle_type",
                        "op": "in",
                        "values": ["human", "none"],
                    },
                    "reason": "oracle_human_or_none",
                },
                {
                    "when": {
                        "all_of": [
                            {"field": "size_band", "op": "in", "values": ["m", "l"]},
                            {
                                "field": "domain_tags",
                                "op": "intersects",
                                "values": [
                                    "persistence",
                                    "concurrency",
                                    "security",
                                    "authority",
                                ],
                            },
                        ]
                    },
                    "reason": "risk_tag_on_m_or_l",
                },
            ],
            "override": {
                "kind": "supervisor_override_is_attempt_evidence",
                "direction": "allow_cheap_trial",
                "description": (
                    "Override is recorded as attempt evidence in either direction."
                ),
            },
        },
    }


def crews_doc() -> dict:
    """Shared two-crew fixture: one named interactive + the auto placeholder.

    Governed-crew coverage lives in ``crews_doc_with_governed()`` so the
    shared document count stays at two (tests/test_doctor.py depends on it).
    """
    return {
        "crews": [
            {
                "crew_id": "night-crew",
                "kind": "interactive",
                "supervisor_route": "route-openrouter-high",
                "worker_routes": {
                    "impl": ["route-openrouter-high", "route-local-fallback"],
                    "plan": ["route-local-fallback"],
                },
                "reviewer_route": "route-openrouter-high",
                "escalation_ladder": ["route-openrouter-high", "route-local-fallback"],
                "authority": "chief",
                "evidence_ref": "scratch fixture evidence",
            },
            {
                "crew_id": "auto",
                "kind": "interactive",
                "computed": True,
                "authority": "policy",
                "evidence_ref": "computed placeholder",
            },
        ]
    }


def crews_doc_with_governed() -> dict:
    """Test-local crews doc: shared fixture plus one governed record at [1].

    Never used for the shared ``crews_doc()`` count; governs nothing.
    """
    doc = crews_doc()
    doc["crews"].insert(
        1,
        {
            "crew_id": "orch-crew",
            "kind": "governed",
            "source": "auto-orch/crews.yaml",
            "crew_name": "auto-orch-default",
            "supervisor": {"kind": "engine", "owner": "auto-orch"},
            "worker_routes": {
                "primary": ["route-openrouter-high"],
                "reviewer": ["route-local-fallback"],
                "judge": ["route-local-fallback"],
            },
            "escalation": "not-recorded",
            "authority": "lee",
            "evidence_ref": "governed fixture evidence",
        },
    )
    return doc


_DOC_BUILDERS = {
    "routes": routes_doc,
    "channels": channels_doc,
    "terms": terms_doc,
    "policy": policy_doc,
    "classes": classes_doc,
    "crews": crews_doc,
}


def write_docs(directory: Path, docs: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, payload in docs.items():
        (directory / f"{name}.yaml").write_text(
            yaml.safe_dump(payload), encoding="utf-8"
        )


_SEGMENTS = re.compile(r"([^\.\[\]]+)|(?:\[(\d+)\])")


def _set_nested(doc: dict, path: str, value: object) -> None:
    """Set ``value`` at a JSON-path suffix like ``routes[0]`` inside ``doc``."""
    matches = list(_SEGMENTS.finditer(path.lstrip("$")))
    node: object = doc
    for match in matches[:-1]:
        node = node[match.group(1)] if match.group(1) else node[int(match.group(2))]
    last = matches[-1]
    key = last.group(1) if last.group(1) else int(last.group(2))
    holder = node
    holder[key] = value  # type: ignore[index]


@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    return tmp_path


# ---------------------------------------------------------------------------
# Valid documents -> typed objects
# ---------------------------------------------------------------------------


def test_load_full_catalog_returns_typed_objects(catalog_dir: Path) -> None:
    catalog = load_staffing_catalog(catalog_dir)
    assert isinstance(catalog.routes, RoutesCatalog)
    assert isinstance(catalog.channels, ChannelsCatalog)
    assert isinstance(catalog.terms, TermsCatalog)
    assert isinstance(catalog.policy, PolicyCatalog)
    assert isinstance(catalog.classes, ClassesCatalog)
    assert isinstance(catalog.crews, CrewsCatalog)


def test_routes_document_types(catalog_dir: Path) -> None:
    routes = load_staffing_catalog(catalog_dir).routes
    assert isinstance(routes.routes, tuple)
    first = routes.routes[0]
    assert isinstance(first, Route)
    assert first.route_id == "route-openrouter-high"
    assert first.effort == "high"
    assert first.usage_capture == "native_json"
    assert first.status == "active"
    assert first.status_reason is None
    assert routes.routes[1].effort is None
    assert routes.routes[1].status == "active"
    assert routes.routes[1].status_reason is None


def test_channels_document_types(catalog_dir: Path) -> None:
    channels = load_staffing_catalog(catalog_dir).channels
    assert isinstance(channels.channels, tuple)
    first = channels.channels[0]
    assert isinstance(first, Channel)
    assert first.kind == "subscription"
    assert first.fee_usd_month[0].effective_from == "2026-01-01"
    assert first.fee_usd_month[0].value == 200
    assert first.fee_usd_month[1].value == "unknown"
    assert first.windows == ("weekly", "rolling-5h")
    assert first.instances == ()
    assert first.effective_instances() == (
        ChannelInstance(
            instance_id="chan-sub-a",
            credential_ref="chan-sub-a",
            enabled=True,
        ),
    )
    assert channels.channels[1].windows == ()


def test_explicit_channel_instances_load_as_typed_values(tmp_path: Path) -> None:
    doc = channels_doc()
    doc["channels"][0]["instances"] = [
        {
            "instance_id": "a",
            "credential_ref": "chan-sub-a/a",
            "enabled": True,
        },
        {
            "instance_id": "b",
            "credential_ref": "chan-sub-a/b",
            "enabled": False,
        },
    ]
    (tmp_path / "channels.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    channels = load_staffing_document("channels", tmp_path / "channels.yaml")
    first = channels.channels[0]
    expected = (
        ChannelInstance(instance_id="a", credential_ref="chan-sub-a/a", enabled=True),
        ChannelInstance(instance_id="b", credential_ref="chan-sub-a/b", enabled=False),
    )
    assert first.instances == expected
    assert all(isinstance(instance, ChannelInstance) for instance in first.instances)
    assert first.effective_instances() == expected


def test_committed_catalog_keeps_implicit_channel_instances() -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config" / "staffing"
    catalog = load_staffing_catalog(config_dir)
    for channel in catalog.channels.channels:
        if channel.instances == ():
            assert channel.effective_instances() == (
                ChannelInstance(
                    instance_id=channel.channel_id,
                    credential_ref=channel.channel_id,
                    enabled=True,
                ),
            )


SOL_HIGH_ROUTE = "codex-gpt-5-6-sol-high-openai-sub"
SOL_XHIGH_ROUTE = "codex-gpt-5-6-sol-xhigh-openai-sub"


def test_committed_catalog_loads_sol_xhigh_route() -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config" / "staffing"
    routes = load_staffing_catalog(config_dir).routes.routes
    route = next(route for route in routes if route.route_id == SOL_XHIGH_ROUTE)

    assert route.model == "gpt-5.6-sol"
    assert route.effort == "xhigh"
    assert route.harness == "codex"
    assert route.channel == "openai-sub"
    assert "CODEX_STAGE_WORKER_REASONING_EFFORT=xhigh" in route.dispatch_template
    assert route.usage_capture == "none"
    assert route.status == "active"


def test_route_show_prints_sol_xhigh_route(capsys: pytest.CaptureFixture[str]) -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config" / "staffing"
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "route",
                "show",
                SOL_XHIGH_ROUTE,
                "--catalog-dir",
                str(config_dir),
            ]
        )

    captured = capsys.readouterr()
    assert excinfo.value.code == 0
    assert SOL_XHIGH_ROUTE in captured.out
    assert "effort: xhigh" in captured.out
    assert "CODEX_STAGE_WORKER_REASONING_EFFORT=xhigh" in captured.out
    assert captured.err == ""


def test_catalog_explain_sol_xhigh_matches_sol_high_eligibility(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config" / "staffing"
    availability_path = tmp_path / "availability.json"
    availability_path.write_text(
        json.dumps(
            {
                "host": "s7b-test",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "subscriptions": [
                    {
                        "provider": "OpenAI/Codex",
                        "bucket": "Weekly limit",
                        "status": "ON TRACK",
                        "remaining_pct": 80,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "catalog",
                "explain",
                "--role",
                "impl",
                "--class",
                "impl/deterministic/none/s/go",
                "--at",
                "2026-09-15",
                "--availability-file",
                str(availability_path),
                "--catalog-dir",
                str(config_dir),
                "--json",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    by_route = {row["route_id"]: row for row in payload["routes"]}
    assert excinfo.value.code == 0
    assert by_route[SOL_XHIGH_ROUTE]["eligible"] is True
    assert (
        by_route[SOL_XHIGH_ROUTE]["eligible"],
        by_route[SOL_XHIGH_ROUTE]["reasons"],
    ) == (
        by_route[SOL_HIGH_ROUTE]["eligible"],
        by_route[SOL_HIGH_ROUTE]["reasons"],
    )
    assert captured.err == ""


def test_terms_document_types(catalog_dir: Path) -> None:
    terms = load_staffing_catalog(catalog_dir).terms
    entry = terms.terms[0]
    assert entry.channel_ref == "chan-sub-a"
    assert entry.fee_usd_month == 200
    assert isinstance(terms.badge_multipliers, BadgeMultipliers)
    assert terms.badge_multipliers.HOT == 1.2
    assert terms.badge_multipliers.TOO_FAST == 1.5


def test_policy_document_types(catalog_dir: Path) -> None:
    policy = load_staffing_catalog(catalog_dir).policy
    assert isinstance(policy, PolicyCatalog)
    assert policy.never_automatic[0].effort == "max"
    assert policy.role_scoped[0].allowed_role_classes == ("role-class-a",)
    assert policy.role_class[0].role_class == "role-class-a"
    assert policy.role_floors[0].effective_from == "2026-01-01"
    assert policy.reviewer_independence[0].fresh_eyes_mode == "fresh-eyes-preferred"
    assert policy.spend_caps[0].cap == 50
    assert policy.human_escalation_cost_usd == 5.00


def test_classes_document_types(catalog_dir: Path) -> None:
    classes = load_staffing_catalog(catalog_dir).classes
    assert isinstance(classes, ClassesCatalog)
    assert classes.key_grammar == "role/oracle_type/domain_tags/size_band/language"
    assert classes.value_sets.role == ("impl", "plan", "review", "judge", "prose")
    assert classes.value_sets.domain_tags[0] == "persistence"
    assert classes.canonical_encoding.empty_tags_segment == "none"
    rule = classes.cheap_trial_rule
    assert rule.rule_name == "dont_cheap_trial"
    assert rule.default == "allow_cheap_trial"
    assert rule.deny_reasons == ("oracle_human_or_none", "risk_tag_on_m_or_l")
    assert rule.deny_predicates[0] == (
        (DenyPredicate(field="oracle_type", op="in", values=("human", "none"))),
    )
    assert rule.deny_predicates[1] == (
        DenyPredicate("size_band", "in", ("m", "l")),
        DenyPredicate(
            "domain_tags",
            "intersects",
            ("persistence", "concurrency", "security", "authority"),
        ),
    )
    assert rule.override_kind == "supervisor_override_is_attempt_evidence"
    assert rule.override_direction == "allow_cheap_trial"


def test_crews_document_types(catalog_dir: Path) -> None:
    crews = load_staffing_catalog(catalog_dir).crews
    assert isinstance(crews.crews, tuple)
    assert all(isinstance(crew, Crew) for crew in crews.crews)


def test_interactive_crew_fields_preserved(catalog_dir: Path) -> None:
    crews = load_staffing_catalog(catalog_dir).crews
    crew = crews.crews[0]
    assert isinstance(crew, Crew)
    assert crew.crew_id == "night-crew"
    assert crew.kind == "interactive"
    assert crew.authority == "chief"
    assert crew.evidence_ref == "scratch fixture evidence"
    assert crew.supervisor_route == "route-openrouter-high"
    assert crew.worker_routes == {
        "impl": ("route-openrouter-high", "route-local-fallback"),
        "plan": ("route-local-fallback",),
    }
    assert crew.reviewer_route == "route-openrouter-high"
    assert crew.escalation_ladder == (
        "route-openrouter-high",
        "route-local-fallback",
    )
    assert crew.source is None
    assert crew.crew_name is None
    assert crew.supervisor is None
    assert crew.escalation is None
    assert crew.computed is None


def test_governed_crew_fields_preserved(tmp_path: Path) -> None:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text(
        yaml.safe_dump(crews_doc_with_governed()), encoding="utf-8"
    )
    crews = load_staffing_catalog(tmp_path).crews
    crew = crews.crews[1]
    assert isinstance(crew, Crew)
    assert crew.crew_id == "orch-crew"
    assert crew.kind == "governed"
    assert crew.authority == "lee"
    assert crew.evidence_ref == "governed fixture evidence"
    assert crew.source == "auto-orch/crews.yaml"
    assert crew.crew_name == "auto-orch-default"
    assert crew.supervisor == CrewSupervisor(kind="engine", owner="auto-orch")
    assert crew.worker_routes == {
        "primary": ("route-openrouter-high",),
        "reviewer": ("route-local-fallback",),
        "judge": ("route-local-fallback",),
    }
    assert crew.escalation == "not-recorded"
    assert crew.supervisor_route is None
    assert crew.reviewer_route is None
    assert crew.escalation_ladder is None
    assert crew.computed is None


def test_auto_placeholder_crew_fields_preserved(catalog_dir: Path) -> None:
    crews = load_staffing_catalog(catalog_dir).crews
    crew = crews.crews[1]
    assert isinstance(crew, Crew)
    assert crew.crew_id == "auto"
    assert crew.kind == "interactive"
    assert crew.authority == "policy"
    assert crew.evidence_ref == "computed placeholder"
    assert crew.computed is True
    assert crew.supervisor_route is None
    assert crew.worker_routes is None
    assert crew.reviewer_route is None
    assert crew.escalation_ladder is None
    assert crew.source is None
    assert crew.crew_name is None
    assert crew.supervisor is None
    assert crew.escalation is None


def test_crew_typed_objects_are_frozen(tmp_path: Path) -> None:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text(
        yaml.safe_dump(crews_doc_with_governed()), encoding="utf-8"
    )
    crews = load_staffing_catalog(tmp_path).crews
    crew = crews.crews[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        crew.crew_id = "x"  # type: ignore[misc]
    supervisor = crews.crews[1].supervisor
    assert supervisor is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        supervisor.owner = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Route lifecycle status (typed loading + schema-conditional status_reason)
# ---------------------------------------------------------------------------


def test_unpriced_route_with_reason_preserved(tmp_path: Path) -> None:
    doc = routes_doc()
    doc["routes"][0]["status"] = "unpriced"
    doc["routes"][0]["status_reason"] = "awaiting current fee quote"
    write_docs(tmp_path, {"routes": doc})
    routes = load_staffing_document("routes", tmp_path / "routes.yaml")
    first = routes.routes[0]
    assert first.status == "unpriced"
    assert first.status_reason == "awaiting current fee quote"


def test_unpriced_route_without_reason_rejected_by_schema(tmp_path: Path) -> None:
    doc = routes_doc()
    doc["routes"][0]["status"] = "unpriced"
    write_docs(tmp_path, {"routes": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("routes", tmp_path / "routes.yaml")
    assert excinfo.value.document == "routes"
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION
    assert "status_reason" in str(excinfo.value)
    assert excinfo.value.path == "$.routes[0]"


def test_active_route_with_reason_accepted_and_preserved(tmp_path: Path) -> None:
    doc = routes_doc()
    doc["routes"][0]["status"] = "active"
    doc["routes"][0]["status_reason"] = "kept for audit trail"
    write_docs(tmp_path, {"routes": doc})
    routes = load_staffing_document("routes", tmp_path / "routes.yaml")
    first = routes.routes[0]
    assert first.status == "active"
    assert first.status_reason == "kept for audit trail"


# ---------------------------------------------------------------------------
# Route.family (Chief round 15): optional independence comparison label only
# ---------------------------------------------------------------------------


def test_route_family_absent_defaults_to_none(catalog_dir: Path) -> None:
    """Committed-style routes without family load with family None."""
    routes = load_staffing_catalog(catalog_dir).routes
    assert all(route.family is None for route in routes.routes)


def test_route_family_preserved_through_catalog_load(tmp_path: Path) -> None:
    """A schema-valid route with a nonempty family loads and preserves it."""
    doc = routes_doc()
    doc["routes"][0]["family"] = "scratch-family"
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "routes.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    routes = load_staffing_catalog(tmp_path).routes
    assert routes.routes[0].family == "scratch-family"
    assert routes.routes[1].family is None


def test_route_family_blank_rejected_by_schema(tmp_path: Path) -> None:
    doc = routes_doc()
    doc["routes"][0]["family"] = ""
    write_docs(tmp_path, {"routes": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("routes", tmp_path / "routes.yaml")
    assert excinfo.value.document == "routes"
    assert excinfo.value.path == "$.routes[0].family"
    assert "family" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_route_family_whitespace_only_rejected_by_schema(tmp_path: Path) -> None:
    doc = routes_doc()
    doc["routes"][0]["family"] = "   "
    write_docs(tmp_path, {"routes": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("routes", tmp_path / "routes.yaml")
    assert excinfo.value.path == "$.routes[0].family"
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


# ---------------------------------------------------------------------------
# Unknown-field invalid cases (one per document) with field/path assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DOCUMENT_ORDER))
def test_unknown_top_level_field_rejected(tmp_path: Path, name: str) -> None:
    doc = _DOC_BUILDERS[name]()
    doc["bogus_extra"] = 1
    write_docs(tmp_path, {name: doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document(name, tmp_path / f"{name}.yaml")
    assert excinfo.value.document == name
    assert excinfo.value.path == "$.bogus_extra"
    assert "bogus_extra" in str(excinfo.value)
    assert name in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


@pytest.mark.parametrize(
    ("name", "nested_path"),
    [
        ("routes", "$.routes[0]"),
        ("channels", "$.channels[0]"),
        ("terms", "$.terms[0]"),
        ("policy", "$.never_automatic[0]"),
        ("classes", "$.canonical_encoding"),
        ("crews", "$.crews[0]"),
    ],
)
def test_unknown_nested_field_rejected(
    tmp_path: Path, name: str, nested_path: str
) -> None:
    doc = _DOC_BUILDERS[name]()
    _set_nested(doc, nested_path, {"bogus_nested": "x"})
    write_docs(tmp_path, {name: doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document(name, tmp_path / f"{name}.yaml")
    assert excinfo.value.document == name
    assert excinfo.value.path == f"{nested_path}.bogus_nested"
    assert "bogus_nested" in str(excinfo.value)


@pytest.mark.parametrize("missing", ["instance_id", "credential_ref", "enabled"])
def test_channel_instance_missing_required_field_rejected(
    tmp_path: Path, missing: str
) -> None:
    doc = channels_doc()
    instance = {
        "instance_id": "a",
        "credential_ref": "chan-sub-a/a",
        "enabled": True,
    }
    del instance[missing]
    doc["channels"][0]["instances"] = [instance]
    (tmp_path / "channels.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("channels", tmp_path / "channels.yaml")
    assert excinfo.value.document == "channels"
    assert missing in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_channel_instance_unknown_field_rejected(tmp_path: Path) -> None:
    doc = channels_doc()
    doc["channels"][0]["instances"] = [
        {
            "instance_id": "a",
            "credential_ref": "chan-sub-a/a",
            "enabled": True,
            "unexpected": "nope",
        }
    ]
    (tmp_path / "channels.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("channels", tmp_path / "channels.yaml")
    assert excinfo.value.document == "channels"
    assert excinfo.value.path == "$.channels[0].instances[0].unexpected"
    assert "unexpected" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_channel_instance_duplicate_ids_rejected_by_loader(tmp_path: Path) -> None:
    doc = channels_doc()
    doc["channels"][0]["instances"] = [
        {
            "instance_id": "a",
            "credential_ref": "chan-sub-a/a",
            "enabled": True,
        },
        {
            "instance_id": "a",
            "credential_ref": "chan-sub-a/other",
            "enabled": True,
        },
    ]
    (tmp_path / "channels.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")

    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("channels", tmp_path / "channels.yaml")
    assert excinfo.value.path == "$.channels[0].instances[1].instance_id"
    assert "duplicate" in str(excinfo.value)


def test_governed_crew_with_supervisor_route_rejected_by_schema(
    tmp_path: Path,
) -> None:
    doc = crews_doc_with_governed()
    doc["crews"][1]["supervisor_route"] = "route-openrouter-high"
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "crews"
    assert "False schema does not allow" in str(excinfo.value)
    assert excinfo.value.path == "$.crews[1]"
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_interactive_named_crew_missing_supervisor_route_rejected_by_schema(
    tmp_path: Path,
) -> None:
    doc = crews_doc()
    del doc["crews"][0]["supervisor_route"]
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "crews"
    assert "supervisor_route" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_auto_placeholder_with_worker_routes_rejected_by_schema(
    tmp_path: Path,
) -> None:
    doc = crews_doc_with_governed()
    doc["crews"][2]["worker_routes"] = {"impl": ["route-local-fallback"]}
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "crews"
    assert "False schema does not allow" in str(excinfo.value)
    assert excinfo.value.path == "$.crews[2]"
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_unknown_field_inside_crew_worker_routes_rejected(tmp_path: Path) -> None:
    doc = crews_doc()
    doc["crews"][0]["worker_routes"]["impl"] = ["route-a", {"nope": 1}]
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "crews"
    assert "crews[0].worker_routes.impl[1]" in excinfo.value.path


# ---------------------------------------------------------------------------
# Other stable failure modes
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# human_escalation_cost_usd (D211): shape is schema-fixed (finite nonnegative
# number); the value itself is the Chief's placeholder and Lee may change it.
# ---------------------------------------------------------------------------


def test_human_escalation_cost_placeholder_value_loads(catalog_dir: Path) -> None:
    """The committed placeholder (5.00) loads into the frozen catalog."""
    policy = load_staffing_catalog(catalog_dir).policy
    assert isinstance(policy, PolicyCatalog)
    assert policy.human_escalation_cost_usd == 5.0
    assert isinstance(policy.human_escalation_cost_usd, float)


@pytest.mark.parametrize("value", [0, 0.0, 1, 12.5, 250, 1000000])
def test_human_escalation_cost_accepts_other_nonnegative_finite_values(
    tmp_path: Path, value: object
) -> None:
    """Any finite nonnegative number is schema-valid (Lee may change it)."""
    doc = policy_doc()
    doc["human_escalation_cost_usd"] = value
    write_docs(tmp_path, {"policy": doc})
    policy = load_staffing_document("policy", tmp_path / "policy.yaml")
    assert policy.human_escalation_cost_usd == value


@pytest.mark.parametrize("value", [-1, -0.01, -5.0, -1e9])
def test_human_escalation_cost_negative_rejected_by_schema(
    tmp_path: Path, value: object
) -> None:
    doc = policy_doc()
    doc["human_escalation_cost_usd"] = value
    write_docs(tmp_path, {"policy": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("policy", tmp_path / "policy.yaml")
    assert excinfo.value.document == "policy"
    assert excinfo.value.path == "$.human_escalation_cost_usd"
    assert "minimum" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


@pytest.mark.parametrize("value", ["5", "five", True, False, None, [5], {"usd": 5}])
def test_human_escalation_cost_non_number_rejected_by_schema(
    tmp_path: Path, value: object
) -> None:
    doc = policy_doc()
    doc["human_escalation_cost_usd"] = value
    write_docs(tmp_path, {"policy": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("policy", tmp_path / "policy.yaml")
    assert excinfo.value.document == "policy"
    assert excinfo.value.path == "$.human_escalation_cost_usd"
    assert "is not of type 'number'" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


@pytest.mark.parametrize(
    ("raw", "label", "message_fragment"),
    [
        # NaN and +inf pass jsonschema's numeric keywords (all comparisons are
        # False) and reach the loader's finite guard; -inf is rejected earlier
        # by the schema's minimum keyword.
        ("human_escalation_cost_usd: .nan\n", "nan", "finite nonnegative number"),
        ("human_escalation_cost_usd: .inf\n", "+inf", "finite nonnegative number"),
        ("human_escalation_cost_usd: -.inf\n", "-inf", "minimum of 0"),
    ],
)
def test_human_escalation_cost_non_finite_rejected(
    tmp_path: Path, raw: str, label: str, message_fragment: str
) -> None:
    """YAML permits non-finite floats the schema cannot see; the loader
    boundary rejects them so the catalog only ever carries finite USD."""
    doc = policy_doc()
    lines = yaml.safe_dump(doc).splitlines(keepends=True)
    # Replace the placeholder line with the non-finite literal under test.
    replaced = [
        raw if line.startswith("human_escalation_cost_usd:") else line for line in lines
    ]
    (tmp_path / "policy.yaml").write_text("".join(replaced), encoding="utf-8")
    assert label  # each literal variant exercises the same rejection path
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("policy", tmp_path / "policy.yaml")
    assert excinfo.value.document == "policy"
    assert excinfo.value.path == "$.human_escalation_cost_usd"
    assert message_fragment in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_human_escalation_cost_missing_rejected_by_schema(tmp_path: Path) -> None:
    doc = policy_doc()
    del doc["human_escalation_cost_usd"]
    write_docs(tmp_path, {"policy": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("policy", tmp_path / "policy.yaml")
    assert excinfo.value.document == "policy"
    assert "'human_escalation_cost_usd' is a required property" in str(excinfo.value)
    assert excinfo.value.path == "$"
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


def test_human_escalation_cost_unknown_sibling_field_rejected(tmp_path: Path) -> None:
    """Strict unknown-field rejection still applies alongside the new field."""
    doc = policy_doc()
    doc["escalation_cost_note"] = "no such field"
    write_docs(tmp_path, {"policy": doc})
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_document("policy", tmp_path / "policy.yaml")
    assert excinfo.value.document == "policy"
    assert excinfo.value.path == "$.escalation_cost_note"


def test_missing_document_raises_stable_error(tmp_path: Path) -> None:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "channels.yaml").unlink()
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "channels"
    assert "channels" in str(excinfo.value)
    assert "could not be read" in str(excinfo.value)


def test_malformed_yaml_raises_stable_error(tmp_path: Path) -> None:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "terms.yaml").write_text("terms: [unclosed\n", encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "terms"
    assert "not valid YAML" in str(excinfo.value)


def test_non_mapping_document_raises_stable_error(tmp_path: Path) -> None:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "crews.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "crews"
    assert "must be a YAML mapping" in str(excinfo.value)


def test_missing_schema_dir_raises_stable_error(tmp_path: Path) -> None:
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    with pytest.raises(StaffingCatalogError):
        load_staffing_catalog(tmp_path, schema_dir=tmp_path / "no-such-schema")


def test_schema_violation_names_field(tmp_path: Path) -> None:
    doc = routes_doc()
    doc["routes"][0]["usage_capture"] = "carrier_pigeon"
    write_docs(tmp_path, {name: builder() for name, builder in _DOC_BUILDERS.items()})
    (tmp_path / "routes.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StaffingCatalogError) as excinfo:
        load_staffing_catalog(tmp_path)
    assert excinfo.value.document == "routes"
    assert excinfo.value.path == "$.routes[0].usage_capture"


# ---------------------------------------------------------------------------
# Canonical class key (loader-owned boundary; D206)
# ---------------------------------------------------------------------------


def _class_block() -> dict:
    return {
        "class_key": "impl/judge/persistence+security/m/python",
        "role": "impl",
        "oracle_type": "judge",
        "domain_tags": ["security", "persistence"],
        "size_band": "m",
        "language": "python",
    }


def test_canonical_class_key_sorts_and_dedups_tags() -> None:
    key = canonical_class_key(
        "impl", "judge", ["security", "persistence", "security"], "m", "python"
    )
    assert key == "impl/judge/persistence+security/m/python"


def test_canonical_class_key_empty_tags_is_literal_none() -> None:
    key = canonical_class_key("plan", "human", [], "s", "markdown")
    assert key == "plan/human/none/s/markdown"
    assert "//" not in key


def test_validate_class_block_accepts_canonical_key() -> None:
    validate_class_block(_class_block(), document="manifest", path="$.class")


def test_validate_class_block_rejects_unsorted_tags() -> None:
    block = _class_block()
    block["class_key"] = "impl/judge/security+persistence/m/python"
    with pytest.raises(StaffingCatalogError) as excinfo:
        validate_class_block(block, document="manifest", path="$.class")
    assert "canonical class-key mismatch" in str(excinfo.value)
    assert "impl/judge/persistence+security/m/python" in str(excinfo.value)
    assert excinfo.value.document == "manifest"
    assert excinfo.value.path == "$.class.class_key"


def test_validate_class_block_rejects_duplicated_tag() -> None:
    block = _class_block()
    block["class_key"] = "impl/judge/persistence+security+persistence/m/python"
    with pytest.raises(StaffingCatalogError) as excinfo:
        validate_class_block(block)
    assert excinfo.value.path == "$.class_key"


def test_validate_class_block_rejects_component_mismatch() -> None:
    block = _class_block()
    block["class_key"] = "plan/judge/persistence+security/m/python"
    with pytest.raises(StaffingCatalogError) as excinfo:
        validate_class_block(block)
    assert "impl/judge/persistence+security/m/python" in str(excinfo.value)


def test_validate_class_block_rejects_empty_tags_segment() -> None:
    block = {
        "class_key": "plan/human//s/markdown",
        "role": "plan",
        "oracle_type": "human",
        "domain_tags": [],
        "size_band": "s",
        "language": "markdown",
    }
    with pytest.raises(StaffingCatalogError) as excinfo:
        validate_class_block(block)
    assert "plan/human/none/s/markdown" in str(excinfo.value)


# ---------------------------------------------------------------------------
# P1-1: stage-worker paths resolve from an installation root
#
# The committed routes.yaml names the five stage-worker scripts (antigravity,
# claude, codex, opencode, pi) through the placeholder token
# STAGE_WORKER_DIR_TOKEN; the loader substitutes it at load time from
# LEE_LLM_ROUTER_STAGE_WORKER_DIR when set and non-empty, else from the
# historical directory. Each test sets the variable explicitly so both
# resolution branches are exercised regardless of the developer's shell.
# ---------------------------------------------------------------------------

#: The five stage-worker script basenames the committed templates name.
STAGE_WORKER_SCRIPTS = ("antigravity", "claude", "codex", "opencode", "pi")

#: The pre-P1-1 committed dispatch template for the sol-xhigh route: the
#: value a loaded route must reproduce byte-for-byte while the environment
#: variable is unset.
SOL_XHIGH_DISPATCH_TEMPLATE = (
    "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/home/lee/.local/bin/codex "
    "CODEX_STAGE_WORKER_MODEL=gpt-5.6-sol "
    "CODEX_STAGE_WORKER_REASONING_EFFORT=xhigh "
    "python3 /home/lee/projects/auto-orch/scripts/codex_stage_worker.py "
    "{stage} {prompt_path} {response_path}"
)


def committed_config_dir() -> Path:
    """Return the committed ``config/staffing`` directory."""
    return Path(__file__).resolve().parents[1] / "config" / "staffing"


def committed_routes() -> tuple[Route, ...]:
    """Load the committed catalog and return its routes in catalog order."""
    return load_staffing_catalog(committed_config_dir()).routes.routes


def route_identity(route: Route) -> tuple[str | None, str | None, str, str]:
    """Return a route's ``(model, effort, harness, channel)`` identity tuple."""
    return (route.model, route.effort, route.harness, route.channel)


def test_stage_worker_dir_defaults_without_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset (and empty) environment resolves to the historical directory."""
    monkeypatch.delenv(STAGE_WORKER_DIR_ENV_VAR, raising=False)
    assert resolve_stage_worker_dir() == DEFAULT_STAGE_WORKER_DIR
    assert DEFAULT_STAGE_WORKER_DIR == "/home/lee/projects/auto-orch/scripts"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, "")
    assert resolve_stage_worker_dir() == DEFAULT_STAGE_WORKER_DIR


def test_stage_worker_dir_prefers_nonempty_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A set, non-empty environment variable wins over the default."""
    workers = tmp_path / "stage-workers"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, str(workers))
    assert resolve_stage_worker_dir() == str(workers)


def test_resolve_dispatch_template_substitutes_token() -> None:
    """The token is the only thing substituted; the rest is untouched."""
    template = (
        f"python3 {STAGE_WORKER_DIR_TOKEN}/pi_stage_worker.py "
        "{stage} {prompt_path} {response_path}"
    )
    expected = (
        "python3 /opt/workers/pi_stage_worker.py "
        "{stage} {prompt_path} {response_path}"
    )
    assert resolve_dispatch_template(template, "/opt/workers") == expected
    without_token = "dispatch {prompt}"
    assert resolve_dispatch_template(without_token, "/opt/workers") == without_token


def test_resolve_dispatch_template_uses_environment_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without an explicit directory the process environment decides."""
    workers = tmp_path / "workers"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, str(workers))
    template = f"python3 {STAGE_WORKER_DIR_TOKEN}/codex_stage_worker.py"
    expected = f"python3 {workers}/codex_stage_worker.py"
    assert resolve_dispatch_template(template) == expected


def test_routes_document_substitutes_token_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A routes document is resolved when it is loaded, not when it is read."""
    workers = "/opt/stage-workers"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, workers)
    doc = routes_doc()
    doc["routes"][0]["dispatch_template"] = (
        f"python3 {STAGE_WORKER_DIR_TOKEN}/pi_stage_worker.py "
        "{stage} {prompt_path} {response_path}"
    )
    write_docs(tmp_path, {"routes": doc})
    routes = load_staffing_document("routes", tmp_path / "routes.yaml")
    expected = (
        f"python3 {workers}/pi_stage_worker.py " "{stage} {prompt_path} {response_path}"
    )
    assert routes.routes[0].dispatch_template == expected
    # A template without the token is untouched by resolution.
    assert routes.routes[1].dispatch_template == "dispatch {prompt}"


def test_routes_document_default_substitution_uses_historical_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset environment substitutes the historical path, not a blank."""
    monkeypatch.delenv(STAGE_WORKER_DIR_ENV_VAR, raising=False)
    doc = routes_doc()
    doc["routes"][0][
        "dispatch_template"
    ] = f"python3 {STAGE_WORKER_DIR_TOKEN}/codex_stage_worker.py {{stage}}"
    write_docs(tmp_path, {"routes": doc})
    routes = load_staffing_document("routes", tmp_path / "routes.yaml")
    expected = f"python3 {DEFAULT_STAGE_WORKER_DIR}/codex_stage_worker.py {{stage}}"
    assert routes.routes[0].dispatch_template == expected


def test_committed_dispatch_template_is_byte_identical_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence 3: with the variable unset, the loaded template is
    byte-identical to its pre-P1-1 committed value, and the route's identity
    fields are unchanged."""
    monkeypatch.delenv(STAGE_WORKER_DIR_ENV_VAR, raising=False)
    route = next(
        route for route in committed_routes() if route.route_id == SOL_XHIGH_ROUTE
    )
    assert route.dispatch_template == SOL_XHIGH_DISPATCH_TEMPLATE
    assert STAGE_WORKER_DIR_TOKEN not in route.dispatch_template
    assert route_identity(route) == ("gpt-5.6-sol", "xhigh", "codex", "openai-sub")


def test_committed_templates_default_resolve_to_historical_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every committed template resolves, with the variable unset, to the
    historical directory, and each of the five scripts resolves there."""
    monkeypatch.delenv(STAGE_WORKER_DIR_ENV_VAR, raising=False)
    routes = committed_routes()
    assert routes
    prefix = f"python3 {DEFAULT_STAGE_WORKER_DIR}/"
    for route in routes:
        assert STAGE_WORKER_DIR_TOKEN not in route.dispatch_template
        assert prefix in route.dispatch_template
    for name in STAGE_WORKER_SCRIPTS:
        path = f"python3 {DEFAULT_STAGE_WORKER_DIR}/{name}_stage_worker.py"
        assert any(path in route.dispatch_template for route in routes), name


def test_committed_templates_resolve_to_environment_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Evidence 4: with the variable set to a temporary directory the loaded
    templates contain that directory and no occurrence of the legacy
    auto-orch path."""
    workers = tmp_path / "installed-stage-workers"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, str(workers))
    routes = committed_routes()
    assert routes
    prefix = f"python3 {workers}/"
    for route in routes:
        assert STAGE_WORKER_DIR_TOKEN not in route.dispatch_template
        assert "/home/lee/projects/auto-orch" not in route.dispatch_template
        assert prefix in route.dispatch_template
    for name in STAGE_WORKER_SCRIPTS:
        path = f"python3 {workers}/{name}_stage_worker.py"
        assert any(path in route.dispatch_template for route in routes), name


def test_stage_worker_dir_changes_only_dispatch_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The override rewrites exactly the stage-worker directory: route order,
    identity fields, usage_capture, and status are unchanged, and each
    template equals its default resolution with the directory swapped."""
    monkeypatch.delenv(STAGE_WORKER_DIR_ENV_VAR, raising=False)
    default_routes = committed_routes()
    workers = tmp_path / "workers"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, str(workers))
    env_routes = committed_routes()

    assert len(env_routes) == len(default_routes)
    for default_route, env_route in zip(default_routes, env_routes):
        assert env_route.route_id == default_route.route_id
        assert route_identity(env_route) == route_identity(default_route)
        assert env_route.usage_capture == default_route.usage_capture
        assert env_route.status == default_route.status
        assert env_route.status_reason == default_route.status_reason
        swapped = default_route.dispatch_template.replace(
            DEFAULT_STAGE_WORKER_DIR, str(workers)
        )
        assert env_route.dispatch_template == swapped


# ---------------------------------------------------------------------------
# P1-2: harness binaries resolve from PATH or LEE_LLM_ROUTER_<HARNESS>_BINARY
#
# The committed routes.yaml now hands each stage worker its harness binary
# through a per-harness placeholder token (@CODEX_BINARY@ and friends,
# following the P1-1 @STAGE_WORKER_DIR@ convention) instead of the absolute
# path that used to be hard-coded there. The loader substitutes the token at
# load time: LEE_LLM_ROUTER_<HARNESS>_BINARY when set and non-empty, else
# shutil.which(<binary name>), else the bare binary name. On this host the
# five binaries are installed at exactly the paths the pre-P1-2 templates
# hard-coded, so an unset environment reproduces those templates
# byte-for-byte. Each test sets the environment explicitly so every
# resolution branch is exercised regardless of the developer's shell.
# ---------------------------------------------------------------------------

#: Harness -> the override variable's harness id, i.e. the environment
#: variable LEE_LLM_ROUTER_<ID>_BINARY.
HARNESS_OVERRIDE_IDS = {
    "codex": "CODEX",
    "pi": "PI",
    "opencode": "OPENCODE",
    "claude": "CLAUDE",
    "agy": "AGY",
}

#: Harness -> the token its dispatch template carries. The module's table is
#: asserted to be exactly this mapping reversed, so the expectation here is
#: an independent statement of which binary each token names.
HARNESS_BINARY_TOKENS_EXPECTED = {
    "codex": "@CODEX_BINARY@",
    "pi": "@PI_BINARY@",
    "opencode": "@OPENCODE_BINARY@",
    "claude": "@CLAUDE_BINARY@",
    "agy": "@AGY_BINARY@",
}

#: The absolute binary paths the pre-P1-2 committed templates hard-coded,
#: per harness. On a host that installs each binary at its historical path,
#: PATH resolution must reproduce these exactly.
PRE_P1_2_HARNESS_BINARY_PATHS = {
    "codex": "/home/lee/.local/bin/codex",
    "pi": "/home/lee/.npm-global/bin/pi",
    "opencode": "/home/lee/.opencode/bin/opencode",
    "claude": "/home/lee/.local/bin/claude",
    "agy": "/home/lee/.local/bin/agy",
}

#: The directories holding those paths, PATH-prepended by the byte-identity
#: test so its lookup is the historical lookup rather than whatever PATH the
#: test runner happens to inherit.
PRE_P1_2_HARNESS_BINARY_DIRS = tuple(
    dict.fromkeys(
        path.rsplit("/", 1)[0] for path in PRE_P1_2_HARNESS_BINARY_PATHS.values()
    )
)

#: The two provenance comment lines that still cite a historical binary
#: path by design (P0-3d agy, P0-3f pi). They are citations, not dispatch
#: data, and this packet leaves them byte-for-byte.
PROVENANCE_BINARY_CITATIONS = (
    "(/home/lee/.npm-global/bin/pi)",
    "/home/lee/.local/bin/agy).",
)

#: The number of routes (and therefore dispatch templates) in the committed
#: catalog.
COMMITTED_ROUTE_COUNT = 31


def harness_override_env_var(harness: str) -> str:
    """Return the literal override variable name for ``harness``."""
    return f"LEE_LLM_ROUTER_{HARNESS_OVERRIDE_IDS[harness]}_BINARY"


def clear_binary_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset the stage-worker directory and every binary override."""
    monkeypatch.delenv(STAGE_WORKER_DIR_ENV_VAR, raising=False)
    for harness in HARNESS_OVERRIDE_IDS:
        monkeypatch.delenv(harness_override_env_var(harness), raising=False)


def committed_routes_document() -> dict:
    """Return the committed routes.yaml as raw (unresolved) text data."""
    text = (committed_config_dir() / "routes.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def committed_raw_templates() -> dict[str, str]:
    """Return route_id -> the dispatch template exactly as committed."""
    return {
        row["route_id"]: row["dispatch_template"]
        for row in committed_routes_document()["routes"]
    }


def sentinel_binaries(tmp_path: Path) -> dict[str, str]:
    """One distinct sentinel binary path per harness (never a real path)."""
    return {
        harness: str(tmp_path / "sentinels" / harness / f"{harness}-sentinel")
        for harness in HARNESS_BINARY_TOKENS_EXPECTED
    }


def make_executable(directory: Path, name: str) -> Path:
    """Create an executable file ``name`` inside ``directory`` and return it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_harness_binary_token_table_is_the_five_harnesses() -> None:
    """One explicit, documented token row per harness, P1-1-shaped."""
    assert HARNESS_BINARY_TOKENS == {
        token: harness for harness, token in HARNESS_BINARY_TOKENS_EXPECTED.items()
    }
    for harness, token in HARNESS_BINARY_TOKENS_EXPECTED.items():
        assert token == f"@{HARNESS_OVERRIDE_IDS[harness]}_BINARY@"
        # Not shell-shaped (no $ or ${...}) so the token can never be read as
        # an environment expansion, exactly as for @STAGE_WORKER_DIR@.
        assert "$" not in token
        assert "{" not in token


@pytest.mark.parametrize(
    ("harness", "env_var"),
    [
        ("codex", "LEE_LLM_ROUTER_CODEX_BINARY"),
        ("pi", "LEE_LLM_ROUTER_PI_BINARY"),
        ("opencode", "LEE_LLM_ROUTER_OPENCODE_BINARY"),
        ("claude", "LEE_LLM_ROUTER_CLAUDE_BINARY"),
        ("agy", "LEE_LLM_ROUTER_AGY_BINARY"),
    ],
)
def test_harness_binary_env_var_names(harness: str, env_var: str) -> None:
    """The override variable is LEE_LLM_ROUTER_<HARNESS>_BINARY."""
    assert HARNESS_BINARY_ENV_VAR_PREFIX == "LEE_LLM_ROUTER_"
    assert HARNESS_BINARY_ENV_VAR_SUFFIX == "_BINARY"
    assert harness_binary_env_var(HARNESS_BINARY_TOKENS_EXPECTED[harness]) == env_var


def test_resolve_harness_binary_prefers_nonempty_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolution 1 wins over 2; an empty variable falls through to PATH."""
    clear_binary_environment(monkeypatch)
    on_path = make_executable(tmp_path / "path-bin", "codex")
    monkeypatch.setenv("PATH", str(on_path.parent))
    assert resolve_harness_binary("@CODEX_BINARY@") == str(on_path)

    sentinel = str(tmp_path / "override" / "codex")
    monkeypatch.setenv("LEE_LLM_ROUTER_CODEX_BINARY", sentinel)
    assert resolve_harness_binary("@CODEX_BINARY@") == sentinel

    monkeypatch.setenv("LEE_LLM_ROUTER_CODEX_BINARY", "")
    assert resolve_harness_binary("@CODEX_BINARY@") == str(on_path)


def test_resolve_harness_binary_uses_path_then_bare_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolution 2 then 3, and never another harness's binary."""
    clear_binary_environment(monkeypatch)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert resolve_harness_binaries() == HARNESS_BINARY_TOKENS

    # Only agy is installed: every other harness keeps its own bare name.
    agy = make_executable(tmp_path / "path-bin", "agy")
    monkeypatch.setenv("PATH", str(agy.parent))
    assert resolve_harness_binary("@AGY_BINARY@") == str(agy)
    for token, binary in HARNESS_BINARY_TOKENS.items():
        if token != "@AGY_BINARY@":
            assert resolve_harness_binary(token) == binary


def test_resolve_dispatch_template_substitutes_both_token_kinds() -> None:
    """The explicit table renders both placeholders; nothing else changes."""
    template = (
        "/usr/bin/env AGY_STAGE_WORKER_BINARY=@AGY_BINARY@ "
        "python3 @STAGE_WORKER_DIR@/antigravity_stage_worker.py {stage}"
    )
    expected = (
        "/usr/bin/env AGY_STAGE_WORKER_BINARY=/opt/bin/agy "
        "python3 /opt/workers/antigravity_stage_worker.py {stage}"
    )
    assert (
        resolve_dispatch_template(
            template, "/opt/workers", {"@AGY_BINARY@": "/opt/bin/agy"}
        )
        == expected
    )


def test_routes_document_resolves_binary_tokens_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A routes document resolves binary tokens when it is loaded, from the
    override when set and from the bare name when nothing can be found."""
    clear_binary_environment(monkeypatch)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    workers = "/opt/stage-workers"
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, workers)
    monkeypatch.setenv("LEE_LLM_ROUTER_CODEX_BINARY", "/opt/bin/codex")

    doc = routes_doc()
    doc["routes"][0]["dispatch_template"] = (
        "/usr/bin/env CODEX_STAGE_WORKER_BINARY=@CODEX_BINARY@ "
        "python3 @STAGE_WORKER_DIR@/codex_stage_worker.py {stage}"
    )
    doc["routes"][1]["dispatch_template"] = (
        "/usr/bin/env PI_STAGE_WORKER_BINARY=@PI_BINARY@ "
        "python3 @STAGE_WORKER_DIR@/pi_stage_worker.py {stage}"
    )
    write_docs(tmp_path, {"routes": doc})

    routes = load_staffing_document("routes", tmp_path / "routes.yaml")
    assert routes.routes[0].dispatch_template == (
        "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/opt/bin/codex "
        f"python3 {workers}/codex_stage_worker.py {{stage}}"
    )
    assert routes.routes[1].dispatch_template == (
        "/usr/bin/env PI_STAGE_WORKER_BINARY=pi "
        f"python3 {workers}/pi_stage_worker.py {{stage}}"
    )


def test_committed_templates_are_byte_identical_without_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence 3: with no override set, every one of the committed templates
    loads byte-identically to its pre-P1-2 value — the token replaced by the
    historical absolute path PATH resolution finds — and no route's identity
    fields differ from the committed YAML."""
    clear_binary_environment(monkeypatch)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join([*PRE_P1_2_HARNESS_BINARY_DIRS, os.environ.get("PATH", "")]),
    )
    raw = committed_raw_templates()
    rows = committed_routes_document()["routes"]
    routes = committed_routes()
    assert len(routes) == COMMITTED_ROUTE_COUNT == len(raw) == len(rows)

    for route, row in zip(routes, rows):
        assert route.route_id == row["route_id"]
        assert route.model == row["model"]
        assert route.effort == row["effort"]
        assert route.harness == row["harness"]
        assert route.channel == row["channel"]
        assert route.status == row["status"]

        token = HARNESS_BINARY_TOKENS_EXPECTED[route.harness]
        historical = PRE_P1_2_HARNESS_BINARY_PATHS[route.harness]
        status = shutil.which(HARNESS_BINARY_TOKENS[token])
        assert status == historical, (
            f"{HARNESS_BINARY_TOKENS[token]} is not installed at {historical}; "
            "PATH resolution cannot reproduce the pre-P1-2 template"
        )
        expected = (
            raw[route.route_id]
            .replace(STAGE_WORKER_DIR_TOKEN, DEFAULT_STAGE_WORKER_DIR)
            .replace(token, historical)
        )
        assert route.dispatch_template == expected
        assert token not in route.dispatch_template
        assert not re.search(r"@[A-Z_]+@", route.dispatch_template)


def test_committed_templates_carry_explicit_binary_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence 4: with each override set to a distinct sentinel, every
    template carries its own sentinel, and no historical binary path and no
    unresolved token remains."""
    clear_binary_environment(monkeypatch)
    sentinels = sentinel_binaries(tmp_path)
    for harness, path in sentinels.items():
        monkeypatch.setenv(harness_override_env_var(harness), path)
    workers = str(tmp_path / "installed-stage-workers")
    monkeypatch.setenv(STAGE_WORKER_DIR_ENV_VAR, workers)

    raw = committed_raw_templates()
    routes = committed_routes()
    assert len(routes) == COMMITTED_ROUTE_COUNT
    for route in routes:
        token = HARNESS_BINARY_TOKENS_EXPECTED[route.harness]
        expected = (
            raw[route.route_id]
            .replace(STAGE_WORKER_DIR_TOKEN, workers)
            .replace(token, sentinels[route.harness])
        )
        assert route.dispatch_template == expected
        assert sentinels[route.harness] in route.dispatch_template
        assert not re.search(r"@[A-Z_]+@", route.dispatch_template)
        for other_token in HARNESS_BINARY_TOKENS_EXPECTED.values():
            if other_token != token:
                assert other_token not in route.dispatch_template
        for historical in PRE_P1_2_HARNESS_BINARY_PATHS.values():
            assert historical not in route.dispatch_template
        for other, path in sentinels.items():
            if other != route.harness:
                assert path not in route.dispatch_template


def test_harness_binary_overrides_change_only_the_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An override rewrites exactly the binary: route order, identity fields,
    usage_capture, and status are unchanged, and each template equals the
    committed template with only its own binary token resolved."""
    clear_binary_environment(monkeypatch)
    raw_rows = committed_routes_document()["routes"]
    sentinels = sentinel_binaries(tmp_path)
    for harness, path in sentinels.items():
        monkeypatch.setenv(harness_override_env_var(harness), path)
    routes = committed_routes()

    assert [route.route_id for route in routes] == [row["route_id"] for row in raw_rows]
    for route, row in zip(routes, raw_rows):
        assert route.model == row["model"]
        assert route.effort == row["effort"]
        assert route.harness == row["harness"]
        assert route.channel == row["channel"]
        assert route.usage_capture == row["usage_capture"]
        assert route.status == row["status"]
        assert route.status_reason == row.get("status_reason")
        expected = (
            row["dispatch_template"]
            .replace(STAGE_WORKER_DIR_TOKEN, DEFAULT_STAGE_WORKER_DIR)
            .replace(
                HARNESS_BINARY_TOKENS_EXPECTED[route.harness],
                sentinels[route.harness],
            )
        )
        assert route.dispatch_template == expected
        assert route.dispatch_template != row["dispatch_template"]


def test_unresolvable_binary_resolves_to_bare_name_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence 5: a token whose binary is neither overridden nor on PATH
    loads as the bare binary name — no raise, no other harness's binary, and
    no collateral damage to unrelated routes."""
    clear_binary_environment(monkeypatch)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    sentinels = sentinel_binaries(tmp_path)
    for harness, path in sentinels.items():
        if harness != "codex":
            monkeypatch.setenv(harness_override_env_var(harness), path)

    routes = committed_routes()
    assert len(routes) == COMMITTED_ROUTE_COUNT
    codex_routes = [route for route in routes if route.harness == "codex"]
    assert len(codex_routes) == 9
    for route in codex_routes:
        assert "CODEX_STAGE_WORKER_BINARY=codex " in route.dispatch_template
        for path in sentinels.values():
            assert path not in route.dispatch_template
        for historical in PRE_P1_2_HARNESS_BINARY_PATHS.values():
            assert historical not in route.dispatch_template
    for route in routes:
        if route.harness == "codex":
            continue
        sentinel = sentinels[route.harness]
        assert f"BINARY={sentinel} " in route.dispatch_template, route.route_id

    # Nothing installed and nothing overridden: loading still succeeds for
    # every route, each template carrying its own harness's bare name.
    for harness in sentinels:
        monkeypatch.delenv(harness_override_env_var(harness), raising=False)
    bare_routes = committed_routes()
    assert len(bare_routes) == COMMITTED_ROUTE_COUNT
    for route in bare_routes:
        token = HARNESS_BINARY_TOKENS_EXPECTED[route.harness]
        binary = HARNESS_BINARY_TOKENS[token]
        assert f"BINARY={binary} " in route.dispatch_template, route.route_id


def test_committed_routes_yaml_carries_tokens_not_binary_paths() -> None:
    """Every committed template names its own harness's token exactly once,
    no other harness's token, and no absolute harness path."""
    raw = committed_raw_templates()
    rows = committed_routes_document()["routes"]
    assert len(raw) == COMMITTED_ROUTE_COUNT == len(rows)
    for row in rows:
        token = HARNESS_BINARY_TOKENS_EXPECTED[row["harness"]]
        template = row["dispatch_template"]
        assert template.count(token) == 1, row["route_id"]
        assert STAGE_WORKER_DIR_TOKEN in template
        for harness, other_token in HARNESS_BINARY_TOKENS_EXPECTED.items():
            if harness != row["harness"]:
                assert other_token not in template, row["route_id"]
        for historical in PRE_P1_2_HARNESS_BINARY_PATHS.values():
            assert historical not in template, row["route_id"]


def test_committed_routes_yaml_keeps_provenance_binary_citations() -> None:
    """The two comment lines citing a historical binary path are provenance
    and stay put (with the P1-1 and P1-2 change notes); no template line
    carries an absolute harness path."""
    text = (committed_config_dir() / "routes.yaml").read_text(encoding="utf-8")
    assert "# P1-1:" in text
    assert "# P1-2:" in text
    for citation in PROVENANCE_BINARY_CITATIONS:
        matching = [line for line in text.splitlines() if citation in line]
        assert len(matching) == 1, citation
        assert matching[0].lstrip().startswith("#")
    template_lines = [
        line for line in text.splitlines() if "dispatch_template:" in line
    ]
    assert len(template_lines) == COMMITTED_ROUTE_COUNT
    for line in template_lines:
        for historical in PRE_P1_2_HARNESS_BINARY_PATHS.values():
            assert historical not in line
