# Phase 4 contracts — router/agent-orch/auto-orch seams (P4-0)

Author: Sonnet 5 supervisor, Group A, 2026-09-12/13. Authority: D215 rulings 4-6 on the
D214 baseline; D216 (subscription reserve). Read-only pass over `agent-orch` (`engine.py`
retry/policy path, `failure_classification.py`, `worker.py` usage receipts, `rate_table.py`),
`auto-orch` (`routing.py`, `routing_authority.py`), and `lee-llm-router` (`staffing/terms.py`,
`staffing/eligibility.py`, `doctor.py` `_run_staff`/`_run_run`). Lists the exact seams each
Phase 4 packet plugs into and the contradictions found, resolved by D215/D216 or recorded
for a ruling.

## 1. agent-orch retry/policy path (`engine.py`)

- All retry/repair/halt decision-making for one step lives in `_run_step`
  (`engine.py:6696`-~`9200`); the decision block is `engine.py:7846-7936`.
- There is **no first-class "slice reviewer verdict" object** in the retry loop. A judge
  verdict is `{"passed": bool, "evidence": [str, ...], "reasoning": str}`
  (`semantic.py:141` `extract_verdict_payload`, schema `SEMANTIC_VERDICT_SCHEMA`), wrapped
  into `ValidationOutcome(rule: dict, passed: bool, message: str, evidence: dict | None)`
  (`validators.py:119`). `_run_step` collects these as `outcomes`, then
  `failed_outcomes = [o for o in outcomes if not o.passed]` (`engine.py:7846`).
- Policy decision precedence (`engine.py:7867-7908`), each producing
  `StepAttemptRecord.policy_decision`:
  1. `budget_refusal_error is not None` -> `"HALT"`
  2. `is_non_repairable(failure_class)` -> `"HALT"`
  3. `unexpected_error` -> `"HALT"`
  4. `repair_requested` (failed outcomes all `_REPAIR_ELIGIBLE_RULE_TYPES`,
     `engine.py:696`, and `repair_cycles_used < max_cycles`) -> `"REPAIR"`
  5. `repair_budget_exhausted` -> `"HALT"`
  6. `attempt_number < last_attempt` -> `"RETRY"`
  7. else -> `"HALT"`
- `repair_cycle`/`repair_reason` live on `StepRecord` (`engine.py:195-196`, per-step, not
  per-attempt), set at `engine.py:6328-6333`; `repair_reason` defaults to the string literal
  `"review_verdict_failure"` (not an enum).
- **P4-5 seam:** `ESCALATE` is a new eighth policy-decision value, tried between steps 4 and
  5 above: when the failed outcome carries a `capability_rejected` judgment (a mapping this
  packet defines from the judge verdict, since no such mapping exists today) *and* the
  playbook mandate carries a nonempty ladder *and* `escalation.enabled` is true, produce
  `"ESCALATE"` instead of falling through to `REPAIR`/`HALT`. New fields
  `escalation_reason: str | None` and `parent_attempt: int | None` (attempt number, since
  attempts are step-scoped) are added to `StepAttemptRecord`, additive with `None` defaults.
  No `ESCALATE`/`capability_rejected`/`ladder`/`mandate`/`parent_attempt` identifier exists
  anywhere in `src/agent_orch/` today (confirmed by full-repo grep) — this is greenfield, not
  a rename of `repair_cycle`/`repair_reason`, which stay exactly as they are and are never
  reused for escalation bookkeeping.

## 2. Failure classification and verification tier (`failure_classification.py`, P4-3)

- `classify_failure(exit_code, stdout, stderr, error_message) -> str | None` returns one of
  the seven `NonRepairableFailureClass` values or `None`. Single call site:
  `engine.py:7872`, result stored as `StepAttemptRecord.failure_classification`
  (`engine.py:7936`; note the dataclass field name differs from the local variable name
  `failure_class`).
- `StepAttemptRecord` siblings for the new fields: `attempt_number: int`,
  `worker_exit_code: int`, `worker_success: bool`, `validation_passed: bool`,
  `validation_errors: list[str]`, `policy_decision: str`, `run_dir: str`,
  `changed_files: list[str]`, `failure_classification: str | None = None`
  (`engine.py:172-183`).
