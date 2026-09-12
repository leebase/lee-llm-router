"""Live snapshot oracle for the staffing catalog (P0-3p, Chief round 13).

Proves, against the live ``/home/lee/projects/auto-orch/config/crews.yaml``
and the catalog YAML in ``config/staffing/``:

1. Every live worker id maps by its command-derived exact
   ``(model, effort, harness, channel)`` tuple to exactly one route in
   ``config/staffing/routes.yaml``, honoring the known backward-compatible
   byte-identical alias workers without inventing models.
2. Every route with ``status: unpriced`` carries a nonempty
   ``status_reason``.
3b. Chief round 15 (``docs/staffing/chief-answers-15.md``, rulings 1-2):
   ``reviewer_independence`` holds exactly two records keyed by the staffing
   reviewer_ref names ``review`` and ``judge``, each copying its archived
   labor-ladder ``roles.yaml`` independence shape verbatim, with provenance
   citing Chief round 15 and the archived roles file, enforcement stated as
   only-with-``--author-route`` (absent input is disclosed, not excluded).
3. Chief round 13 (``docs/staffing/chief-answers-13.md``, ruling 3): no
   literal governed/live name equality — instead (a) every live Auto-Orch
   crew name resolves to exactly one catalog record of either kind (a
   governed ``crew_name`` or an interactive ``governed_ref``), (b) every
   governed catalog ``crew_name`` names a live crew, and (c) every
   live-backed interactive record carries ``governed_ref`` equal to its
   live name, and each live governed ``primary``/``reviewer``/``judge``
   route resolves by its exact ``(model, effort, harness)`` key — effort
   compared verbatim, never inferred — to exactly one catalog row (which
   pins the channel) whose route id equals the FIRST entry of the
   record's ordered ``impl``/``review``/``judge`` role routes, with
   ``sol-low-glm-pi`` exercised explicitly. Each governed crew's five stage bindings
   additionally resolve to recorded route refs that match the live stage
   worker's identity tuple.
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
    GOVERNED_ROLES,
    STAGE_NAMES,
    CrewsConfig,
    GovernedRoute,
    Worker,
    load_crews,
    resolve_crews_path,
    resolve_worker,
)
from lee_llm_router.staffing import (
    Crew,
    CrewsCatalog,
    PolicyCatalog,
    ReviewIndependenceRule,
    RoleFloorRecord,
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

# Chief round 13: the live governed role names mapped onto the interactive
# record's ordered role-route arrays (chief-answers-13 ruling 3c).
GOVERNED_ROLE_TO_RECORD_STAGE = {
    "primary": "impl",
    "reviewer": "review",
    "judge": "judge",
}

# D215 ruling 2 (2026-09-12): "Governed routes stop being pinned to metered
# channels for accounting's sake once agent-orch prices attempts at both
# list and marginal (Phase 4); until then the governed primary stays where
# it is, with this decision as the reason." D215 ruling 1 reorders
# sol-low-glm-pi's interactive `impl` array to prepaid-first while its live
# governed `primary` intentionally stays pinned to the metered OpenRouter
# lane until agent-orch's P4-4 marginal-cost work lands. This is the one
# documented, narrowly-scoped exception to round 13(c)'s strict first-entry
# equality; every other live-backed interactive record/role keeps the
# strict check.
_D215_GOVERNED_PRIMARY_ORDER_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(
    {("sol-low-glm-pi", "primary")}
)

# Route identity in staffing catalog order (model, effort, harness, channel)
# — the tuple every live worker must map to exactly one route by.
Identity = tuple[str | None, str | None, str, str]

# Chief round 10 Luna escalation rung and its effort-max counterpart (the
# never_automatic policy narrows to the latter).
LUNA_XHIGH_PI_ROUTE_ID = "pi-gpt-5-6-luna-xhigh-openai-sub"
LUNA_MAX_ROUTE_ID = "codex-gpt-5-6-luna-max-openai-sub"


def worker_identity(worker: Worker) -> Identity:
    """Derive a worker's exact ``(model, effort, harness, channel)`` tuple.

    Uses the public crews resolution pipeline (``resolve_worker`` for the
    command-derived provider/model/effort/channel and
    ``crew_page.HARNESS_BY_PROVIDER`` for the catalog harness spelling,
    including ``pi_cli -> pi``). The effort is the resolver's own value
    verbatim — including the Pi/OMP ``_STAGE_WORKER_THINKING`` dial — and an
    absent dial stays ``None``: no effort is ever inferred.
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


