"""Focused P5-2 tests for ``ladder_derivation.py`` — deriving cheapest-first
ladders from the attempt ledger and diffing against hand-authored sources.

Every test constructs deterministic attempt records in memory and calls
:func:`derive_ladders` or the diff helpers directly. No real router state,
ledger file, or provider is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lee_llm_router.staffing.ladder_derivation import (
    SCHEMA_VERSION,
    derive_ladders,
    diff_against_benchmark,
    diff_against_crews,
    render_ladder_diff,
)
from lee_llm_router.staffing.rollup import MINIMUM_SAMPLE_SIZE

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "staffing"
    / ("attempt-record-router-run-unavailable.json")
)

CLASS_KEY_IMPL = "impl/deterministic/none/s/python"
CLASS_KEY_PLAN = "plan/deterministic/tooling/s/python"

REAL_ROLE_ALIASES = {
    "code-review": "code-review",
    "coder": "coder",
    "implementation": "coder",
    "planner": "planner",
    "reviewer": "code-review",
}


def _record(
    *,
    attempt_id: str,
    route_id: str,
    class_key: str = CLASS_KEY_IMPL,
    verified_success: bool = True,
    usd_marginal: float | None = 0.01,
    usd_list: float | None = 0.015,
    verdict: str = "pass",
    wall_clock_ms: int | None = 100,
) -> dict:
    """Build a deterministic scratch attempt record in memory."""
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record["attempt_id"] = attempt_id
    record["router_event"]["route_id"] = route_id
    record["class_record"] = {
        "class_key": class_key,
        "role": class_key.split("/", 1)[0],
        "oracle_type": class_key.split("/")[1],
        "domain_tags": [],
        "size_band": class_key.split("/")[3],
        "language": class_key.split("/")[4],
    }
    record["verdict"] = verdict
    record["oracle_cmd"] = "check"
    record["usage"] = {
        "basis": "provider_reported",
        "input_tokens": 10,
        "output_tokens": 5,
    }
    record["wall_clock_ms"] = wall_clock_ms
    record["verified_success"] = verified_success

    if usd_marginal is not None and usd_list is not None:
        record["cost"] = {
            "basis": "calculated",
            "usd_list": usd_list,
            "usd_marginal": usd_marginal,
        }
    else:
        record["cost"] = {"basis": ["unavailable"]}

    return record


def _records_for_route(
    prefix: str,
    route_id: str,
    class_key: str,
    count: int,
    usd_marginal: float,
    pass_rate: float = 1.0,
) -> list[dict]:
    """Generate ``count`` attempt records for one route/class pair.

    Args:
        prefix: Attempt id prefix.
        route_id: Route id string.
        class_key: Class key string.
        count: Number of records to generate.
        usd_marginal: The ``cost.usd_marginal`` for verified-success records.
        pass_rate: Fraction of records that have ``verified_success: True``.

    Returns:
        A list of record dicts.
    """
    records: list[dict] = []
    verified_count = int(count * pass_rate)
    for i in range(count):
        verified = i < verified_count
        records.append(
            _record(
                attempt_id=f"{prefix}-{i:04d}",
                route_id=route_id,
                class_key=class_key,
                verified_success=verified,
                usd_marginal=usd_marginal if verified else None,
                usd_list=usd_marginal * 1.5 if verified else None,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Fixture helpers for patching rollup_ledger and ledger reads
# ---------------------------------------------------------------------------


def _monkeypatch_ledger(monkeypatch, records: list[dict]) -> None:
    """Replace ``rollup_ledger`` and the ledger reader with deterministic data.

    Patches ``rollup_ledger`` to call ``build_rollup(records)`` and the
    internal ``_read_materialized_records`` to return de-duplicated records.
    """

    from lee_llm_router.staffing import rollup as rollup_module

    original_build_rollup = rollup_module.build_rollup

    def fake_rollup_ledger(path=None):
        return original_build_rollup(records)

    # ladder_derivation imports `rollup_ledger` by name (`from ...rollup import
    # rollup_ledger`), binding it into its own module namespace at import time.
    # Patching rollup_module.rollup_ledger alone would not affect that already
    # -bound reference, so the module ladder_derivation actually calls through
    # is patched directly.
    import lee_llm_router.staffing.ladder_derivation as ld_module

    monkeypatch.setattr(ld_module, "rollup_ledger", fake_rollup_ledger)

    # Also patch the internal _read_materialized_records in ladder_derivation
    def fake_read_materialized(path=None):
        return records

    monkeypatch.setattr(ld_module, "_read_materialized_records", fake_read_materialized)

    # Patch resolve_attempts_path in the ledger module so the patched
    # rollup_ledger never hits the real file system.
    from lee_llm_router.staffing import ledger as ledger_module

    monkeypatch.setattr(
        ledger_module, "resolve_attempts_path", lambda p=None: "/dev/null"
    )


# ---------------------------------------------------------------------------
# Test: class with n>=5 for one route (derived, single rung)
# ---------------------------------------------------------------------------


def test_derive_single_route_one_rung(monkeypatch) -> None:
    """A class with n>=5 for exactly one route yields one derived rung."""
    records = _records_for_route(
        prefix="r1",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE + 1,
        usd_marginal=0.005,
        pass_rate=1.0,
    )
    _monkeypatch_ledger(monkeypatch, records)

    derived = derive_ladders()
    assert derived["schema_version"] == SCHEMA_VERSION
    assert derived["derived_at"] is not None

    classes = derived["classes"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls["class_key"] == CLASS_KEY_IMPL
    assert cls["evidence_status"] == "derived"
    rungs = cls["rungs"]
    assert len(rungs) == 1
    assert rungs[0]["route_id"] == "route-alpha"
    assert rungs[0]["n"] == MINIMUM_SAMPLE_SIZE + 1
    assert rungs[0]["mean_cost_usd_marginal"] == 0.005


# ---------------------------------------------------------------------------
# Test: class with n>=5 for two routes with different marginal costs
# ---------------------------------------------------------------------------


def test_derive_two_routes_cheapest_first(monkeypatch) -> None:
    """Two routes with different mean marginal cost: cheapest ranked first."""
    records_a = _records_for_route(
        prefix="r1",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE + 1,
        usd_marginal=0.01,
        pass_rate=1.0,
    )
    records_b = _records_for_route(
        prefix="r2",
        route_id="route-beta",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE + 2,
        usd_marginal=0.005,
        pass_rate=0.9,
    )
    _monkeypatch_ledger(monkeypatch, records_a + records_b)

    derived = derive_ladders()
    classes = derived["classes"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls["evidence_status"] == "derived"
    rungs = cls["rungs"]
    assert len(rungs) == 2
    # Cheapest first: route-beta (0.005) before route-alpha (0.01)
    assert rungs[0]["route_id"] == "route-beta"
    assert rungs[1]["route_id"] == "route-alpha"
    assert rungs[0]["mean_cost_usd_marginal"] == 0.005
    assert rungs[1]["mean_cost_usd_marginal"] == 0.01


# ---------------------------------------------------------------------------
# Test: tie-breaking by higher pass_rate
# ---------------------------------------------------------------------------


def test_derive_tie_break_by_pass_rate(monkeypatch) -> None:
    """Two routes with same mean cost but different pass_rate: higher pass first."""
    # Same cost for both
    records_a = _records_for_route(
        prefix="r1",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.01,
        pass_rate=0.8,  # 4 of 5 pass
    )
    records_b = _records_for_route(
        prefix="r2",
        route_id="route-beta",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.01,
        pass_rate=1.0,  # 5 of 5 pass
    )
    _monkeypatch_ledger(monkeypatch, records_a + records_b)

    derived = derive_ladders()
    rungs = derived["classes"][0]["rungs"]
    assert len(rungs) == 2
    # route-beta has higher pass_rate (1.0 > 0.8), so it should be first
    assert rungs[0]["route_id"] == "route-beta"
    assert rungs[0]["pass_rate"] == 1.0
    assert rungs[1]["route_id"] == "route-alpha"
    assert rungs[1]["pass_rate"] == 0.8


# ---------------------------------------------------------------------------
# Test: no route at n>=5 — insufficient evidence
# ---------------------------------------------------------------------------


def test_derive_insufficient_evidence(monkeypatch) -> None:
    """A class with no route at n>=5 gets 'insufficient evidence' with empty rungs."""
    records = _records_for_route(
        prefix="r1",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE - 1,  # n=4, below minimum
        usd_marginal=0.01,
        pass_rate=1.0,
    )
    _monkeypatch_ledger(monkeypatch, records)

    derived = derive_ladders()
    classes = derived["classes"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls["evidence_status"] == "insufficient evidence, hand ladder retained"
    assert cls["rungs"] == []


# ---------------------------------------------------------------------------
# Test: two classes in the ledger
# ---------------------------------------------------------------------------


def test_derive_two_classes(monkeypatch) -> None:
    """Two distinct class_keys each with n>=5 produce separate ladders."""
    records_a = _records_for_route(
        prefix="r1",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.01,
    )
    records_b = _records_for_route(
        prefix="r2",
        route_id="route-beta",
        class_key=CLASS_KEY_PLAN,
        count=MINIMUM_SAMPLE_SIZE + 1,
        usd_marginal=0.02,
    )
    _monkeypatch_ledger(monkeypatch, records_a + records_b)

    derived = derive_ladders()
    classes = derived["classes"]
    assert len(classes) == 2

    class_keys = sorted(c["class_key"] for c in classes)
    assert class_keys == [CLASS_KEY_IMPL, CLASS_KEY_PLAN]


# ---------------------------------------------------------------------------
# Test: diff against benchmark — agreement
# ---------------------------------------------------------------------------


def test_diff_benchmark_agreement() -> None:
    """Derived ladder order agrees with a benchmark ladder's rung order."""
    # Build a synthetic derived ladder
    derived = {
        "schema_version": SCHEMA_VERSION,
        "derived_at": "2026-09-15",
        "classes": [
            {
                "class_key": CLASS_KEY_IMPL,
                "evidence_status": "derived",
                "rungs": [
                    {
                        "route_id": "codex-gpt-5-6-sol-low-openai-sub",
                        "n": 7,
                        "verified_pass": 7,
                        "pass_rate": 1.0,
                        "mean_cost_usd_marginal": 0.005,
                    },
                ],
            },
        ],
    }

    # Build a synthetic benchmark with matching model_aliases and ladders
    benchmark_data = {
        "schema_version": "benchmark.escalation-ladder/1",
        "role_aliases": REAL_ROLE_ALIASES,
        "model_aliases": {
            "gpt-5.6-sol": {
                "model_family": "sol",
                "display_name": "Sol",
            },
        },
        "ladders": [
            {
                "role": "coder",
                "ladder_id": "coder-default",
                "variant": "default",
                "label": "Coder default",
                "rungs": [
                    {
                        "rung_id": "sol-low-codex",
                        "label": "Sol Low via Codex",
                        "worker": {
                            "model_family": "sol",
                            "harness": "codex",
                            "effort": "low",
                        },
                    },
                ],
            },
        ],
    }

    diffs = diff_against_benchmark(
        derived,
        benchmark_data_override=benchmark_data,
    )

    assert len(diffs) == 1
    assert diffs[0]["agreement"] is True
    assert diffs[0]["ladder_id"] == "coder-default"


