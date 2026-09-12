# Phase 5 contracts — evidence report, ladder derivation, harvest, pricing refresh (P5-0)

Author: Sonnet 5 supervisor, first Phase 5 iteration, 2026-09-12. Authority: D220 on the
D219 baseline; D215/D216 doctrine; D206 class-metadata prohibition; D207 pricing-source
authority. Read-only pass over `lee-llm-router`'s `staffing/rollup.py`, `staffing/ledger.py`,
`staffing/terms.py`, `staffing/eligibility.py`, `config/staffing/*.yaml`, the attempt-record
schema, and `ai-workforce-benchmark`'s `config/escalation-ladders.json` and packet manifest
shape. Lists the exact seams P5-1 through P5-4 plug into.

## 1. Attempt ledger / rollup (`evidence report`'s data source, P5-1)

- Ledger path: `resolve_attempts_path()` (`staffing/ledger.py`), default
  `~/.local/state/lee-llm-router/attempts/<hostname>.jsonl`, override
  `$LEE_LLM_ROUTER_ATTEMPTS_STATE_ROOT`. One JSON object per line, appended by
  `append_attempt()`, read by `read_attempts()` (schema-validated against
  `config/staffing/schema/attempt-record.schema.json`).
- Attempt record required top-level fields: `schema_version`, `attempt_id`, `record_kind`,
  `captured_at`, `verified_success`, `provenance`. Everything else (`packet_id`, `route`,
  `class_record`, `usage`, `cost`, `wall_clock_ms`, `selection`, `verdict`,
  `failure_class`) is optional and, when absent, is `null` — never a fabricated zero
  (`rollup.py` module docstring, same discipline evidence report must follow).
- `route` object: `{model, effort, harness, channel, provider?}` — route identity is exactly
  the `(model, effort, harness, channel)` tuple (P0-1 contract, restated in the schema
  description); `provider` is observed metadata only, never part of identity, never a
  substitute for `channel`.
- `usage` object: `{basis, source?, unavailable_reason?, input_tokens?, output_tokens?,
  cached_input_tokens?, reasoning_tokens?, cache_write_tokens?, total_tokens?}`. `basis` is
  required; a record counts as "known usage" only when `basis` is one of `observed`,
  `provider_reported`, `calculated` (`rollup._known_usage`). Individual token counters are
  independent nullable observations (`rollup.TOKEN_FIELDS`); a component with no observed
  counters renders `null`, never `0`.
- `cost` object: `{basis, usd_list?, usd_marginal?, pricing_snapshot_ref?,
  pricing_snapshot_sha256?}`. `evidence report`'s "cost per verified success at list and
  marginal" must read `cost.usd_list`/`cost.usd_marginal` directly off each record it counts
  — it must not recompute a price out-of-band from `usage` and a route id, because that would
  duplicate `terms.route_price`'s badge/date resolution and could drift from the price that
  was actually charged/decided at attempt time. Where a counted attempt has no `cost` object
  or `cost.basis` is unavailable, its contribution to "cost per verified success" is
  `unavailable` for that row (report the reason), never silently zero and never averaged over
  fewer records without saying so.
- `class_record` object: `{class_key, role, oracle_type, domain_tags, size_band, language}`,
  all six required when present; the same closed vocab as `config/staffing/classes.yaml`.
  `class_source: "none"` is the only condition under which `class_key` is optional (imported
  historical attempts with no class metadata). `class_key` is the join key to
  `ai-workforce-benchmark` evidence and the report's grouping key — never a lookup to a
  preferred model/route (D206).
- `verdict` has two shapes that both mean "passed", and `evidence report`'s escalation/
  reviewer-fallback and pass counts must recognize both without double-counting
  (`rollup._pass_oracle_type` is the existing, tested reference implementation — reuse it,
  do not reimplement pass-detection): (a) canonical v2 records, `verdict == "pass"`, broken
  down by `class_record.oracle_type`; (b) agent-orch imports, `verdict == {"tier":
  "engine_validation"}` combined with `verified_success == true`, counted under the fixed key
  `engine_validation`.
- `selection` object: `{basis, reason, excluded, explain_ref}` — `excluded` is the list of
  routes the router ruled out and why (e.g. `reserve: N% kept in the tank (D216)`,
  `independence`). This is the source for "route changes recommended by evidence with the
  evidence line" and for explaining reserve/independence exclusions in the report, not a
  field to re-derive.
- Benchmark source de-duplication: `rollup.build_rollup` already materializes exactly one
  effective record per benchmark source run (canonical `benchmark:v6:<run_id>` correction
  wins over other raw-v6 lines, which win over legacy lines — `_without_superseded_benchmark_lines`).
  `evidence report` must call `rollup.rollup_ledger()`/`build_rollup()` for this
  materialization rather than reading `read_attempts()` raw, or it will double-count
  corrected benchmark runs.
