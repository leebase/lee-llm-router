# Attempt record — field mapping (Phase 1 P1-2 + P1-7b1, v2)

**Status:** document only. This file documents the accepted v2 schema
`config/staffing/schema/attempt-record.schema.json` (Phase 1, P1-2 plus the
P1-7b1 same-route repair) field by field, under the authority of D209 ruling 2
as mapped by `docs/staffing/phase1-contracts.md` (D208 accepting the Phase 0
baseline) and Chief of Staff answer 3 in
`docs/staffing/chief-answers-p1-3.md`. It is a mapping document, not a
specification change: the schema itself is the authority for every constraint
quoted or summarized here. The contract deliverable is this document, the
schema, the six fixture copies under `tests/fixtures/staffing/`, and the
focused tests in `tests/test_staffing_attempt_record.py` — nothing else.

**P1-7b1 adds no writer.** This sub-packet is limited to the attempt-record
schema, mapping documentation, one real-run-derived fixture, and focused
validation tests. Importer/CLI behavior is outside this contract repair, and
the fixture was assembled by reading named retained artifacts without a real
provider call.

`schema_version` is `2`. D209 ruling 2 is represented without duplicate
top-level aliases: the packet, link, oracle, and verdict facts are top-level
attempt facts, `usage` and `cost` are nested objects, and `selection` is a
new object carrying run-command selection evidence. The v1 source-specific
payloads remain embedded verbatim as provenance evidence; they are not
competing locations for v2 usage, cost, selection, or verdict.

P1-7b1 adds a fourth, deliberately separate kind,
`record_kind: agent_orch_attempt`. It represents one retained raw attempt from
an `agent-orch-runs` directory. It does not reinterpret that attempt as an
`agent_orch_observation`, and it does not change any constraint or payload for
the three legacy kinds (`agent_orch`, `benchmark_run`, and `router_run`).

---

## Source-payload provenance

The v1 source-specific payloads remain embedded verbatim inside each record
and are **provenance evidence, not competing locations** for v2 usage, cost,
selection, or verdict:

| Payload | Required when | Source system |
|---|---|---|
| `router_event` | `record_kind: router_run` | lee-llm-router ledger dispatch event (`src/lee_llm_router/events.py`, exactly the 17 `EVENT_FIELDS` keys in the `build_event` shape) |
| `agent_orch_observation` | `record_kind: agent_orch` | Agent-Orch `OBSERVATION_SCHEMA` (`/home/lee/projects/auto-orch/src/auto_orch/performance.py`), embedded verbatim with internal `$ref`s re-scoped |
| `agent_orch_attempt` | `record_kind: agent_orch_attempt` | Authorized raw fields read from one retained Agent-Orch `run.json`, that attempt's `route-selection.json`, and its `usage.json` when present; `source_paths` names exactly the files read |
| `benchmark_run` | `record_kind: benchmark_run` | AI Workforce Benchmark crew-run record (`/home/lee/projects/ai-workforce-benchmark/config/crew-run.schema.json`), embedded verbatim minus its `$schema`/`$id`/`title`/`description` envelope |

Where a v1 payload carries its own usage, cost, acceptance, or review
vocabulary (AO `review.final_verdict`, BENCH `final_acceptance`, crew-run
stage/totals cost figures), those stay inside the payload exactly as the
source recorded them. The canonical v2 `verdict`, nested `usage`, nested
`cost`, and `selection` live at the top level; consumers needing
source-specific semantics must read the embedded payloads, not reinterpret
the v2 fields.

The new `agent_orch_attempt` payload is a closed object containing only
`run_id`, `step_id`, `attempt_number`, `route` (`harness`, `model`, `effort`),
`worker_exit_code`, `validation_passed`, `policy_decision`,
`failure_classification`, `accounting_status`, raw `usage` token fields when
present, `cost_usd` only for measured accounting, optional `started_at` and
`ended_at` when present, and `source_paths`. Values copied from retained files
remain verbatim. Missing optional evidence is null or absent; it is never
inferred. In particular, the raw payload has no class field, channel,
provider, supervisor route, oracle command, or synthesized observation.

`record_kind` drops the v1 `interactive` kind: a bare dispatch event records
no outcome and is not an attempt. Dispatch events remain in the events ledger
under `events.py`'s own shape, and `router_event` survives as provenance
evidence on `router_run` records.

## D206 verbatim, and class ↔ route coexistence

Quoted verbatim (also embedded in the schema's top-level and `classRecord`
descriptions):

> Class metadata MUST NOT map directly to a preferred model or route. It may
> only: 1. join production attempts to comparable benchmark evidence; and
> 2. determine whether an unevidenced cheap trial is permitted.

The schema permits `class_record` and `route` (and `supervisor_route`) to
coexist **only as observed attempt evidence**: the class block describes the
work; the route block describes the attempt's identity tuple. No
class-to-model or class-to-route property exists anywhere in the schema —
including `selection`, which carries route ids and explain reasons only — and
none may be added (such a property fails `classes.schema.json`
`$defs/classBlock` per D206 and is a High review finding). Route identity is
exactly `(model, effort, harness, channel)` (P0-1 §Route); `provider` is
separate optional observed metadata, never part of the identity tuple, never
a replacement for `channel`, and never invented for a source that lacks one.