def governed_role_identity(
    role_route: GovernedRoute,
) -> tuple[str | None, str | None, str]:
    """Return a live governed route's exact ``(model, effort, harness)`` key.

    The harness spelling goes through ``crew_page.HARNESS_BY_PROVIDER``
    (including ``pi_cli -> pi``); the model and effort are the live
    record's own values verbatim — effort is never inferred from another
    role, crew, or route.
    """
    harness = HARNESS_BY_PROVIDER.get(role_route.harness)
    assert harness is not None, (
        f"governed {role_route.role!r} route harness "
        f"{role_route.harness!r} has no catalog harness spelling"
    )
    return (role_route.model, role_route.effort, harness)


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
def policy() -> PolicyCatalog:
    return load_staffing_document("policy", STAFFING_DIR / "policy.yaml")


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
# 1b. Role floors: recorded data only (Chief round 15, D86/D87)
# ---------------------------------------------------------------------------

# Chief round 15 vocabulary mapping and the archived floors it points at
# (copied verbatim from labor-ladder/policy/roles.yaml: every mapped archived
# role currently has floor T2). Exactly these five records, nothing else.
# Keys are the staffing role names (impl, plan, review, judge, prose) — the
# names a Phase-2 floors[role] lookup must resolve; the archived labor-ladder
# names stay in the records' provenance (see ARCHIVED_ROLE_BY_STAFFING_ROLE).
EXPECTED_ROLE_FLOORS: dict[str, str] = {
    "impl": "T2",
    "plan": "T2",
    "review": "T2",
    "judge": "T2",
    "prose": "T2",
}

# The Chief round 15 vocabulary mapping the records must preserve in their
# decision/source provenance: staffing role -> archived labor-ladder role.
ARCHIVED_ROLE_BY_STAFFING_ROLE: dict[str, str] = {
    "impl": "implementer",
    "plan": "planner",
    "review": "reviewer",
    "judge": "evaluator",
    "prose": "author",
}


def test_role_floors_are_exactly_the_chief_round15_mapping(
    policy: PolicyCatalog,
) -> None:
    """Chief round 15 (chief-answers-15.md, D86/D87): the role_floors array
    holds exactly five records keyed by the staffing role names impl, plan,
    review, judge, prose (the names a Phase-2 floors[role] lookup resolves),
    each carrying the floor copied verbatim from the archived labor-ladder
    tier policy (T2 for every mapped role). No extra or missing records."""
    assert len(policy.role_floors) == 5
    recorded = {record.role_ref: record.floor for record in policy.role_floors}
    assert recorded == EXPECTED_ROLE_FLOORS