- `rollup.build_rollup` groups strictly by `(route_id, class_key)` and returns
  `attempts, verified_pass, pass_by_oracle_type, token_sums, token_medians,
  wall_clock_median_ms, usage_known, comparison_eligible` (`comparison_eligible` = `attempts
  >= MINIMUM_SAMPLE_SIZE` = 5). `evidence report`'s per-class/per-route breakdown is this
  same grouping with cost/escalation/reviewer-fallback columns added — not a second
  aggregation with different grouping semantics. `route_id` is read from
  `router_event.route_id` (v2 records place it there, not in the `route` identity object).

## 2. Terms, channels, pricing, reserve (headroom/reserve column, P5-1; refresh, P5-4)

- `channels.yaml`: seven channel ids (`openai-sub`, `anthropic-sub`, `gemini-sub`,
  `opencode-go`, `openrouter`, `opencode-zen`, `local`), each with `fee_usd_month` (dated,
  `unknown` where unsourced), `windows`, `harness_lock`, `replacement_price_ref` (a pointer
  to a pricing source file, never a price value).
- `terms.yaml`: dated terms per channel; `reporting_price_ref` (list-price accounting) vs
  `decision_price_ref` (marginal-price decision input, badge-multiplied). Badge multipliers:
  `COLD 0.0, USE IT 0.0, ON TRACK 0.25, HOT 0.75, TOO FAST 1.0, NO DATA 1.0`; an unrecorded
  badge fails closed to `NO DATA` (multiplier 1.0) — never invented.
- `policy.yaml` `reserve_fraction`: `default: 0.10`, with per-channel overrides (currently
  `anthropic-sub: 0.10`, `gemini-sub: 0.10`, i.e. no override beyond the default today).
  `eligibility.py` excludes a route when `headroom.remaining_fraction <= reserve`, reason
  string `"reserve: {pct}% kept in the tank (D216)"` (`_RESERVE_REASON`). This is exactly the
  D216 rule; the report's "headroom utilisation per channel against the terms file and the
  reserve" means: for each channel, the live snapshot's `remaining_pct`/`used_pct` per bucket
  (`~/.local/state/lee-llm-router/availability/<host>.json`, `subscriptions[]` with
  `provider, bucket, status, used_pct, remaining_pct, pace_ratio, resets_at`) compared against
  `reserve_fraction` for that channel — is the channel currently inside or outside its
  reserve floor, and by how much.
- Live pricing sources: pinned OpenRouter snapshot
  `config/staffing/pricing/openrouter-20260911.json` (+ `.sha256` sidecar) and OpenCode Zen
  docs snapshot `config/staffing/pricing/opencode-zen-20260909.mdx` (+ `.sha256`), with
  `auto-orch/src/agent_orch/rate_table.yaml` as the P0-4 fallback where OpenRouter has no row
  (D207). `route_price()` (`staffing/terms.py:411`) is the single seam that turns a route id
  + token counts + date into list/marginal USD — P5-4's refresh script produces a new dated
  snapshot pair (file + sha256) and a reviewed commit repointing `channels.yaml`/`terms.yaml`
  refs; it must never touch `route_price`'s calculation logic.