- **Timeout is currently unclassified.** A worker timeout only appends
  `f"Worker timed out after {self.timeout_seconds} seconds."` to stderr
  (`worker.py:2255`); none of the seven regex families in `failure_classification.py`
  (lines 24-71) match that text, and the exit code is not reliably 126/127. A timeout today
  classifies as `None` (repairable/retryable) even though it is a platform condition, not a
  content defect. **P4-3 seam:** add an eighth `NonRepairableFailureClass.PLATFORM_TIMEOUT =
  "platform_timeout"` and a matcher in `classify_failure` for the exact stderr string
  `f"Worker timed out after {timeout_seconds} seconds."` (or a compiled pattern over it).
  Additive: existing seven classes and their patterns are unchanged.
- `worker.py` has an unrelated, disjoint `classify_failure` concept per adapter
  (`worker.py:2050,2699,...`), returning `{"failure_classification": "token_exhaustion", ...}`
  merged into `metadata` (`worker.py:2287`). **Contradiction recorded, not fixed here:** two
  differently-scoped "failure classification" mechanisms share a name across
  `failure_classification.py` and `worker.py`'s adapter layer. D215/D216 do not rule on
  unifying them and the sprint plan scopes P4-3 to the engine-level enum only; this stays a
  recorded naming collision for a future phase, not a Phase 4 defect to fix.
- **Verification tier per step:** no such field exists today. P4-3 adds
  `verification_tier: str` to `StepAttemptRecord` (additive, a sibling of
  `failure_classification`). The sprint plan does not name the tier's value set; D213's
  Phase-3 carryover note ("judge verdicts should be recorded as judge outcomes rather than
  `unverified`") and the existing `verified_success_reason`/`OracleOutcome` vocabulary in
  `lee_llm_router.staffing.run` are the closest committed vocabulary. P4-3 records the tier
  using the same three-value shape already used for attempt verification elsewhere in this
  migration (`verified` / `unavailable` / a named gap reason), rather than inventing a new
  taxonomy — implementers should default `verification_tier` to `"engine_validation"` for a
  step whose only verification is the engine's own validator/judge outcomes (mirroring the
  already-committed router `verdict.tier: engine_validation`, `chief-answers-p1-3.md`), and to
  a named oracle/reviewer tier when the step's playbook step declares an external oracle.

## 3. Usage receipts and pricing (`worker.py`, `rate_table.py`, P4-4)

- `TokenUsage` (`employee_contract.usage.TokenUsage`) fields: `input_tokens`,
  `output_tokens`, `total_tokens`, `model: str | None`, `cached_read_tokens`,
  `cached_write_tokens`, `cost_usd: float | None`, `raw_usage: dict`. **No `route` field** —
  only `model`. Route/model identity for pricing comes from `record.identity.route`
  (`model`/`harness` keys; judge context also carries `route_id`), read at
  `engine.py:2339-2348`.
- `RateTable.compute_cost` (`rate_table.py:138`) is called at `engine.py:2358`; the priced
  result replaces `cost_usd` via `replace(usage, model=model, cost_usd=priced_cost)`
  (`engine.py:2360-2364`). This is the existing **list-price** cost path (agent-orch's own
  `rate_table.yaml`, not the router).
- `cost_usd` is not a `StepAttemptRecord` field; it lives on the per-attempt usage/accounting
  artifact (`usage.json`/accounting payload keys `cost_usd`, `cumulative_cost_usd`,
  `generation_cost_usd`; read/written around `engine.py:4258-4498`). **P4-4 seam:** add a
  sibling key `cost_usd_marginal` to that same usage/accounting payload (not to
  `StepAttemptRecord`), computed by shelling out to
  `lee-llm-router price --route ID --input N --output N [--cached N] [--at DATE]`
  (P4-1, new command) with the same `record.identity.route` model/harness used for the
  existing list-price lookup, and the token counts already on the priced `TokenUsage`.
  Fail-open per the sprint plan: when the router CLI is absent, times out, or exits nonzero,
  `cost_usd_marginal` is set to the literal string `"unavailable"` (not `None` and not a
  fabricated number) and the run is never blocked — this mirrors the existing
  `_run_verify_cli` fail-open convention in `auto-orch/cycle.py:1726-1761` (§ auto-orch
  below), which agent-orch does not yet have its own copy of; P4-4 introduces one local to
  agent-orch (argv list, no shell, capped timeout, `OSError`/`TimeoutExpired` ->
  `"unavailable"`).