# ---------------------------------------------------------------------------
# Test: diff against benchmark — disagreement
# ---------------------------------------------------------------------------


def test_diff_benchmark_disagreement() -> None:
    """Test that disagreement is detected when the model_family order differs."""
    # Build a derived ladder with two rungs, cheapest first
    derived = {
        "schema_version": SCHEMA_VERSION,
        "derived_at": "2026-09-15",
        "classes": [
            {
                "class_key": CLASS_KEY_IMPL,
                "evidence_status": "derived",
                "rungs": [
                    {
                        "route_id": "route-beta",
                        "n": 7,
                        "verified_pass": 7,
                        "pass_rate": 1.0,
                        "mean_cost_usd_marginal": 0.005,
                    },
                    {
                        "route_id": "route-alpha",
                        "n": 6,
                        "verified_pass": 6,
                        "pass_rate": 1.0,
                        "mean_cost_usd_marginal": 0.01,
                    },
                ],
            },
        ],
    }

    # Benchmark has them in the OPPOSITE order
    benchmark_data = {
        "schema_version": "benchmark.escalation-ladder/1",
        "role_aliases": REAL_ROLE_ALIASES,
        "model_aliases": {
            "gpt-5.6-sol": {
                "model_family": "sol",
                "display_name": "Sol",
            },
            "gpt-5.6-terra": {
                "model_family": "terra",
                "display_name": "Terra",
            },
        },
        "ladders": [
            {
                "role": "coder",
                "ladder_id": "coder-default",
                "variant": "default",
                "label": "Coder default",
                "rungs": [
                    {
                        "rung_id": "rung-alpha",
                        "label": "Alpha rung",
                        "worker": {
                            "model_family": "sol",
                            "harness": "codex",
                            "effort": "high",
                        },
                    },
                    {
                        "rung_id": "rung-beta",
                        "label": "Beta rung",
                        "worker": {
                            "model_family": "terra",
                            "harness": "codex",
                            "effort": "high",
                        },
                    },
                ],
            },
        ],
    }

    diffs = diff_against_benchmark(
        derived,
        benchmark_data_override=benchmark_data,
    )

    assert len(diffs) == 1
    assert diffs[0]["agreement"] is False
    assert len(diffs[0]["disagreements"]) > 0


