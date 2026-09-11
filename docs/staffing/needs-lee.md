# Phase 0 needs Lee

## Blocking

None.

## Expected open items

- **Phase 2 router reader compatibility with prompt-variant worker keys.** The
  benchmark sidecar legitimately carries four D15 keys shaped
  `model|harness|effort|review-protocol-v1`, while router
  `crew_page.load_benchmark` accepts only the three-part `WorkerIdentity`
  shape at its `WorkerIdentity.parse(row["worker_key"])` check. The committed
  v5 sidecar already fails the same rows. Per `chief-answers-7.md`, Phase 0
  requires v5/v6 outcome parity and must not change either the v6 key shape or
  the Phase 2 reader.

- OpenCode Go monthly plan fee and capacity are unknown (P0-4).
- `opencode-go/mimo-v2.5` remains unpriced: the pinned Zen catalog publishes
  only the distinct `mimo-v2.5-free` id, while OpenRouter publishes
  `xiaomi/mimo-v2.5`. D207 forbids equating either with the Go id without a
  documented identity. It is excluded from Phase 0 routes and remains a
  pre-existing status-quo worker in other crews.
- Three provider parsing/registry constants in `crews.py` have no explicit
  governing decision cited: `WORKER_ENV_PREFIX_PROVIDERS`,
  `_BUILTIN_REGISTERED_PROVIDERS`, and `WORKER_PROVIDER_OVERRIDES`. They are
  route/provider metadata rather than eligibility policy and therefore do not
  block P0-1, but their authority should be named before later phases treat
  them as durable catalog data. P0-2's additions are authorized by D204 and
  the sprint plan; the pre-existing sets are not separately sourced.
- Pi did not emit authoritative token/cost lines for two timed-out GLM
  attempts, the completed GLM attempt, or the DeepSeek review. The phase's
  exact metered spend therefore cannot be reconciled from worker output.
- Any policy constant without a governing decision will be listed here during
  P0-1/P0-3 review.
- **Resolved in P0-8:** the sidecar remains
  `benchmark.staffing-evidence/2`; `class` and token fields are additive and
  the router's required subset remains compatible. The reviewed choice is
  covered by `ai-workforce-benchmark` commit `51c4402`; round 7 separately
  records the pre-existing four-part-key reader incompatibility for Phase 2.

## Resolved by Chief (2026-09-09, appended while the supervisor was running)

Both blocking items above are resolved in `docs/staffing/chief-answers-1.md` (same directory):
class value sets are now in the recommendation §3.1 ("Initial value sets") and are to be
copied verbatim; the named-crew `authority` enum is `lee | chief | policy`; and Lee's
prohibition (D206, "Class metadata MUST NOT map directly to a preferred model or route…") is
to be added to `phase0-contracts.md` as its own contract. P0-1 is unblocked. Supervisor: move
the two items to a Resolved list citing that file, then continue.

## Resolved by Chief — round 2

Source: `docs/staffing/chief-answers-2.md`, D204–D207; supersedes round 1.

- **Class enumerations:** resolved by the recommendation §3.1 table “Initial
  value sets” and the deterministic don't-cheap-trial rule. Copied into
  `phase0-contracts.md` with D206's verbatim prohibition.
- **Named-crew authority:** resolved as `lee | chief | policy`; `policy` is
  reserved for the computed `auto` placeholder.
- **OpenCode Go pricing:** resolved by D207. OpenCode Zen's published pricing
  is the authorized same-catalog accounting proxy for `opencode-go/*`; ids
  absent from Zen remain unpriced, are excluded from Phase 0 routes, and are
  newly listed here if found.

## Resolved by Chief — round 3

Source: `docs/staffing/chief-answers-3.md`; Chief-of-Staff commit `1cc6b24`.

- **Canonical `domain_tags` serialization:** structured fields are authoritative;
  the derived lowercase key uses sorted `+`-joined tags and literal `none` for
  an empty set. The earlier empty-segment proposal is rejected.
- **Invalid Phase gate/P0-5 example:** replaced in the committed plan with
  `--role impl --class impl/deterministic/none/s/python`.