- **Route/model ambiguity for the price lookup:** `lee-llm-router price --route ID` takes a
  router **route id** (e.g. `pi-z-ai-glm-5-3-flash-openrouter`), but agent-orch's
  `record.identity.route` carries a bare `model`/`harness` pair, not a router route id, and
  agent-orch's own `rate_table.yaml` keys are bare model ids (e.g.
  `z-ai/glm-5.3-flash`), not router route ids. **Contradiction, resolved:** P4-4 must resolve
  agent-orch's `(model, harness, channel)` triple to a router route id before calling `price`;
  where the router catalog has no route matching that exact triple (an agent-orch worker not
  represented in `config/staffing/routes.yaml`), `cost_usd_marginal` is `"unavailable"` with
  the reason recorded, never a best-effort guess. This is additive and never blocks list-price
  accounting, which is unaffected.

## 4. auto-orch routing (`routing.py`, `routing_authority.py`, P4-6/P4-7 — Group B, recorded here for the seam)

- Stage routing today: `RoutingConfig.route_for(stage)`/`worker_for(stage)`
  (`routing.py:129-143`), built by `parse_routing_config(raw, *, crews_path=None)`
  (`routing.py:230-371`). Governed roles (`primary`/`reviewer`/`judge`,
  `GOVERNED_ROLES`, `routing_authority.py:101`) resolve via
  `resolve_governed_mandate(routing_config) -> GovernedMandate`
  (`routing_authority.py:271-320`), output `dict[role -> ResolvedRole(role, spec:
  RouteSpec(harness, model, effort), source)]`.
- `routing.crew: <name>` is read at `routing.py:253-277` via `load_crews()`
  (`routing.py:160-227`, default `config/crews.yaml`). **No `auto` crew exists today**;
  `crew: auto` currently raises `ValueError` ("unknown crew") at the dict-lookup
  (`routing.py:259-262`) rather than meaning anything — this is the exact seam P4-6 (Group B)
  must special-case before that lookup.
- The "playbook routing mandate" is `GovernedMandate.to_payload()`
  (`routing_authority.py:170-192`) -> `{"crew": ..., "roles": [{"role", "source", "harness",
  "model", "effort"?}, ...]}`; it has **no slot for a router `staff` block**. P4-6 must add a
  new field (e.g. on `RoutingConfig` alongside `crew`, `routing.py:113`, or appended into
  `authority_summary()`'s payload, `routing_authority.py:667-693`) to carry the `staff` JSON
  block verbatim, additive.
- Backlog items have no "packet" file today — `BacklogItem` (`envision.py:150-218`,
  parsed by `parse_backlog(path)` from `missions/<mission>/backlog.md`) is the closest
  representation; P4-6 must serialize one to a packet file for `staff --from-packet`. No
  serializer exists yet.
- No `lee-llm-router` invocation exists anywhere in auto-orch today. The closest existing
  subprocess convention to reuse is `_run_verify_cli` (`cycle.py:1726-1761`): argv list (no
  shell), `subprocess.run(capture_output=True, text=True, timeout=...)`, three explicit
  outcomes (`"verified"` / `"verdict_failed"` / `"unavailable"` on `OSError`/
  `TimeoutExpired`) — this is the fail-closed-to-last-named-crew pattern the sprint plan
  requires and P4-6 should follow it exactly rather than inventing a new one.
- `task_type` does not exist anywhere in `src/auto_orch/`; it exists only in
  `agent-orch/src/agent_orch/models.py:110` (`ExecutionIntent.task_type`), a different
  package. Performance rollup is `summarize_observations()` (`performance.py:514-574` ->
  `<mission>/performance/summary.json`), grouped by `(kind, producer_json, reviewer_json)`
  provenance tuples (`_PROVENANCE_SCHEMA`, `performance.py:24-31`) with **no `class` key**
  anywhere in that schema. P4-7 is the owner's call (delegate to `evidence rollup`, or add a
  `class` key to the provenance tuple) — recorded here, not resolved, since P4-7 is Group B
  scope.
- **Doc staleness recorded:** `docs/auto-orch-b3-worker-routing-contract.md` and
  `docs/auto-orch-routing-authority-contract.md` (both last touched 2026-08-02) predate
  crew-based routing entirely and mention neither `crew`, `auto`, nor `lee-llm-router`; they
  are background/rationale only, not the current interface spec. Not a Phase 4 defect, just a
  trap for a reader who opens them expecting current truth.

## 5. `lee-llm-router price` (P4-1) — exact seam it composes