def test_role_floors_recorded_not_enforced_with_nonempty_provenance(
    policy: PolicyCatalog,
) -> None:
    """Every role-floor record cites Chief round 15 for the vocabulary
    mapping and the archived labor-ladder roles file for the floor shape and
    value, states recorded-not-enforced, and adds no unsourced effective
    date (floors are recorded data only in Phase 0)."""
    assert policy.role_floors, "role_floors must not be empty"
    for record in policy.role_floors:
        assert isinstance(record, RoleFloorRecord)
        assert record.decision.strip(), f"{record.role_ref}: empty decision"
        assert record.source.strip(), f"{record.role_ref}: empty source"
        decision = record.decision
        source = record.source
        # Chief round 15 supplies the vocabulary mapping for every record.
        assert "Chief round 15" in decision and "Chief round 15" in source, (
            f"{record.role_ref}: decision/source must cite Chief round 15 "
            "for the vocabulary mapping"
        )
        assert (
            "chief-answers-15.md" in source
        ), f"{record.role_ref}: source must cite chief-answers-15.md"
        # The archived labor-ladder roles file supplies the floor shape/value.
        assert (
            "labor-ladder/policy/roles.yaml" in source
        ), f"{record.role_ref}: source must cite the archived roles file"
        # The archived labor-ladder role name must survive in provenance so
        # the Chief round 15 vocabulary mapping is not lost by re-keying to
        # the staffing role names.
        archived = ARCHIVED_ROLE_BY_STAFFING_ROLE[record.role_ref]
        assert archived in decision and archived in source, (
            f"{record.role_ref}: decision/source must keep the archived "
            f"role name {archived!r} mapping (Chief round 15 vocabulary)"
        )
        # Recorded data only: not enforced in Phase 0.
        assert (
            "not enforced" in decision
        ), f"{record.role_ref}: decision must state recorded-not-enforced"
        # No unsourced effective dates.
        assert record.effective_from is None, (
            f"{record.role_ref}: effective_from {record.effective_from!r} "
            "is not sourced"
        )


# ---------------------------------------------------------------------------
# 1c. Reviewer independence: exactly two archived shapes (Chief round 15)
# ---------------------------------------------------------------------------

# Chief round 15 (chief-answers-15.md, rulings 1-2): reviewer independence is
# recorded for exactly the staffing reviewer_ref names review and judge (the
# vocabulary mapping review -> reviewer, judge -> evaluator), copying the
# archived labor-ladder roles.yaml independence shapes verbatim. Exactly
# these two records, nothing else; the archived role names stay in the
# records' provenance (see ARCHIVED_INDEPENDENCE_ROLE_BY_REVIEWER_REF).
EXPECTED_INDEPENDENCE_SHAPES: dict[str, dict[str, object]] = {
    "review": {"not_same_worker_as": "authors", "prefer_different_family": True},
    "judge": {"second_opinion_mode": "different-family-than-author"},
}

# The Chief round 15 vocabulary mapping the records must preserve in their
# decision/source provenance: staffing reviewer_ref -> archived role.
ARCHIVED_INDEPENDENCE_ROLE_BY_REVIEWER_REF: dict[str, str] = {
    "review": "reviewer",
    "judge": "evaluator",
}


def test_reviewer_independence_is_exactly_two_chief_round15_records(
    policy: PolicyCatalog,
) -> None:
    """Chief round 15: the reviewer_independence array holds exactly two
    records keyed by the staffing reviewer_ref names review and judge, each
    carrying its archived labor-ladder independence shape verbatim and no
    fields from any other variant (no mode mixing across the schema's
    three-shape oneOf). No extra or missing records."""
    rules = policy.reviewer_independence
    assert len(rules) == 2
    by_ref = {rule.reviewer_ref: rule for rule in rules}
    assert set(by_ref) == {"review", "judge"}
    for ref, shape in EXPECTED_INDEPENDENCE_SHAPES.items():
        rule = by_ref[ref]
        assert isinstance(rule, ReviewIndependenceRule)
        # Verbatim archived shape: exactly the archived variant's fields.
        assert rule.not_same_worker_as == shape.get("not_same_worker_as")
        assert rule.prefer_different_family == shape.get("prefer_different_family")
        assert rule.second_opinion_mode == shape.get("second_opinion_mode")
        # The fresh-eyes variant is archived for the debugger role only; it
        # is invented on neither record.
        assert rule.fresh_eyes_mode is None, (
            f"{ref}: fresh_eyes_mode {rule.fresh_eyes_mode!r} is invented "
            "(no archived shape carries it for this reviewer)"
        )