# ---------------------------------------------------------------------------
# Test: diff against crews.yaml — agreement
# ---------------------------------------------------------------------------


def test_diff_crews_agreement(monkeypatch) -> None:
    """Derived ladder order agrees with a crew's escalation_ladder."""
    records = _records_for_route(
        prefix="r1",
        route_id="route-beta",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.005,
    ) + _records_for_route(
        prefix="r2",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.01,
    )
    _monkeypatch_ledger(monkeypatch, records)

    derived = derive_ladders()

    crews_ladders = [
        {
            "crew_id": "test-crew",
            "escalation_ladder": ["route-beta", "route-alpha"],
        }
    ]

    diffs = diff_against_crews(
        derived,
        crews_ladders_override=crews_ladders,
    )

    assert len(diffs) == 1
    assert diffs[0]["agreement"] is True
    assert diffs[0]["crew_id"] == "test-crew"


# ---------------------------------------------------------------------------
# Test: diff against crews.yaml — disagreement
# ---------------------------------------------------------------------------


def test_diff_crews_disagreement(monkeypatch) -> None:
    """Derived ladder order disagrees with a crew's escalation_ladder."""
    records = _records_for_route(
        prefix="r1",
        route_id="route-alpha",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.01,
    ) + _records_for_route(
        prefix="r2",
        route_id="route-beta",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.005,  # cheaper
    )
    _monkeypatch_ledger(monkeypatch, records)

    derived = derive_ladders()

    # Crew has them in the OPPOSITE order (alpha first, beta second)
    crews_ladders = [
        {
            "crew_id": "test-crew",
            "escalation_ladder": ["route-alpha", "route-beta"],
        }
    ]

    diffs = diff_against_crews(
        derived,
        crews_ladders_override=crews_ladders,
    )

    assert len(diffs) == 1
    assert diffs[0]["agreement"] is False
    assert diffs[0]["crew_id"] == "test-crew"


