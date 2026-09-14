# Phase 0 needs Lee

## Phase 3 — blocking after the authorized P3-6 rerun (2026-09-11)

- Restore eligibility/headroom for the attested
  `codex-gpt-5-6-sol-low-openai-sub` supervisor route, or govern a replacement
  supervisor identity for the acceptance session. The router refused the A2
  same-route repair before launch when this route became `likely_exhausted`.
- Authorize another independent P3-6 acceptance session after the build
  supervisor fixes the discovered crew-binding defect in `/supervise`. The
  plan-authorized single rerun was consumed. A2 remains an uncommitted
  candidate requiring a real-import multiprocessing regression and reduction
  to, or a governed amendment of, its 520-line bound. P3-7 is dependency-blocked.

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

## Phase 2 — 2026-09-11

- No authority blocker at P2-0. D204–D211 and D189 cover execution,
  consumption identities, the $10 ceiling, shim reinstall, and acceptance.
- Safe contract interpretation: D211's root policy constant requires a small
  strict-schema shape extension alongside the data row; otherwise the policy
  loader rejects `policy.yaml`. This is mechanical representation of D211's
  exact name/value, not a new policy decision, and is reviewed with P2-1.
- Replay class keys in `phase2-contracts.md` apply the locked taxonomy to the
  five trace facts. They join evidence only and encode no route choice.

## Resolved by Chief, Phase 3 round 1 (2026-09-11)

See `docs/staffing/chief-answers-p3-1.md`: skill dispatches with the block's chosen route;
attested passing attempts must verify true; domain tags only from explicit fields or paths;
A2 repackaged per Rule B; OpenAI channel exhausted until 2026-09-14 20:34 CDT so the build
and acceptance supervisors run as Sonnet 5 via Claude Code with the gate reviewer falling back
to Sonnet read-only; second acceptance rerun authorized after the fixes.

## Resolved by Sonnet, Phase 3 close-out (2026-09-11/12)

All three answer-1/2/3 fixes are committed and independently reviewed (see
`phase3-execution-log.md` "Sonnet close-out" section): `bbcc5da` (route
dispatch), `fefd714` (subscription verification), `dc6c321` (domain-tag
over-tagging). A2 repackaging (answer 4) is committed as `297c358`
(A2a/A2b in `phase3-acceptance-plan.md`). The second independent
acceptance run (answer 6) is launched, uncoached, per D213 ruling 6; its
result is recorded in `phase3-execution-log.md` once it completes. No
blocking item remains open as of this close-out.

## Resolved by Chief, Phase 3 round 2 (2026-09-12)

See `docs/staffing/chief-answers-p3-2.md`: `/supervise` gains the foreground rule (a headless
session cannot be notified); the headless launch form is recorded; a third uncoached
acceptance run is authorized after the fix; authoring goes back through `run`.

## Third acceptance run complete — Phase 3 acceptance plan closed (2026-09-12)

The authorized third acceptance run (see `phase3-execution-log.md` "Third
acceptance run" section) accepted A2a (commit `1aa64cd`) and A2b (commit
`0f1e5d9`); A1 was already committed (`6631b02`). All three packets in
`docs/staffing/phase3-acceptance-plan.md` are now committed and
independently reviewed. Full suite 1660 passed / 1 skipped; Black/Ruff
clean; `census --json` empty throughout. No blocking item remains open.

One non-blocking observation for a future session: the review route
`pi-deepseek-deepseek-v4-flash-openrouter` reported no shell/bash tool
access during both of this run's review dispatches (it fell back to
grep/static reading and disclosed the gap rather than fabricating oracle
results), unlike earlier P1–P3 sessions where the same route ran
`pytest`/`black`/`ruff` directly. Worth checking whether this is a
transient harness issue before relying on that route's reviews to execute
oracles unsupervised.

## Phase 3 close (Chief, 2026-09-12)

