"""Live snapshot oracle for the staffing catalog (P0-3p).

Proves, against the live ``/home/lee/projects/auto-orch/config/crews.yaml``
and the catalog YAML in ``config/staffing/``:

1. Every live worker id maps by its command-derived exact
   ``(model, effort, harness, channel)`` tuple to exactly one route in
   ``config/staffing/routes.yaml``, honoring the known backward-compatible
   byte-identical alias workers without inventing models.
2. Every route with ``status: unpriced`` carries a nonempty
   ``status_reason``.
3. The 14 governed ``crew_name`` values in ``config/staffing/crews.yaml``
   exactly equal the 14 live crew names, and each governed crew's five
   stage bindings resolve to recorded route refs that match the live
   stage worker's identity tuple.
4. The two interactive crews and the ``auto`` computed placeholder load
   as typed ``Crew`` objects with no field dropped.

Read-only and deterministic: both the live crews file and the staffing
documents load through the existing public loaders
(``lee_llm_router.crews.load_crews`` and
``lee_llm_router.staffing.load_staffing_document``); no provider calls
and no prompts are involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lee_llm_router.crew_page import HARNESS_BY_PROVIDER
from lee_llm_router.crews import (
    STAGE_NAMES,
    CrewsConfig,
    Worker,
    load_crews,
    resolve_crews_path,
    resolve_worker,
)
from lee_llm_router.staffing import (
    Crew,
    CrewsCatalog,
    Route,
    RoutesCatalog,
    load_staffing_document,
)

STAFFING_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"

# Known backward-compat alias workers in the live crews.yaml whose commands
# are byte-identical to their canonical counterparts (per the live file's own
# comments). Each must deduplicate to the canonical worker's route tuple.
ALIAS_TO_CANONICAL: dict[str, str] = {
    "claude_fable_high": "claude_fable51_high",
    "antigravity_gemini37_flash_high": "antigravity_gemini38_flash_high",
    "antigravity_gemini37_flash_medium": "antigravity_gemini38_flash_medium",
    "antigravity_gemini37_flash_low": "antigravity_gemini38_flash_low",
}

GOVERNED_CREW_COUNT = 14

# Route identity in staffing catalog order (model, effort, harness, channel)
# — the tuple every live worker must map to exactly one route by.
Identity = tuple[str | None, str | None, str, str]


def worker_identity(worker: Worker) -> Identity:
    """Derive a worker's exact ``(model, effort, harness, channel)`` tuple.

    Uses the public crews resolution pipeline only: ``resolve_worker`` for
    the command-derived provider/model/effort and
    ``crew_page.HARNESS_BY_PROVIDER`` for the catalog harness spelling.
    """
    resolved = resolve_worker(worker)
    harness = HARNESS_BY_PROVIDER.get(resolved.provider)
    assert harness is not None, (
        f"worker {worker.id!r} resolves to provider {resolved.provider!r} "
        "with no catalog harness spelling"
    )
    return (resolved.model, resolved.effort, harness, resolved.channel)


def route_identity(route: Route) -> Identity:
    """Return a staffing route's ``(model, effort, harness, channel)`` tuple."""
    return (route.model, route.effort, route.harness, route.channel)


# ---------------------------------------------------------------------------
# Fixtures (module scope; read-only loads through the public loaders)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live() -> CrewsConfig:
    path = resolve_crews_path()
    assert path.exists(), f"live auto-orch crews file missing: {path}"
    return load_crews(path)


@pytest.fixture(scope="module")
def routes() -> RoutesCatalog:
    return load_staffing_document("routes", STAFFING_DIR / "routes.yaml")


@pytest.fixture(scope="module")
def crews() -> CrewsCatalog:
    return load_staffing_document("crews", STAFFING_DIR / "crews.yaml")


@pytest.fixture(scope="module")
def routes_by_identity(routes: RoutesCatalog) -> dict[Identity, list[str]]:
    """Map each route identity tuple to the route ids carrying it."""
    index: dict[Identity, list[str]] = {}
    for route in routes.routes:
        index.setdefault(route_identity(route), []).append(route.route_id)
    return index


@pytest.fixture(scope="module")
def routes_by_id(routes: RoutesCatalog) -> dict[str, Route]:
    return {route.route_id: route for route in routes.routes}