---

## `verified_success` gates (v2)

For `record_kind: agent_orch_attempt`, Chief answer 3 defines an exact
equivalence:

```text
verified_success == (agent_orch_attempt.worker_exit_code == 0
                     and agent_orch_attempt.validation_passed == true)
```

The schema enforces both directions. A zero exit plus passed validation
requires `verified_success: true`; every other exit/validation combination
requires `false`. The `verdict: {"tier": "engine_validation"}` object labels
the source of that determination. It does not claim a deterministic, judge,
or human oracle selected by this repository. The legacy evidence gate below
is bypassed only for this new record kind.

For the three legacy record kinds, `verified_success: true` requires **all**
of the following, simultaneously and genuinely present in the record
(enforced by the schema's first `allOf` gate):

1. A substantive `route` — the full identity tuple
   `(model, effort, harness, channel)` per the P0-1 route contract.
2. `supervisor_route` present (non-null).
3. A structured `class_record` including `class_key` and `oracle_type`.
4. `verdict` exactly `"pass"` (the canonical v2 vocabulary; the v1
   `accepted` alternative is gone).
5. `failure_class` present and **null** (no failure recorded).
6. `usage` with a non-unavailable `basis` (`observed | provider_reported |
   calculated`), a required `source`, and the **input/output token fields the
   current P0-4 pricing needs**: `input_tokens` and `output_tokens` non-null
   nonnegative integers. The optional `cached_input_tokens` and
   `reasoning_tokens` components stay null (or absent) when the authoritative
   harness output genuinely omits them — they are **not** required for
   `verified_success`, and zero is never fabricated as an unknown sentinel.
   `total_tokens` remains truthful: optional/null unless the source
   authoritatively reports it or it is calculated from authoritatively
   reported components — never fabricated as a sum across unknown components.
7. `cost` with both figures `usd_list` and `usd_marginal` present as
   nonnegative JSON numbers (i.e. `basis: ["list", "marginal"]`).
8. `wall_clock_ms` non-null, non-negative integer.
9. `oracle_cmd` a non-empty string.

If the source's outcome passed but **any** required evidence is missing, the
record still gets `verified_success: false`. Missing evidence is never
invented, estimated, or backfilled to reach `true`; absence is recorded as
`null` or by field omission — never fabricated.

## Failure classes (exact list)

`failure_class` admits exactly five string values, proven by the P0-9a task
contract. No named source proves others, so none are added:

- `platform_timeout`
- `platform_env`
- `spec_rejected`
- `capability_rejected`
- `unaccounted_spend`

`null` means no failure recorded and is **required** to be null when
`verified_success` is true. Unlike v1 there is no `interactive` branch, so
the v1 interactive carve-out no longer applies.

## Verdict shapes

The field is a `oneOf` with two disjoint tiers:

- The three legacy kinds retain exactly the string `pass | fail |
  unverified` — the run-command oracle semantics of phase1-contracts §run
  command (exit 0 = pass, nonzero = fail, no oracle = unverified).
- `agent_orch_attempt` requires exactly the closed object
  `{"tier": "engine_validation"}`. No string verdict and no extra object
  member is accepted for this kind. Conversely, the object tier is rejected
  for every legacy kind.

The v1 source-specific outcome vocabularies
(Agent-Orch review `pass`/`fail`, benchmark acceptance
`accepted`/`not_accepted`/`unverified`) are **no longer admitted at the top
level**; they remain inside the embedded v1 payloads as provenance evidence,
and imports map them to the canonical value when the source provides one
(e.g. `review.final_verdict: "pass"` → `verdict: "pass"`;
`final_acceptance: "accepted"` → `verdict: "pass"`).

For `router_run` records the schema pairs verdict and oracle: `pass`/`fail`
require a non-empty `oracle_cmd`; `unverified` forces `oracle_cmd` null.

---

## Top-level record fields

Exactly `schema_version`, `attempt_id`, `record_kind`, `captured_at`,
`verified_success`, `provenance` are required on every record;
`additionalProperties: false` closes the envelope. Everything else is
required only under the conditional rules below.

| Field | Schema constraint | Notes |
|---|---|---|
| `schema_version` | `const: 2` | v2 attempt envelope (phase1-contracts §Attempt record v2 placement). |
| `attempt_id` | `string`, pattern `^[A-Za-z0-9._:-]+$`, minLength 1 | Caller-supplied; pattern taken verbatim from the benchmark crew-run `attempt_id`. |
| `record_kind` | enum `agent_orch` \| `agent_orch_attempt` \| `benchmark_run` \| `router_run` | Discriminant selecting the required source payload and `provenance.source` pairing. The new raw-attempt kind is distinct from the unchanged full-observation `agent_orch` kind. v2 drops `interactive`. |
| `captured_at` | `string`, `format: date-time` | Aware UTC capture timestamp (analogous to `events.py` `ts` and crew-run `provenance.assembled_at`). |
| `verified_success` | `boolean` | Legacy evidence gate, or the exact Agent-Orch exit/validation equivalence for `agent_orch_attempt`; see above. |
| `packet_id` | `string`, minLength 1 | Top-level packet fact (D209): the packet driving this attempt. Required for `router_run` records; imports predate packets and omit it. |
| `parent_attempt_id` | `string` (same pattern) \| `null` | Link fact: parent attempt of an escalation. Nullable/optional for an initial attempt; an escalation requires both this and `escalation_reason`. |
| `escalation_reason` | `string` minLength 1 \| `null` | Link fact: why this attempt escalates from `parent_attempt_id`. Nullable/optional for an initial attempt; an escalation requires both. |
| `oracle_cmd` | `string` minLength 1 \| `null` | Oracle fact: the oracle command whose exit status produced the verdict. Null/absent for unverified attempts and for imports without an oracle command. |
| `verdict` | `oneOf` legacy string enum or closed `{tier: engine_validation}` object | The record-kind conditionals select exactly one shape. Optional on legacy imports; required on `router_run` and `agent_orch_attempt`. |
| `failure_class` | enum of the five classes, or `null` | Failure taxonomy; see above. |
| `route` | `$ref: #/$defs/route` | Observed attempt identity tuple; never derived from class metadata (D206). Required non-null when `verified_success: true`. |
| `supervisor_route` | `route \| null` | Present only when the source records one (named-crew contract); null is the explicit "none recorded" marker. Required non-null when `verified_success: true`. |
| `class_record` | `$ref: #/$defs/classRecord` | Strict class block (see below). Required on `router_run` records; omitted only by unclassed imports (with `class_source: "none"`). Forbidden together with `class_source`. |
| `class_source` | enum `none` | Marks the absence of class metadata. See the import rule below. |
| `usage` | `$ref: #/$defs/usage` | Nested v2 usage object; see `usage` table. |
| `cost` | `oneOf` `$defs/cost` or `$defs/agentOrchAttemptCost` | Legacy kinds retain the existing cost object. `agent_orch_attempt` uses its narrower list-or-unavailable shape. |
| `wall_clock_ms` | `integer \| null`, minimum 0 | Observed wall-clock duration in ms, or null when the source records none. Never estimated or invented. |
| `selection` | `$ref: #/$defs/selection` | Run-command selection evidence. Required on `router_run` records; forbidden on imports. |
| `router_event` | `$ref: #/$defs/eventRecord` | **ROUTER** dispatch event; required when `record_kind: router_run`. |
| `agent_orch_observation` | `$ref: #/$defs/agentOrchObservation` | **AO** observation; required when `record_kind: agent_orch`. |
| `agent_orch_attempt` | `$ref: #/$defs/agentOrchAttempt` | **AO raw attempt**; required only when `record_kind: agent_orch_attempt`. |
| `benchmark_run` | `$ref: #/$defs/crewRunRecord` | **BENCH** crew-run record; required when `record_kind: benchmark_run`. |
| `provenance` | `$ref: #/$defs/provenance` | Record-level provenance including the new required `source` discriminant. |

---

## `$defs/usage` (nested, strict source/unavailable conditions)

`usage` is a closed object with one required member, `basis`. Token counters
are nonnegative integers when reported and null or absent when unknown; zero
is evidence only when the source actually reports zero and is never an
unknown sentinel. `total_tokens` stays truthful: optional/null unless the
source authoritatively reports it or it is calculated from authoritatively
reported components. No parser estimates tokens from text, context length,
cost, or elapsed time.

| Field | Schema constraint | Notes |
|---|---|---|
| `basis` | enum `observed` \| `provider_reported` \| `calculated` \| `unavailable` | The narrowest truthful basis. |
| `source` | `string`, minLength 1; **required iff `basis` is not `unavailable`**, **forbidden when `basis` is `unavailable`** (schema-enforced both ways) | Basis-dependent pairing: for `provider_reported`, exactly one of the ten exact usage-taxonomy strings: `pi --mode json events`, `codex exec --json usage`, `claude -p --output-format stream-json result event`, `agy -p usage line (agent-orch worker.py)`, `opencode run JSON usage event`, `opencode worker-written usage.json from provider output`, `omp -p --mode json events`, `benchmark v6 CSV usage_*_tokens`, `agent-orch usage.json/accounting_status`, `agent-orch usage.json`. The tenth is the P1-7b1 raw receipt source. For `observed`/`calculated`, a nonempty authoritative source description — never one of the ten provider-reported strings. |
| `unavailable_reason` | `string`, minLength 1 | **Required iff `basis` is `unavailable`** and forbidden otherwise (e.g. `text mode` for supervisor Pi attempts until P1-4a). The specific missing-event/output reason. |
| `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`, `total_tokens` | `$defs/tokenCounter`: `integer \| null`, minimum 0 | Nonnegative integers when reported; null or absent when unknown. Zero only when the source reports zero. |

The schema enforces the basis↔source/reason pairing with four inner `allOf`
branches: `basis: "unavailable"` → `unavailable_reason` required and `source`
forbidden; a known basis (`observed`/`provider_reported`/`calculated`) →
`source` required and `unavailable_reason` forbidden; `provider_reported` →
`source` must be exactly one of the ten taxonomy strings; and
`observed`/`calculated` → `source` must be a descriptive authoritative source
and must not be one of the ten strings. If a documented stream
contains no authoritative usage, record `unavailable` with the specific
reason — never an estimate.

## `$defs/cost` (nested; no numeric cost without required known tokens)

| Field | Schema constraint | Notes |
|---|---|---|
| `basis` | closed enum of exactly two arrays: `["list", "marginal"]` or `["unavailable"]` | Known cost carries both figures; unavailable cost is the sole member and carries neither figure. |
| `usd_list` | `number`, minimum 0 (null-forced when cost is unavailable) | List-cost JSON number from list input/output/cache rates; present only with known cost. |
| `usd_marginal` | `number`, minimum 0 (null-forced when cost is unavailable) | Marginal cost: same token quantities after the channel badge multiplier selected at the attempt timestamp. |
| `pricing_snapshot_ref` | `string \| null`, minLength 1 | Optional dated-terms pricing snapshot citation; null/absent when no snapshot is cited. **Pre-existing accepted Phase 0 baseline field (P0-9a, accepted by D208)**, carried forward unchanged — not a D209 addition, and never a competing usage or cost fact. |
| `pricing_snapshot_sha256` | `^[0-9a-fA-F]{64}$` or `null` | SHA-256 of the cited pricing snapshot; null/absent when none is cited. **Pre-existing accepted Phase 0 baseline field (P0-9a, accepted by D208)**, carried forward unchanged — not a D209 addition, and never a competing usage or cost fact. |

Cost figures are JSON numbers derived from known tokens and the selected
dated P0-4 terms. The schema enforces **no numeric cost without the required
known tokens** via the top-level usage-cost conditional: when `usage` is
absent, `usage.basis` is `unavailable`, or either of `input_tokens` /
`output_tokens` is null or absent, `usd_list` and `usd_marginal` are forced
to null. Conversely, known tokens with `basis: ["unavailable"]` is valid when
the selected dated terms price nothing (unknown terms never yield an
estimate). Harness cost estimates and subscription fees are provenance notes,
never attempt-token cost substitutes. D207 remains the source rule where
OpenRouter has no row. The governing dated-terms citation lives in
`provenance` (`source_refs`/`notes`) or the pricing snapshot fields — never
in an invented number. The two `pricing_snapshot_*` fields themselves are not
D209 additions: they were accepted in the Phase 0 baseline (P0-9a, accepted by
D208), where the v1 `cost` object carried them beside its free-form citation
`basis`, and they are preserved unchanged in v2. They cite the dated-terms
pricing snapshot only — they never carry or imply a second usage figure or
cost figure, and no competing usage/cost fact lives in them.

### `$defs/agentOrchAttemptCost`

The raw-attempt cost is a separate closed shape selected only by
`record_kind: agent_orch_attempt`:

| Field | Schema constraint | Notes |
|---|---|---|
| `basis` | scalar enum `list` \| `unavailable` | `measured` requires `list`; `unaccounted`, a missing receipt, and `not_applicable` require `unavailable`. This scalar is intentionally distinct from the unchanged legacy basis arrays. |
| `usd_list` | `number`, minimum 0 | Required only for `basis: list`, copied verbatim from raw `usage.json` `cost_usd`; forbidden for unavailable cost. |

No `usd_marginal`, pricing snapshot, estimated value, or subscription fee is
admitted in this shape. The top-level `cost.oneOf` does not weaken legacy
records: each legacy record-kind branch still requires `$defs/cost`, while the
new branch requires `$defs/agentOrchAttemptCost`.

### Raw Agent-Orch accounting mapping

The payload and canonical top-level facts stay separate but exact:

| Raw `agent_orch_attempt.accounting_status` | Top-level `usage` | Top-level `cost` | Raw payload requirements |
|---|---|---|---|
| `measured` | `basis: provider_reported`, `source: agent-orch usage.json`, known nonnegative `input_tokens` and `output_tokens` | `basis: list` plus `usd_list` | Raw `usage` with input/output tokens and raw `cost_usd` are required. Optional reported token components remain verbatim. |
| `unaccounted` | `basis: unavailable` plus a nonempty source-record reason | `basis: unavailable`, no figure | Raw `cost_usd` is forbidden; token counters are absent at the top level. |
| `null` (missing receipt) | `basis: unavailable` plus a nonempty missing-receipt reason | `basis: unavailable`, no figure | The absent `usage.json` is omitted from `source_paths`; raw `cost_usd` is forbidden. |
| `not_applicable` | exactly `basis: unavailable`, `unavailable_reason: non-metered adapter` | `basis: unavailable`, no figure | Raw `cost_usd` is forbidden; token counters are absent at the top level. |

For the measured fixture, top-level `cached_input_tokens` copies
`usage.json.cached_read_tokens`, and top-level `reasoning_tokens` copies
`usage.json.raw_usage.reasoning_output_tokens`. JSON Schema enforces the
allowed shapes and pairings; the schema example and fixture tests pin the
copied values because JSON Schema cannot compare sibling numeric values for
equality.

## `$defs/selection` (run-command evidence only)

Required on `router_run` records (together with `packet_id`); **forbidden on
imports** (`selection: false` in both import branches). Closed object with
exactly:

| Field | Schema constraint | Notes |
|---|---|---|
| `basis` | enum `explicit` \| `explain_cheapest_eligible` | `explicit` (`--route`) or `explain_cheapest_eligible` (role/class selection: first eligible route in `catalog explain --json` marginal-price order). |
| `reason` | `string`, minLength 1 | Selection reason as recorded by the run command. |
| `explain_ref` | `string`, minLength 1 | Reference to the `catalog explain --json` evidence backing the selection. |
| `excluded` | array of closed objects, each requiring exactly `route_id` and `reason` (both non-empty strings) | All excluded-route summaries: route ids and explain reasons only. |

`selection` preserves catalog explain evidence — not a new selection
judgment — and contains no class metadata: per D206 it creates no
class-to-model or class-to-route mapping.

## Import rule: `class_source: "none"`

`class_source` has exactly one permitted value, `none`, and marks the absence
of class metadata. The schema enforces:

- `class_source` and `class_record` are mutually exclusive.
- Every `agent_orch_attempt` requires `class_source: "none"`, forbids
  `class_record`, and cannot carry a top-level `class_key` because the envelope
  is closed.
- An import (`record_kind` `agent_orch` or `benchmark_run`) that omits
  `class_record` **must** carry `class_source: "none"` — the only condition
  under which `class_key` (and the rest of the class block) is optional.
- `router_run` records always carry `class_record` (so they never carry
  `class_source`).

Historical agent-orch rows without class metadata therefore use
`class_source: "none"` (phase1-contracts §Ledger, rollup, and imports).

## `$defs/route`

Unchanged from v1. Required: `model`, `effort`, `harness`, `channel`;
optional `provider` (`string \| null`) is observed metadata, never part of
the identity tuple and never invented. `effort` is null only where the
harness has no effort dial. `channel` must match a `channel_id` in
`docs/staffing/catalog.md` (cross-catalog check is loader work). Observed
attempt evidence only; never derived from class metadata (D206).

## `$defs/classRecord`

Reproduces `classes.schema.json` `$defs/classBlock` verbatim, as in v1: same
six required fields (`class_key`, `role`, `oracle_type`, `domain_tags`,
`size_band`, `language`), same closed value sets, same canonical `class_key`
pattern (`role/oracle_type/domain_tags/size_band/language`; tags sorted
ascending by codepoint, deduplicated, `+`-joined, empty set = literal
`none`). Per D206 no class→model or class→route property exists.

## `$defs/provenance` (with the v2 `source` discriminant)

| Field | Schema constraint | Notes |
|---|---|---|
| `source` | closed enum `benchmark` \| `agent-orch` \| `agent-orch-runs` \| `router-run` | **Required** and paired with `record_kind` by the top-level conditionals: `agent_orch` ↔ `agent-orch`, `agent_orch_attempt` ↔ `agent-orch-runs`, `benchmark_run` ↔ `benchmark`, `router_run` ↔ `router-run`. `agent-orch-runs` identifies retained per-attempt artifacts, not the Phase 4 full-observation source. |
| `recorded_by` | `string`, minLength 1 (required) | Who recorded the unified record. |
| `source_refs` | array of non-empty strings, minItems 1 (required) | Named sources that justify this record's fields. |
| `notes` | array of non-empty strings (optional) | Free-form notes, including dated-terms citations. |

## Source-payload `$defs`

The three legacy embedded source payloads are carried over from v1 unchanged
and keep their v1 field semantics (see the Phase 0 history of this document in
git for the per-field source tables; the payloads are embedded verbatim):
`eventRecord` is exactly the 17 `EVENT_FIELDS` keys of `build_event` (all
required; non-string `authorized_by` still forces `mode: "bind"`);
`agentOrchObservation` is **AO** `OBSERVATION_SCHEMA` verbatim with
`$defs/aoProvenance` / `$defs/aoParticipant` / `$defs/aoSeverityCounts`
re-scoped; `crewRunRecord` is **BENCH** crew-run verbatim minus its envelope,
keeping its own `attempt_id`. These payloads are provenance evidence only
(see the source-payload provenance section).

P1-7b1 adds `$defs/agentOrchAttempt`, the closed authorized-raw-fields shape
listed above. Its nested route requires exactly `harness`, `model`, and
`effort`; its optional raw usage object admits only `input_tokens`,
`output_tokens`, `cached_read_tokens`, `reasoning_output_tokens`, and
`total_tokens`; and its `source_paths` contains at least the run and route
selection files. Measured accounting additionally requires raw usage input
and output tokens plus `cost_usd`; every other accounting status forbids
`cost_usd`.

## Shared scalar `$defs`

| Def | Schema constraint |
|---|---|
| `$defs/sha256` | `string`, pattern `^[0-9a-fA-F]{64}$` |
| `$defs/money_or_null` | `string \| null`, pattern `^(0|[1-9][0-9]*)(\.[0-9]+)?$` (v1 benchmark money-string shape, used inside embedded payloads) |
| `$defs/acceptance` | `string \| null`, enum `accepted` \| `not_accepted` \| `unverified` \| `null` (benchmark vocabulary, embedded payload only — never the top-level v2 `verdict`) |
| `$defs/tokenCounter` | `integer \| null`, minimum 0 |

## Conditional rules (`allOf`)

The schema enforces fifteen top-level conditional families. P1-7b1 adds the
new-kind branch and four truth-mapping branches; the legacy families retain
their prior semantics:

1. **Legacy `verified_success: true` gate** — for every kind except
   `agent_orch_attempt`, requires `route`, `supervisor_route`,
   `class_record`, `verdict`, `failure_class`, `usage`, `cost`,
   `wall_clock_ms`, `oracle_cmd`; forces `failure_class` null, `verdict`
   exactly `"pass"`, `oracle_cmd` a non-empty string, usage with a
   non-unavailable basis and a required `source` plus **`input_tokens` and
   `output_tokens` non-null nonnegative integers** (the fields current P0-4
   pricing needs), and both cost figures non-null nonnegative numbers. The
   optional `cached_input_tokens`/`reasoning_tokens` components may remain
   genuinely unknown (null/absent) when the authoritative harness output
   omits them, and `total_tokens` stays optional/null unless authoritatively
   reported or calculated. (See the prominent section above.)
2. **`record_kind: agent_orch`** → `agent_orch_observation` required,
   `provenance.source` const `agent-orch`, legacy verdict/cost shapes, and
   `selection` forbidden. This branch is unchanged.
3. **`record_kind: agent_orch_attempt`** → `agent_orch_attempt`,
   `class_source`, verdict, usage, and cost required; `class_source` const
   `none`; provenance source const `agent-orch-runs`; new verdict/cost shapes
   required; `class_record`, legacy source payloads, top-level route,
   supervisor route, oracle, and selection forbidden.
4. **`record_kind: benchmark_run`** → `benchmark_run` required,
   `provenance.source` const `benchmark`, `selection` forbidden.
5. **`record_kind: router_run`** → `router_event`, `packet_id`, `selection`,
   `class_record`, `verdict`, `usage`, `cost` required;
   `provenance.source` const `router-run`.
6. **`router_run` + `verdict` `pass`/`fail`** → `oracle_cmd` required,
   non-empty string.
7. **`router_run` + `verdict` `unverified`** → `oracle_cmd` forced `null`.
8. **Raw-attempt success equivalence** — zero worker exit plus passed
   validation forces `verified_success: true`; every other combination for
   `agent_orch_attempt` forces false.
9. **Raw-attempt measured accounting** — requires provider-reported usage
   from exactly `agent-orch usage.json`, known input/output tokens, and
   list-basis cost with `usd_list`.
10. **Raw-attempt unaccounted/missing receipt** — `accounting_status` equal
    to `unaccounted` or null forces unavailable usage with a nonempty reason,
    no top-level token counters, and unavailable cost.
11. **Raw-attempt non-metered accounting** — `accounting_status` equal to
    `not_applicable` forces unavailable usage with the exact reason
    `non-metered adapter`, no top-level token counters, and unavailable cost.
12. **Escalation link** — if either `parent_attempt_id` or
   `escalation_reason` is a non-empty string, both are required (and
   `parent_attempt_id` must match the attempt-id pattern). Initial attempts
   may carry both as `null` or omit them.
13. **`class_source` present** → `class_record` forbidden.
14. **Legacy import without `class_record`** → `class_source` required with
    const `none`.
15. **Shared usage-cost rule** — if `usage` is absent, `usage.basis` is
    `unavailable`, or `input_tokens`/`output_tokens` is null or absent, then
    `cost.usd_list` and `cost.usd_marginal` are forced to `null` (no numeric
    cost without the required known tokens). The raw-attempt kind's narrower
    cost branch independently enforces its mapping.

Inside `$defs/usage`: `basis: "unavailable"` → `unavailable_reason` required
and `source` forbidden; a known basis → `source` required and
`unavailable_reason` forbidden; `provider_reported` → `source` restricted to
the exact ten taxonomy strings; `observed`/`calculated` → `source` a
nonempty authoritative description that is never one of the ten taxonomy
strings. Inside `$defs/cost`: `["list", "marginal"]`
→ both figures required (numbers ≥ 0); `["unavailable"]` → both figures
forced null. Inside `$defs/eventRecord`: non-null `authorized_by` forces
`mode: "bind"`.

---

## The six schema examples and fixture copies

The schema ships exactly six examples: the five accepted P1-2 examples plus
one P1-7b1 raw-attempt example. The first five are scratch examples with no
private run material or real pricing. The sixth is derived from three named
retained files in real run `a6a85c6b02c6`; reading them required no provider
call. Every example demonstrates truthful absence semantics — missing source
evidence is null or omitted where permitted, never invented.

1. **`agent_orch` import example (`attempt_id: a6a85c6b02c6`).** Embedded AO
   observation verbatim as provenance evidence; `provenance.source` is
   `agent-orch`. The observation records requested model/harness/effort only
   (`executed_attested: false`, no channel), so **no route and no provider
   are asserted**; `supervisor_route` is null. `usage.basis` is
   `unavailable` (the observation records no token counters) with an explicit
   reason; `cost.basis` is `["unavailable"]` with no figures; no
   `wall_clock_ms`. `verdict: "pass"` is the canonical v2 mapping of
   `review.final_verdict`; the source-specific value remains in the payload.
   `verified_success` is **false**: a passing outcome without complete route,
   supervisor-route, usage, cost, oracle, and duration evidence — nothing is
   invented.
2. **`benchmark_run` import example (`attempt_id:
   bench-mixed-economy-0001`).** Embedded crew-run record verbatim including
   its own `attempt_id`; `provenance.source` is `benchmark`; source usage is
   preserved exactly (this v1 shape captures none). No route, provider, or
   `supervisor_route` is asserted (the worker records
   model/harness/effort/model_family only, no channel). `usage.basis` is
   `unavailable` (`evidence_status: unmeasured` — no token counters);
   `cost.basis` is `["unavailable"]` because the `benchmark v6 CSV
   usage_*_tokens` inputs this import needs are absent and no dated terms
   price an untokenized row. `verdict: "pass"` is the canonical mapping of
   `final_acceptance: "accepted"`; the acceptance vocabulary remains in the
   payload. `verified_success` is **false** for the same missing-evidence
   reason.
3. **`router_run` unverified example (`attempt_id: pi-run-0001`).** A live
   run-command attempt: `packet_id` present, `selection` with basis
   `explicit`, `class_record` present, and the embedded `router_event`
   carrying exactly the `EVENT_FIELDS` keys. `usage.basis` is `unavailable`
   with `unavailable_reason: "text mode"` (supervisor Pi attempts until
   P1-4a); `cost.basis` is `["unavailable"]` with no figures; `verdict` is
   `unverified` because no `--oracle CMD` was given, so `oracle_cmd` is null.
   `parent_attempt_id`/`escalation_reason` are both null (initial attempt).
   `verified_success` is **false**.
4. **`router_run` escalation example (`attempt_id: pi-run-0002`).** A linked
   attempt: `parent_attempt_id` and `escalation_reason` are both present, as
   phase1-contracts requires. `usage.basis` is `provider_reported` from the
   exact `codex exec --json usage` evidence string with scratch counter
   values (including source-reported zeros); `cost.basis` is
   `["unavailable"]` because this scratch example selects no dated P0-4 terms
   — figures are never estimated from tokens. `verdict: "fail"` with
   `failure_class: "spec_rejected"` and a recorded `oracle_cmd` (nonzero
   exit). `selection` with basis `explain_cheapest_eligible` preserves two
   excluded-route summaries (route ids and explain reasons only).
   `verified_success` is **false** (fail verdict, no duration).
5. **Unclassed import example (`attempt_id: a6a85c6b02c7`).** An imported
   agent-orch row without class metadata: `class_source: "none"` and no
   `class_record` (the only condition under which the class block may be
   omitted). `usage.basis` is `provider_reported` from the exact
   `agent-orch usage.json/accounting_status` string, preserving the accounted
   artifact's usage exactly — including the unknown reasoning component as
   `null` (never zero); an `accounting_status: unaccounted` row would instead
   record `unavailable` with a reason. `cost.basis` is `["unavailable"]` (no
   dated terms selected in this scratch import). `verified_success` is
   **false** (no route, supervisor route, class record, or duration).
6. **Raw `agent_orch_attempt` example (`attempt_id:
   b0ccf22e228b8dbc599747372cbf018150ff39eeedd3437de8d4f70e2ec00daa`).**
   The id is SHA-256 of
   `a6a85c6b02c6/step_01_seal_authority_and_anchor_repairs/1`. Its payload is
   derived only from these exact files:

   - `/home/lee/projects/linux-utilities-agent-orch-runs/a6a85c6b02c6/run.json`
   - `/home/lee/projects/linux-utilities-agent-orch-runs/a6a85c6b02c6/steps/step_01_seal_authority_and_anchor_repairs/attempt-1/route-selection.json`
   - `/home/lee/projects/linux-utilities-agent-orch-runs/a6a85c6b02c6/steps/step_01_seal_authority_and_anchor_repairs/attempt-1/usage.json`

   `provenance.source` is `agent-orch-runs`; `source_refs` cites Chief answer
   3 and those same three files; `agent_orch_attempt.source_paths` names the
   three raw files. `captured_at` preserves `run.json.last_updated_at`. The
   attempt has worker exit 0 and passed validation, so the exact equivalence
   requires `verified_success: true` and the closed verdict object is
   `{"tier": "engine_validation"}`. Measured accounting maps to
   provider-reported `agent-orch usage.json` usage and scalar list-basis cost.
   Token counts and `cost_usd` are copied verbatim; the raw cached-read and
   reasoning-output names map to their canonical top-level names. No class,
   channel, provider, supervisor route, oracle, timestamps absent from the
   attempt, or wall-clock duration is inferred.

### Fixtures

The six files are the five legacy
`tests/fixtures/staffing/attempt-record-{agent-orch,benchmark-run,router-run-unavailable,router-run-escalation,import-agent-orch-unclassed}.json`
fixtures plus
`tests/fixtures/staffing/attempt-record-agent-orch-raw-attempt.json`. They are
deterministic copies of the corresponding schema examples, one per example
above. The new raw-attempt fixture is additionally pinned byte for byte to the
canonical two-space-indented encoding of its schema example. They are
validated by `tests/test_staffing_attempt_record.py`, which asserts each
fixture validates under Draft 2020-12 and exactly equals its schema example,
and separately checks the new fixture's bytes, so the fixtures cannot drift
from the schema. Note: the repository's
`.gitignore` `*.json` rule covers `tests/fixtures/staffing/` (its negation
exempts only `tests/fixtures/*.json` one level up), so these fixtures are
intentionally ignored and require explicit `git add -f
tests/fixtures/staffing/attempt-record-*.json` to commit; `.gitignore` is
deliberately not altered.

---

## Cross-cutting notes

- **Closed payloads and closed records.** The record and every v2 object
  (`route`, `usage`, both cost shapes, `selection`, `class_record`, the
  engine-validation verdict, `agent_orch_attempt`, and `provenance`) sets
  `additionalProperties: false`; the v1 source-specific payloads keep their
  own closed shapes. Unlike meanings (AO review verdict, raw engine validation,
  benchmark acceptance, and canonical legacy verdict) remain distinct.
- **No v1 aliases.** D209 ruling 2 means no duplicate fields: `amount_usd`
  (v1 cost alias), `usage_capture` (v1 usage field), and the v1 top-level
  `verdict` values (`accepted`/`not_accepted`) are retired outright; v2
  `usage`/`cost` are nested objects. Legacy verdicts remain exactly `pass |
  fail | unverified`; only the new kind admits the engine-validation object.
- **Route identity.** Exactly `(model, effort, harness, channel)` per P0-1;
  `provider` is optional observed metadata, never part of the tuple, never a
  replacement for `channel`, never invented. The nested raw-attempt route is
  not promoted to this canonical route: it preserves only the three fields
  (`harness`, `model`, `effort`) authorized by Chief answer 3.
- **No invention.** Every token count, price, fee, capacity, date, or
  multiplier needs a source; the schema invents none. Absent evidence is
  `null` or omitted. Zero is evidence only when a source reports zero.
- **No P1-7b1 writer change.** This repair changes only the contract, fixture,
  documentation, and focused tests; importer/CLI work remains outside its
  packet.

### Referenced paths

- Schema documented here: `config/staffing/schema/attempt-record.schema.json`
  (`$id` …/attempt-record.schema.json, Draft 2020-12)
- Fixtures: `tests/fixtures/staffing/attempt-record-*.json` (six files,
  ignored by `*.json` — commit with `git add -f`)
- Tests: `tests/test_staffing_attempt_record.py`
- Contracts: `docs/staffing/phase1-contracts.md` (§Attempt record v2
  placement, §Usage evidence taxonomy, §Cost rule, §run command, §Ledger,
  rollup, and imports); `docs/staffing/phase0-contracts.md` (§Route, §Class
  key, §Class-metadata prohibition (D206), §Terms and prices)
- P1-7b1 ruling: `docs/staffing/chief-answers-p1-3.md` (Chief answer 3)
- Router source: `src/lee_llm_router/events.py` (`EVENT_FIELDS`,
  `OPTIONAL_FIELDS`, `build_event`, `BIND_MODE`)
- Agent-Orch source: `/home/lee/projects/auto-orch/src/auto_orch/performance.py`
  (`OBSERVATION_SCHEMA`)
- Raw Agent-Orch fixture sources:
  `/home/lee/projects/linux-utilities-agent-orch-runs/a6a85c6b02c6/run.json`,
  its
  `steps/step_01_seal_authority_and_anchor_repairs/attempt-1/route-selection.json`,
  and the adjacent `usage.json`
- Benchmark source: `/home/lee/projects/ai-workforce-benchmark/config/crew-run.schema.json`
- Schemas: `config/staffing/schema/routes.schema.json`,
  `config/staffing/schema/classes.schema.json`
- Catalog (channel ids, supervisor routes): `docs/staffing/catalog.md`