- `lee_llm_router.staffing.terms.route_price(route_id, badge, catalog, ...) -> RoutePrice`
  already computes **per-token** marginal/replacement input and output prices for one route
  under one badge (`terms.py:411-455`), using `replacement_token_prices` (OpenRouter pinned
  snapshot first, then the agent-orch rate table, `terms.py:353-408`) and
  `badge_multiplier` (`terms.py:163-174`). Nothing here yet multiplies by a token count or
  picks the badge from a live snapshot for a given route+date.
- `lee_llm_router.staffing.eligibility.evaluate_eligibility(...)` derives the **live badge**
  for a route's channel from an `AvailabilitySnapshot` at a given date
  (`eligibility.py:530-596`, `_availability_badge`/`_dated_terms_entry`), falling back to the
  committed `NO DATA` badge (multiplier 1.0) when the channel has no recorded status. P4-1's
  `price` command is new CLI glue, not new pricing math: given `--route ID --input N --output
  N [--cached N] [--at DATE]`, it (a) loads the catalog + availability snapshot exactly as
  `staff`/`run` already do, (b) resolves the route's channel badge the same way
  `evaluate_eligibility` does (a channel with no recorded badge fails closed to `NO DATA`,
  never invents a badge), (c) calls `route_price` for that route+badge, and (d) multiplies
  the per-token list/marginal prices by the supplied token counts (input, output, and
  optional `cached` at the read-cache rate when the resolved model has one, else fails closed
  per `replacement_token_prices`'s existing unpriced-model behavior — no new unpriced-cache
  fallback is invented). Output: JSON with `list_usd` (replacement price × tokens) and
  `marginal_usd` (marginal price × tokens), plus the badge/multiplier/source fields
  `RoutePrice` already carries, so agent-orch's P4-4 caller and any human caller see the same
  provenance `catalog explain`/`staff` already print.
- No existing CLI subcommand computes a total-dollar price for a token count; `catalog
  explain` and `staff` only ever show the eligibility/selection view with per-route pricing
  metadata, not a caller-supplied token count multiplied through. This is the one genuinely
  new arithmetic surface in Group A; everything else it touches (`route_price`, the badge
  resolution, the pinned snapshot/rate-table lookups) is reused verbatim.

## Contradictions found and their disposition

| # | Contradiction | Disposition |
|---|---|---|
| 1 | `failure_classification.py`'s engine-level enum and `worker.py`'s per-adapter dict share the name "classify_failure" but are disjoint mechanisms. | Recorded only; P4-3 touches the engine-level enum exclusively, per sprint-plan scope. Not a Phase 4 blocker. |
| 2 | agent-orch's `(model, harness)` identity has no direct router route-id mapping; `price --route ID` needs a route id. | Resolved for P4-4: resolve to a router route id from the catalog before pricing; `"unavailable"` (never a guess) when no route matches. |
| 3 | `repair_cycle`/`repair_reason` (per-step) already occupy semantic territory adjacent to the new `ESCALATE`/`escalation_reason`/`parent_attempt` (per-attempt) fields. | Resolved: kept fully separate. `ESCALATE` is a new `policy_decision` value; `escalation_reason`/`parent_attempt` are new `StepAttemptRecord` fields. Nothing about `repair_cycle`/`repair_reason` changes. |
| 4 | `verification_tier`'s value set is not named anywhere in the sprint plan or D215/D216. | Resolved by analogy to the already-committed router `verdict.tier: engine_validation` vocabulary (`chief-answers-p1-3.md`) rather than inventing a new taxonomy; default `"engine_validation"`, named oracle/reviewer tier when a playbook step declares an external oracle. Not escalated — a reasonable, cited default under D86/D87 continue-and-record discipline. |
| 5 | P4-7's `task_type`/rollup approach (own `class` key vs. delegate to `evidence rollup`) is explicitly left as "owner's call recorded" by the sprint plan. | Not resolved here — Group B's (P4-6/P4-7) scope; recorded for that session. |

## Group A packet order (this contract governs)

P4-1 (`price`) -> P4-2 (crew reorder + `crew_ordering_rule`) -> P4-2b (subscription reserve,
D216, `chief-answers-p4-1.md`) -> P4-3 (`platform_timeout` + `verification_tier`) -> P4-4
(`cost_usd_marginal`, depends on P4-1's `price` command existing) -> P4-5 (`ESCALATE`,
depends on P4-3's failure-class/tier fields existing on the same `StepAttemptRecord`).
