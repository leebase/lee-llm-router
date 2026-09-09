# Phase 0 staffing catalog — field reference (P0-1d)

Status: documentation of the six Phase 0 schemas under `config/staffing/schema/`.
Authority: `docs/staffing/phase0-contracts.md` (D152, D155, D157, D158, D187,
D188, D189, D203, D204, D205; D206 verbatim), the schema files themselves, and
Chief answers 1–3.

## Coverage method

Every field listed below was taken by direct read of the six schema JSON
files in `config/staffing/schema/` (973 lines total): routes (58 lines),
channels (87), terms (103), policy (282), classes (334), crews (109). Each
top-level property, rule/entry property, nested property, and named `$defs`
entry is documented below with type, required/optional, constraints, meaning,
and authority. No field was added, and no data value, default, or behavior was
invented; where the schema declares a value as data-not-schema, that is stated
rather than filled in. Packet assignments are given only where the on-disk
records (`execution-log.md`, `needs-lee.md`, `chief-answers-*.md`) name them;
unassigned packets are flagged in "Gaps".

## Schema validation vs. P0-2 loader checks

Every schema here is **shape-only** by its own description: no ids, model
names, roles, prices, dates, tiers, caps, or decision values are encoded.
The following checks are **not** expressible in these schemas and are P0-2
loader cross-record work (each is named in the schema descriptions or
contracts; none is enforced by JSON Schema here):

- **Tuple/id uniqueness.** Route identity is the tuple
  `(model, effort, harness, channel)`; uniqueness of that tuple across
  `routes[]` (distinct from `route_id` uniqueness) is loader work, as is
  uniqueness of `channel_id`, `crew_id`, and pairwise distinctness of terms
  entries beyond JSON-level `uniqueItems` on whole objects.
- **Cross-catalog references.** `route.channel` → a `channel_id`;
  `terms.channel_ref` → a channel; crew `supervisor_route`, `reviewer_route`,
  `worker_routes` members, and `escalation_ladder` members → a `route_id`.
  All reference fields are opaque strings at validation time; resolution is
  the loader's job (stated verbatim in the terms and crews schema
  descriptions).
- **Date format assertion.** The `isoDate` $def carries `format: date` plus a
  regex that enforces month 01–12 and day 01–31; JSON Schema `format` is
  annotation-only by default, so real calendar-date assertion (e.g. rejecting
  2026-02-31) is loader work.
- **Canonical-key equality and sorting.** `class_key` must equal the
  five-part join of the authoritative component fields with tags sorted
  ascending by codepoint, deduplicated, `+`-joined, and the empty set as
  literal `none`. The schema pattern cannot check equality to the derived
  join or full sortedness/dedup of the segment; both schema descriptions say
  this is loader work.
- **Exact risk-rule semantics.** `cheap_trial_rule` is pinned data, but
  *evaluating* the pinned predicates (oracle_type in {human, none}; risk tags
  intersecting {persistence, concurrency, security, authority} with size_band
  in {m, l}) against a concrete classBlock, plus the supervisor-override
  lift/impose in either direction, is loader behavior.