## Resolved by Chief, round 3 (2026-09-09)

Both Blocking items above are resolved in `docs/staffing/chief-answers-3.md`: canonical
class-key string is five segments with `domain_tags` sorted and `+`-joined, `none` when empty
(recommendation §3.1 "Canonical class-key string", with regex); the phase-gate example and
P0-5 acceptance now use `impl/deterministic/none/s/python`. Supervisor: move both to Resolved
citing that file and continue P0-1.

## Resolved by Chief, round 4 (2026-09-09)

`jsonschema>=4.26,<5` is authorized as a runtime dependency in `pyproject.toml` (one line, now
inside P0-2's file set) and installed into `.venv`; see `docs/staffing/chief-answers-4.md`.
P0-2 may continue; P0-8 and P0-9 are unblocked by the P0-1 commit `aaefb9a`.

- **P0-2 runtime validator dependency / plan-scope contradiction:** resolved
  by this round under D86/D87. The authorized runtime requirement is exactly
  `jsonschema>=4.26,<5`; vendoring, system-package reliance, and a partial
  validator remain forbidden.

## Resolved by Chief, round 5 (2026-09-09)

See `docs/staffing/chief-answers-5.md`: channel inference for `pi_cli`/`omp_cli` fails open
to `unknown`; four named test files join P0-2's scope for fixture-only updates with a strict
reviewer rule; the benchmark's OpenCode version-pin mismatch is excluded from P0-8's gate and
recorded, pin unchanged.

- **P0-2 channel behavior and fixture scope:** resolved under D86/D87.
  Uninferrable Pi/OMP channels resolve to `unknown` rather than raising. The
  four named router test files are in scope for fixture-only updates under the
  line-by-line review restriction.
- **P0-8 OpenCode environment drift:** resolved as a single permitted gate
  exclusion. Installed `1.18.30` versus pinned `1.18.26` stays recorded; the
  reproducibility pin must not change.

## Resolved by Chief, round 6 (2026-09-09)

Source: `docs/staffing/chief-answers-6.md`, D86/D87.

- **P0-3 live-route coverage versus D207 exclusion:** every live worker stays
  in the complete catalog. Unpriced exact ids use required route status
  `unpriced` plus a sourced `status_reason`; eligibility excludes them later.
  P0-3 may add the reviewed `status` schema field and continue in source-sized
  route packets.

## Resolved by Chief, round 6 (2026-09-09)

See `docs/staffing/chief-answers-6.md`: the catalog maps every `crews.yaml` worker, including
`opencode_go_mimo_v25`; routes gain `status: active | unpriced | retired` (schema field added
under P0-3 scope); `unpriced` routes carry a `status_reason` citing D207 and are excluded by
eligibility, not absent from the catalog. Continue P0-3, split by source per Rule B.

## Resolved by Chief, round 7 (2026-09-09)

See `docs/staffing/chief-answers-7.md`: when OpenCode Go reports its limit, the reviewer falls
back to `deepseek/deepseek-v4-flash | pi | openrouter` with the reason recorded; P0-8's router
check becomes no-regression against v5 (same accept/reject outcome on v6), and the reader's
four-part-key rejection is a Phase 2 router item, recorded here, not a P0-8 fix.

## Resolved by Chief, round 8 (2026-09-09)

Source: Chief's round-8 handoff and chief-of-staff commit `d25b965`.

- **P0-3 typed route status fields:** `staffing/catalog.py` and
  `tests/test_staffing_catalog.py` join P0-3 scope narrowly for `Route.status`
  and `Route.status_reason`; `_build` must preserve both. The same narrowly
  scoped typed-object rule applies when P0-4/P0-5 consume committed schema
  fields.

## Resolved by Chief, round 8 (2026-09-09)

See `docs/staffing/chief-answers-8.md`: `catalog.py` and its tests join P0-3's scope for the
typed `Route` `status`/`status_reason` fields only; standing rule that a packet may extend the
typed loader for a schema field it consumes, reviewer confirming the field is in the committed
schema. Close P0-3 and continue.

## Resolved by Chief, round 9 (2026-09-09)

See `docs/staffing/chief-answers-9.md`: named crews carry `kind: interactive | governed`;
governed crews reference the Auto-Orch crew, carry `supervisor: {kind: engine, owner:
auto-orch}` and `escalation: not-recorded`; interactive crews keep the full shape;
`crews.schema.json` joins P0-3's scope for the discriminator only. Never map supervisor to
primary.

## Blocking — after round 9 continuation (2026-09-09)

- **`luna-sol` has a required shape but no sourced composition.** The amended
  sprint plan P0-3 names `luna-sol` as an interactive crew and round 9 requires
  `supervisor_route`, role-keyed `worker_routes`, `reviewer_route`, and a
  nonempty escalation ladder. The only other source is D203's interface example
  `/crew luna-sol`; neither source specifies which catalog route supervises,
  which Sol effort serves each worker role, which route reviews, or the ladder
  order. Repository-wide search found no further definition. Assigning those
  values from the crew name would invent routes/policy constants, prohibited by
  the Phase 0 contract. Needed ruling: the exact route id for each required
  field (or authority to omit `luna-sol` from Phase 0).

## Resolved by Chief, round 10 (2026-09-09)

See `docs/staffing/chief-answers-10.md`: `sol-low-glm-pi` and `luna-sol` interactive blocks are
defined (supervisor, per-role ordered routes with same-role fallbacks, reviewer, judge,
escalation ladders, authority `chief`, evidence ref). Missing route ids come from existing
`crews.yaml` workers; nothing without a source.

## Blocking — after round 10 continuation (2026-09-09)

- **P0-3 acceptance depends on a P0-4-owned file.** P0-3 requires
  `doctor --catalog` to exit 0 on the real `config/staffing` files, while that
  command loads all six documents and currently exits 3 because
  `config/staffing/terms.yaml` is absent. The sprint plan assigns that file
  exclusively to P0-4, and P0-4 explicitly depends on P0-3. Required ruling:
  either (a) permit P0-3 to commit after its 692-test/live-snapshot gates with
  the real doctor check deferred until P0-4, or (b) move an initial
  schema-valid `terms.yaml` into P0-3 scope and amend the dependency/order.
  Observed output: `catalog invalid: staffing catalog document 'terms' could
  not be read ... [Errno 2] No such file or directory`, exit 3.

## Resolved by Chief, round 11 (2026-09-09)

See `docs/staffing/chief-answers-11.md`: P0-3 commits on its reviewed data,
live-snapshot mapping test, and full router suite. The real complete-catalog
`doctor --catalog` check moves to P0-4 acceptance and remains phase-gate item
1 because `terms.yaml` is P0-4-owned; dependency order remains P0-3 → P0-4.

## Blocking — P0-7 supervisor acceptance (2026-09-10)

- **The existing Pi stage wrapper does not implement its configured
  `--preflight` command.** All four new Pi worker preflights exit 1 with
  `pi-stage-worker: usage: pi_stage_worker.py <stage> <prompt_path>
  <response_path>`. Inspection confirms `scripts/pi_stage_worker.py::main`
  accepts only three stage arguments and has no preflight branch, although
  its existing documentation and the P0-7 worker shape prescribe
  `pi_stage_worker.py --preflight`. Astra's analogous Codex preflight exits
  0. P0-7 scope permits only additive `config/crews.yaml` and one parser test
  file, so repairing the wrapper requires an explicit scope amendment.

- **Router `doctor --crews` still rejects governed `pi_cli` harnesses.** On
  the live additive Auto-Orch file it exits 1 with two errors: governed
  `primary` and `reviewer` of `sol-low-glm-pi` report unknown harness
  `pi_cli`; the printed known set is `codex_cli, claude_code,
  claude_code_cli, omp_cli, opencode_cli, antigravity_cli`. P0-2 added Pi
  provider/channel inference but did not add `pi_cli` to this governed-role
  harness validation path. P0-7 acceptance requires this exact doctor check
  to pass, while P0-7 has no router-code scope. Required ruling: reopen the
  relevant P0-2 router harness mapping/validator and its tests, or amend the
  P0-7 governed harness representation with a sourced supported spelling.

## Resolved by Chief, round 12 (2026-09-10)

See `docs/staffing/chief-answers-12.md`: P0-7 scope now includes the
Auto-Orch Pi wrapper plus one test file for a no-call `--preflight` mode,
and router packet P0-7r may reopen the governed-harness validator for
`pi_cli` (and `omp_cli` if absent) with focused tests. Both defects were
exposed by P0-7 and are owner-repo work authorized by D86/D87 and D172.

## Blocking — P0-7 router-suite integration after round 12 (2026-09-10)

Round 12's two repairs work: four real Pi preflights exit 0 without model
calls, and live `doctor --crews` exits 0 (`15 crews, 30/30 workers
resolved`). The required full router suite nevertheless has three failures
caused by the additive P0-7 live file:

- `tests/test_crews.py::test_live_crews_file_has_fourteen_complete_crews`
  hard-codes 14; the live file now correctly has 15. Round 12 authorizes one
  P0-7r test file (`tests/test_doctor.py` was used), not this file.
- `tests/test_staffing_catalog_live.py::test_every_live_worker_maps_to_exactly_one_route`
  looks up `crew_page.HARNESS_BY_PROVIDER["pi_cli"]`, which is absent, even
  though the reopened doctor validator now accepts governed `pi_cli`.
  Repair would require `crew_page.py` and/or its snapshot test, outside
  round-12 scope.
- `tests/test_staffing_catalog_live.py::test_governed_crew_names_exactly_equal_live_crews`
  assumes all live Auto-Orch crews correspond exactly to the catalog's 14
  `kind: governed` records. P0-7 adds live `sol-low-glm-pi`, while round 10
  explicitly defines the staffing-catalog record of that name as
  `kind: interactive`; the test now sees 15 live versus 14 governed. A
  ruling is needed on the correct invariant (likely compare only the 14
  pre-existing governed references and separately assert the interactive
  example).

Required authority: expand P0-7r to the two named router test files and the
minimal `crew_page.HARNESS_BY_PROVIDER` Pi mapping, with the intended updated
live-snapshot invariant stated. P0-7 and P0-7r remain uncommitted until the
router suite is green.

## Resolved by Chief, round 13 (2026-09-10)

See `docs/staffing/chief-answers-13.md`: P0-7r scope gains the two live test
files, exact `pi_cli -> pi` and `omp_cli -> omp` benchmark harness mappings,
and interactive-only optional `governed_ref`. Live counts become presence and
completeness checks; every live name resolves to one catalog record of either
kind; governed records point to live crews; a live-backed interactive record
maps governed primary/reviewer/judge to the first impl/review/judge routes.

## Resolved by Chief, round 11 (2026-09-09)

See `docs/staffing/chief-answers-11.md`: ruling (a). P0-3 commits on its own gates; the real
`doctor --catalog` exit 0 on the full set is P0-4's acceptance and phase-gate item 1.

## Resolved by Chief, round 12 (2026-09-10)

See `docs/staffing/chief-answers-12.md`: P0-7 scope gains `auto-orch/scripts/pi_stage_worker.py`
(add the missing `--preflight` branch mirroring the Codex wrapper) plus a test; router packet
P0-7r adds `pi_cli` to the governed-role harness validation set with tests. Then P0-7 closes
on its stated acceptance, then the gate.

## Resolved by Chief, round 13 (2026-09-10)

See `docs/staffing/chief-answers-13.md`: P0-7r scope gains the two named test files, the
`crew_page.HARNESS_BY_PROVIDER` Pi/OMP mapping, and an optional interactive-only
`governed_ref` field; the live-vs-catalog invariant is restated as three assertions; no
literal crew counts. Then commit P0-7r and P0-7, run the gate, dispatch Astra.

## Blocking — round 13 first-route contradiction (2026-09-10)

Round 13(c) requires live `sol-low-glm-pi` governed `primary` to equal the
**first** entry of the interactive catalog record's `impl` array. The two
authoritative definitions disagree: round 10 orders
`glm-5.3-flash | pi | opencode-go` first and
`z-ai/glm-5.3-flash | pi | openrouter` second, while P0-7 defines the live
governed primary as the latter OpenRouter route. Review and judge do equal
their first entries.

The worker weakened first-entry equality to membership and obtained a review
PASS; supervisor inspection rejects that change because membership does not
implement the explicit ruling. Required ruling: change P0-7's live primary,
reorder round 10's impl array, or explicitly amend round 13(c) to unique
exact-route membership. No weakened invariant is committed.

## Resolved by Chief, round 14 (2026-09-10)

See `docs/staffing/chief-answers-14.md`: reorder the interactive
`sol-low-glm-pi` impl array and first escalation rung to put the exactly
metered OpenRouter GLM route first and the Go subscription route second.
The live P0-7 primary remains OpenRouter; round 13(c) remains strict
first-entry equality. Evidence records the accounting rationale.

## Resolved by Chief, round 14 (2026-09-10)

See `docs/staffing/chief-answers-14.md`: round 10's `sol-low-glm-pi` `impl` order is reversed
(OpenRouter first, Go fallback) with the reason recorded; P0-7's live primary unchanged;
round 13(c) stays first-entry equality. Commit P0-7r and P0-7, then the gate and Astra.

## Resolved by Chief, round 15 (2026-09-10)

See `docs/staffing/chief-answers-15.md`: role-name map to archived floor names recorded in
`policy.yaml`, floors recorded but not enforced in Phase 0; `explain` gains optional
`--author-route` for independence with a printed note when absent. Chief re-ran gate items 1
and 2 live and accepted them, with the `--at` tier display recorded as Phase 1's first packet.
This moves both former phase-gate blocking items (the unsourced role-floor vocabulary map and
the missing reviewer/author comparison input) to Resolved. The reviewed implementation is in
router commit `b5ed4b5`; Phase 1 has not begun.

## Phase 1 — 2026-09-10

- No authority blocker at P1-0. D209 rulings 1–8 resolve field placement,
  selection, live-proof alternatives, and the $10 ceiling. Safe implementation
  assumption recorded in `phase1-contracts.md`: D209's flat field names are
  represented inside the existing `usage`, `cost`, and new `selection` objects
  rather than duplicated at top level, as the sprint plan explicitly requires.
- OpenCode Go is currently `TOO FAST` / `likely_exhausted`; it is excluded from
  dispatch. Reviews use the explain-eligible OpenRouter DeepSeek fallback until
  availability changes. This is governed by D209 and is not missing authority.
- P1-5a design question after two author rounds did not converge: explicit
  `doctor run --route ID` must prove the route currently eligible through the
  same class-sensitive eligibility path as `catalog explain`, but the approved
  syntax makes `--route ID` mutually exclusive with `--role R --class C`.
  Which class context governs explicit-route eligibility: require `--class`
  alongside `--route`, derive a stored/default class, or define an explicit
  route check that intentionally omits class policy? No third same-route
  author attempt was made.

  Resolved by Chief in `chief-answers-p1-1.md`: `--role` and `--class` are
  always required; optional `--route` is an explicit override checked under
  that same role/class context. The corrected-contract attempt is authorized
  as fresh, not a third retry under the superseded contract.
- P1-5b did not converge in two GLM rounds: both attempts spent the watchdog
  on the combined oracle + cost + schema record + append surface, leaving only
  a partial `run.py` and no CLI/tests. Proposed decomposition requiring a
  ruling before another author attempt: P1-5b1 oracle execution/verification;
  P1-5b2 cost + complete v2 record + append/CLI. Continue with disjoint
  packets meanwhile; do not decorate the partial implementation.
- P1-6 also failed to converge in two GLM rounds, including a core-only retry;
  neither attempt created an owned file. Current dispatch constraints leave no
  authorized substitute author: OpenCode Go is `likely_exhausted`, Gemini is
  reserved for one agy live proof, DeepSeek Flash is the review fallback, and
  Luna XHigh escalation is defined after review failure rather than author
  timeout. Ruling needed: authorize a timeout-based author escalation route,
  or change the GLM watchdog/packet strategy beyond the two-round ceiling.

  Resolved by Chief answer 2: watchdog/no-output and two-round
  non-convergence are ladder failures. After one Rule B split where needed,
  escalate implementation to eligible Pi Luna XHigh, then Codex Sol High,
  recording `parent_attempt_id` and `escalation_reason`.

## Resolved by Chief, Phase 1 round 1 (2026-09-10)

See `docs/staffing/chief-answers-p1-1.md`: `run` always takes `--role` and `--class`;
`--route ID` pins the choice and is checked for eligibility under the same role/class path as
explain; ineligible explicit route exits 3 with the reason. Continue P1-5a with the corrected
contract quoted.

## Resolved by Chief, Phase 1 round 2 (2026-09-10)

See `docs/staffing/chief-answers-p1-2.md`: watchdog kills with no output and two-round
non-convergence are the cheap route failing the packet; escalate by the plan's ladder (Luna
XHigh via Pi, then Sol High) with `escalation_reason` recorded; one Rule B split first where the
packet is wide. Not a missing authority.

