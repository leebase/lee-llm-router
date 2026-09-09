# Phase 0 staffing contracts

Authority: chief-of-staff decisions D152, D155, D157, D158, D187, D188,
D189, D203, D204, and D205; the Phase 0 sprint plan; and the staffing
architecture recommendation §§3–5.

## Route

A route is the tuple `(model, effort, harness, channel)`. Every route has a
dispatch template copied exactly from its owner source and a `usage_capture`
value from `native_json`, `stream_events`, `worker_written`, or `none`.

## Channel

A channel records `kind` (`subscription`, `metered`, or `local`),
`fee_usd_month` with `effective_from`, zero or more window ids drawn from
`rolling-5h`, `weekly`, `monthly`, and `daily`, a `harness_lock` list, and a
`replacement_price_ref`.

## Class key

The class key grammar is
`role/oracle_type/domain_tags/size_band/language`. It has exactly two jobs:
evidence comparability and identifying work that must not receive a cheap
trial. It must not predict the perfect model before an attempt. Taxonomy growth
requires a decision (D205).

Initial value sets (recommendation §3.1; these are the whole taxonomy until a
decision grows it):

- `role`: `impl`, `plan`, `review`, `judge`, `prose`.
- `oracle_type`: `deterministic`, `judge`, `human`, `none`.
- `domain_tags` (set, may be empty): `persistence`, `concurrency`, `security`,
  `authority`, `ui-browser`, `data-schema`, `infra-env`.
- `size_band`: `xs` (≤1 file, ≤50 changed lines), `s` (≤3 files, ≤200), `m`
  (≤8 files, ≤600), `l` (larger). A pre-diff estimate is recorded as an
  estimate.
- `language`: `python`, `typescript`, `shell`, `c`, `sql`, `yaml-config`,
  `markdown`, `mixed`.

The deterministic don't-cheap-trial rule is: `oracle_type` in `{human, none}`,
or any of `{persistence, concurrency, security, authority}` present with
`size_band` in `{m, l}`. Everything else is cheap-trial safe. The supervisor
may override either way, and the override is recorded on the attempt.

The structured five named fields are the record of truth. The lowercase
string is a derived join key. `domain_tags` are sorted and joined with `+`; an
empty set is encoded as literal `none`, never as an empty segment. Canonical
examples: `impl/deterministic/none/s/python`,
`impl/judge/authority+persistence/m/python`, and
`review/judge/none/xs/markdown`.

## Class-metadata prohibition (D206, verbatim)

> Class metadata MUST NOT map directly to a preferred model or route. It may only:
> 1. join production attempts to comparable benchmark evidence; and
> 2. determine whether an unevidenced cheap trial is permitted.

A schema, document, or code path that maps a class to a model or route is a
High review finding.

## Policy

- `never_automatic`: Fable 5.1, Opus 5, and Luna Max (D152, D187, D204).
- `role_scoped`: Gemini 3.1 Pro is eligible only for planner/reviewer work and
  never automatic for coding/implementation (D188).
- `role_class` (D189): `author` and `primary` map to `coding`; `envision`,
  `ideate`, `reconsider`, `score`, `reviewer`, and `judge` map to
  `planning_review`.
- Role floors and reviewer-independence shapes come from archived
  `labor-ladder/policy/roles.yaml`; copying a shape does not create policy
  authority.
- Spend caps must cite their governing decision.

## Named crew

A named crew is a saved staffing block with a supervisor route, worker routes
per role, reviewer route, escalation ladder, `authority` (`lee`, `chief`, or
`policy`), and `evidence_ref`. `lee` pins or overrides; `chief` chooses under
delegated managerial authority; `policy` is reserved for the computed `auto`
crew placeholder and means the staffing system's choice (D206).

## Terms and prices

Terms entries are dated. D203 is the authority for OpenAI $200/month,
Anthropic $100/month changing to $20/month on 2026-09-30, Gemini $100/month
changing to $20/month on 2026-09-30, and the effective date. OpenCode Go's fee
is `unknown` until Lee supplies it. OpenRouter and OpenCode Zen are metered at
list price.

Badge-to-marginal multipliers are editable defaults: `COLD: 0.0`, `USE IT:
0.0`, `ON TRACK: 0.25`, `HOT: 0.75`, `TOO FAST: 1.0`, and `NO DATA: 1.0`.
Unknown badges fail closed to `1.0`. Reporting price remains list price;
decision price uses the marginal multiplier.

No fee, price, capacity, policy constant, or date may be invented. Every such
value has a source line.

## Ownership and frozen evidence

Changes in owner repositories are additive only. Existing Auto-Orch crew and
worker lines remain byte-identical. Benchmark `private/`, existing exports,
and signed/frozen artifacts are never written; their before/after hashes are
recorded. Provider prompts use scratch inputs only. No Phase 0 implementation
calls a real provider.