def test_reviewer_independence_provenance_cites_chief_round15_and_archive(
    policy: PolicyCatalog,
) -> None:
    """Every reviewer-independence record cites Chief round 15 for the
    vocabulary mapping and the explain --author-route behavior, cites the
    archived labor-ladder roles file for the verbatim shape, and keeps the
    archived role name in provenance so the Chief round 15 vocabulary
    mapping is not lost by re-keying to the staffing reviewer_ref."""
    assert policy.reviewer_independence, "reviewer_independence must not be empty"
    for rule in policy.reviewer_independence:
        assert rule.decision.strip(), f"{rule.reviewer_ref}: empty decision"
        assert rule.source.strip(), f"{rule.reviewer_ref}: empty source"
        assert (
            "Chief round 15" in rule.decision and "Chief round 15" in rule.source
        ), f"{rule.reviewer_ref}: decision/source must cite Chief round 15"
        assert (
            "chief-answers-15.md" in rule.source
        ), f"{rule.reviewer_ref}: source must cite chief-answers-15.md"
        assert (
            "labor-ladder/policy/roles.yaml" in rule.source
        ), f"{rule.reviewer_ref}: source must cite the archived roles file"
        archived = ARCHIVED_INDEPENDENCE_ROLE_BY_REVIEWER_REF[rule.reviewer_ref]
        assert archived in rule.decision and archived in rule.source, (
            f"{rule.reviewer_ref}: decision/source must keep the archived "
            f"role name {archived!r} mapping (Chief round 15 vocabulary)"
        )


def test_reviewer_independence_enforcement_only_with_author_route(
    policy: PolicyCatalog,
) -> None:
    """Chief round 15 ruling 2: enforcement occurs only when explain
    receives --author-route; when the input is absent, explain discloses
    "independence not evaluated (no --author-route)" instead of excluding
    routes. Independence is an author/candidate comparison, never a
    class-to-model preference (D206)."""
    for rule in policy.reviewer_independence:
        assert "--author-route" in rule.decision, (
            f"{rule.reviewer_ref}: decision must state the --author-route "
            "enforcement gate"
        )
        assert "not evaluated" in rule.decision, (
            f"{rule.reviewer_ref}: decision must state the absent-input "
            "disclosure, not a silent exclusion"
        )
        assert "disclos" in rule.decision, (
            f"{rule.reviewer_ref}: decision must state that absent input is "
            "disclosed, not excluded"
        )
        assert "author/candidate" in rule.decision, (
            f"{rule.reviewer_ref}: decision must frame independence as an "
            "author/candidate comparison"
        )
        assert "never a class-to-model preference" in rule.decision, (
            f"{rule.reviewer_ref}: decision must state the independence is "
            "never a class-to-model preference (D206)"
        )


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
# 3. Chief round 13 live-vs-catalog invariant + governed stage bindings
# ---------------------------------------------------------------------------


def test_round13_live_crew_names_map_to_exactly_one_catalog_record(
    live: CrewsConfig, crews: CrewsCatalog
) -> None:
    """Chief round 13 (a): every live Auto-Orch crew name resolves to
    exactly one catalog record, matching either a governed ``crew_name``
    or an interactive ``governed_ref`` — zero or multiple matches fail.
    """
    records_by_name: dict[str, list[str]] = {}
    for crew in crews.crews:
        name = crew.crew_name if crew.kind == "governed" else crew.governed_ref
        if name is None:
            continue
        records_by_name.setdefault(name, []).append(crew.crew_id)
    problems: list[str] = []
    for name in live.crews:
        matches = records_by_name.get(name, [])
        if len(matches) != 1:
            problems.append(
                f"live crew {name!r} matched {len(matches)} catalog records "
                f"{matches} (expected exactly 1)"
            )
    assert (
        not problems
    ), "live crew names did not map to exactly one catalog record each:\n" + "\n".join(
        problems
    )