The Phase 3 blocking entry above is superseded: the third authorized uncoached acceptance run
(Chief-launched, detached, harness command form) landed A2a `1aa64cd` and A2b `0f1e5d9` with
A1 `6631b02` standing; four ledger rows with explicit crew-route selection, provider-reported
usage, oracle verdicts, and recorded reviewer fallbacks. Gate items 1–4 re-run by Chief; the
gate review (Sonnet 5 read-only, recorded Astra fallback) returned PASS with one non-blocking
finding (this file's stale entry, now closed) and one self-flagged future concern. No open
Phase 3 item. Carried to Phase 4: reviewers need test-execution tools; judge verdicts should
be recorded as judge outcomes rather than `unverified`; headless supervisor sessions must run
router commands in the foreground (fixed in the skill) and are launched via the harness
command form, never with a command file's contents as the prompt.

## Phase 4 Group A — router and agent-orch (2026-09-12/13)

All six Group A packets committed and independently reviewed; see
`docs/staffing/phase4-execution-log.md` for the full record. Router: `0d8ca17` (P4-0 contract
pass + P4-1 `price` command), `20d5176` (P4-2 crew reorder + `crew_ordering_rule`), `19ee902`
(P4-2b subscription reserve, D216). Agent-orch: `af5dea5` (P4-3 `platform_timeout` +
`verification_tier`), `39a0457` (P4-4 `cost_usd_marginal`), `7751a07` (P4-5 `ESCALATE`, gate
item (a)). Owner suites green in both repos (router full suite; agent-orch full suite modulo
3 pre-existing, unrelated `tests/test_codex_usage.py` failures present on `HEAD` before any
Phase 4 change — not a regression, not fixed here, out of Group A's scope).

**Blocking for Group B / Group C, or for whoever next touches `agent-orch`:**

- **Pre-existing, unrelated uncommitted WIP in `agent-orch` is stashed, not popped.** Before
  any Group A dispatch, `git stash push -u -m "pre-existing WIP unrelated to Phase 4
  staffing, set aside by Sonnet supervisor 2026-09-12"` was run in `agent-orch` to keep
  someone else's in-progress `engine.py`/`worker.py`/`main.py`/etc. changes (resume-retry
  feedback, `stdin_text` replay, and other unrelated work — not staffing-related) from
  bundling into Phase 4 commits. It remains at `stash@{0}` in `agent-orch`. **This session did
  not pop it and does not know whose work it is or whether it is still wanted.** Popping it
  now will very likely conflict with this session's own extensive `engine.py`/`worker.py`
  changes. Whoever owns that WIP needs to `git stash show -p stash@{0}` and manually
  reconcile it against the new Phase 4 commits — do not `git stash drop` it without checking.

**Not blocking, recorded for a future phase:**

- `lee-llm-router`'s `derive_class.py` (packet-based class derivation) has no `.json`
  extension entry in its owned-path language table, so `staff --from-packet` refuses any
  packet whose owned paths include a `.json` file (e.g. a schema file) — hit during P4-2.
  Worked around by staffing directly with explicit `--role`/`--class` instead of
  `--from-packet` for that one packet; not fixed, since it's outside Group A's scope.
- Three of six P4-1 dispatch attempts, and one of two P4-5 dispatch attempts, produced zero
  incremental progress on unambiguous, narrow implementation asks before a route change
  unstuck them (`agy-gemini-3-8-flash-high-gemini-sub` and, once,
  `pi-z-ai-glm-5-3-flash-openrouter`, both on **impl**-role coding dispatches specifically —
  both routes worked fine for **review**-role dispatches all session). One Claude Sonnet
  dispatch (escalating past those) failed outright in 6 seconds with empty stream-json,
  matching the empty-stream defect recorded at the Phase 1 close-out, apparently recurring
  specifically for a Claude Code dispatch launched from within a Claude Code supervisor
  session (a nested-harness case). `pi-deepseek-deepseek-v4-flash-openrouter` was the one
  route that reliably produced real, substantive implementation work all session (used for
  every impl-role packet after the first). Worth a future look at whether `run`'s impl-role
  dispatch, or specifically the nested-Claude-Code case, has a systemic defect distinct from
  ordinary model capability variance — this echoes, but is not identical to, the pre-existing
  note above about `pi-deepseek-deepseek-v4-flash-openrouter` and tool access in Phase 3
  review dispatches; the two observations should be reconciled by whoever investigates.

## D218 DeepSeek V4.1 Flash intake — P4-7 cannot be dispatched as specified (2026-09-12)

**Blocking, recorded rather than worked around:** the D218 lane's step 3 instruction was to
dispatch Phase 4 packet P4-7 as the DeepSeek V4.1 Flash trial. Pre-dispatch inspection shows
P4-7 is not independently dispatchable yet:

- The sprint plan (`chief-of-staff/docs/staffing-phase4-sprint-plan.md`, Group B) and
  `docs/staffing/phase4-contracts.md` §4 both place P4-7 ("`task_type` populated from the
  derived class key on new runs; performance rollup keyed by class") strictly after P4-6
  (the `auto` crew: `routing.py` resolving stage roles through `staff --mode auto --json`).
  Confirmed by contracts.md §4 verbatim: "`task_type` does not exist anywhere in
  `src/auto_orch/`... P4-7 is the owner's call... recorded here, not resolved, since P4-7 is
  Group B scope" — i.e. there is no "derived class key on new runs" for auto-orch to key a
  rollup by until P4-6 exists.
- **P4-6 has not been dispatched by any session**: no `docs/staffing/packets/P4-6*.md`, no
  P4-6 entry in `phase4-execution-log.md`, no `crew: auto`/`staff --mode auto` reference
  anywhere in `auto-orch/src/auto_orch/routing.py` (confirmed by grep). The uncommitted WIP
  present in the `auto-orch` working tree this session (`cycle.py`, `scheduling_policy.py`,
  mission files) is unrelated linux-utilities recovery work by another lane, not P4-6.
  agent-orch already has an author-supplied `task_type` field (`ExecutionIntent.task_type`,
  a static playbook-template placeholder `__TASK_TYPE__`, unconnected to any router class
  key) — this is a different, pre-existing mechanism, not evidence that any part of P4-7 is
  done.
- **P4-6 itself cannot be used for this trial in DeepSeek V4.1 Flash's place**: it is
  classed `impl/deterministic/authority/m/python`, explicitly "don't-cheap-trial: staff
  directly at the ladder's first proven eligible rung" (sprint plan; the same class P4-5
  already exercised this session, staffing directly at the proven
  `pi-deepseek-deepseek-v4-flash-openrouter` route specifically to honor this rule). Using
  the new, unproven DeepSeek V4.1 Flash route for P4-6 would be exactly the "bypass an
  exclusion merely to keep execution moving" D209 forbids.

No in-repo Phase 4 packet is both (a) ready to dispatch today and (b) eligible for an
unproven-route cheap trial. Rather than inventing a scope expansion into P4-6 (out of this
bounded lane's D218 authority, and risking collision with whichever lane is assigned Group B)
or force-dispatching P4-7 against a contract it cannot satisfy, this session substituted a
different piece of genuinely real, already-recorded, correctly-classed work for the D218
trial itself: the `derive_class.py` `.json`-extension gap recorded above under "Phase 4
Group A" ("not fixed here... recorded for a future router packet"). That satisfies D218
ruling 2's actual requirement (real work, an oracle, independent review, landing in the
ledger with provider-reported usage) without inventing P4-6/P4-7's missing mechanism. See
`docs/staffing/phase4-execution-log.md` ("D218 DeepSeek V4.1 Flash intake") for the trial's
ledger evidence.

**Needs Lee/Chief:** decide who picks up P4-6 (Group B), since P4-7 stays blocked until it
lands; and whether the derive_class.py fix landed by this trial should be folded into a
future Group A/B packet's close-out notes or left as its own standalone commit (this session
treated it as standalone, since it was dispatched and reviewed independently of any Phase 4
packet group).