## Phase 1 stop — P1-7b schema/source incompatibility (2026-09-10)

P1-7b cannot honestly import the specified last-30-days per-attempt artifacts
under the accepted attempt-record v2 schema. The schema condition for
`record_kind: agent_orch` requires `agent_orch_observation`, whose required
fields include mission/cycle identities, producer and reviewer participants,
outcome, and a full review verdict/count payload. The authorized inputs
(`run.json`, per-attempt `route-selection.json`, `usage.json`, and
`accounting_status`) do not carry that complete canonical observation.

Observed scope is material: 108 runs, 524 attempts; 440 measured, 60
not_applicable, 11 unaccounted, 13 missing receipts. Please choose one:

1. authorize a v2 schema extension/new record kind that embeds a verbatim raw
   agent-orch attempt payload with absent class and truthful usage; or
2. identify the authoritative per-attempt `agentOrchObservation` source and
   join rule (including review pairing) that P1-7b may use.

No production/test partial remains. P1-8/P1-9 are held because the plan makes
P1-7 a dependency of the live-proof/final-gate chain.

## Resolved by Chief, Phase 1 round 3 (2026-09-10)

See `docs/staffing/chief-answers-p1-3.md`: new `record_kind: agent_orch_attempt` built only from
raw attempt artifacts with a fixed truth mapping from `accounting_status`; `verdict.tier:
engine_validation`; class absent; the full-observation kind stays for Phase 4.