def test_round13_governed_records_name_live_crews(
    live: CrewsConfig, crews: CrewsCatalog
) -> None:
    """Chief round 13 (b): every governed catalog ``crew_name`` names a
    live crew. The catalog keeps its P0-3 fourteen governed records; live
    counts are read, never asserted (chief-answers-13 ruling 1/3).
    """
    governed = [crew for crew in crews.crews if crew.kind == "governed"]
    assert (
        len(governed) == GOVERNED_CREW_COUNT
    ), f"expected {GOVERNED_CREW_COUNT} governed catalog records, found {len(governed)}"
    names = [crew.crew_name for crew in governed]
    assert None not in names, "governed crew missing crew_name"
    assert len(set(names)) == GOVERNED_CREW_COUNT, "duplicate crew_name values"
    missing = sorted(set(names) - set(live.crews))
    assert not missing, f"governed crew_name values with no live crew: {missing}"


def test_round13_live_backed_interactive_records_resolve_governed_roles(
    live: CrewsConfig,
    crews: CrewsCatalog,
    routes: RoutesCatalog,
    routes_by_id: dict[str, Route],
) -> None:
    """Chief round 13 (c): every live-backed interactive record carries
    ``governed_ref`` equal to its live crew name, and each live governed
    ``primary``/``reviewer``/``judge`` route resolves — by its exact
    ``(model, effort, harness)`` key over the whole route catalog, with
    the channel supplied by that unique row and the effort compared
    verbatim (never inferred) — to exactly one recorded route whose id
    equals the FIRST entry of the record's ordered
    ``impl``/``review``/``judge`` role routes (strict first-entry
    equality, not mere membership; later entries are same-role
    fallbacks documented by the record's evidence_ref).
    """
    live_backed = [
        crew
        for crew in crews.crews
        if crew.kind == "interactive" and crew.governed_ref is not None
    ]
    assert live_backed, "expected at least one live-backed interactive record"
    for crew in live_backed:
        ref = crew.governed_ref
        assert (
            ref in live.crews
        ), f"{crew.crew_id}: governed_ref {ref!r} names no live crew"
        assert (
            crew.computed is not True
        ), f"{crew.crew_id}: a live-backed record must not be computed"
        assert crew.worker_routes, f"{crew.crew_id}: no worker_routes"
        live_governed = live.crews[ref].governed
        for role in GOVERNED_ROLES:
            if role not in live_governed:
                continue
            role_route = live_governed[role]
            key = governed_role_identity(role_route)
            matches = [
                route
                for route in routes.routes
                if (route.model, route.effort, route.harness) == key
            ]
            assert len(matches) == 1, (
                f"{crew.crew_id}: live governed {role!r} {key} resolved to "
                f"{[route.route_id for route in matches]} (expected exactly 1)"
            )
            resolved = matches[0]
            stage = GOVERNED_ROLE_TO_RECORD_STAGE[role]
            refs = list((crew.worker_routes or {}).get(stage) or [])
            assert refs, f"{crew.crew_id}: no recorded {stage!r} role routes"
            if (crew.crew_id, role) in _D215_GOVERNED_PRIMARY_ORDER_EXCEPTIONS:
                assert resolved.route_id in refs, (
                    f"{crew.crew_id}: live governed {role!r} {key} resolves to "
                    f"{resolved.route_id} {route_identity(resolved)}, which is "
                    f"not even present in the record's ordered {stage!r} "
                    f"routes {refs} (D215 ruling 2 permits it to trail, not "
                    f"be absent)"
                )
            else:
                assert resolved.route_id == refs[0], (
                    f"{crew.crew_id}: live governed {role!r} {key} resolves to "
                    f"{resolved.route_id} {route_identity(resolved)}, which is "
                    f"not the first entry of the record's ordered {stage!r} "
                    f"routes {refs} (expected {refs[0]})"
                )