# ---------------------------------------------------------------------------
# 1. Live worker -> exactly one route by exact identity tuple
# ---------------------------------------------------------------------------


def test_every_live_worker_maps_to_exactly_one_route(
    live: CrewsConfig, routes_by_identity: dict[Identity, list[str]]
) -> None:
    """Every live worker id maps to exactly one route by its exact tuple.

    Honors the byte-identical alias workers (they share the canonical
    worker's tuple and therefore its single route) and forbids inventing
    models: a tuple with no catalog row is a failure, and so is a tuple
    matching two or more rows.
    """
    problems: list[str] = []
    for worker_id, worker in live.workers.items():
        identity = worker_identity(worker)
        matches = routes_by_identity.get(identity, [])
        if len(matches) != 1:
            problems.append(
                f"{worker_id}: {identity} matched {len(matches)} routes "
                f"{matches} (expected exactly 1)"
            )
    assert (
        not problems
    ), "live workers did not map to exactly one route each:\n" + "\n".join(problems)


def test_alias_workers_are_byte_identical_to_canonical(
    live: CrewsConfig, routes_by_identity: dict[Identity, list[str]]
) -> None:
    """Known backward-compat aliases run byte-identical commands and share
    their canonical worker's single route — no invented models."""
    for alias_id, canonical_id in ALIAS_TO_CANONICAL.items():
        assert alias_id in live.workers, f"alias worker {alias_id!r} missing live"
        assert (
            canonical_id in live.workers
        ), f"canonical worker {canonical_id!r} missing live"
        alias = live.workers[alias_id]
        canonical = live.workers[canonical_id]
        assert alias.command == canonical.command, (
            f"alias {alias_id!r} command diverged from {canonical_id!r}; "
            "the alias is no longer byte-identical"
        )
        assert worker_identity(alias) == worker_identity(canonical)
        assert len(routes_by_identity[worker_identity(alias)]) == 1


# ---------------------------------------------------------------------------
# 2. Unpriced routes carry a nonempty status_reason
# ---------------------------------------------------------------------------


def test_unpriced_routes_have_nonempty_status_reason(routes: RoutesCatalog) -> None:
    unpriced = [route for route in routes.routes if route.status == "unpriced"]
    assert unpriced, "expected the documented unpriced route(s) in the snapshot"
    for route in unpriced:
        assert (
            isinstance(route.status_reason, str) and route.status_reason.strip()
        ), f"route {route.route_id!r} is unpriced but has no status_reason"


def test_documented_unpriced_mimo_route_still_mapped(
    routes: RoutesCatalog, routes_by_identity: dict[Identity, list[str]]
) -> None:
    """The one D207 unpriced Go route stays in the catalog (mapped, not
    omitted) per chief-answers-6."""
    mimo = [
        route
        for route in routes.routes
        if route.route_id == "opencode-opencode-go-mimo-v2-5-opencode-go"
    ]
    assert len(mimo) == 1
    route = mimo[0]
    assert route.status == "unpriced"
    assert isinstance(route.status_reason, str) and route.status_reason.strip()
    assert routes_by_identity[route_identity(route)] == [route.route_id]


# ---------------------------------------------------------------------------
# 3. Governed crew names + five stage bindings resolve to recorded routes
# ---------------------------------------------------------------------------


def test_governed_crew_names_exactly_equal_live_crews(
    live: CrewsConfig, crews: CrewsCatalog
) -> None:
    governed = [crew for crew in crews.crews if crew.kind == "governed"]
    assert (
        len(governed) == GOVERNED_CREW_COUNT
    ), f"expected {GOVERNED_CREW_COUNT} governed crews, found {len(governed)}"
    assert (
        len(live.crews) == GOVERNED_CREW_COUNT
    ), f"expected {GOVERNED_CREW_COUNT} live crews, found {len(live.crews)}"
    names = [crew.crew_name for crew in governed]
    assert None not in names, "governed crew missing crew_name"
    assert sorted(names) == sorted(live.crews)
    assert len(set(names)) == GOVERNED_CREW_COUNT, "duplicate crew_name values"