**Resolved 2026-09-12 (Group B session, auto-orch):** both P4-6 and P4-7 committed
(`74d6fe3`, `92d3800`); see `docs/staffing/phase4-execution-log.md` "Group B — auto-orch
(P4-6, P4-7)" for full detail. Not blocking: four independent-review dispatches (two per
packet) returned no usable verdict, recorded there as a new data point on worker/review
reliability, not a Phase 4 blocker per this Phase's established Rule D precedent (supervisor's
own diff read and full-suite run stand as the evidence of record).

## Phase 4 addition by Chief (2026-09-12): P4-5c persist worker output per attempt

`run` captures the worker's stdout for usage parsing but neither persists nor prints it, so a
judge review's verdict text is lost unless the caller watches the console. Packet P4-5c:
write worker stdout/stderr to `~/.local/state/lee-llm-router/artifacts/<attempt_id>/` and
record the path in the attempt's `provenance`; for `--role review`/`judge`, parse a final
`REVIEW VERDICT: ACCEPT|REJECT` line into `verdict.outcome` as `judge_pass`/`judge_fail`
(D214 carry-over). Tests. Class `impl/deterministic/none/s/python`.

**Resolved 2026-09-12 (Group A2 session, router only):** implemented as
`resolve_artifacts_dir`/`_persist_worker_output`/`_parse_judge_verdict` in
`src/lee_llm_router/staffing/run.py`, additive `judge_pass`/`judge_fail` `canonicalVerdict`
enum values and `provenance.worker_output_dir` in `attempt-record.schema.json`. The note's
literal `verdict.outcome` field path does not exist — the real, current field is the flat
top-level `verdict` string, and the resolution extends that string's value set rather than
inventing a nested object (recorded as an imprecision in the original note, not a
requirements change). Live-verified: a real review dispatch's judge verdict now lands as
`judge_pass` in the ledger and its full stdout is readable at
`provenance.worker_output_dir`. Two Hardening-only findings recorded in
`phase4-execution-log.md`'s "Group A2" section (the `rfind`-based matcher's theoretical
false-match edge case; `run.py` importing a private name from `doctor.py`) — neither
blocking. Committed `ed71aa7`. Also folded into this same session: `docs/staffing/packets/
P4-5b.md` (the `/supervise` dispatch pattern for auto-backgrounding harnesses), committed
`7e1e249` — unrelated to P4-5c except sharing a session.