- **Additional cross-record checks** named in schema descriptions:
  `role_scoped` allowed/denied disjointness ("a data-quality concern for the
  cited decision"); non-overlap of dated fee/terms entries "via ordering
  conventions outside this schema"; behavior for badges outside the six keys
  (fails closed to `1.0` per D203-era contract, implementation not schema);
  `worker_routes` order-significance semantics.

---

## 1. Routes — `routes.schema.json`

Route identity is the tuple **(model, effort, harness, channel)**. The schema
encodes no selection, ranking, probability, or pricing; dispatch templates are
data and never executed by validation.

| Field | Type | Req | Constraints / meaning | Authority | Data from |
|---|---|---|---|---|---|
| `routes` | array of route | required | `uniqueItems: true` on whole objects | route contract (phase0-contracts §Route) | P0-3 (route rows; e.g. chief-answers-2 adds `glm-5.3-flash \| pi \| opencode-go` here) |
| `routes[].route_id` | string ≥1 | required | stable id | data | P0-3 |
| `routes[].model` | string ≥1 | required | part of identity tuple | data | P0-3 |
| `routes[].effort` | string ≥1 or null | required (key) | effort dial; part of tuple; null only where the harness has no effort dial | data | P0-3 |
| `routes[].harness` | string ≥1 | required | part of tuple | data | P0-3 |
| `routes[].channel` | string ≥1 | required | part of tuple; must match a `channel_id` in the channel catalog (cross-catalog check is loader work) | data | P0-3 |
| `routes[].dispatch_template` | string ≥1 | required | dispatch template copied exactly from its owner source; data only, never executed by validation | owner source; route contract | P0-3 |
| `routes[].usage_capture` | string enum | required | exactly one of `native_json`, `stream_events`, `worker_written`, `none` | route contract | P0-3 |

$defs: `nonemptyString` (string, minLength 1) reused by all ids.

**Usage capture.** Exactly one mechanism per route, from the closed four-value
enum; the route contract requires every route to carry one. How each mechanism
is exercised at dispatch time is implementation, not schema.

---

## 2. Channels — `channels.schema.json`

Shape only: no fee, price, capacity, or policy values are encoded.

| Field | Type | Req | Constraints / meaning | Authority | Data from |
|---|---|---|---|---|---|
| `channels` | array of channel | required | `uniqueItems: true` | channel contract | P0-3 |
| `channels[].channel_id` | string ≥1 | required | stable id; the join target for `route.channel` and `terms.channel_ref` | data | P0-3 |
| `channels[].kind` | string enum | required | `subscription` \| `metered` \| `local` | channel contract | P0-3 |
| `channels[].fee_usd_month` | array of feeEntry | required | dated monthly-fee entries; non-overlap "via ordering conventions outside this schema" (loader) | D203 (OpenAI/Anthropic/Gemini fees and dates), D207 (Go metered ids); OpenCode Go plan fee unknown per needs-lee | P0-4 |
| `channels[].fee_usd_month[].effective_from` | ISO date | required | YYYY-MM-DD, month/day ranges regex-enforced; `format: date` assertion is loader work | data | P0-4 |
| `channels[].fee_usd_month[].value` | number ≥0 or `"unknown"` | required | monthly fee in USD, or literal `unknown`; no values defined by schema | data (D203) | P0-4 |
| `channels[].windows` | array of string enum | required | unique window ids from exactly `rolling-5h`, `weekly`, `monthly`, `daily`; zero or more per channel contract | channel contract | P0-3 |
| `channels[].harness_lock` | array of string ≥1 | required (key) | harness ids the channel is locked to; may be empty; entries unique | channel contract | P0-3 |
| `channels[].replacement_price_ref` | string ≥1 | required | nonempty catalog pointer to replacement-price data; a reference string only, never a price value | data | P0-4 |

---

## 3. Terms — `terms.schema.json`

Dated channel terms plus badge marginal multipliers. Reference fields are
opaque strings; resolution and unknown-badge behavior are implementation, not
schema.

| Field | Type | Req | Constraints / meaning | Authority | Data from |
|---|---|---|---|---|---|
| `terms` | array of termsEntry | required | `uniqueItems: true`; one entry per channel effective-date pair | terms contract | P0-4 |
| `terms[].channel_ref` | string ≥1 | required | opaque reference to a channel defined elsewhere; never an inline definition or id enumeration | data | P0-4 |
| `terms[].kind` | string enum | required | `subscription` \| `metered` \| `local` | data | P0-4 |
| `terms[].effective_from` | ISO date | required | same `isoDate` shape as channels | D203 effective date | P0-4 |
| `terms[].fee_usd_month` | number ≥0 or `"unknown"` | required | `feeUsdMonth` $def; no values defined in schema | D203; Go fee unknown → `"unknown"` | P0-4 |
| `terms[].source` | string ≥1 | required | nonempty citation (publisher, page, retrieval note, or equivalent provenance) | terms contract: "Every such value has a source line" | P0-4 |
| `terms[].decision_price_ref` | string ≥1 | required | opaque reference to the price series used for **routing decisions**; carries no price value | D203: "decision price uses the marginal multiplier" | P0-4 |
| `terms[].reporting_price_ref` | string ≥1 | required | opaque reference to the **list price** used for reporting and cost accounting; distinct in purpose from `decision_price_ref` | D203: "Reporting price remains list price" | P0-4 |
| `badge_multipliers` | object | required | exactly the six contract keys, all required, `additionalProperties: false`; values finite nonnegative numbers | D203 editable defaults (COLD 0.0, USE IT 0.0, ON TRACK 0.25, HOT 0.75, TOO FAST 1.0, NO DATA 1.0 are *data*, not schema) | P0-4 |
| `badge_multipliers.COLD` / `USE IT` / `ON TRACK` / `HOT` / `TOO FAST` / `NO DATA` | number ≥0 | each required | marginal multiplier per badge; unknown badges fail closed to `1.0` (implementation, not schema) | D203 | P0-4 |

Decision-vs-reporting: the two price references exist so decision pricing
(list × badge multiplier) and reporting/cost accounting (list price) use
distinct series without the schema ever carrying a number.

---

## 4. Policy — `policy.schema.json`

Six homes, all required at top level: `never_automatic`, `role_scoped`,
`role_class`, `role_floors`, `reviewer_independence`, `spend_caps`. Every
authoritative rule requires a nonempty `decision` **and** a nonempty `source`
citation. The schema description restates the D206 prohibition and that
role-class governance is never task-class model preference.

| Field | Type | Req | Constraints / meaning | Authority | Data from |
|---|---|---|---|---|---|
| `never_automatic` | array of neverAutomaticRule | required | `uniqueItems: true`; model/effort combinations that must never be used without an explicit non-automatic decision | D152, D187, D204 (Fable 5.1, Opus 5, Luna Max) | Phase 0 policy data (packet not named on disk — see Gaps) |
| `role_scoped` | array of roleScopedRule | required | model-to-roles scoping only; class-to-model is forbidden here; allowed/denied disjointness is loader/data-quality work | D188 (Gemini 3.1 Pro planner/reviewer only) | same |
| `role_class` | array of roleClassEntry | required | role-to-class governance only; MUST NOT be read as class→model/route or task-class preference | D189 (author/primary→coding; envision/ideate/reconsider/score/reviewer/judge→planning_review) | same |
| `role_floors` | array of roleFloorRecord | required | shaped after the archived tier policy; floor labels are opaque stable strings, no tier names/ordering/values baked in | archived `labor-ladder/policy/roles.yaml` ("copying a shape does not create policy authority") | same |
| `reviewer_independence` | array of reviewerIndependenceRule | required | strict three-shape oneOf; mixing mode fields across variants is forbidden | archived `roles.yaml` shapes | same |
| `spend_caps` | array of spendCap | required | nonnegative cap with unit and scope; must cite its governing decision | cited decision per entry | same |

Shared $defs: `nonemptyString`; `stableRef` (`^[A-Za-z0-9][A-Za-z0-9._:/-]*$`,
allows slash-qualified ids such as model ids); `isoDate` (as above).

| Rule fields | Req | Notes |
|---|---|---|
| neverAutomaticRule: `model_ref`, `effort`, `decision`, `source` | `model_ref`, `decision`, `source` required; `effort` optional | `effort` absent ⇒ model-level rule covering all efforts; catch-all effort labels are data |
| roleScopedRule: `model_ref`, `allowed_role_classes`, `denied_role_classes`, `decision`, `source` | all required | class lists are unique arrays of stableRef; denied "expected to be disjoint" from allowed (loader check) |
| roleClassEntry: `role_ref`, `role_class`, `decision`, `source` | all required | `role_class` description repeats the D206-only-two-jobs rule |
| roleFloorRecord: `role_ref`, `floor`, `effective_from`, `decision`, `source` | all but `effective_from` required | `effective_from` optional; archived floors without a recorded date omit it |
| spendCap: `cap`, `unit`, `scope`, `effective_from`, `decision`, `source` | all but `effective_from` required | `cap` number ≥0; `unit`/`scope` opaque stableRef; currency/period vocabulary is data |
| reviewerIndependenceRule: `reviewer_ref`, `decision`, `source` + exactly one variant | required | `reviewerRef`, `independenceDecision`, `independenceSource` $defs wrap the shared fields |

**Archived independence variants (strict oneOf, no mixing):**
- **A — worker separation:** requires `not_same_worker_as` (stableRef) and
  `prefer_different_family` (const `true`; the archived rule requires the
  preference, it is not optional).
- **B — fresh-eyes mode:** `fresh_eyes_mode` const-enum, sole archived value
  `fresh-eyes-preferred`.
- **C — second-opinion mode:** `second_opinion_mode` const-enum, sole
  archived value `different-family-than-author`.

---

## 5. Classes — `classes.schema.json`

Declares exactly five closed value sets, the canonical encoding, and the
don't-cheap-trial rule as inspectable data. **D206 (verbatim, contract):**
"Class metadata MUST NOT map directly to a preferred model or route. It may
only: 1. join production attempts to comparable benchmark evidence; and 2.
determine whether an unevidenced cheap trial is permitted." A class→model or
class→route mapping is a **High** finding; nothing here can express one, and
`classBlock` has `additionalProperties: false` so fields like
`preferred_model`, `model_ref`, `route`, or `provider` fail validation.

| Field | Type | Req | Constraints / meaning | Authority | Data from |
|---|---|---|---|---|---|
| `taxonomy_version` | stableRef (`^[A-Za-z0-9][A-Za-z0-9._:-]*$` — no slash, unlike policy's) | required | id of this taxonomy revision; growth requires a decision (D205) | D205 | Phase 0 class data (packet not named on disk — see Gaps) |
| `key_grammar` | const | required | exactly `role/oracle_type/domain_tags/size_band/language` | contract §Class key | fixed here |
| `canonical_encoding` | object | required | the one canonical encoding of the domain-tags segment (below) | Chief round 3 (execution-log: canonical derived key ruling) | fixed here |
| `value_sets` | object | required | exactly five closed arrays (below); authoritative vocabularies | recommendation §3.1 per contract | fixed here |
| `cheap_trial_rule` | object | required | pinned rule data (below); no model ids/routes/preferences | contract §Class key | fixed here |

**canonical_encoding:** `segment_separator` const `/`; `tag_separator` const
`+` (safe because no tag value contains `+`); `tag_order` const "ascending
codepoint"; `tag_dedup` const `true`; `empty_tags_segment` const `"none"`
(never an empty segment, i.e. a doubled slash is invalid); `notes` nonempty
prose stating component fields remain authoritative and cross-field key
equality is loader work.

**Exact class value sets (each array enum-closed with exact min/maxItems and
uniqueItems — no taxonomy growth):**
- `role` (5): `impl`, `plan`, `review`, `judge`, `prose`
- `oracle_type` (4): `deterministic`, `judge`, `human`, `none`
- `domain_tags` (7): `persistence`, `concurrency`, `security`, `authority`,
  `ui-browser`, `data-schema`, `infra-env`
- `size_band` (4): `xs`, `s`, `m`, `l` (size-band line-count meanings live in
  the contract, not the schema)
- `language` (8): `python`, `typescript`, `shell`, `c`, `sql`,
  `yaml-config`, `markdown`, `mixed`

**Canonical key:** five-part lowercase join
`role/oracle_type/domain_tags/size_band/language`; tags sorted ascending by
codepoint, deduplicated, `+`-joined; empty set is literal `none`. Contract
canonical examples: `impl/deterministic/none/s/python`,
`impl/judge/authority+persistence/m/python`, `review/judge/none/xs/markdown`.
Structured fields are the record of truth; the string is the derived join key.

**cheap_trial_rule (risk-only gate, positionally pinned):**
- `rule_name` const `dont_cheap_trial`; `default` const
  `allow_cheap_trial` (classes matching no deny condition permit an
  unevidenced cheap trial).
- `deny_conditions`: exactly two, `prefixItems` + `items:false` +
  minItems/maxItems 2, order fixed:
  - position 0 (`denyOracleHumanOrNone`): `when` = {field const
    `oracle_type`, op const `in`, values const `["human","none"]`}, reason
    const `oracle_human_or_none`.
  - position 1 (`denyRiskTagOnMOrL`): `when.all_of` exactly two predicates in
    order — {field const `size_band`, op const `in`, values const
    `["m","l"]`} then {field const `domain_tags`, op const `intersects`,
    values const `["persistence","concurrency","security","authority"]`} —
    reason const `risk_tag_on_m_or_l`. `ui-browser`, `data-schema`,
    `infra-env` are not risk tags and are forbidden here.
- `override`: kind const `supervisor_override_is_attempt_evidence`;
  `direction` enum `allow_cheap_trial` | `deny_cheap_trial` (the override is
  recorded as attempt evidence in either direction — lifting a denial or
  imposing one); `description` nonempty prose. Risk gating only: names no
  model, route, provider, or preference.

**$defs/classBlock** (reusable, referenced as
`classes.schema.json#/$defs/classBlock`, for manifests and attempt records):
all six fields required — `class_key` (pattern-checked five-part key; tags
segment allows `none` or `+`-joined members; full sortedness/dedup and
component-equality are loader work), plus the five authoritative components
`role`, `oracle_type`, `domain_tags` (unique, possibly empty), `size_band`,
`language`, each enum-closed to the value sets above. Component fields, not
the key string, are authoritative for validation.

---

## 6. Crews — `crews.schema.json`

Named crews are saved staffing blocks. Route references are opaque catalog ids
resolved against the route catalog (loader work). No selection, ranking,
probability, class metadata, or model preference.

| Field | Type | Req | Constraints / meaning | Authority | Data from |
|---|---|---|---|---|---|
| `crews` | array of crew | required | `uniqueItems: true` | crew contract (D206 authority note) | P0-3 computes the `auto` placeholder (chief-answers-1); named crews packet not named on disk — see Gaps |
| `crews[].crew_id` | string ≥1 | required | stable id; `auto` is the single reserved placeholder id and pairs only with authority `policy` | D206 | P0-3 (placeholder) |
| `crews[].supervisor_route` | routeRef (string ≥1) | required | opaque route-catalog id for the supervisor role | data | named-crews packet |
| `crews[].worker_routes` | object | required | ≥1 property; keys are `roleKey` (string ≥1) role names; each value is a unique, ≥1-item array of routeRefs whose **order is the role's route preference order**; a single route is still a one-element array | crew contract | named-crews packet |
| `crews[].reviewer_route` | routeRef | required | opaque route-catalog id for the reviewer role | crew contract | named-crews packet |
| `crews[].escalation_ladder` | array of routeRef | required | ordered, nonempty (`minItems: 1`), unique; **array order is the ladder order** | crew contract | named-crews packet |
| `crews[].authority` | string enum | required | `lee` (pins/overrides) \| `chief` (chooses under delegated managerial authority) \| `policy` (reserved for the computed `auto` placeholder; means the staffing system's choice) | crew contract, D206 | P0-3 (placeholder) / named-crews packet |
| `crews[].evidence_ref` | string ≥1 | required | nonempty reference to the evidence backing this block | crew contract | named-crews packet |

**auto ↔ policy pairing (two `allOf` if/then guards, both directions):**
authority `policy` ⇒ crew_id must be `auto`; crew_id `auto` ⇒ authority must
be `policy`. So a named crew (`lee`/`chief`) can never use id `auto`, and the
placeholder can never carry `lee`/`chief` authority.

---

## Schema-to-section index

| Schema file / $def | Section |
|---|---|
| `routes.schema.json` — `routes`, `route`, `nonemptyString` | §1 |
| `channels.schema.json` — `channels`, `channel`, `feeEntry`, `isoDate` | §2 |
| `terms.schema.json` — `terms`, `termsEntry`, `badge_multipliers`, `badgeMultipliers`, `feeUsdMonth`, `finiteNonnegativeNumber`, `isoDate` | §3 |
| `policy.schema.json` — six top-level arrays; `neverAutomaticRule`, `roleScopedRule`, `roleClassEntry`, `roleFloorRecord`, `reviewerIndependenceRule` (+A/B/C variants), `spendCap`, `stableRef`, `isoDate` | §4 |
| `classes.schema.json` — top five fields; `canonicalEncoding`, `valueSets`, `cheapTrialRule`, `denyOracleHumanOrNone`, `denyRiskTagOnMOrL`, `classBlock`, `stableRef` | §5 |
| `crews.schema.json` — `crews`, `crew`, `routeRef`, `roleKey`, auto↔policy guards | §6 |
| Loader vs schema split | "Schema validation vs. P0-2 loader checks" |
| Constants table | "Policy-constant home table" |

## Policy-constant home table

Current module-level constants in `src/lee_llm_router/crews.py` (read-only;
the file is 823 lines on disk and its module-level constants span lines
32–657) mapped to their schema home, or marked as route/channel/
provider-registration data with no policy home. Every module-level constant in
the file is classified below — none is omitted:

| Constant (crews.py) | Value on disk | Schema home / disposition |
|---|---|---|
| `NEVER_AUTOMATIC_MODELS` | `claude-fable-5-1`, `claude-fable-5`, `gpt-5.6-luna`, `claude-opus-5` | **policy.never_automatic[]** (`model_ref`, optional `effort`, `decision`, `source`); authority D152/D187/D204. Route/channel data? No — this is a policy rule. Note: four model ids render the three contract-named models (Fable 5.1, Luna Max, Opus 5); the Fable-5.1-vs-Fable-5 split is existing code data. |
| `ROLE_SCOPED_MODELS` | `gemini-3.1-pro` | **policy.role_scoped[]** (`model_ref`, `allowed_role_classes`, `denied_role_classes`, `decision`, `source`); authority D188. |
| `ROLE_SCOPED_CITATION` | `"decisions.md D188"` | The citation string a `role_scoped` record's `source` field carries. Not a separate schema home — `source` is the citation home. |
| `ROLE_CLASS_BY_ROLE` | author/primary→`coding`; envision/ideate/reconsider/score/reviewer/judge→`planning_review` | **policy.role_class[]** (`role_ref`→`role_class`, `decision`, `source`). **Gap:** the constant's docstring cites D188, while `phase0-contracts.md` assigns the role-class mapping to **D189** — the citation needs reconciliation before the policy packet is authored (flagged in Gaps). |
| `CHANNELS` (crews.py) | `openai-sub`, `anthropic-sub`, `gemini-sub`, `gemini-sub-thirdparty`, `openrouter`, `opencode-go` | **Route/channel data, not policy.** Home is the channel catalog: `channels[].channel_id` (§2). |
| `PROVIDER_CHANNELS` | codex_cli→openai-sub; claude_code_cli→anthropic-sub; antigravity_cli→gemini-sub; opencode_cli→opencode-go; omp_cli→openrouter | **No schema home in the six catalogs.** Provider→channel funding metadata is neither a route, channel, policy, class, term, nor crew field; it is router-internal funding configuration. Flagged in Gaps. |
| `WORKER_CHANNEL_OVERRIDES` | `{}` (empty) | **No schema home.** Worker-level funding pins; router-internal, not represented in any Phase 0 schema. |
| `WORKER_ENV_PREFIX_PROVIDERS` | CODEX→codex_cli; CLAUDE→claude_code_cli; OMP→omp_cli; OPENCODE→opencode_cli; ANTIGRAVITY→antigravity_cli | **Provider parsing/registry metadata, not eligibility policy.** Maps a stage-worker env-var prefix to a registered router provider name for worker parsing; it establishes no eligibility rule. **No Phase 0 schema home:** the six catalogs encode no provider or provider-registration field. No explicit governing decision is cited for the pre-existing values — the supervisor recorded this in `needs-lee.md`. P0-2's planned Pi/OMP additions are authorized by D204 and the sprint plan; that authorization is not backfilled to the older values. |
| `_BUILTIN_REGISTERED_PROVIDERS` | frozenset of 19 built-in provider ids (codex_cli; claude_code_cli/claude_code/claude; gemini_cli/gemini; omp_cli; opencode_cli/opencode; antigravity_cli/antigravity/agy; openrouter_http; openai_http; opencode_subscription_http; openai_codex_subscription_http; openai_codex_http; chatgpt_subscription_http; mock) | **Provider registry metadata, not eligibility policy.** The built-in registered-provider name set used by router registration. **No Phase 0 schema home:** no provider field exists in the six catalogs. No explicit governing decision is cited for the pre-existing values — the supervisor recorded this in `needs-lee.md`. P0-2's planned Pi/OMP additions are authorized by D204 and the sprint plan; that authorization is not backfilled to the pre-existing ids. |
| `WORKER_PROVIDER_OVERRIDES` | `{}` (empty) | **Route metadata, not eligibility policy.** `worker_id → (provider, model, effort)` pins that beat command-string parsing — worker-level route pinning with no counterpart among the six schemas. **No Phase 0 schema home.** No explicit governing decision is cited for the pre-existing (empty) value — the supervisor recorded this in `needs-lee.md`. P0-2's planned Pi/OMP additions are authorized by D204 and the sprint plan; that authorization is not backfilled to the pre-existing value. |
| `DEFAULT_CREWS_FILE`, `CREWS_FILE_ENV_VAR`, `STAGE_NAMES`, `GOVERNED_ROLES`, `_WORKER_ENV_PATTERN` | `~/projects/auto-orch/config/crews.yaml`; `LEE_LLM_ROUTER_CREWS_FILE`; envision/ideate/reconsider/score/author; primary/reviewer/judge; `(?P<prefix>[A-Z]+)_STAGE_WORKER_(?P<key>…)=(?P<value>\S+)` parse pattern | **Router-internal plumbing and naming metadata, not eligibility policy.** Crews-file location plumbing, canonical stage-name order, governed route-role names, and the stage-worker env-var parse pattern. **No Phase 0 schema home:** the catalogs encode neither file locations nor these worker/stage vocabularies. The classes `role` value set (§5) is a different vocabulary; no mapping between `GOVERNED_ROLES` and it is asserted here. |
| `CHANNELS` / `GEMINI_CHANNELS` (availability.py) | same six ids; gemini-sub, gemini-sub-thirdparty | **Route/channel data**, channel catalog (§2); the Gemini split is channel-level, not policy. |

No crews.py constant maps a class to a model or route; the D206 prohibition
applies to any future home for these values, and the policy schema cannot
express such a mapping.

## Gaps (flagged, not resolved here)

1. **Policy data packet unnamed.** The on-disk log names packets P0-2
   (loader), P0-3 (route/channel data, `auto` placeholder), P0-4 (terms/pricing
   incl. unknown OpenCode Go fee), P0-5 (phase gate), P0-7 (blocked by Go
   pricing), P0-8 (evidence sidecar), P0-9 (class-dependent). No packet is
   recorded as supplying the policy catalog rows (`never_automatic`,
   `role_scoped`, `role_class`, `role_floors`, `reviewer_independence`,
   `spend_caps`), the `taxonomy_version` value, or named crew rows.
2. **`ROLE_CLASS_BY_ROLE` citation mismatch:** code docstring cites D188;
   phase0-contracts assigns the mapping to D189.
3. **`PROVIDER_CHANNELS` / `WORKER_CHANNEL_OVERRIDES`:** provider→channel
   funding metadata has no home among the six schemas; if it must be governed,
   a decision is needed (not invented here).
4. **`NEVER_AUTOMATIC_MODELS` effort scope:** the constant is model-level;
   the schema's optional per-effort `effort` narrowing has no current code
   counterpart. Whether any D152/D187/D204 rule is effort-scoped is decision
   data the policy packet must supply.
5. **Provider parsing/registry constants lack cited authority.**
   `WORKER_ENV_PREFIX_PROVIDERS`, `_BUILTIN_REGISTERED_PROVIDERS`, and
   `WORKER_PROVIDER_OVERRIDES` are provider parsing/registry/route metadata
   (not eligibility policy) with no Phase 0 schema home; no explicit governing
   decision is cited for their pre-existing values, and the supervisor
   recorded this in `needs-lee.md`. P0-2's planned Pi/OMP additions are
   authorized by D204 and the sprint plan; that authorization is not
   backfilled to the older values.

Nothing in this file assigns decision authority beyond what the schemas and
contracts state; fields marked "data" carry their values from cited decisions
via the packets named above.