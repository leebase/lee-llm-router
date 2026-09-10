"""Tests for the staffing catalog loader/validator (shape boundary only).

Fixtures here are handwritten scratch data; they do not depend on the
not-yet-authored live catalog YAML. No provider prompts are involved.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
import yaml

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
from lee_llm_router.staffing.catalog import CrewSupervisor

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
    assert channels.channels[1].windows == ()


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