Also recorded by this session, not Group A2's to fix: the P4-6/P4-7 blocker above is still
open, and three pre-existing, unrelated uncommitted working-tree changes (`context.md`,
`result-review.md`, `docs/crew-resolver/execution-log.md` — Crew Resolver Sprint 6 status
notes) were present at session start and deliberately left untouched.

## Phase 4 Group C (P4-8 live proof, 2026-09-12): two cross-repo needs-lee/chief items

Full detail in `phase4-execution-log.md`'s "Group C" section. Summary:

1. **Route dispatch metadata ownership.** A caller like `auto-orch` that must actually invoke
   a router-selected route needs its harness/model/effort. `lee-llm-router catalog explain
   --json` deliberately never discloses them. This session's fix derives `harness` from the
   route_id's own naming convention and `model` via `price --route ID --json` — both real and
   verified working — but `effort` has no resolution path today, and neither workaround is a
   substitute for a real decision on which repo should own this and how. Not decided
   unilaterally by a bounded proof session.
2. **Trusted playbook template's user-simulation/smoke gate invokes bare `python3`.** Any
   target repo not installed into system site-packages (i.e. anything using a `.venv`, which
   is most of this estate) will see false-negative gate failures independent of the actual
   code's correctness — confirmed live, root-caused by independent review. Playbooks
   targeting router-style CLI commands should invoke `.venv/bin/python` or an installed CLI
   entry point instead.

Neither blocked Phase 4's gate (b): a live cycle proved the `auto` crew's actual mechanism
(router-resolved mandate, real governed attempts, real pricing) works once the mid-session
fixes above landed; the backlog item itself was landed and independently reviewed despite the
cycle's own reported `failed` outcome (caused by item 2, not by the delivered diff).

**Addendum (P4-9 gate, 2026-09-12):** a third item from the same live proof — the
`staffing-proof` mission's `human-direction.md` asked the Author stage to enable
`escalation:` on the implementation step; it never did across four cycles. Not investigated
further (escalation firing was evidence-if-it-occurs for gate (b), not a requirement) — worth
a look if a future session wants to observe ESCALATE fire through the real authoring pipeline
rather than only through P4-5's own hand-built `StepDefinition` test.

## Phase 4.1 / Group D (2026-09-12): D219's three recorded gaps — closed