# ---------------------------------------------------------------------------
# Test: render_ladder_diff produces readable text
# ---------------------------------------------------------------------------


def test_render_ladder_diff_text() -> None:
    """Text rendering includes headings and markers for agreement/disagreement."""
    benchmark_diffs = [
        {
            "source": "benchmark",
            "ladder_id": "coder-default",
            "role": "coder",
            "label": "Coder default",
            "agreement": True,
            "disagreements": [],
        },
        {
            "source": "benchmark",
            "ladder_id": "planner-default",
            "role": "planner",
            "label": "Planner default",
            "agreement": False,
            "disagreements": [
                {
                    "position": 0,
                    "message": (
                        "derived has route-z at position 0; " "benchmark has sol/codex"
                    ),
                }
            ],
        },
    ]

    crews_diffs = [
        {
            "source": "crews.yaml",
            "crew_id": "test-crew",
            "agreement": True,
            "message": "agrees",
        },
    ]

    text = render_ladder_diff(benchmark_diffs, crews_diffs)
    assert "Diff against benchmark" in text
    assert "✓ coder-default" in text
    assert "✗ planner-default" in text
    assert "Diff against crews.yaml" in text
    assert "✓ crew test-crew" in text


# ---------------------------------------------------------------------------
# Test: unmapped model in diff
# ---------------------------------------------------------------------------