- Pricing refresh precedent: D218/the 2026-09-11 refresh already did this once by hand (GLM
  5.3 Flash prompt/completion doubled, DeepSeek V4 Flash dropped) — see `terms.yaml`'s own
  comment block and `docs/staffing/phase4-execution-log.md` ("D218 DeepSeek V4.1 Flash
  intake") for the exact diff shape a script should reproduce mechanically.

## 3. Escalation ladders — two hand-authored locations, both in scope for the diff (P5-2)

- `ai-workforce-benchmark/config/escalation-ladders.json`: `schema_version`, `role_aliases`
  (benchmark role name -> canonical role, e.g. `implementation`/`reviewer` -> `coder`/
  `code-review`), `model_aliases` (route model id -> `{model_family, display_name}`), and
  `ladders: [{role, ladder_id, variant, label, rungs: [{rung_id, label, worker:
  {model_family, harness, effort | efforts: [...]}}]}]`. Six ladders today across `coder`,
  `planner`, `code-review`, each with a `-default` (cheap-first) and `-start-at-luna` variant.
- `config/staffing/crews.yaml` embedded `escalation_ladder` field: a flat list of **route
  ids** (not model families), e.g. the interactive `sol-low-glm-pi` crew's
  `[pi-z-ai-glm-5-3-flash-openrouter, pi-glm-5-3-flash-opencode-go,
  pi-gpt-5-6-luna-xhigh-openai-sub, codex-gpt-5-6-sol-high-openai-sub]`. This is a different
  representation (route id, not `{model_family, harness, effort}`) of the same concept —
  `evidence ladders --derive` must diff against both and state which representation each
  named ladder is in, rather than forcing a lossy conversion.
- `MINIMUM_SAMPLE_SIZE = 5` (`rollup.py`) is the same "comparison eligible" bar the sprint
  plan's gate (2) names ("`n ≥ 5` at some evidence level"); the derivation must reuse this
  constant, not restate `5` as a new magic number.
- Derived-ladder output path per the gate: `config/staffing/derived-ladders-<date>.json`.
  No existing schema for this file; P5-2 defines one additively (new file, new schema doc) —
  it does not modify `escalation-ladders.json`'s schema or `crews.schema.json`.

## 4. Benchmark packet manifest (harvest script target shape, P5-3)

- `ai-workforce-benchmark/packets/<task-id>/v1/manifest.json`, schema `pilot-packet/1`.
  Required shape observed in existing packets: `task_id`, `task_version`, `role`,
  `difficulty_intent`, `design_target_minutes`, `origin_kind`, `origin{repository_label,
  commit, parent_commit, observed_files, source_lines, evidence_summary,
  reconstruction_deviations}`, `repo_path`, `start_commit`, `start_tree`,
  `repo_archive_sha256`, `visible_inputs: [{path, sha256}]`,
  `environment{image, network, artifact_mount, private_evaluator_mount}`,
  `protocol{fresh_session, subagents, candidate_visible_paths, briefing_delivery,
  manifest_mount, candidate_network, candidate_cannot_read}`,
  `output_contract{required, verification, evaluation_schema,
  acceptance_is_not_model_ranking}`, `class{class_key, role, oracle_type, domain_tags,
  size_band, language}` — the class block is the same five-segment class key as router
  attempt records, the join surface D206 authorizes.
- Harvested packets are additive under `packets/harvested/<id>/v1/`, alongside a
  `briefing.md` (from the failed production packet's own text) and the packet's oracle
  command. Frozen/existing packets under `packets/` (non-`harvested`) are never touched.
  "Additively committed" + "the benchmark's own validation green" means: whatever
  `ai-workforce-benchmark`'s own packet-validation entrypoint is (check its `scripts/`/
  `tests/` for a manifest validator before inventing one) must pass on the new packets before
  they are committed there.
- Harvest source: the router's own attempt ledger, filtered to the last 30 days,
  `verdict: fail` (or the schema's failure-classification field, `capability_rejected`),
  grouped by `packet_id` + `class_record.class_key`. `packet_id` on production attempts is
  the router's own packet reference (whatever `--packet FILE` was dispatched with) — the
  harvest script reads that file's text for the benchmark packet's `briefing.md`, not a
  paraphrase.

## 5. Class taxonomy (shared join key, all packets)

- `taxonomy_version: classes-2026-09-09.1`. Canonical class-key string:
  `role/oracle_type/domain_tags/size_band/language`, `domain_tags` sorted ascending by
  codepoint, deduplicated, `+`-joined, `none` for the empty set. D206 (verbatim): "Class
  metadata MUST NOT map directly to a preferred model or route. It may only: 1. join
  production attempts to comparable benchmark evidence; and 2. determine whether an
  unevidenced cheap trial is permitted." No packet in this phase adds a class-to-model
  mapping; the report and ladder derivation only ever join and count by `class_key`.

## 6. What each packet actually adds (surface summary)

- **P5-1** (`evidence report --month YYYY-MM`): new `doctor.py` subparser + handler calling
  `rollup.rollup_ledger()`, joining `cost`/`selection`/channel-headroom data per §1-§2 above,
  filtered to `captured_at` within the given month. No new aggregation semantics beyond what
  `build_rollup` already computes — this packet adds cost/headroom/route-change columns and
  month filtering on top of it.
- **P5-2** (`evidence ladders --derive`): new subparser + handler reading the same rollup,
  computing per-class-per-role cheapest-first rungs at `n >= MINIMUM_SAMPLE_SIZE`, writing
  `config/staffing/derived-ladders-<date>.json`, and diffing against both ladder sources in
  §3. Where n < 5 for a class, the class's line reads "insufficient evidence, hand ladder
  retained" — never a guessed rung order.
- **P5-3** (`scripts/harvest_failed_packets.py`): reads the ledger per §1/§4, writes
  benchmark packet skeletons; at least two committed additively in
  `ai-workforce-benchmark` with that repo's own validation green.
- **P5-4** (`scripts/refresh_pricing_snapshot.sh`): re-fetches OpenRouter + the pinned Zen
  docs table, writes new dated snapshot + sha256, proposes (never installs) a cron line to
  `needs-lee.md` per D121/D167.
- **P5-5**: independent review of the whole Phase 5 diff, gates, closing report.