D219 (chief-of-staff/decisions.md) recorded three gaps for Group D to close before Phase 5.
All three are closed this session; full detail in `phase4-execution-log.md`'s "Group D"
section.

1. **Reviewer independence in governed `auto` crews (D219 finding 1 / D211 ruling 5).**
   Closed by P4-13: the `auto` crew now passes `--author-route <primary's route>` when
   resolving `reviewer`/`judge`. Live-proven: cycle `20260912T124316Z`'s mandate resolved
   `reviewer`/`judge` to `agy-gemini-3-8-flash-high-gemini-sub`, distinct from `primary`'s
   `codex-gpt-5-6-sol-low-openai-sub`.
2. **Route dispatch metadata (D219 finding 2).** Closed by P4-10 (router: `route show
   <route_id> [--json]`) and P4-11 (auto-orch: `resolve_role_route` consumes it, keeping the
   naming-convention harness only as a fail-closed cross-check). `effort` now has a real
   resolution path — the specific gap the original P4-8 note (item 1, above) left open.
3. **Trusted playbook smoke gates invoking bare `python3` (D219 finding 3).** Closed by P4-12,
   scoped precisely to `user_journeys_execution_verified` (the validator actually implicated
   in the live P4-8 false-failure): a claimed bare `python`/`python3` command now re-executes
   against the target workspace's `.venv/bin/python` when present, recorded as
   `interpreter_path` in the gate evidence. Live-proven: cycle `20260912T124316Z`'s
   `step_08b_user_simulation_gate` passed genuinely (6/6 verified) for the first time in this
   proof mission's history. **Recorded, not closed:** the code-review `checks_run_match`
   cross-validator (`agent-orch/src/agent_orch/validators.py`) has the identical
   claim-re-execution shape and could hit the same false-negative for a bare-python claim; not
   observed live, not in this packet's named scope, a candidate for a future packet if it is.

## Phase 4.1 / Group D (2026-09-12): P4-14 — pre-existing `test_codex_usage.py` failures bisected

The three failures D217/D219 called "pre-existing, unrelated" are now precisely bisected via
`git worktree` per commit (never `git checkout` in the main tree): the first bad commit is
`agent-orch` `4270736` ("fix: bound worker validation and recover timeout usage",
2026-09-11) — **not** a Phase 4 commit. It added a strict UUID-format `re.fullmatch` check on
Codex's `thread.started.thread_id`; the three tests' fixtures use the non-UUID placeholder
`"thread_id": "t"`, which the new check now rejects. `d166e4d` (P0 baseline) and `e500056`
(the commit immediately before `4270736`) both pass 15/15; every commit from `4270736` onward,
including all five Phase 4 commits, fails the same 3 tests. **Recorded, not fixed:** this is
another lane's test-fixture debt (the fixtures should use a schema-valid placeholder UUID, or
the validation's test coverage needs a real-shaped fixture) — out of Phase 4/4.1's scope to
fix unilaterally; flagged for whichever lane owns `4270736`'s follow-through.

## Phase 5 — findings recorded by Chief (2026-09-12)