def test_diff_unmapped_model() -> None:
    """A route whose model has no model_aliases entry reports as 'unmapped'."""
    from lee_llm_router.staffing.ladder_derivation import _resolve_route_model_family

    catalog_routes = {
        "route-unknown": type("Route", (), {"model": "unknown-model-v42"})(),
    }

    model_aliases = {
        "gpt-5.6-sol": {"model_family": "sol"},
    }

    family = _resolve_route_model_family("route-unknown", catalog_routes, model_aliases)
    assert family == "unmapped"


# ---------------------------------------------------------------------------
# Test: unknown route in catalog
# ---------------------------------------------------------------------------


def test_diff_unknown_route_id() -> None:
    """A route_id not in the catalog routes map reports as 'unmapped'."""
    from lee_llm_router.staffing.ladder_derivation import _resolve_route_model_family

    catalog_routes: dict = {}

    family = _resolve_route_model_family("nonexistent-route", catalog_routes, {})
    assert family == "unmapped"


# ---------------------------------------------------------------------------
# Test: tuple-typed crew ladders load
# ---------------------------------------------------------------------------


def test_load_crews_ladders_tuple(monkeypatch) -> None:
    """_load_crews_ladders loads escalation_ladder when stored as a tuple."""
    import lee_llm_router.staffing.catalog as cat_module
    from lee_llm_router.staffing.ladder_derivation import _load_crews_ladders

    fake_crew = type(
        "Crew",
        (),
        {
            "crew_id": "tuple-crew",
            "escalation_ladder": ("route-alpha", "route-beta"),
        },
    )()
    fake_catalog = type(
        "Catalog",
        (),
        {"crews": type("Crews", (), {"crews": [fake_crew]})()},
    )()

    monkeypatch.setattr(cat_module, "load_staffing_catalog", lambda p: fake_catalog)

    ladders = _load_crews_ladders()
    assert len(ladders) == 1
    assert ladders[0]["crew_id"] == "tuple-crew"
    assert ladders[0]["escalation_ladder"] == ["route-alpha", "route-beta"]


# ---------------------------------------------------------------------------
# Test: crews catalog error yields error entry and renders ERROR:
# ---------------------------------------------------------------------------


def test_load_crews_catalog_error(monkeypatch) -> None:
    """A crews catalog error yields the error entry and renders ERROR:."""
    import lee_llm_router.staffing.catalog as cat_module
    from lee_llm_router.staffing.catalog import StaffingCatalogError
    from lee_llm_router.staffing.ladder_derivation import _load_crews_ladders

    def _raise_error(path):
        raise StaffingCatalogError("malformed yaml in crews catalog", document="crews")

    monkeypatch.setattr(cat_module, "load_staffing_catalog", _raise_error)

    ladders = _load_crews_ladders()
    assert len(ladders) == 1
    assert ladders[0]["source"] == "crews.yaml"
    assert "malformed yaml in crews catalog" in ladders[0]["error"]

    diffs = diff_against_crews(
        {"schema_version": SCHEMA_VERSION, "classes": []},
        crews_ladders_override=ladders,
    )
    assert len(diffs) == 1
    assert "error" in diffs[0]

    rendered = render_ladder_diff([], diffs)
    assert "ERROR: malformed yaml in crews catalog" in rendered


# ---------------------------------------------------------------------------
# Test: real-file role join
# ---------------------------------------------------------------------------


def test_real_file_role_join() -> None:
    """Real benchmark ladders join derived impl/.../python to coder-default."""
    repo_parent = Path(__file__).resolve().parents[2]
    benchmark_path = (
        repo_parent / "ai-workforce-benchmark" / "config" / "escalation-ladders.json"
    )
    if not benchmark_path.is_file():
        pytest.skip(f"Benchmark file absent: {benchmark_path}")

    derived = {
        "schema_version": SCHEMA_VERSION,
        "derived_at": "2026-09-15",
        "classes": [
            {
                "class_key": CLASS_KEY_IMPL,
                "evidence_status": "derived",
                "rungs": [
                    {
                        "route_id": "codex-gpt-5-6-sol-low-openai-sub",
                        "n": 7,
                        "verified_pass": 7,
                        "pass_rate": 1.0,
                        "mean_cost_usd_marginal": 0.005,
                    }
                ],
                "excluded_routes": [],
            }
        ],
    }

    diffs = diff_against_benchmark(derived, benchmark_path=benchmark_path)
    coder_diffs = [
        d
        for d in diffs
        if d.get("ladder_id") == "coder-default"
        and d.get("class_key") == CLASS_KEY_IMPL
    ]
    assert len(coder_diffs) == 1