def test_round13_sol_low_glm_pi_governed_roles_resolve_explicitly(
    live: CrewsConfig,
    crews: CrewsCatalog,
    routes_by_id: dict[str, Route],
) -> None:
    """Chief round 13 (c) exercised explicitly on ``sol-low-glm-pi``: the
    interactive record is live-backed via ``governed_ref``, and the live
    governed roles pin their exact ``(model, effort, harness, channel)``
    tuples — the OpenRouter GLM lane for the governed primary, the
    OpenCode Go V4 Pro lane for the governed reviewer, and the Astra Low
    codex judge. Uniqueness and recording are asserted generically; this
    test pins the concrete lanes.
    """
    record = next(
        (crew for crew in crews.crews if crew.crew_id == "sol-low-glm-pi"), None
    )
    assert record is not None, "catalog record sol-low-glm-pi missing"
    assert record.kind == "interactive"
    assert record.governed_ref == "sol-low-glm-pi"
    assert "sol-low-glm-pi" in live.crews
    assert record.worker_routes is not None

    live_governed = live.crews["sol-low-glm-pi"].governed
    assert set(live_governed) == set(GOVERNED_ROLES), (
        f"live sol-low-glm-pi governed roles {sorted(live_governed)} != "
        f"{sorted(GOVERNED_ROLES)}"
    )

    expected = {
        "primary": (
            "pi-z-ai-glm-5-3-flash-openrouter",
            ("z-ai/glm-5.3-flash", None, "pi", "openrouter"),
        ),
        "reviewer": (
            "pi-deepseek-v4-pro-opencode-go",
            ("deepseek-v4-pro", None, "pi", "opencode-go"),
        ),
        "judge": (
            "codex-gpt-6-astra-low-openai-sub",
            ("gpt-6-astra", "low", "codex", "openai-sub"),
        ),
    }
    for role, (route_id, identity) in expected.items():
        key = governed_role_identity(live_governed[role])
        assert key == identity[:3], (
            f"sol-low-glm-pi: live governed {role!r} derived {key}, "
            f"expected {identity[:3]}"
        )
        assert route_identity(routes_by_id[route_id]) == identity, (
            f"sol-low-glm-pi: route {route_id!r} identity "
            f"{route_identity(routes_by_id[route_id])} != {identity}"
        )


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


def test_interactive_escalation_refs_point_to_active_xhigh_luna_routes(
    crews: CrewsCatalog, routes_by_id: dict[str, Route]
) -> None:
    """Chief round 10 places `gpt-5.6-luna | pi | xhigh | openai-sub` as an
    automatic escalation rung in both interactive crews, so the Luna entry
    in every escalation ladder must be the active XHigh route — never the
    effort-max route the never_automatic policy narrows to."""
    interactive = [
        crew
        for crew in crews.crews
        if crew.kind == "interactive" and crew.computed is None
    ]
    assert {crew.crew_id for crew in interactive} == {
        "sol-low-glm-pi",
        "luna-sol",
    }
    for crew in interactive:
        assert crew.escalation_ladder, f"{crew.crew_id}: no escalation ladder"
        for ref in crew.escalation_ladder:
            assert (
                ref in routes_by_id
            ), f"{crew.crew_id}: escalation ref {ref!r} is not a recorded route"
            assert (
                routes_by_id[ref].status == "active"
            ), f"{crew.crew_id}: escalation ref {ref!r} is not active"
            assert ref != LUNA_MAX_ROUTE_ID, (
                f"{crew.crew_id}: escalation ladder names the effort-max Luna "
                f"route {LUNA_MAX_ROUTE_ID!r}, which is never_automatic"
            )
        luna_rungs = [
            ref
            for ref in crew.escalation_ladder
            if routes_by_id[ref].model == "gpt-5.6-luna"
        ]
        assert luna_rungs == [LUNA_XHIGH_PI_ROUTE_ID], (
            f"{crew.crew_id}: Luna escalation rungs {luna_rungs} != "
            f"[{LUNA_XHIGH_PI_ROUTE_ID!r}] (chief round 10)"
        )
        luna_route = routes_by_id[LUNA_XHIGH_PI_ROUTE_ID]
        assert (luna_route.model, luna_route.effort, luna_route.harness) == (
            "gpt-5.6-luna",
            "xhigh",
            "pi",
        )
