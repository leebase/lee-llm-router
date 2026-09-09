# Attempt record — field mapping (P0-9b)

**Status:** document only. This file documents the accepted schema
`config/staffing/schema/attempt-record.schema.json` (Phase 0, P0-9a) field by
field. It is a mapping document, not a specification change: the schema itself
is the authority for every constraint quoted or summarized here.

**No writer exists until Phase 1.** Nothing in this repository currently
produces a unified attempt record. `src/lee_llm_router/events.py` writes only
its own ledger event shape (`EVENT_FIELDS` via `build_event`); no code in this
repo or in the owner repositories assembles, validates, or writes
attempt-record documents. The P0-9a deliverable was the schema and its
examples; this P0-9b deliverable is this document only. Any writer is Phase 1
work and does not exist yet. (Phase 0 execution-log records that no Phase 1
work has begun.)

Source abbreviations used in the tables below. Each names a source system and
the source contract the field comes from:

| Abbrev | Source system | Source contract |
|---|---|---|
| **ROUTER** | lee-llm-router (`src/lee_llm_router/events.py`) | `EVENT_FIELDS` / `build_event` contract: all 17 keys always present; `OPTIONAL_FIELDS` (`ts`, `host`, `harness`, `effort`, `authorized_by`, `snapshot_observed_at`) filled by the builder; `authorized_by` non-null only when `mode` is `bind` (`BIND_MODE`); headroom wire values from `src/lee_llm_router/availability.py` `Health` |
| **AO** | Agent-Orch (`/home/lee/projects/auto-orch/src/auto_orch/performance.py`) | `OBSERVATION_SCHEMA` (`agent-orch:model-effort-observation:v1`), embedded verbatim with internal `$ref`s re-scoped |
| **BENCH** | AI Workforce Benchmark (`/home/lee/projects/ai-workforce-benchmark/config/crew-run.schema.json`) | crew-run record, embedded verbatim minus its `$schema`/`$id`/`title`/`description` envelope |
| **P0-1** | accepted Phase 0 contracts (`docs/staffing/phase0-contracts.md` §Route/§Channel/§Class key; `config/staffing/schema/routes.schema.json` `$defs/route`; `config/staffing/schema/classes.schema.json` `$defs/classBlock`) | route identity tuple, `usage_capture`, class-key grammar, D206 |
| **P0-9** | P0-9a synthesis (this schema's own task contract) | unified-record fields introduced by `attempt-record.schema.json` that no single named source supplies |

A source citation in the Source column means the field's **shape and value
constraints** are taken from that source. It does **not** mean that unlike
sources carry identical semantics for identically named fields; the
"Semantics" notes below call out the deliberate non-unifications (review
verdict vs. benchmark acceptance vs. failure class).

---

## `verified_success` — prominent statement

`verified_success: true` requires **all** of the following, simultaneously and
genuinely present in the record (enforced by the schema's `allOf` gate on
`verified_success: true`):

1. A substantive, non-null `route` — the full identity tuple
   `(model, effort, harness, channel)` per the P0-1 route contract. A source
   that records only requested model/harness/effort (AO), or
   model/harness/effort/model_family with no channel (BENCH worker), does not
   satisfy this.
2. `supervisor_route` present (non-null). Null is the explicit "the source
   records no supervisor route" marker.
3. A structured `class_record` including `class_key` and `oracle_type` (all
   six classBlock fields required).
4. A `verdict`, restricted to `pass` or `accepted` when `verified_success` is
   true.
5. `failure_class` present and **null** (no failure recorded).
6. `usage` with **all five token counters** (`input_tokens`,
   `output_tokens`, `cached_input_tokens`, `reasoning_tokens`,
   `total_tokens`) non-null integers, plus a valid `usage_capture` (one of
   `native_json | stream_events | worker_written | none`).
7. `cost` with non-null `amount_usd` (benchmark money-string shape) **and** a
   non-empty `basis` citation.
8. `wall_clock_ms` non-null, non-negative integer.

If the source's outcome passed but **any** required evidence is missing, the
record still gets `verified_success: false`. Legacy and existing records with
incomplete evidence remain `false` forever — missing evidence is never
invented, estimated, or backfilled to reach `true`. A source that reports
success (e.g. AO `review.final_verdict: "pass"` or BENCH
`final_acceptance: "accepted"`) without the complete route, supervisor route,
token, cost, and duration evidence yields `false`. `provider` is optional
observed metadata and is never invented; absence of channel, provider,
supervisor route, usage, cost, or duration is recorded as `null` or by field
absence — never fabricated.

---

## Failure classes (exact list)

`failure_class` admits exactly five string values, proven by the P0-9a task
contract. No named source proves others, so none are added:

- `platform_timeout`
- `platform_env`
- `spec_rejected`
- `capability_rejected`
- `unaccounted_spend`

`null` means no failure recorded and is **required** to be null when
`verified_success` is true. On `interactive` records the router event is a
dispatch event that records no outcome, so the source event itself supplies no
failure classification and `failure_class` may remain absent; the accepted
schema does not, however, forbid `failure_class` on interactive records — it
constrains only `verdict` (forbidden) and `verified_success` (forced `false`)
there, so a synthesized failure classification remains schema-valid.

---

## D206 verbatim, and class ↔ route coexistence

Quoted verbatim from `docs/staffing/phase0-contracts.md` (§Class-metadata
prohibition, D206):

> Class metadata MUST NOT map directly to a preferred model or route. It may only:
> 1. join production attempts to comparable benchmark evidence; and
> 2. determine whether an unevidenced cheap trial is permitted.

The schema therefore permits `class_record` and `route` (and
`supervisor_route`) to **coexist on the same record only as observed attempt
evidence**: both are facts about what happened in this attempt, recorded by
its source. The class block describes the work; the route block describes the
attempt's identity tuple and observed metadata. There is **no**
class→preferred-route or class→preferred-model mapping anywhere in the
schema: no such property exists and none may be added (a class-to-model or
class-to-route property fails `classes.schema.json` `$defs/classBlock` per
D206 and is a High review finding). The only permitted uses of class metadata
are the two D206 jobs above. Route identity is exactly
`(model, effort, harness, channel)` (P0-1 §Route; `routes.schema.json`
`$defs/route`); `provider` is separate optional observed metadata — not part
of the identity tuple, never a replacement for `channel`, and never invented
for a source that lacks one.

---

## Top-level record fields

One row per top-level property of the accepted schema.

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `schema_version` | `const: 1` | **P0-9** — unified-record envelope version introduced by this schema | Not taken from any named source schema. |
| `attempt_id` | `string`, pattern `^[A-Za-z0-9._:-]+$`, minLength 1 | **BENCH** — pattern taken verbatim from crew-run `attempt_id` | A real Agent-Orch attempt id (e.g. `a6a85c6b02c6`) matches it. Mirrors `benchmark_run.attempt_id` when present. |
| `record_kind` | enum `agent_orch` \| `benchmark_run` \| `interactive` | **P0-9** — discriminant selecting the required embedded source payload (`allOf` bindings) | An `interactive` record is a dispatch event: no verdict may be asserted and `verified_success` is always `false`. |
| `captured_at` | `string`, `format: date-time` | **P0-9** — record capture timestamp | Analogous to **ROUTER** `ts` and **BENCH** `provenance.assembled_at`; the analogy is positional, not a claim of identical semantics. |
| `verified_success` | `boolean` | **P0-9** — synthesis evidence gate (see prominent section above) | True only when source-reported success *and* every required evidence field are genuinely present. |
| `route` | `$ref: #/$defs/route` | **P0-1** — route identity tuple `(model, effort, harness, channel)` (phase0-contracts §Route; `routes.schema.json` `$defs/route`) | Observed attempt evidence only; never derived from class metadata (D206). Optional at top level; required (non-null) when `verified_success: true`. |
| `supervisor_route` | `anyOf: [route, null]` | **P0-1** — named-crew contract: a named crew carries a supervisor route (`crews[].supervisor_route` in `docs/staffing/catalog.md`) | Present only when the source records one; null = the source records no supervisor route; never invented. Required non-null when `verified_success: true`. |
| `class_record` | `$ref: #/$defs/classRecord` | **P0-1** — strict class vocabulary reproduced verbatim from `classes.schema.json` `$defs/classBlock` | Same six required fields, same closed value sets, same canonical `class_key` pattern. Coexists with route only as observed attempt evidence (D206). |
| `verdict` | enum `pass` \| `fail` \| `accepted` \| `not_accepted` \| `unverified` | **AO** (`review.final_verdict`: `pass`/`fail`) and **BENCH** (`final_acceptance` enum: `accepted`/`not_accepted`/`unverified`) | Deliberately NOT unified semantically: `pass`/`fail` are Agent-Orch review words; `accepted`/`not_accepted`/`unverified` are benchmark acceptance words. They do not mean the same thing; consumers must branch on `record_kind`. Forbidden on `interactive` records (schema sets `verdict: false` there). Restricted to `pass`/`accepted` when `verified_success: true`. |
| `failure_class` | enum of the five classes above, or `null` | **P0-9** — failure taxonomy from the P0-9a task contract | Exactly five proven values; `null` = no failure recorded; required null when `verified_success: true`. On `interactive` records the router event itself supplies no outcome or failure classification, so `failure_class` may remain absent there, but the accepted schema does not prohibit one (it constrains only `verdict` and `verified_success` on `interactive`). |
| `usage` | `$ref: #/$defs/usage` | **P0-9** structure with **P0-1** `usage_capture` contract | See `usage` table below. |
| `cost` | `$ref: #/$defs/cost` | **P0-9** structure with **BENCH** money-string shape and **P0-1** no-invented-price rule | See `cost` table below. |
| `wall_clock_ms` | `integer \| null`, minimum 0 | **P0-9** synthesis; **BENCH** supplies `elapsed_ms` (stage/totals) | **ROUTER** events and **AO** observations record no duration → null. Never estimated or invented. Required non-null when `verified_success: true`. |
| `router_event` | `$ref: #/$defs/eventRecord` | **ROUTER** — one ledger event, exactly `EVENT_FIELDS` keys, `build_event` shape | Required when `record_kind: interactive`. |
| `agent_orch_observation` | `$ref: #/$defs/agentOrchObservation` | **AO** — `OBSERVATION_SCHEMA` embedded with internal `$ref`s re-scoped | Required when `record_kind: agent_orch`. |
| `benchmark_run` | `$ref: #/$defs/crewRunRecord` | **BENCH** — crew-run record embedded verbatim minus envelope | Required when `record_kind: benchmark_run`. |
| `provenance` | `$ref: #/$defs/provenance` | **P0-9** — record-level provenance added by this schema | Who recorded this unified record and which named sources it cites. Required at top level. |

Additional properties are closed (`additionalProperties: false`); exactly
`schema_version`, `attempt_id`, `record_kind`, `captured_at`,
`verified_success`, `provenance` are required on every record.

---

## `$defs/route`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `model` | `string`, minLength 1 | **P0-1** tuple member; observed from **ROUTER** `model`, **AO** participant `model`, **BENCH** worker `model` | Part of the identity tuple. |
| `effort` | `string \| null`, minLength 1 | **P0-1** tuple member; observed from **ROUTER** `effort`, **AO** participant `effort`, **BENCH** worker `effort` | Null only where the harness has no effort dial. Part of the identity tuple. |
| `harness` | `string`, minLength 1 | **P0-1** tuple member; observed from **ROUTER** `harness`, **AO** participant `harness`, **BENCH** worker `harness` | Part of the identity tuple. |
| `channel` | `string`, minLength 1 | **P0-1** tuple member; observed from **ROUTER** `channel` | Must match a `channel_id` in the channel catalog (`docs/staffing/catalog.md`); the cross-catalog check is loader work. **AO** and **BENCH** record no channel, so neither source can produce a full tuple on its own. |
| `provider` | `string \| null` (optional) | **ROUTER** `provider` | Optional observed metadata: not part of the identity tuple, never a replacement for `channel`, null/absent when the source does not observe a provider. Never invented. |

---

## `$defs/classRecord`

Reproduces `classes.schema.json` `$defs/classBlock` verbatim: same six
required fields, same closed value sets, same canonical `class_key` pattern.

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `class_key` | `string`, pattern `^(impl\|plan\|review\|judge\|prose)/(deterministic\|judge\|human\|none)/(none\|(?:persistence\|concurrency\|security\|authority\|ui-browser\|data-schema\|infra-env)(?:\+(?:persistence\|concurrency\|security\|authority\|ui-browser\|data-schema\|infra-env))*)/(xs\|s\|m\|l)/(python\|typescript\|shell\|c\|sql\|yaml-config\|markdown\|mixed)$` | **P0-1** class-key grammar (phase0-contracts §Class key) rendered canonically by **P0-1** `classes.schema.json` `$defs/classBlock` | Canonical rendering: `role/oracle_type/domain_tags/size_band/language`; tags sorted ascending by codepoint, deduplicated, `+`-joined; empty set = literal `none`, never an empty segment. Cross-field equality with the components and sortedness/dedup beyond the pattern are loader work (`catalog.validate_class_block`). |
| `role` | enum `impl` \| `plan` \| `review` \| `judge` \| `prose` | **P0-1** initial value set (phase0-contracts §Class key; `classes.schema.json`) | Closed. |
| `oracle_type` | enum `deterministic` \| `judge` \| `human` \| `none` | **P0-1** initial value set (phase0-contracts §Class key; `classes.schema.json`) | Closed; feeds the deterministic don't-cheap-trial rule. |
| `domain_tags` | array, unique items from the closed seven-tag vocabulary `persistence`, `concurrency`, `security`, `authority`, `ui-browser`, `data-schema`, `infra-env`; possibly empty | **P0-1** initial value set (phase0-contracts §Class key; `classes.schema.json`) | Authoritative component for the third key segment. |
| `size_band` | enum `xs` \| `s` \| `m` \| `l` | **P0-1** initial value set (phase0-contracts §Class key; `classes.schema.json`) | Closed. |
| `language` | enum `python` \| `typescript` \| `shell` \| `c` \| `sql` \| `yaml-config` \| `markdown` \| `mixed` | **P0-1** initial value set (phase0-contracts §Class key; `classes.schema.json`) | Closed. |

Per D206, no class→model or class→route property exists here (see the D206
section above).

---

## `$defs/usage` (and `tokenCounter`)

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `usage_capture` | enum `native_json` \| `stream_events` \| `worker_written` \| `none` | **P0-1** — exactly the accepted P0-1 contract (`routes.schema.json` `$defs/route.usage_capture`) | `none` means the source captures no usage and every counter is then null (schema-enforced); no counter is ever estimated or invented. |
| `input_tokens` | `tokenCounter`: `integer \| null`, minimum 0 | **P0-9** — synthesis counter; populated only when a source reports it | None of the three embedded source shapes currently records token counters. |
| `output_tokens` | `tokenCounter` | **P0-9** — synthesis counter; populated only when a source reports it | As above. |
| `cached_input_tokens` | `tokenCounter` | **P0-9** — synthesis counter; populated only when a source reports it | As above. |
| `reasoning_tokens` | `tokenCounter` | **P0-9** — synthesis counter; populated only when a source reports it | As above. |
| `total_tokens` | `tokenCounter` | **P0-9** — synthesis counter; populated only when a source reports it | As above. |

All six fields are required; the counters are null where source availability
requires. All five counters plus `usage_capture` are required non-null when
`verified_success: true`.

---

## `$defs/cost`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `amount_usd` | `money_or_null`: `string \| null`, pattern `^(0|[1-9][0-9]*)(\.[0-9]+)?$` | **BENCH** money-string shape; **P0-1** no-invented-price rule (phase0-contracts §Terms and prices) | Null when the source does not price the attempt. Required non-null when `verified_success: true`. |
| `basis` | `string`, minLength 1 | **P0-1** — every price (or its absence) has a source line: pricing snapshot, crews file, contract terms entry, or an explicit statement that the source records no price | Free-form citation; no invented basis categories. Required non-empty when `verified_success: true`. |
| `pricing_snapshot_ref` | `string \| null`, minLength 1 | **BENCH** stage `pricing_snapshot_ref` | Null/absent when no snapshot is cited. |
| `pricing_snapshot_sha256` | `$defs/sha256` (`^[0-9a-fA-F]{64}$`) or null | **BENCH** stage `pricing_snapshot_sha256` | Null/absent when no snapshot is cited. |

---

## `$defs/eventRecord` (router event — all 17 `EVENT_FIELDS`)

Exactly the keys of `src/lee_llm_router/events.py` `EVENT_FIELDS`, in the
shape `build_event` returns: all seventeen keys are present, with
`OPTIONAL_FIELDS` (`ts`, `host`, `harness`, `effort`, `authorized_by`,
`snapshot_observed_at`) filled by the builder and therefore required here,
nullable where the builder allows `None`.

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `ts` | `string`, `format: date-time` | **ROUTER** `EVENT_FIELDS`; `OPTIONAL_FIELD` filled by `build_event` (`_utc_now_iso`, aware UTC ISO, seconds precision) | Builder default: now. |
| `host` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS`; `OPTIONAL_FIELD` defaulted to `socket.gethostname()` by `build_event` | Same value `availability.py` uses. |
| `harness` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS`; `OPTIONAL_FIELD` defaulted to `"cli"` by `build_event` | Caller-supplied otherwise. |
| `crew` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Caller-supplied. |
| `role` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Caller-supplied. |
| `mode` | enum `strict` \| `flex` \| `bind` | **ROUTER** resolution modes documented by `events.py` | `bind` is `events.BIND_MODE`, the only mode permitting non-null `authorized_by`. |
| `worker_id` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Caller-supplied. |
| `provider` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Observed metadata; not part of the route identity tuple. |
| `model` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Route identity component. |
| `effort` | `string \| null`, minLength 1 | **ROUTER** `EVENT_FIELDS`; `OPTIONAL_FIELD` defaulting to `None` | Route identity component. |
| `channel` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Route identity component; ids cataloged in `docs/staffing/catalog.md`. |
| `headroom` | enum `healthy` \| `degraded` \| `likely_exhausted` \| `exhausted` \| `unknown` | **ROUTER** — funding-headroom wire values from `src/lee_llm_router/availability.py` `Health` | Judgement that produced the dispatch. |
| `reason` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Caller-supplied. |
| `authorized_by` | `string \| null` | **ROUTER** `EVENT_FIELDS`; `OPTIONAL_FIELD` defaulting to `None`; non-null only when `mode` is `bind` (`build_event` raises otherwise; schema `allOf` enforces the same) | — |
| `route_id` | `string`, minLength 1 | **ROUTER** `EVENT_FIELDS` (required) | Opaque router route id. |
| `snapshot_observed_at` | `string` (`format: date-time`) or `null` | **ROUTER** `EVENT_FIELDS`; `OPTIONAL_FIELD` defaulting to `None` | Availability-snapshot observation time. |
| `snapshot_stale` | `boolean` | **ROUTER** `EVENT_FIELDS` (required; `build_event` rejects non-bool) | Availability-snapshot staleness flag. |

---

## `$defs/agentOrchObservation` (Agent-Orch observation, embedded verbatim)

Embedded from **AO** `OBSERVATION_SCHEMA` (`performance.py`), verbatim except
that its internal `$defs.provenance`/`participant`/`severityCounts` are
re-scoped to `$defs/aoProvenance`, `$defs/aoParticipant`, and
`$defs/aoSeverityCounts`. Required when `record_kind: agent_orch`.

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `schema_version` | `const: 1` | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `idempotency_key` | `string`, pattern `^sha256:[0-9a-f]{64}$` | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `source` | object, closed; see sub-table | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `task` | object, closed; see sub-table | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `producer` | `$ref: aoParticipant` | **AO** `OBSERVATION_SCHEMA` `$defs/participant` | Verbatim (re-scoped `$ref`). |
| `reviewer` | `$ref: aoParticipant` | **AO** `OBSERVATION_SCHEMA` `$defs/participant` | Verbatim (re-scoped `$ref`). |
| `outcome` | object, closed; see sub-table | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `review` | object, closed; see sub-table | **AO** `OBSERVATION_SCHEMA` | Verbatim. |

### `agent_orch_observation.source`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `mission` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `cycle_id` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `run_id` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `producer_step_id` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `producer_attempt` | `integer`, minimum 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `review_step_id` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `review_attempt` | `integer`, minimum 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |

### `agent_orch_observation.task`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `backlog_title` | `string \| null` | **AO** `OBSERVATION_SCHEMA` | Nullable in the source. |
| `producer_role` | `string \| null` | **AO** `OBSERVATION_SCHEMA` | Nullable in the source. |
| `reviewer_role` | `string \| null` | **AO** `OBSERVATION_SCHEMA` | Nullable in the source. |

### `agent_orch_observation.producer` / `.reviewer` (`$defs/aoParticipant`)

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `requested` | `$ref: aoProvenance` | **AO** `OBSERVATION_SCHEMA` `$defs/participant` | Verbatim (re-scoped `$ref`). |
| `executed` | `$ref: aoProvenance` | **AO** `OBSERVATION_SCHEMA` `$defs/participant` | Verbatim (re-scoped `$ref`). |
| `executed_attested` | `boolean` | **AO** `OBSERVATION_SCHEMA` `$defs/participant` | Verbatim. |

### `$defs/aoProvenance` (AO requested/executed block)

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `harness` | `string`, minLength 1 | **AO** `_PROVENANCE_SCHEMA` (`performance.py`) | Verbatim. |
| `model` | `string`, minLength 1 | **AO** `_PROVENANCE_SCHEMA` | Verbatim. |
| `effort` | enum `low` \| `medium` \| `high` \| `xhigh` \| `unknown` | **AO** `_PROVENANCE_SCHEMA` (`CANONICAL_EFFORTS` + `unknown`) | Verbatim. |

Requested-only provenance with `executed_attested: false` does **not**
constitute a substantive executed route: the source records no channel, so no
full `(model, effort, harness, channel)` identity tuple exists in this shape.

### `agent_orch_observation.outcome`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `run_status` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `run_passed` | `boolean` | **AO** `OBSERVATION_SCHEMA` | Verbatim. Source outcome evidence; not interchangeable with `verdict`. |
| `cycle_outcome` | `string`, minLength 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `final_completion` | `boolean` | **AO** `OBSERVATION_SCHEMA` | Verbatim. |

### `agent_orch_observation.review`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `final_verdict` | enum `pass` \| `fail` | **AO** `OBSERVATION_SCHEMA` | Source of the unified `verdict` values `pass`/`fail`. Semantics are Agent-Orch review semantics only. |
| `first_review_clean` | `boolean` | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `severity_threshold` | enum `Low` \| `Medium` \| `High` \| `Critical` | **AO** `OBSERVATION_SCHEMA` (`SEVERITIES`, reversed order) | Verbatim. |
| `severity_counts` | `$ref: aoSeverityCounts` | **AO** `_SEVERITY_COUNTS_SCHEMA` | Verbatim (re-scoped `$ref`). |
| `finding_count` | `integer`, minimum 0 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `blocking_finding_count` | `integer`, minimum 0 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `review_cycles` | `integer`, minimum 1 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `repair_cycles` | `integer`, minimum 0 | **AO** `OBSERVATION_SCHEMA` | Verbatim. |
| `artifact_sha256s` | array, minItems 1, items `^[0-9a-f]{64}$` | **AO** `OBSERVATION_SCHEMA` | Verbatim. |

### `$defs/aoSeverityCounts`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `Critical` | `integer`, minimum 0 | **AO** `_SEVERITY_COUNTS_SCHEMA` (`SEVERITIES`) | Verbatim. |
| `High` | `integer`, minimum 0 | **AO** `_SEVERITY_COUNTS_SCHEMA` | Verbatim. |
| `Medium` | `integer`, minimum 0 | **AO** `_SEVERITY_COUNTS_SCHEMA` | Verbatim. |
| `Low` | `integer`, minimum 0 | **AO** `_SEVERITY_COUNTS_SCHEMA` | Verbatim. |

---

## `$defs/crewRunRecord` (benchmark crew-run record, embedded verbatim)

Embedded from **BENCH** (`crew-run.schema.json`) verbatim, minus its
`$schema`/`$id`/`title`/`description` envelope. It keeps its own `attempt_id`;
the unified top-level `attempt_id` mirrors it. Required when
`record_kind: benchmark_run`.

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `schema_version` | `const: "benchmark.crew-run/1"` | **BENCH** | Verbatim. |
| `crew_name` | enum of 14 crew ids (`mixed-flagship` … `gemini-pro-crew`) | **BENCH** | Verbatim closed enum. |
| `crews_file_sha256` | `$defs/sha256` | **BENCH** | Verbatim. |
| `mission` | object, closed; see sub-table | **BENCH** | Verbatim. |
| `attempt_id` | `string`, pattern `^[A-Za-z0-9._:-]+$`, minLength 1 | **BENCH** | The unified top-level `attempt_id` takes its pattern verbatim from here. |
| `stages` | array of `$defs/crewStage`, minItems 1 | **BENCH** | Verbatim. |
| `totals` | object, closed; see sub-table | **BENCH** | Verbatim. |
| `final_acceptance` | `$defs/acceptance`: `accepted` \| `not_accepted` \| `unverified` \| `null` | **BENCH** | Source of the unified `verdict` values `accepted`/`not_accepted`/`unverified`. Benchmark acceptance semantics; not interchangeable with Agent-Orch review verdict semantics. |
| `provenance` | object, closed; see sub-table | **BENCH** | Verbatim. |

### `benchmark_run.mission`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `task_key` | `string`, minLength 1 | **BENCH** | Verbatim. |
| `role_composition` | array of `string`, minItems 1, unique | **BENCH** | Verbatim. |

### `$defs/crewStage` (benchmark_run.stages[])

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `stage` | enum `envision` \| `ideate` \| `reconsider` \| `score` \| `author` | **BENCH** | Verbatim. |
| `worker` | `$ref: crewWorker` | **BENCH** `$defs/worker` | See crewWorker table. |
| `run_id` | `string \| null`, minLength 1 | **BENCH** | Verbatim. |
| `cost_low_usd` | `money_or_null` | **BENCH** | Verbatim; part of the benchmark cost range. |
| `cost_high_usd` | `money_or_null` | **BENCH** | Verbatim; part of the benchmark cost range. |
| `elapsed_ms` | `integer \| null`, minimum 0 | **BENCH** | Verbatim; a source for unified `wall_clock_ms`. |
| `acceptance` | `$defs/acceptance` | **BENCH** | Stage-level acceptance; distinct from `final_acceptance` and from `verdict` semantics. |
| `pricing_snapshot_ref` | `string \| null`, minLength 1 | **BENCH** | Source for unified `cost.pricing_snapshot_ref`. |
| `pricing_snapshot_sha256` | `string \| null`, pattern `^[0-9a-fA-F]{64}$` | **BENCH** | Source for unified `cost.pricing_snapshot_sha256`. |
| `evidence_status` | enum `measured` \| `hand-assembled` \| `unmeasured` | **BENCH** | Verbatim. |

### `$defs/crewWorker` (benchmark worker block)

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `model` | `string`, minLength 1 | **BENCH** | Route identity component candidate. |
| `harness` | `string`, minLength 1 | **BENCH** | Route identity component candidate. |
| `effort` | `string \| null`, minLength 1 | **BENCH** | Route identity component candidate. |
| `model_family` | `string`, minLength 1 | **BENCH** | Benchmark-only metadata; **not** part of the unified route identity tuple. |

The worker records `model`/`harness`/`effort`/`model_family` only, with no
channel and no supervisor route, so this source alone cannot produce a full
route identity tuple; nothing beyond the source is claimed.

### `benchmark_run.totals`

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `cost_low_usd` | `money_or_null` | **BENCH** | Verbatim; a range bound, not a single amount. |
| `cost_high_usd` | `money_or_null` | **BENCH** | Verbatim; a range bound, not a single amount. |
| `elapsed_ms` | `integer \| null`, minimum 0 | **BENCH** | Verbatim; a source for unified `wall_clock_ms`. |
| `stage_count` | `integer`, minimum 1 | **BENCH** | Verbatim. |
| `priced_stage_count` | `integer`, minimum 0 | **BENCH** | Verbatim. |
| `timed_stage_count` | `integer`, minimum 0 | **BENCH** | Verbatim. |

### `benchmark_run.provenance` (embedded crew-run provenance)

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `assembled_by` | `string`, minLength 1 | **BENCH** | Verbatim. |
| `assembled_at` | `string`, `format: date-time` | **BENCH** | Analogous to unified `captured_at`; the analogy is positional, not identical semantics. |
| `source_csv_sha256` | `$defs/sha256` | **BENCH** | Verbatim. |
| `notes` | array of `string` | **BENCH** | Verbatim. |

---

## `$defs/provenance` (unified record-level provenance)

| Field | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `recorded_by` | `string`, minLength 1 | **P0-9** — record-level provenance introduced by this schema | Identifies who recorded the unified record (e.g. the P0-9a task id in the examples). |
| `source_refs` | array of `string` (minLength 1 each), minItems 1 | **P0-9** — record-level provenance introduced by this schema | References to the named sources that justify this record's fields. |
| `notes` | array of `string` (minLength 1 each), optional | **P0-9** — record-level provenance introduced by this schema | Free-form notes. |

---

## Shared scalar `$defs`

| Def | Schema constraint | Source system / source contract | Notes |
|---|---|---|---|
| `$defs/sha256` | `string`, pattern `^[0-9a-fA-F]{64}$` | **BENCH** `$defs/sha256` | Same pattern reused for `cost.pricing_snapshot_sha256`, `benchmark_run.crews_file_sha256`, and `benchmark_run.provenance.source_csv_sha256`. |
| `$defs/money_or_null` | `string \| null`, pattern `^(0|[1-9][0-9]*)(\.[0-9]+)?$` | **BENCH** `$defs/money_or_null` | Benchmark money-string shape; used by `cost.amount_usd`. |
| `$defs/acceptance` | `string \| null`, enum `accepted` \| `not_accepted` \| `unverified` \| `null` | **BENCH** `$defs/acceptance` | Benchmark acceptance vocabulary only; distinct from the AO review verdict and from `failure_class`. |
| `$defs/tokenCounter` | `integer \| null`, minimum 0 | **P0-9** — synthesis scalar for the five usage counters | — |

---

## Conditional rules (`allOf`)

The schema enforces four conditional families; each is a mapping of source or
synthesis semantics, not a new field:

1. **`verified_success: true` gate** — requires `route`, `supervisor_route`,
   `class_record`, `verdict`, `failure_class`, `usage`, `cost`,
   `wall_clock_ms`; forces `failure_class` null, `verdict` ∈
   {`pass`, `accepted`}, all five usage counters non-null with a valid
   `usage_capture`, `amount_usd` matching the money pattern with non-empty
   `basis`, and integer `wall_clock_ms` ≥ 0. (See the prominent statement
   above; the source column for this rule is **P0-9** — the P0-9a task
   contract.)
2. **`record_kind: agent_orch`** → `agent_orch_observation` required (**AO**).
3. **`record_kind: benchmark_run`** → `benchmark_run` required (**BENCH**).
4. **`record_kind: interactive`** → `router_event` required (**ROUTER**),
   `verified_success` forced `false`, and `verdict` forbidden (`false`) — a
   router event is a dispatch event that records no outcome, so no verdict may
   be asserted for it. The interactive branch constrains nothing else: the
   router event itself supplies no outcome or failure class, so `failure_class`
   may remain absent, but the accepted schema does not prohibit a synthesized
   failure classification on an interactive record.

Inside `$defs/usage`, `usage_capture: "none"` forces all five counters to
null (**P0-1** contract semantics). Inside `$defs/eventRecord`,
non-string `authorized_by` (i.e. any non-null value) forces `mode: "bind"`
(**ROUTER** `build_event` rule).

---

## The three schema examples and their source/absence semantics

The schema ships exactly three examples, one per `record_kind`. Each is a
**scratch** example: no private run material, no real pricing, and no
provider calls; every hash is a zero digest and every id a scratch id. Each
example demonstrates the absence semantics for the fields its source does not
record — absence is recorded as `null` (or field omission where the schema
permits it), never invented.

1. **`agent_orch` example (`attempt_id: a6a85c6b02c6`).** Source: **AO**
   `OBSERVATION_SCHEMA`. The observation records *requested*
   model/harness/effort only, with `executed_attested: false` on both
   participants and **no channel**, so no route and no provider are asserted
   and no full identity tuple exists in this source. `supervisor_route` is
   null (the source records no executed supervisor route). `usage_capture` is
   `none` with all counters null (the observation records no token counters);
   `wall_clock_ms` is null (no duration recorded); `amount_usd` is null (the
   observation records no cost and no price is asserted). It carries
   `verdict: "pass"` (from `review.final_verdict`) and `failure_class: null`,
   yet `verified_success` is **false**: the source reports a passing outcome
   but lacks complete route, supervisor-route, token, cost, and duration
   evidence, and nothing is invented to reach true.

2. **`benchmark_run` example (`attempt_id: bench-mixed-economy-0001`).**
   Source: **BENCH** crew-run record, embedded verbatim including its own
   `attempt_id`, which the unified top-level `attempt_id` mirrors. No route,
   provider, or `supervisor_route` is asserted: the crew-run worker records
   model/harness/effort/model_family only, with no channel and no supervisor
   route. Token usage is not captured by this source, so `usage_capture` is
   `none` with all counters null; `wall_clock_ms` is null because
   `totals.elapsed_ms` is null; money fields stay null because
   `totals.cost_low_usd`/`cost_high_usd` are a range and both are null in this
   unpriced example. It carries `verdict: "accepted"` (from
   `final_acceptance`) and `failure_class: null`, yet `verified_success` is
   **false** for the same missing-evidence reason; nothing is invented.

3. **`interactive` example (`attempt_id: pi-interactive-0001`).** Source:
   **ROUTER** ledger event; the embedded `router_event` payload carries
   exactly the `EVENT_FIELDS` keys. The unified `route` is derived **only**
   from fields the event itself records (`model`, `effort`, `harness`,
   `channel`, `provider`); `anthropic-sub` is a channel id from
   `docs/staffing/catalog.md`, and `provider` is optional observed metadata
   carried by the event, not part of the identity tuple.
   `verified_success` is **false** — structurally so: an interactive record is
   a dispatch event that records no outcome, so `verified_success` is forced
   `false` and no `verdict` or `supervisor_route` is asserted. In this example
   `failure_class` is absent because the router event itself supplies no
   failure classification; the schema does not forbid `failure_class` on
   interactive records (it constrains only `verdict` and `verified_success`
   there), so this absence is an example-level choice, not a schema rule. `usage_capture` is `none` with all counters null (the ledger
   event records no usage); no `wall_clock_ms` is asserted (the event records
   no duration); `amount_usd` is null (the channel is a subscription and no
   price is asserted).

---

## Cross-cutting notes

- **Closed payloads.** Each source shape is preserved as its own closed
  payload (`router_event`, `agent_orch_observation`, `benchmark_run`);
  unlike meanings — Agent-Orch review verdict vs. benchmark acceptance vs.
  P0-9 failure class — are kept distinct and are never claimed identical.
- **Route identity.** Exactly `(model, effort, harness, channel)` per the
  accepted P0-1 route contract (phase0-contracts §Route;
  `routes.schema.json` `$defs/route`). `provider` is separate optional
  observed metadata, never part of the identity tuple, never a replacement
  for `channel`, and never invented for a source that lacks one.
- **`usage_capture`.** Exactly the accepted P0-1 contract:
  `native_json | stream_events | worker_written | none`.
- **Class block.** Reproduces `classes.schema.json` `$defs/classBlock`
  verbatim; `class_key` is the canonical rendering
  (`role/oracle_type/domain_tags/size_band/language`, tags sorted ascending by
  codepoint, deduplicated, `+`-joined, empty set rendered as literal `none`).
- **No invention.** Every price, fee, capacity, date, or multiplier needs a
  source; the schema invents none. Absent evidence is `null` or omitted.
- **No writer until Phase 1.** Nothing yet writes records of this shape; see
  the prominent statement at the top of this document.

### Referenced paths

- Schema documented here: `config/staffing/schema/attempt-record.schema.json`
- Router source: `src/lee_llm_router/events.py` (`EVENT_FIELDS`,
  `OPTIONAL_FIELDS`, `build_event`, `BIND_MODE`);
  `src/lee_llm_router/availability.py` (`Health` wire values)
- Agent-Orch source: `/home/lee/projects/auto-orch/src/auto_orch/performance.py`
  (`OBSERVATION_SCHEMA`, `_PROVENANCE_SCHEMA`, `_SEVERITY_COUNTS_SCHEMA`)
- Benchmark source: `/home/lee/projects/ai-workforce-benchmark/config/crew-run.schema.json`
- Contracts: `docs/staffing/phase0-contracts.md` (§Route, §Channel, §Class
  key, §Class-metadata prohibition (D206), §Terms and prices, §Named crew)
- Schemas: `config/staffing/schema/routes.schema.json` (`$defs/route`,
  `usage_capture`), `config/staffing/schema/classes.schema.json`
  (`$defs/classBlock`, don't-cheap-trial rule)
- Catalog (channel ids, e.g. `anthropic-sub`;
  `crews[].supervisor_route`): `docs/staffing/catalog.md`