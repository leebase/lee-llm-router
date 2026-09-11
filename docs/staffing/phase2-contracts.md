# Phase 2 staffing-service contracts

Authority: D211 rulings 1–8 on the D210 accepted baseline. D204–D209 remain
active, especially D205/D206: a class key joins comparable evidence and gates
cheap trials; it never maps a class directly to a model or route.

## P2-0 observed input shapes

`evidence rollup` emits `{"groups": [...]}`. Each group has exactly
`route_id`, `class_key`, `attempts`, `verified_pass`, `pass_by_oracle_type`,
`token_sums`, `token_medians`, `wall_clock_median_ms`, `usage_known`, and
`comparison_eligible`. Both token objects carry `input_tokens`,
`output_tokens`, `cached_input_tokens`, `reasoning_tokens`, and
`total_tokens`. Missing facts stay JSON `null`; exact half-integer medians may
be lossless decimal strings.

Attempt record v2 is the strict `schema_version: 2` envelope documented in
`attempt-record.md`. Phase 2 consumes, without moving or duplicating them:
`record_kind`, `attempt_id`, `packet_id`, `parent_attempt_id`,
`escalation_reason`, `router_event.route_id`, `route`, `supervisor_route`,
`class_record.class_key`, `class_record.oracle_type`, `usage.basis`, usage
token counters, `cost.basis`, `cost.usd_list`, `cost.usd_marginal`,
`wall_clock_ms`, `oracle_cmd`, `verdict`, `failure_class`,
`verified_success`, and `provenance.source`. Benchmark prior rows are
`benchmark_run`; production posterior rows are `router_run`.

`catalog explain --json` emits top-level `role`, `class_key`, `at`, `terms`,
`floors_disclosure`, `independence`, and `routes`. Each term has
`effective_from`, `fee_usd_month`, and `kind`; independence has `evaluated`,
`applicable`, and `disclosure`. Each route has `route_id`, `eligible`,
`channel`, `badge`, `headroom`, `health`, marginal and replacement input/output
prices, and `reasons`. Ordering and exclusion reasons are evidence.

Named crew blocks use `crew_id`, `kind`, optional `governed_ref`,
`supervisor_route`, role-keyed `worker_routes`, `reviewer_route`,
`escalation_ladder`, `authority`, and `evidence_ref`. `sol-low-glm-pi` and
`luna-sol` are saved interactive blocks. `auto` is computed with
`authority: policy` and no invented route-bearing fields.

## D211 rulings 1–8, bound to fields

1. **Evidence join.** Exact `class_record.class_key` first, then: drop
   `language`; drop `size_band`; drop `domain_tags`; `role/oracle_type`; then
   `none`. Return exactly `{level, n, k, estimate, low_evidence, prior_n,
   posterior_n}` and expose the used level as `evidence_level`. `n` is joined
   attempts; `k` is verified passes; benchmark rows count in `prior_n` and
   production rows in `posterior_n`. `estimate = (k+1)/(n+2)`;
   `low_evidence` is exactly `n < 5`. Never show the estimate without `k/n`
   and level.
2. **Demand.** Expected tokens and wall clock come from rollup
   `token_medians` and `wall_clock_median_ms` at the same join level. With no
   usable median emit `demand: unknown`, and no expected-cost figure.
3. **Ladder arithmetic.** Known rungs return exactly `{route, a, v, s, q,
   q_prime, E}` plus the argmin start, using
   `E_i=(a_i+v+s)+(1-q_i)*((a'_i+v+s)+(1-q'_i)*E_(i+1))`. `v=0` for a
   deterministic oracle and is the chosen reviewer route's expected cost for
   a judge oracle. Derive `s` only from rows with `supervisor_route` when
   `n>=5`; otherwise omit and state why. `q_prime=q` unless repair rows
   (`parent_attempt_id`) reach `n>=5`. Terminal cost is policy
   `human_escalation_cost_usd: 5.00`, source D211. If arithmetic is
   unavailable, order eligible routes by marginal price with `proof_status`
   first and say `expected cost unavailable`.
4. **Proof status.** `proven` means any `router_run` for the route has
   `usage.basis` in `{observed, provider_reported}` or
   `verified_success: true`; otherwise `unproven`. `auto` never selects an
   unproven route while a proven eligible one exists, and says so.
5. **Modes.** `auto` has authority `policy`; `crew NAME` renders the saved
   block/authority; `bind ROUTE --authorized-by --reason` is ledgered through
   `events.py`. Never-automatic routes bind only with `--authorized-by lee`.
   CLI: `lee-llm-router staff --role R --class C [--mode auto|crew NAME|bind
   ROUTE] [--author-route ID] [--at DATE] [--json]`. The compact block is
   always emitted and is never a gate.
6. **Next action.** Pure mapping: `platform_*` →
   `retry_same_route_after_platform_repair`; `spec_rejected` →
   `return_to_planner`; first `capability_rejected` → `repair_same_route`,
   second → `escalate`; `unaccounted_spend` → `reconcile_then_retry`; unknown
   → `supervisor_judgment`. It never dispatches.
7. **Replay fixtures.** The five trace-derived facts below are fixed inputs;
   tests compare `expected_action` exactly.
8. **Removal.** Remove resolver selection and old `LLMRouter` only after
   consumer grep is empty and the full suite passes. Preserve consumed
   `Resolution`/event shapes and note any retained consumer in `needs-lee.md`.
   Shims point to `staff`; resolve-only semantics remain.

## Five replay facts

| Case | Class key | Oracle | Failure class | Expected action |
|---|---|---|---|---|
| `linux-sniffcopy-a24aa58959fe` | `impl/deterministic/infra-env/m/c` | deterministic | `platform_timeout` | `retry_same_route_after_platform_repair` |
| `linux-jsoncarve-35-cycle-loop` | `plan/judge/authority/l/yaml-config` | judge | `spec_rejected` | `return_to_planner` |
| `snowflake-elt-478250b5f6a1` | `impl/deterministic/ui-browser/m/mixed` | deterministic | `platform_env` | `retry_same_route_after_platform_repair` |
| `revenue-e3fbeb9f3c4c` | `impl/judge/authority/s/markdown` | judge | `unaccounted_spend` | `reconcile_then_retry` |
| `job-search-starburst-exit-143` | `impl/human/none/s/mixed` | human | `platform_env` | `retry_same_route_after_platform_repair` |

The class keys apply the locked taxonomy to the trace's work, oracle, failure
surface, packet breadth, and artifacts. They are evidence keys, never route
preferences.