# ---------------------------------------------------------------------------
# Test: insufficient-evidence entries for benchmark and crew
# ---------------------------------------------------------------------------


def test_insufficient_evidence_benchmark_and_crew() -> None:
    """Insufficient-evidence entries for a benchmark ladder and for a crew."""
    derived_insufficient = {
        "schema_version": SCHEMA_VERSION,
        "derived_at": "2026-09-15",
        "classes": [
            {
                "class_key": CLASS_KEY_IMPL,
                "evidence_status": "insufficient evidence, hand ladder retained",
                "rungs": [],
                "excluded_routes": [],
            }
        ],
    }

    benchmark_data = {
        "schema_version": "benchmark.escalation-ladder/1",
        "role_aliases": REAL_ROLE_ALIASES,
        "model_aliases": {},
        "ladders": [
            {
                "role": "coder",
                "ladder_id": "coder-default",
                "variant": "default",
                "label": "Coder default",
                "rungs": [],
            }
        ],
    }

    b_diffs = diff_against_benchmark(
        derived_insufficient, benchmark_data_override=benchmark_data
    )
    assert len(b_diffs) == 1
    assert b_diffs[0]["agreement"] is None
    assert b_diffs[0]["status"] == "insufficient evidence, hand ladder retained"
    assert b_diffs[0]["minimum_sample_size"] == MINIMUM_SAMPLE_SIZE
    assert b_diffs[0]["classes_considered"] == [CLASS_KEY_IMPL]

    c_diffs = diff_against_crews(
        derived_insufficient,
        crews_ladders_override=[
            {"crew_id": "crew-a", "escalation_ladder": ["route-1"]}
        ],
    )
    assert len(c_diffs) == 1
    assert c_diffs[0]["agreement"] is None
    assert c_diffs[0]["status"] == "insufficient evidence, hand ladder retained"
    assert c_diffs[0]["minimum_sample_size"] == MINIMUM_SAMPLE_SIZE
    assert c_diffs[0]["classes_considered"] == [CLASS_KEY_IMPL]


# ---------------------------------------------------------------------------
# Test: per-class entries when two classes of one role are both derived
# ---------------------------------------------------------------------------


def test_per_class_entries_when_two_classes_derived() -> None:
    """Two derived classes of one role produce separate diff entries for that ladder."""
    derived = {
        "schema_version": SCHEMA_VERSION,
        "derived_at": "2026-09-15",
        "classes": [
            {
                "class_key": "impl/deterministic/none/s/python",
                "evidence_status": "derived",
                "rungs": [
                    {
                        "route_id": "route-alpha",
                        "n": 5,
                        "verified_pass": 5,
                        "pass_rate": 1.0,
                        "mean_cost_usd_marginal": 0.01,
                    }
                ],
                "excluded_routes": [],
            },
            {
                "class_key": "impl/deterministic/none/xs/python",
                "evidence_status": "derived",
                "rungs": [
                    {
                        "route_id": "route-beta",
                        "n": 6,
                        "verified_pass": 6,
                        "pass_rate": 1.0,
                        "mean_cost_usd_marginal": 0.005,
                    }
                ],
                "excluded_routes": [],
            },
        ],
    }

    benchmark_data = {
        "schema_version": "benchmark.escalation-ladder/1",
        "role_aliases": REAL_ROLE_ALIASES,
        "model_aliases": {},
        "ladders": [
            {
                "role": "coder",
                "ladder_id": "coder-default",
                "variant": "default",
                "label": "Coder default",
                "rungs": [],
            }
        ],
    }

    diffs = diff_against_benchmark(derived, benchmark_data_override=benchmark_data)
    coder_entries = [d for d in diffs if d.get("ladder_id") == "coder-default"]
    assert len(coder_entries) == 2
    keys = {d.get("class_key") for d in coder_entries}
    assert keys == {
        "impl/deterministic/none/s/python",
        "impl/deterministic/none/xs/python",
    }