## Phase 1 close authority boundary — Claude proof consumed (2026-09-10)

Gate item 2 is not sealable under the current consumption ledger. Anthropic was
eligible (0.88 headroom), so the authorized Claude Sonnet branch was used once.
That attempt exposed missing safe noninteractive permission flags and failed
with empty stream JSON. The defect is now fixed in reviewed commit `335ef28`,
but D209 permits **at most one Claude Code live proof**, already consumed, and
the Gemini alternative applies only when Anthropic is `likely_exhausted` at
dispatch. Two choices require Lee/Chief authority: authorize one post-fix
Claude Sonnet reproof, or explicitly accept the failed pre-fix record plus the
reviewed fake-boundary remediation as gate evidence. No Gemini substitution or
second Claude call was invented.

## Resolved by Chief, Phase 1 round 4 (2026-09-10)

See `docs/staffing/chief-answers-p1-4.md`: one post-fix Claude Sonnet re-proof authorized;
Astra final-review ceiling 1200 s with a three-way split fallback; `run --supervisor-route`
attests the caller so `verified_success` can be true; one attested GLM proof; then close.

## Phase 1 close (2026-09-11)

No Phase 1 implementation decision remains for Lee. The authorized second
Claude Sonnet proof failed with empty stream evidence and unavailable usage;
the failure is preserved and no third call was made. Current attested GLM and
Sol proofs pass, gates 1–4 pass, and the final Astra Low whole-diff review has
0 contract-blocking, 0 High, and 0 Medium findings. Chief still owns the D210
seal. Two non-blocking Phase 2 candidates remain: bring text explain's tier
`kind` to parity with JSON, and decide whether import writers need concurrency
control beyond the current serialized-writer assumption.
