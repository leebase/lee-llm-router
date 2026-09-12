"""Focused P1-2/P1-7b1 tests for the attempt-record schema v2.

Authority: D209 ruling 2 via docs/staffing/phase1-contracts.md, with D206
preserved verbatim (class metadata never maps to a preferred model or route).

These tests validate the schema document, its six shipped examples, and the
deterministic fixture copies under tests/fixtures/staffing/. No provider
prompts are made and no state directory is touched; every record here is
scratch data and no real pricing is asserted.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT / "config" / "staffing" / "schema" / "attempt-record.schema.json"
)
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "staffing"
AGENT_ORCH_ATTEMPT_ID = (
    "b0ccf22e228b8dbc599747372cbf018150ff39eeedd3437de8d4f70e2ec00daa"
)
BENCHMARK_V6_RUN_ID = "benchmark:scratch-run-1"
LEGACY_BENCHMARK_ID = "bench-mixed-economy-0001"

FIXTURE_FILES = [
    "attempt-record-agent-orch.json",
    "attempt-record-benchmark-run.json",
    "attempt-record-router-run-unavailable.json",
    "attempt-record-router-run-escalation.json",
    "attempt-record-import-agent-orch-unclassed.json",
    "attempt-record-agent-orch-raw-attempt.json",
    "attempt-record-benchmark-v6-run.json",
]

D206_VERBATIM = (
    "Class metadata MUST NOT map directly to a preferred model or route. "
    "It may only: 1. join production attempts to comparable benchmark "
    "evidence; and 2. determine whether an unevidenced cheap trial is "
    "permitted."
)

USAGE_SOURCES = [
    "pi --mode json events",
    "codex exec --json usage",
    "claude -p --output-format stream-json result event",
    "agy -p usage line (agent-orch worker.py)",
    "opencode run JSON usage event",
    "opencode worker-written usage.json from provider output",
    "omp -p --mode json events",
    "benchmark v6 CSV usage_*_tokens",
    "agent-orch usage.json/accounting_status",
    "agent-orch usage.json",
]


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def examples(schema: dict) -> dict:
    return {ex["attempt_id"]: ex for ex in schema["examples"]}


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    """Format checking consistent with src/lee_llm_router/staffing/catalog.py."""
    return Draft202012Validator(schema, format_checker=FormatChecker())


def paths_of(errors: list) -> set[str]:
    return {
        "$." + ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "$"
        for e in errors
    }


def error_details(validator: Draft202012Validator, record: dict) -> list[tuple]:
    """Return compact validation details for assertion diagnostics."""
    return [
        (list(error.absolute_path), error.validator, error.message)
        for error in validator.iter_errors(record)
    ]


def require_error(
    validator: Draft202012Validator, record: dict, path: str, validator_name: str
) -> None:
    """Assert a validation error fires at ``path`` with the given validator."""
    matching = [e for e in validator.iter_errors(record) if paths_of([e]) == {path}]
    assert matching, (
        f"expected a validation error at {path}, got "
        f"{error_details(validator, record)}"
    )
    assert any(e.validator == validator_name for e in matching), [
        (list(e.absolute_path), e.validator, e.message) for e in matching
    ]


def require_boolean_rejection(
    validator: Draft202012Validator, record: dict, marker: str
) -> None:
    """Assert a closed-schema (``false``) rejection mentioning ``marker``.

    jsonschema reports boolean-subschema violations with validator ``None``;
    the message embeds the offending property value, so tests plant a
    distinctive value (or match the dumped field name for object payloads).
    """
    matching = [
        e
        for e in validator.iter_errors(record)
        if e.validator is None and marker in e.message
    ]
    assert matching, (
        f"expected a closed-schema rejection mentioning {marker!r}, got "
        f"{error_details(validator, record)}"
    )


def require_required_error(
    validator: Draft202012Validator, record: dict, field: str
) -> None:
    matching = [
        e
        for e in validator.iter_errors(record)
        if e.validator == "required"
        and f"'{field}' is a required property" in e.message
    ]
    assert matching, (
        f"expected a required-property error naming '{field}', got "
        f"{error_details(validator, record)}"
    )


# ---------------------------------------------------------------------------
# Positive: shipped examples and fixtures
# ---------------------------------------------------------------------------


def test_all_schema_examples_validate(
    validator: Draft202012Validator, schema: dict
) -> None:
    assert len(schema["examples"]) == 7
    for ex in schema["examples"]:
        problems = [
            (list(e.absolute_path), e.message) for e in validator.iter_errors(ex)
        ]
        assert not problems, f"example {ex['attempt_id']}: {problems}"


@pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
def test_fixture_validates_and_matches_schema_example(
    validator: Draft202012Validator, schema: dict, fixture_name: str
) -> None:
    fixture = json.loads((FIXTURE_DIR / fixture_name).read_text())
    assert not list(validator.iter_errors(fixture))
    example = next(
        (ex for ex in schema["examples"] if ex["attempt_id"] == fixture["attempt_id"]),
        None,
    )
    assert example is not None, f"no schema example for {fixture['attempt_id']}"
    assert fixture == example, "fixture drifted from the shipped schema example"


def test_raw_attempt_fixture_is_canonical_byte_copy(schema: dict) -> None:
    """Pin the reviewed example to one deterministic on-disk byte encoding."""
    example = next(
        ex for ex in schema["examples"] if ex["attempt_id"] == AGENT_ORCH_ATTEMPT_ID
    )
    expected = (json.dumps(example, indent=2) + "\n").encode()
    fixture_path = FIXTURE_DIR / "attempt-record-agent-orch-raw-attempt.json"
    assert fixture_path.read_bytes() == expected


def test_v2_envelope_shape(schema: dict) -> None:
    assert schema["properties"]["schema_version"]["const"] == 2
    assert schema["properties"]["record_kind"]["enum"] == [
        "agent_orch",
        "agent_orch_attempt",
        "benchmark_run",
        "router_run",
    ]
    for field in (
        "packet_id",
        "parent_attempt_id",
        "escalation_reason",
        "oracle_cmd",
        "verdict",
        "selection",
        "class_source",
        "usage",
        "cost",
        "route",
        "supervisor_route",
        "verified_success_reason",
        "class_record",
        "failure_class",
        "wall_clock_ms",
        "provenance",
    ):
        assert field in schema["properties"], f"missing top-level {field}"
    assert schema["required"] == [
        "schema_version",
        "attempt_id",
        "record_kind",
        "captured_at",
        "verified_success",
        "provenance",
    ]


def test_selection_preserves_only_route_ids_and_reasons(schema: dict) -> None:
    selection = schema["$defs"]["selection"]
    assert selection["properties"]["basis"]["enum"] == [
        "explicit",
        "explain_cheapest_eligible",
    ]
    assert set(selection["properties"]) == {
        "basis",
        "reason",
        "explain_ref",
        "excluded",
    }
    excluded = selection["properties"]["excluded"]["items"]
    assert set(excluded["properties"]) == {"route_id", "reason"}
    assert excluded["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Usage conditionals
# ---------------------------------------------------------------------------


def test_usage_source_pairing_rules(schema: dict) -> None:
    assert len(USAGE_SOURCES) == 10
    usage = schema["$defs"]["usage"]
    assert usage["properties"]["source"]["type"] == "string"
    assert usage["properties"]["source"]["minLength"] == 1
    assert usage["properties"]["basis"]["enum"] == [
        "observed",
        "provider_reported",
        "calculated",
        "unavailable",
    ]
    branches = usage["allOf"]
    reported = [
        b
        for b in branches
        if b.get("if", {}).get("properties", {}).get("basis", {}).get("const")
        == "provider_reported"
    ]
    assert len(reported) == 1
    assert reported[0]["then"]["properties"]["source"]["enum"] == USAGE_SOURCES
    free = [
        b
        for b in branches
        if b.get("if", {}).get("properties", {}).get("basis", {}).get("enum")
        == ["observed", "calculated"]
    ]
    assert len(free) == 1
    assert free[0]["then"]["properties"]["source"]["not"]["enum"] == USAGE_SOURCES


def test_provider_reported_source_requires_exact_taxonomy_string(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    record["usage"]["source"] = "codex CLI printed totals somewhere"
    require_error(validator, record, "$.usage.source", "enum")


def test_observed_and_calculated_use_descriptive_sources(
    validator: Draft202012Validator, examples: dict
) -> None:
    for basis, source in (
        ("observed", "operator-read token totals from the harness transcript"),
        ("calculated", "components summed from the provider's own usage event"),
    ):
        record = copy.deepcopy(examples["pi-run-0002"])
        record["usage"]["basis"] = basis
        record["usage"]["source"] = source
        assert not list(validator.iter_errors(record)), (basis, source)


@pytest.mark.parametrize("taxonomy_source", USAGE_SOURCES)
def test_taxonomy_strings_never_pair_with_observed_or_calculated(
    validator: Draft202012Validator, examples: dict, taxonomy_source: str
) -> None:
    for basis in ("observed", "calculated"):
        record = copy.deepcopy(examples["pi-run-0002"])
        record["usage"]["basis"] = basis
        record["usage"]["source"] = taxonomy_source
        matching = [e for e in validator.iter_errors(record) if e.validator == "not"]
        assert matching, (basis, taxonomy_source)


def test_unavailable_usage_carries_reason_and_no_source(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    assert record["usage"] == {
        "basis": "unavailable",
        "unavailable_reason": "text mode",
    }
    assert not list(validator.iter_errors(record))


def test_token_counters_are_nonnegative_integers_or_unknown(
    validator: Draft202012Validator, examples: dict
) -> None:
    base = examples["pi-run-0002"]

    def record_with(mutate) -> dict:
        record = copy.deepcopy(base)
        record["cost"] = {"basis": ["unavailable"]}
        mutate(record["usage"])
        return record

    # Known: nonnegative integers, including genuine source-reported zero.
    for value in (0, 1, 1540):
        assert not list(
            validator.iter_errors(
                record_with(lambda u, v=value: u.update(input_tokens=v))
            )
        ), value
    # Unknown: null or absent — never a fabricated sentinel.
    assert not list(
        validator.iter_errors(record_with(lambda u: u.update(input_tokens=None)))
    )
    assert not list(validator.iter_errors(record_with(lambda u: u.pop("input_tokens"))))
    # Never negative, fractional, or textual.
    for bad, name in ((-1, "minimum"), (1.5, "type"), ("1540", "type")):
        record = record_with(lambda u, v=bad: u.update(input_tokens=v))
        require_error(validator, record, "$.usage.input_tokens", name)


# ---------------------------------------------------------------------------
# Negative: usage basis/source/unavailable_reason conditionals
# ---------------------------------------------------------------------------


def test_known_basis_without_source_rejected_naming_source(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    del record["usage"]["source"]
    require_error(validator, record, "$.usage", "required")
    require_required_error(validator, record, "source")


def test_unavailable_basis_without_reason_rejected_naming_unavailable_reason(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    del record["usage"]["unavailable_reason"]
    require_error(validator, record, "$.usage", "required")
    require_required_error(validator, record, "unavailable_reason")


def test_unavailable_basis_with_source_rejected(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    record["usage"][
        "source"
    ] = "pi --mode json events"  # planted: source on unavailable
    require_boolean_rejection(validator, record, "pi --mode json events")


# ---------------------------------------------------------------------------
# P1-9: unavailable usage never hides numeric token evidence
# ---------------------------------------------------------------------------


def unavailable_forbid_branch(schema: dict) -> dict:
    """Return the $defs/usage allOf branch keyed on basis const unavailable."""
    branches = schema["$defs"]["usage"]["allOf"]
    branch = next(
        b
        for b in branches
        if b.get("if", {}).get("properties", {}).get("basis", {}).get("const")
        == "unavailable"
    )
    return branch


def test_unavailable_branch_forces_every_counter_to_null_or_absent(
    schema: dict,
) -> None:
    branch = unavailable_forbid_branch(schema)
    then_props = branch["then"]["properties"]
    assert then_props["source"] is False
    for counter in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        assert then_props[counter] == {"type": "null"}, counter
    assert branch["then"]["required"] == ["unavailable_reason"]


@pytest.mark.parametrize(
    "counter",
    [
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    ],
)
def test_unavailable_usage_never_hides_numeric_token_evidence(
    validator: Draft202012Validator, examples: dict, counter: str
) -> None:
    """Astra repro 3 at the schema layer: a non-null counter under
    basis 'unavailable' is rejected — unavailable means the tokens are
    unavailable, never hidden numeric evidence."""
    record = copy.deepcopy(examples["pi-run-0001"])  # usage basis unavailable
    record["usage"][counter] = 1200
    require_error(validator, record, f"$.usage.{counter}", "type")


def test_unavailable_usage_allows_null_or_absent_counters(
    validator: Draft202012Validator, examples: dict
) -> None:
    """Positive real-row shape: explicit null counters stay valid."""
    record = copy.deepcopy(examples["pi-run-0001"])
    record["usage"].update(
        input_tokens=None,
        output_tokens=None,
        cached_input_tokens=None,
        reasoning_tokens=None,
        total_tokens=None,
    )
    assert not list(validator.iter_errors(record))


def test_known_basis_with_unavailable_reason_rejected(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    record["usage"][
        "unavailable_reason"
    ] = "unavailable_reason planted on a known basis"
    require_boolean_rejection(
        validator, record, "unavailable_reason planted on a known basis"
    )


# ---------------------------------------------------------------------------
# Cost rule
# ---------------------------------------------------------------------------


def priced_cost() -> dict:
    return {"basis": ["list", "marginal"], "usd_list": 0.01, "usd_marginal": 0.008}


def test_numeric_cost_with_unavailable_usage_rejected_naming_cost_fields(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])  # usage basis unavailable
    record["cost"] = priced_cost()
    require_error(validator, record, "$.cost.usd_list", "type")
    require_error(validator, record, "$.cost.usd_marginal", "type")


def test_numeric_cost_with_unknown_required_tokens_rejected_naming_cost_fields(
    validator: Draft202012Validator, examples: dict
) -> None:
    for mutate in (
        lambda u: u.update(input_tokens=None),
        lambda u: u.pop("input_tokens"),
        lambda u: u.update(output_tokens=None),
        lambda u: u.pop("output_tokens"),
    ):
        record = copy.deepcopy(examples["pi-run-0002"])
        mutate(record["usage"])
        record["cost"] = priced_cost()
        require_error(validator, record, "$.cost.usd_list", "type")
        require_error(validator, record, "$.cost.usd_marginal", "type")


def test_known_tokens_with_unpriced_cost_is_valid(
    validator: Draft202012Validator, examples: dict
) -> None:
    # Cost exists only when the selected dated P0-4 terms price the known
    # tokens; this scratch record selects no terms, so ['unavailable'] with no
    # numeric figure is correct — never an estimate from tokens.
    assert not list(validator.iter_errors(examples["pi-run-0002"]))


def test_known_cost_requires_both_figures(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    record["cost"] = {"basis": ["list", "marginal"], "usd_marginal": 0.008}
    require_error(validator, record, "$.cost", "required")
    require_required_error(validator, record, "usd_list")


def test_unavailable_cost_rejects_figures(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    record["cost"] = {"basis": ["unavailable"], "usd_list": 0.01}
    require_error(validator, record, "$.cost.usd_list", "type")


@pytest.mark.parametrize(
    "basis",
    [
        ["list"],
        ["marginal"],
        ["marginal", "list"],
        ["unavailable", "list"],
        ["list", "marginal", "unavailable"],
    ],
)
def test_cost_basis_vocabulary_is_closed(
    validator: Draft202012Validator, examples: dict, basis: list
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    record["cost"] = {"basis": basis, "usd_list": 0.01, "usd_marginal": 0.008}
    require_error(validator, record, "$.cost.basis", "enum")


def test_negative_cost_figure_rejected(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    record["cost"] = {
        "basis": ["list", "marginal"],
        "usd_list": -0.01,
        "usd_marginal": 0.008,
    }
    require_error(validator, record, "$.cost.usd_list", "minimum")


def test_pricing_snapshot_fields_are_preserved_p0_baseline_fields(schema: dict) -> None:
    # The reviewer claimed these two fields have no D209 trace; inspection
    # proved both existed in the D208/Phase 0 (P0-9a) baseline schema. They
    # are preserved, and the schema documents that P0 baseline provenance
    # rather than presenting them as D209 additions or competing facts.
    cost = schema["$defs"]["cost"]
    for field in ("pricing_snapshot_ref", "pricing_snapshot_sha256"):
        assert field in cost["properties"], f"baseline field {field} must be preserved"
        description = cost["properties"][field]["description"]
        assert "P0-9a" in description and "D208" in description, field
        assert "not a D209 addition" in description, field
        assert "never a competing usage or cost fact" in description, field


# ---------------------------------------------------------------------------
# Class placement: D206 + class_key optional only for unclassed imports
# ---------------------------------------------------------------------------


def test_d206_verbatim_preserved_and_no_class_route_mapping(schema: dict) -> None:
    assert D206_VERBATIM in schema["description"]
    class_record = schema["$defs"]["classRecord"]
    assert class_record["additionalProperties"] is False
    assert set(class_record["properties"]) == {
        "class_key",
        "role",
        "oracle_type",
        "domain_tags",
        "size_band",
        "language",
    }
    assert D206_VERBATIM in class_record["description"]
    # Neither the selection object nor any def maps class to model/route.
    selection = schema["$defs"]["selection"]
    assert not {"class_key", "role", "class_record"} & set(selection["properties"])
    assert "preferred" not in selection["description"].replace("never", "")


def test_class_source_none_marks_unclassed_imports(
    validator: Draft202012Validator, examples: dict
) -> None:
    # Positive: imported historical attempt without class metadata.
    record = copy.deepcopy(examples["a6a85c6b02c7"])
    assert record["class_source"] == "none"
    assert "class_record" not in record
    assert not list(validator.iter_errors(record))
    # Negative: class_source 'none' together with a class record is contradictory.
    record = copy.deepcopy(examples["pi-run-0002"])
    record["class_source"] = "none"
    require_boolean_rejection(validator, record, "'class_key'")


def test_import_without_class_record_requires_class_source_none(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["a6a85c6b02c7"])
    del record["class_source"]
    require_required_error(validator, record, "class_source")


def test_router_run_requires_class_record(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    del record["class_record"]
    require_required_error(validator, record, "class_record")


# ---------------------------------------------------------------------------
# Packet, link, oracle, and verdict facts
# ---------------------------------------------------------------------------


def test_escalation_requires_both_link_fields(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0002"])
    del record["escalation_reason"]
    require_required_error(validator, record, "escalation_reason")

    record = copy.deepcopy(examples["pi-run-0002"])
    del record["parent_attempt_id"]
    require_required_error(validator, record, "parent_attempt_id")

    # Initial attempt: both null is valid.
    record = copy.deepcopy(examples["pi-run-0001"])
    assert record["parent_attempt_id"] is None
    assert record["escalation_reason"] is None
    assert not list(validator.iter_errors(record))


def test_router_run_verdict_oracle_pairing(
    validator: Draft202012Validator, examples: dict
) -> None:
    # pass|fail require the recorded oracle command.
    record = copy.deepcopy(examples["pi-run-0002"])
    del record["oracle_cmd"]
    require_required_error(validator, record, "oracle_cmd")
    # unverified means no oracle ran.
    record = copy.deepcopy(examples["pi-run-0001"])
    record["oracle_cmd"] = "scratch-oracle --check"
    require_error(validator, record, "$.oracle_cmd", "type")


def test_v2_verdict_vocabulary_is_canonical(
    validator: Draft202012Validator, schema: dict, examples: dict
) -> None:
    assert schema["$defs"]["canonicalVerdict"]["enum"] == [
        "pass",
        "fail",
        "unverified",
        "judge_pass",
        "judge_fail",
    ]
    assert "engine_validation" not in schema["$defs"]["canonicalVerdict"]["enum"]
    record = copy.deepcopy(examples["a6a85c6b02c6"])
    record["verdict"] = "accepted"  # v1 benchmark word; the payload keeps it now
    require_error(validator, record, "$.verdict", "enum")


def test_record_kind_v2_drops_interactive(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    record["record_kind"] = "interactive"
    require_error(validator, record, "$.record_kind", "enum")
    record = copy.deepcopy(examples["pi-run-0001"])
    record["record_kind"] = "agent_orch"
    require_required_error(validator, record, "agent_orch_observation")


def test_selection_is_run_command_evidence_only(
    validator: Draft202012Validator, examples: dict
) -> None:
    # Required on router_run records, together with packet_id.
    record = copy.deepcopy(examples["pi-run-0001"])
    del record["selection"]
    require_required_error(validator, record, "selection")
    record = copy.deepcopy(examples["pi-run-0001"])
    del record["packet_id"]
    require_required_error(validator, record, "packet_id")
    # Forbidden on imports.
    record = copy.deepcopy(examples["a6a85c6b02c7"])
    record["selection"] = copy.deepcopy(examples["pi-run-0001"]["selection"])
    require_boolean_rejection(validator, record, "'explain_ref'")


def test_provenance_source_pairs_with_record_kind(
    validator: Draft202012Validator, examples: dict
) -> None:
    pairs = {
        "a6a85c6b02c6": ("agent-orch", "benchmark"),
        AGENT_ORCH_ATTEMPT_ID: ("agent-orch-runs", "agent-orch"),
        LEGACY_BENCHMARK_ID: ("benchmark", "agent-orch"),
        BENCHMARK_V6_RUN_ID: ("benchmark", "agent-orch"),
        "pi-run-0001": ("router-run", "benchmark"),
    }
    for attempt_id, (correct, wrong) in pairs.items():
        record = copy.deepcopy(examples[attempt_id])
        record["provenance"]["source"] = wrong
        require_error(validator, record, "$.provenance.source", "const")
        record["provenance"]["source"] = correct
        assert not list(validator.iter_errors(record))


# ---------------------------------------------------------------------------
# P1-7b1 raw agent-orch attempt truth mappings
# ---------------------------------------------------------------------------


def raw_agent_orch_attempt(examples: dict) -> dict:
    """Return the real-run-derived P1-7b1 example for mutation tests."""
    return copy.deepcopy(examples[AGENT_ORCH_ATTEMPT_ID])


def unavailable_raw_attempt(examples: dict, status: str | None, reason: str) -> dict:
    """Build a truthful unavailable-accounting variant without inference."""
    record = raw_agent_orch_attempt(examples)
    payload = record["agent_orch_attempt"]
    payload["accounting_status"] = status
    payload.pop("usage")
    payload.pop("cost_usd")
    if status is None:
        payload["source_paths"] = [
            path for path in payload["source_paths"] if not path.endswith("/usage.json")
        ]
    record["usage"] = {"basis": "unavailable", "unavailable_reason": reason}
    record["cost"] = {"basis": "unavailable"}
    return record


def test_agent_orch_attempt_payload_is_closed_to_authorized_raw_fields(
    validator: Draft202012Validator, schema: dict, examples: dict
) -> None:
    payload_schema = schema["$defs"]["agentOrchAttempt"]
    assert payload_schema["additionalProperties"] is False
    assert set(payload_schema["properties"]) == {
        "run_id",
        "step_id",
        "attempt_number",
        "route",
        "worker_exit_code",
        "validation_passed",
        "policy_decision",
        "failure_classification",
        "accounting_status",
        "usage",
        "cost_usd",
        "started_at",
        "ended_at",
        "source_paths",
    }
    record = raw_agent_orch_attempt(examples)
    record["agent_orch_attempt"]["worker_success"] = True
    require_error(validator, record, "$.agent_orch_attempt", "additionalProperties")


def test_agent_orch_attempt_rejects_invented_class_fields(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = raw_agent_orch_attempt(examples)
    record["class_record"] = copy.deepcopy(examples["pi-run-0001"]["class_record"])
    require_boolean_rejection(validator, record, "'class_key'")

    record = raw_agent_orch_attempt(examples)
    record["class_key"] = "invented/class/key"
    require_error(validator, record, "$", "additionalProperties")


@pytest.mark.parametrize(
    "bad_verdict",
    [
        "pass",
        {"tier": "deterministic"},
        {"tier": "engine_validation", "oracle_cmd": "invented"},
    ],
)
def test_agent_orch_attempt_rejects_wrong_verdict_shape(
    validator: Draft202012Validator, examples: dict, bad_verdict: object
) -> None:
    record = raw_agent_orch_attempt(examples)
    record["verdict"] = bad_verdict
    assert list(validator.iter_errors(record))


@pytest.mark.parametrize(
    ("worker_exit_code", "validation_passed"),
    [(0, True), (0, False), (1, True), (1, False)],
)
def test_agent_orch_attempt_verified_success_is_exact_equivalence(
    validator: Draft202012Validator,
    examples: dict,
    worker_exit_code: int,
    validation_passed: bool,
) -> None:
    record = raw_agent_orch_attempt(examples)
    payload = record["agent_orch_attempt"]
    payload["worker_exit_code"] = worker_exit_code
    payload["validation_passed"] = validation_passed
    expected = worker_exit_code == 0 and validation_passed is True

    record["verified_success"] = expected
    assert not list(validator.iter_errors(record))

    record["verified_success"] = not expected
    require_error(validator, record, "$.verified_success", "const")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["usage"].update(basis="observed"),
        lambda r: r["usage"].update(source="agent-orch usage.json/accounting_status"),
        lambda r: r["usage"].pop("input_tokens"),
        lambda r: r.update(cost={"basis": "unavailable"}),
        lambda r: r["agent_orch_attempt"].pop("cost_usd"),
    ],
)
def test_agent_orch_attempt_measured_accounting_mapping_is_enforced(
    validator: Draft202012Validator, examples: dict, mutate
) -> None:
    record = raw_agent_orch_attempt(examples)
    mutate(record)
    assert list(validator.iter_errors(record))


@pytest.mark.parametrize(
    ("status", "reason"),
    [("unaccounted", "unaccounted"), (None, "missing usage receipt")],
)
def test_agent_orch_attempt_unavailable_accounting_mapping(
    validator: Draft202012Validator,
    examples: dict,
    status: str | None,
    reason: str,
) -> None:
    record = unavailable_raw_attempt(examples, status, reason)
    assert not list(validator.iter_errors(record))

    record["usage"]["input_tokens"] = 0
    require_boolean_rejection(validator, record, "0")


def test_agent_orch_attempt_unavailable_accounting_requires_reason(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = unavailable_raw_attempt(examples, "unaccounted", "unaccounted")
    del record["usage"]["unavailable_reason"]
    require_required_error(validator, record, "unavailable_reason")


def test_agent_orch_attempt_not_applicable_mapping_is_exact(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = unavailable_raw_attempt(examples, "not_applicable", "non-metered adapter")
    assert not list(validator.iter_errors(record))

    record["usage"]["unavailable_reason"] = "not applicable"
    require_error(validator, record, "$.usage.unavailable_reason", "const")


def test_agent_orch_attempt_cost_shape_does_not_weaken_legacy_kinds(
    validator: Draft202012Validator, examples: dict
) -> None:
    raw = raw_agent_orch_attempt(examples)
    raw["cost"] = {"basis": ["list", "marginal"], "usd_list": 0.1, "usd_marginal": 0.1}
    assert list(validator.iter_errors(raw))

    for attempt_id in ("a6a85c6b02c6", "bench-mixed-economy-0001", "pi-run-0001"):
        legacy = copy.deepcopy(examples[attempt_id])
        assert isinstance(legacy["cost"]["basis"], list)
        assert not list(validator.iter_errors(legacy))


def test_agent_orch_legacy_kind_rejects_new_attempt_only_shapes(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["a6a85c6b02c6"])
    record["verdict"] = {"tier": "engine_validation"}
    assert list(validator.iter_errors(record))

    record = copy.deepcopy(examples["a6a85c6b02c6"])
    record["provenance"]["source"] = "agent-orch-runs"
    require_error(validator, record, "$.provenance.source", "const")


# ---------------------------------------------------------------------------
# verified_success gate
# ---------------------------------------------------------------------------


def verified_record(base: dict) -> dict:
    """A complete verified pass record built from scratch test values only."""
    record = copy.deepcopy(base)
    record["verdict"] = "pass"
    record["failure_class"] = None
    record["verified_success"] = True
    record["supervisor_route"] = {
        "model": "scratch-supervisor-model",
        "effort": "high",
        "harness": "cli",
        "channel": "openrouter",
    }
    record["wall_clock_ms"] = 5000
    record["cost"] = priced_cost()
    return record


def test_verified_success_gate_accepts_complete_evidence(
    validator: Draft202012Validator, examples: dict
) -> None:
    assert not list(validator.iter_errors(verified_record(examples["pi-run-0002"])))


def test_verified_success_reason_is_conditional_and_truthful(
    validator: Draft202012Validator, examples: dict
) -> None:
    """Reasons are optional for legacy records but constrained on router runs."""
    unattested = copy.deepcopy(examples["pi-run-0001"])
    assert not list(validator.iter_errors(unattested))
    unattested["verified_success_reason"] = "supervisor_route_unattested"
    assert not list(validator.iter_errors(unattested))

    attested = copy.deepcopy(examples["pi-run-0001"])
    attested["supervisor_route"] = {
        "model": "scratch-supervisor-model",
        "effort": "low",
        "harness": "cli",
        "channel": "openrouter",
    }
    attested["verified_success_reason"] = "oracle_not_passed"
    assert not list(validator.iter_errors(attested))

    del attested["verified_success_reason"]
    require_required_error(validator, attested, "verified_success_reason")

    attested["verified_success_reason"] = "supervisor_route_unattested"
    require_error(validator, attested, "$.verified_success_reason", "enum")

    successful = verified_record(examples["pi-run-0002"])
    successful["verified_success_reason"] = "evidence_incomplete"
    require_boolean_rejection(validator, successful, "evidence_incomplete")


@pytest.mark.parametrize(
    "mutate",
    [
        # Authoritative harness output may omit the optional usage components:
        # genuinely unknown cached/reasoning/total stay null or absent and the
        # record can still be verified_success on known input/output tokens.
        lambda r: r["usage"].update(cached_input_tokens=None),
        lambda r: r["usage"].update(reasoning_tokens=None),
        lambda r: r["usage"].pop("cached_input_tokens"),
        lambda r: r["usage"].pop("reasoning_tokens"),
        lambda r: r["usage"].update(total_tokens=None),
        lambda r: r["usage"].pop("total_tokens"),
    ],
)
def test_verified_success_allows_genuinely_unknown_optional_components(
    validator: Draft202012Validator, examples: dict, mutate
) -> None:
    record = verified_record(examples["pi-run-0002"])
    mutate(record)
    assert not list(
        validator.iter_errors(record)
    ), "gate must not require the optional cached/reasoning/total components"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(supervisor_route=None),
        lambda r: r.pop("supervisor_route"),
        lambda r: r.update(wall_clock_ms=None),
        lambda r: r.pop("cost"),
        lambda r: r.update(verdict="fail"),
        lambda r: r.update(failure_class="spec_rejected"),
        lambda r: r["usage"].update(input_tokens=None),
        lambda r: r["usage"].pop("input_tokens"),
        lambda r: r["usage"].update(output_tokens=None),
        lambda r: r["usage"].pop("output_tokens"),
        lambda r: r["usage"].pop("source"),
        lambda r: r["usage"].update(source="an invented non-taxonomy string"),
        lambda r: r.update(oracle_cmd=None),
        lambda r: r.pop("class_record"),
        lambda r: r["usage"].update(
            basis="unavailable", unavailable_reason="text mode"
        ),
    ],
)
def test_verified_success_gate_rejects_missing_evidence(
    validator: Draft202012Validator, examples: dict, mutate
) -> None:
    record = verified_record(examples["pi-run-0002"])
    mutate(record)
    assert list(
        validator.iter_errors(record)
    ), "gate must not accept incomplete evidence"


# ---------------------------------------------------------------------------
# Raw benchmark v6 payload (D209: preserved source facts, never invented)
# ---------------------------------------------------------------------------


def raw_benchmark_v6_run(examples: dict) -> dict:
    """Return the raw benchmarkV6Run example for mutation tests."""
    return copy.deepcopy(examples[BENCHMARK_V6_RUN_ID])


def test_benchmark_run_payload_is_one_of_two_closed_shapes(schema: dict) -> None:
    payload = schema["$defs"]["benchmarkRunPayload"]
    assert payload["oneOf"] == [
        {"$ref": "#/$defs/crewRunRecord"},
        {"$ref": "#/$defs/benchmarkV6Run"},
    ]
    raw = schema["$defs"]["benchmarkV6Run"]
    assert raw["additionalProperties"] is False
    assert set(raw["properties"]) == {
        "schema_version",
        "sidecar_sha256",
        "source_csv",
        "generated_at",
        "run_id",
        "task_key",
        "class",
        "worker",
        "usage",
        "acceptance",
        "elapsed_ms",
        "source_timestamps",
    }
    # The v6 sidecar provides neither a crew name nor a crews-file identity;
    # neither may exist as a machine field in the raw shape.
    assert "crew_name" not in raw["properties"]
    assert "crews_file_sha256" not in raw["properties"]
    assert "stages" not in raw["properties"]
    assert "role_composition" not in json.dumps(raw)
    # The legacy crew-run envelope stays valid only for committed history.
    assert schema["$defs"]["crewRunRecord"].get("deprecated") is True
    legacy_description = schema["$defs"]["crewRunRecord"]["description"]
    assert "append-only ledger" in legacy_description
    assert "benchmark:v6:" in legacy_description


def test_raw_benchmark_example_validates_and_carries_no_fabricated_facts(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = examples[BENCHMARK_V6_RUN_ID]
    assert not list(validator.iter_errors(record))
    payload = json.dumps(record["benchmark_run"])
    assert "crew_name" not in payload
    assert "crews_file_sha256" not in payload
    assert "mixed-economy" not in json.dumps(record)
    assert "benchmark.crew-run/1" not in payload
    # The sidecar digest appears only as the honestly named sidecar fact, and
    # no fabricated field name appears as a machine key anywhere in the record
    # (the prose notes may name what they refuse to fabricate).
    assert record["benchmark_run"]["sidecar_sha256"]

    def keys_of(value: object) -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                found.append(str(key))
                found.extend(keys_of(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(keys_of(item))
        return found

    assert not [k for k in keys_of(record) if "crew" in k]


def test_legacy_benchmark_shape_remains_valid_for_committed_ledger_lines(
    validator: Draft202012Validator, examples: dict
) -> None:
    """Schema evolution never invalidates the append-only ledger history."""
    legacy = examples[LEGACY_BENCHMARK_ID]
    assert legacy["benchmark_run"]["schema_version"] == "benchmark.crew-run/1"
    assert legacy["benchmark_run"]["crew_name"] == "mixed-economy"
    assert not list(validator.iter_errors(legacy))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crew_name", "mixed-economy"),
        ("crews_file_sha256", "0" * 64),
        ("stages", []),
        ("role_composition", ["author"]),
    ],
)
def test_fabricated_crew_fields_planted_into_raw_benchmark_record_rejected(
    validator: Draft202012Validator,
    examples: dict,
    field: str,
    value: object,
) -> None:
    """Astra reproducer at the schema layer: the crew-run envelope fields are
    not readable into the raw v6 shape — planting any of them fails oneOf."""
    record = raw_benchmark_v6_run(examples)
    record["benchmark_run"][field] = value
    require_error(validator, record, "$.benchmark_run", "oneOf")


def test_benchmark_payload_shapes_are_disjoint(
    validator: Draft202012Validator, examples: dict
) -> None:
    # A raw record missing a required v6 fact is not rescued by the legacy
    # branch: the two payload shapes admit no interpolation.
    record = raw_benchmark_v6_run(examples)
    del record["benchmark_run"]["sidecar_sha256"]
    assert list(validator.iter_errors(record))

    record = raw_benchmark_v6_run(examples)
    record["benchmark_run"]["schema_version"] = "benchmark.crew-run/1"
    assert list(validator.iter_errors(record))

    # The legacy example fails as a raw shape too (no sidecar_sha256).
    legacy = copy.deepcopy(examples[LEGACY_BENCHMARK_ID])
    legacy["benchmark_run"].pop("crew_name")
    assert list(validator.iter_errors(legacy))


def test_raw_benchmark_worker_covers_only_join_verified_fields(schema: dict) -> None:
    worker = schema["$defs"]["benchmarkV6Run"]["properties"]["worker"]["$ref"]
    assert worker == "#/$defs/crewWorker"
    # The raw shape reuses the crew worker def (model/harness/effort/model_family)
    # — the four fields the import verifies against the CSV row.
    assert set(schema["$defs"]["crewWorker"]["properties"]) == {
        "model",
        "harness",
        "effort",
        "model_family",
    }


# ---------------------------------------------------------------------------
# Envelope strictness
# ---------------------------------------------------------------------------


def test_schema_version_1_rejected(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    record["schema_version"] = 1
    require_error(validator, record, "$.schema_version", "const")


def test_v1_aliases_stay_retired(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    record["amount_usd"] = "0.01"  # v1 top-level cost alias
    record["usage"]["usage_capture"] = "native_json"  # v1 usage field
    record["interactive_extra"] = True
    additional = [
        e
        for e in validator.iter_errors(record)
        if e.validator == "additionalProperties"
    ]
    assert additional
    messages = " | ".join(e.message for e in additional)
    assert "'amount_usd'" in messages and "'interactive_extra'" in messages
    record = copy.deepcopy(examples["pi-run-0001"])
    record["usage"]["usage_capture"] = "none"
    require_error(validator, record, "$.usage", "additionalProperties")


@pytest.mark.skipif(
    importlib.util.find_spec("rfc3339_validator") is None,
    reason=(
        "jsonschema date-time checking needs rfc3339-validator "
        "(absent here, same as catalog.py)"
    ),
)
def test_captured_at_format_checked_when_checker_available(
    validator: Draft202012Validator, examples: dict
) -> None:
    record = copy.deepcopy(examples["pi-run-0001"])
    record["captured_at"] = "2026-09-09 12:00:00"
    assert list(validator.iter_errors(record))