- **Fixed in-lane (router `run.py`):** every agy-harness worker was cut off at agy's default
  `--print-timeout` of 5m0s ("[agy] print timeout after 5m0s with turn in progress; returning
  partial output"), regardless of `lee-llm-router run --timeout`. Observed on P5-2b and the
  first P5-3 attempt. `build_dispatch_command` now passes `--print-timeout <run ceiling>s`
  for agy (the watchdog's `DEFAULT_MAX_MINUTES` when no `--timeout` is given). Test added in
  `tests/test_staffing_run.py`. This also means every earlier agy attempt in the ledger longer
  than five minutes of work was a harness cut-off, not a model failure — a caveat on the
  Gemini rows in the first evidence report.
- **Needs a ruling, not fixed:** a Fable 5.1 supervisor cannot attest itself.
  `--supervisor-route claude-claude-fable-5-1-high-anthropic-sub` is refused as
  `never_automatic` (P1-4 ruling 3 applies the selection policy to the attested identity).
  Phase 5 attempts supervised directly by the Chief therefore record
  `verified_success_reason: supervisor_route_unattested` even when the oracle passes, and
  the rollup counts them as unverified. Options: exempt `never_automatic` from the attestation
  check (it governs selection, not identity), or accept that Chief-run lanes are unverified
  by construction. Chief recommends the exemption; it is a contract change, so it is filed
  here rather than made in-lane.

## Phase 5 — pricing snapshot refresh (P5-4, 2026-09-12)

```
4bc55d92d30d8eada73c43d73d88a4c2a3b8201e8a750fcc1e7250c71cff0aef  config/staffing/pricing/openrouter-20260912.json
b89301ba11ce8099c4e03292703ef4d635159e756a9f335cc66cb992afb13827  config/staffing/pricing/openrouter-20260912.json.sha256
b5b08064e24cd68e28b76c3da7503c7bc361956cdc722bbea4359bc82d033a07  config/staffing/pricing/opencode-zen-20260912.mdx
6ea1debe19f0f28bdaed614f4bc003de4070ea80ad6ed5f2955cb98952bccf0a  config/staffing/pricing/opencode-zen-20260912.mdx.sha256
0b0a69e2d87f41caaba972396ca175f76ec02ad21ee5f7ff7fa380394d1e0329  config/staffing/pricing/opencode-zen-20260912.mdx.source
```

```
PROPOSED (not applied) — apply through a reviewed commit:
config/staffing/channels.yaml:
- # catalog snapshot config/staffing/pricing/openrouter-20260911.json (D176
+ # catalog snapshot config/staffing/pricing/openrouter-20260912.json (D176
- # config/staffing/pricing/opencode-zen-20260909.mdx (sha256 sidecar
+ # config/staffing/pricing/opencode-zen-20260912.mdx (sha256 sidecar
-     replacement_price_ref: config/staffing/pricing/openrouter-20260911.json
+     replacement_price_ref: config/staffing/pricing/openrouter-20260912.json
-     replacement_price_ref: config/staffing/pricing/openrouter-20260911.json
+     replacement_price_ref: config/staffing/pricing/openrouter-20260912.json
-     replacement_price_ref: config/staffing/pricing/openrouter-20260911.json
+     replacement_price_ref: config/staffing/pricing/openrouter-20260912.json
-     replacement_price_ref: config/staffing/pricing/opencode-zen-20260909.mdx
+     replacement_price_ref: config/staffing/pricing/opencode-zen-20260912.mdx
-     replacement_price_ref: config/staffing/pricing/openrouter-20260911.json
+     replacement_price_ref: config/staffing/pricing/openrouter-20260912.json
-     replacement_price_ref: config/staffing/pricing/opencode-zen-20260909.mdx
+     replacement_price_ref: config/staffing/pricing/opencode-zen-20260912.mdx
config/staffing/terms.yaml:
- #     config/staffing/pricing/openrouter-20260911.json (sha256 sidecar
+ #     config/staffing/pricing/openrouter-20260912.json (sha256 sidecar
- #     config/staffing/pricing/opencode-zen-20260909.mdx (sha256 sidecar
+ #     config/staffing/pricing/opencode-zen-20260912.mdx (sha256 sidecar
- # the price series now points at config/staffing/pricing/openrouter-20260911.json (sha256
+ # the price series now points at config/staffing/pricing/openrouter-20260912.json (sha256
- # sidecar openrouter-20260911.json.sha256), captured 2026-09-11 from
+ # sidecar openrouter-20260912.json.sha256), captured 2026-09-11 from
-     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
+     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
-     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
+     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
-     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
+     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
-     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
+     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
-     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
+     decision_price_ref: "marginal(badge multiplier × replacement list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
-     decision_price_ref: "marginal(badge multiplier × same-catalog accounting-proxy list price) — decision input per phase0-contracts.md §Terms and prices; proxy series: config/staffing/pricing/opencode-zen-20260909.mdx (D207, decisions.md:5183-5187: Zen's published pricing is the authorized accounting proxy for opencode-go/*)"
+     decision_price_ref: "marginal(badge multiplier × same-catalog accounting-proxy list price) — decision input per phase0-contracts.md §Terms and prices; proxy series: config/staffing/pricing/opencode-zen-20260912.mdx (D207, decisions.md:5183-5187: Zen's published pricing is the authorized accounting proxy for opencode-go/*)"
-     reporting_price_ref: "list-price accounting via the authorized same-catalog proxy per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109) and D207 (decisions.md:5183-5187): config/staffing/pricing/opencode-zen-20260909.mdx"
+     reporting_price_ref: "list-price accounting via the authorized same-catalog proxy per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109) and D207 (decisions.md:5183-5187): config/staffing/pricing/opencode-zen-20260912.mdx"
-     decision_price_ref: "marginal(badge multiplier × list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
+     decision_price_ref: "marginal(badge multiplier × list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207, decisions.md:5183-5185)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260911.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/openrouter-20260912.json, fallback agent-orch/src/agent_orch/rate_table.yaml where OpenRouter has no row (D207)"
-     decision_price_ref: "marginal(badge multiplier × list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/opencode-zen-20260909.mdx (D207, decisions.md:5183-5187: Zen's published pricing is the authorized source for opencode ids)"
+     decision_price_ref: "marginal(badge multiplier × list price) — decision input per phase0-contracts.md §Terms and prices; price series: config/staffing/pricing/opencode-zen-20260912.mdx (D207, decisions.md:5183-5187: Zen's published pricing is the authorized source for opencode ids)"
-     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/opencode-zen-20260909.mdx (D207)"
+     reporting_price_ref: "list-price accounting source per agent-orch convention (agent-orch/src/agent_orch/rate_table.yaml:105-109): config/staffing/pricing/opencode-zen-20260912.mdx (D207)"
```

```
PROPOSED CRON (not installed):
15 06 * * 1 cd /home/lee/projects/lee-llm-router && scripts/refresh_pricing_snapshot.sh >> ~/.local/state/lee-llm-router/pricing-refresh.log 2>&1
```

Neither the proposed terms repoints nor the proposed cron schedule was applied; repointing the price series remains a reviewed commit.

## Rulings by Lee (2026-09-12, D223) — closes the two Phase 5 items above

- **Fable supervisor attestation: exemption approved and applied.** `never_automatic` is no
  longer imposed on `--supervisor-route` (it governs worker selection, not supervisor
  identity); status, channel, harness lock, headroom and terms checks still refuse. Router
  `run.py` + `tests/test_staffing_run.py`. Chief-run lanes now record verified successes.
- **Pricing refresh cadence: on demand, no cron.** Lee: "no cadence to model releases and no
  need to retest what hasn't changed." The proposed weekly cron line is withdrawn; run
  `scripts/refresh_pricing_snapshot.sh` when a model is released or a price signal appears.
- **Terms repointed to the 2026-09-12 snapshots** (reviewed diff in `terms.yaml`'s header
  comment: GLM 5.3 Flash halved back, DeepSeek V4 Flash −1.7%, 445 ids unchanged in count).

## D224 closure (2026-09-12, Chief) — `/supervise` five-harness parity

Closed at router `d82f239` (review D224-3 ACCEPT). Pi is the fifth managed shim target
(`~/.pi/agent/prompts/`); both templates bind `$ARGUMENTS` explicitly; Codex's invocation is
`/prompts:supervise <args>` (recorded in its rendered shim); OpenCode's is
`opencode run --command supervise "<plan-path> auto"` and it hands the message over as one
quoted string, which the templates now strip. Native expansion proven 5/5
(`docs/staffing/shims-native-smoke.md` §5). Real shims installed in all five harnesses;
`shims diff` clean for `crew` and `supervise`. Known limitation: the OMP smoke uses the real
HOME for credentials. Not blocking: a sandboxed reviewer cannot run live harness smokes.

## Filed 2026-09-14 (Chief) — Gemini 3.1 Pro route cannot dispatch

`agy-gemini-3-1-pro-gemini-sub` has `effort: null`; agy refuses `--model gemini-3.1-pro` without
`--effort` (available: low, high), so every dispatch on that route fails in ~5 s with
`invalid model selection` (attempt `router-run-2b424a7d…`). It is eligible as a reviewer (D188)
but unusable. Repair: give the route an explicit effort (a new identity tuple, so a catalog
change with a test), or mark it inactive until then. Not fixed in-lane tonight.