# ---------------------------------------------------------------------------
# Test: zero-success routes are not rungs
# ---------------------------------------------------------------------------


def test_zero_success_route_excluded_from_rungs(monkeypatch) -> None:
    """A class whose only n>=5 route has no successes is insufficient."""
    records = _records_for_route(
        prefix="zero",
        route_id="route-failing",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE + 2,
        usd_marginal=0.01,
        pass_rate=0.0,
    )
    _monkeypatch_ledger(monkeypatch, records)

    derived = derive_ladders()
    classes = derived["classes"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls["evidence_status"] == "insufficient evidence, hand ladder retained"
    assert cls["rungs"] == []
    assert len(cls["excluded_routes"]) == 1
    assert cls["excluded_routes"][0] == {
        "route_id": "route-failing",
        "n": MINIMUM_SAMPLE_SIZE + 2,
        "verified_pass": 0,
        "reason": "no verified success",
    }

    # Also verify render_ladder_diff shows the excluded route under the entry
    diff_entry = {
        "source": "benchmark",
        "ladder_id": "coder-default",
        "role": "coder",
        "agreement": None,
        "status": "insufficient evidence, hand ladder retained",
        "classes_considered": [CLASS_KEY_IMPL],
        "minimum_sample_size": MINIMUM_SAMPLE_SIZE,
        "excluded_routes": cls["excluded_routes"],
    }
    rendered = render_ladder_diff([diff_entry], [])
    assert (
        f"excluded: route-failing (n={MINIMUM_SAMPLE_SIZE + 2}, verified_pass=0)"
        in rendered
    )


def test_zero_success_route_excluded_when_other_success_present(monkeypatch) -> None:
    """When a class has successes and failures, zero-success is excluded."""
    records_good = _records_for_route(
        prefix="good",
        route_id="route-good",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE,
        usd_marginal=0.01,
        pass_rate=1.0,
    )
    records_bad = _records_for_route(
        prefix="bad",
        route_id="route-bad",
        class_key=CLASS_KEY_IMPL,
        count=MINIMUM_SAMPLE_SIZE + 1,
        usd_marginal=0.005,
        pass_rate=0.0,
    )
    _monkeypatch_ledger(monkeypatch, records_good + records_bad)

    derived = derive_ladders()
    cls = derived["classes"][0]
    assert cls["evidence_status"] == "derived"
    assert len(cls["rungs"]) == 1
    assert cls["rungs"][0]["route_id"] == "route-good"
    assert len(cls["excluded_routes"]) == 1
    assert cls["excluded_routes"][0]["route_id"] == "route-bad"
    assert cls["excluded_routes"][0]["verified_pass"] == 0


def test_diff_benchmark_cost_unknown_rendered() -> None:
    """A rung with mean_cost_usd_marginal: None renders cost=unknown."""
    derived = {
        "schema_version": SCHEMA_VERSION,
        "derived_at": "2026-09-15",
        "classes": [
            {
                "class_key": CLASS_KEY_IMPL,
                "evidence_status": "derived",
                "rungs": [
                    {
                        "route_id": "route-free",
                        "n": 5,
                        "verified_pass": 2,
                        "pass_rate": 0.4,
                        "mean_cost_usd_marginal": None,
                    },
                ],
                "excluded_routes": [],
            },
        ],
    }
    benchmark_data = {
        "schema_version": "benchmark.escalation-ladder/1",
        "role_aliases": REAL_ROLE_ALIASES,
        "model_aliases": {},
        "ladders": [
            {
                "role": "coder",
                "ladder_id": "coder-default",
                "variant": "default",
                "label": "Coder default",
                "rungs": [],
            },
        ],
    }
    diffs = diff_against_benchmark(derived, benchmark_data_override=benchmark_data)
    assert len(diffs) == 1
    assert diffs[0]["agreement"] is False
    msg = diffs[0]["disagreements"][0]["message"]
    assert "cost=unknown" in msg
    assert "cost=None" not in msg