def test_governed_stage_bindings_resolve_to_recorded_routes(
    live: CrewsConfig,
    crews: CrewsCatalog,
    routes_by_id: dict[str, Route],
    routes_by_identity: dict[Identity, list[str]],
) -> None:
    """Each governed crew's five stage bindings are single refs to recorded
    routes whose identity equals the live stage worker's derived tuple."""
    for crew in crews.crews:
        if crew.kind != "governed":
            continue
        assert crew.crew_name is not None
        assert crew.worker_routes is not None, f"{crew.crew_name}: no worker_routes"
        live_crew = live.crews[crew.crew_name]
        for stage in STAGE_NAMES:
            binding = crew.worker_routes.get(stage)
            assert (
                binding is not None
            ), f"{crew.crew_name}: stage {stage!r} not recorded"
            assert (
                len(binding) == 1
            ), f"{crew.crew_name}: stage {stage!r} binds {len(binding)} routes"
            route_id = binding[0]
            assert route_id in routes_by_id, (
                f"{crew.crew_name}: {stage!r} ref {route_id!r} is not a "
                "recorded route"
            )
            live_worker_id = live_crew.eligible(stage)[0]
            expected = worker_identity(live.workers[live_worker_id])
            actual = route_identity(routes_by_id[route_id])
            assert actual == expected, (
                f"{crew.crew_name}: {stage!r} binds {route_id} with identity "
                f"{actual}, but live worker {live_worker_id!r} derives {expected}"
            )
            assert routes_by_identity[expected] == [route_id]


# ---------------------------------------------------------------------------
# 4. Interactive crews + auto placeholder: typed loading, no dropped fields
# ---------------------------------------------------------------------------

# Governed-only attributes that must stay unset on interactive/auto crews.
_GOVERNED_ONLY_FIELDS = ("source", "crew_name", "supervisor", "escalation")


def _normalize(raw: object) -> object:
    """Convert raw YAML lists/dicts into the loader's tuple/dict shapes."""
    if isinstance(raw, list):
        return tuple(_normalize(item) for item in raw)
    if isinstance(raw, dict):
        return {key: _normalize(value) for key, value in raw.items()}
    return raw


def test_interactive_crews_and_auto_load_typed_without_dropped_fields(
    crews: CrewsCatalog,
    routes_by_id: dict[str, Route],
) -> None:
    """The two interactive crews and the auto computed placeholder load as
    typed ``Crew`` objects carrying every field present in the raw YAML."""
    raw_docs = yaml.safe_load((STAFFING_DIR / "crews.yaml").read_text(encoding="utf-8"))
    raw_by_id = {record["crew_id"]: record for record in raw_docs["crews"]}
    typed_by_id = {crew.crew_id: crew for crew in crews.crews}

    routed_interactive = [
        crew
        for crew in crews.crews
        if crew.kind == "interactive" and crew.computed is None
    ]
    assert {crew.crew_id for crew in routed_interactive} == {
        "sol-low-glm-pi",
        "luna-sol",
    }

    for crew_id in ("sol-low-glm-pi", "luna-sol", "auto"):
        crew = typed_by_id[crew_id]
        assert isinstance(crew, Crew), f"{crew_id}: not a typed Crew object"
        raw = raw_by_id[crew_id]
        for field, raw_value in raw.items():
            assert hasattr(
                crew, field
            ), f"{crew_id}: typed Crew dropped field {field!r}"
            assert getattr(crew, field) == _normalize(
                raw_value
            ), f"{crew_id}: field {field!r} value changed in typed loading"
        for field in _GOVERNED_ONLY_FIELDS:
            assert getattr(crew, field) is None, (
                f"{crew_id}: governed field {field!r} invented on an "
                "interactive/computed crew"
            )

    # The auto placeholder stays computed with no invented routes.
    auto = typed_by_id["auto"]
    assert auto.kind == "interactive"
    assert auto.computed is True
    assert auto.authority == "policy"
    assert auto.supervisor_route is None
    assert auto.worker_routes is None
    assert auto.reviewer_route is None
    assert auto.escalation_ladder is None

    # Both routed interactive crews keep their full round-10 shape, and
    # every recorded ref is a real route id.
    for crew in routed_interactive:
        assert crew.supervisor_route in routes_by_id
        assert crew.reviewer_route in routes_by_id
        assert crew.worker_routes
        for refs in crew.worker_routes.values():
            assert refs
            for ref in refs:
                assert ref in routes_by_id
        assert crew.escalation_ladder
        for ref in crew.escalation_ladder:
            assert ref in routes_by_id
