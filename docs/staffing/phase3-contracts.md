# Phase 3 supervisor-protocol contracts

Authority: D213 rulings 1–8 on the D212 accepted baseline. D204–D209 remain
active. In particular, D205/D206 still make class keys evidence/comparability
keys, never preferred-route mappings; D209 still governs staffing, usage
truth, Rule B, review classification, continuation, and genuine stops.

## P3-0 observed command contracts

The live Phase 2 CLI exposes these exact dispatch signatures:

```text
lee-llm-router staff --role ROLE --class CLASS
  [--mode auto | crew NAME | bind ROUTE_ID]
  [--author-route ROUTE_ID] [--supervisor-route ROUTE_ID]
  [--authorized-by ID] [--reason TEXT] [--at DATE]
  [--availability-file PATH] [--catalog-dir PATH] [--json]

lee-llm-router run --role ROLE --class CLASS --packet FILE
  [--route ROUTE_ID] [--supervisor-route ROUTE_ID]
  [--author-route ROUTE_ID] [--oracle CMD] [--workdir DIR]
  [--class-derivation FILE]
  --owned-paths PATH [--owned-paths PATH ...]
  [--parent ATTEMPT_ID] [--escalation-reason R] [--timeout S]
  [--at DATE] [--availability-file PATH] [--catalog-dir PATH]
  [--openrouter-snapshot PATH] [--rate-table PATH] [--json]

lee-llm-router census [--json]
```

`staff --json` returns the compact staffing block plus the selected route,
selection reason, eligible/excluded routes and reasons, proof/evidence basis,
ladder, reviewer, authority, demand, and expected-cost disclosures. `run
--json` returns the schema-v2 attempt record written to the per-host ledger.
Selection is either `explicit` or `explain_cheapest_eligible`; a staffed run
never escalates itself. Pi is dispatched in JSON event mode, Codex with
`--json`; unknown usage remains unavailable. The caller attests its identity
through `--supervisor-route`.

The current shim mechanism renders one package template for the four harness
tags, hashes the body below its managed marker, refuses edited or unmanaged
targets without force, supports dry-run/apply, and diffs installed content
against the rendered target. Phase 3 adds a second managed command without
changing `/crew` semantics.

Agent-Orch's cited platform signatures cover authentication/token expiry,
logged-out/session-limit text, missing binaries and exits 126/127, quota/rate
limit/billing exhaustion, permission failures, and service/gateway/connection
failures. Phase 3 copies those signatures with source citation; it does not
import owner-repository code.

## D213 rulings bound to implementation

1. **Harness skill, not daemon.** “One template” renders `/supervise
   <plan-path> [crew NAME | auto]` in Claude Code, Codex, OMP, and OpenCode.
   Its numbered loop calls only `staff`, `run`, `classify-failure`,
   `next-action`, `census`, and `evidence rollup`. It quotes Rules A–K as
   guardrails and ends with the staffing block plus ledger evidence.
2. **Conservative derivation.** Language comes from owned-path extensions
   (`mixed` for multiple); size comes from declared file/line estimates and is
   `l` if undeclared; oracle is deterministic only for a named test/validator,
   otherwise judge for a named reviewer, otherwise none; domain tags are only
   explicit `classes.yaml` keyword-table matches; role comes from packet kind.
   Overrides are recorded on the attempt.
3. **Evidence classification.** Deterministic classes are
   `platform_timeout`, `platform_env`, `unaccounted_spend`, `oracle_failed`,
   and `unknown`. `spec_rejected` and `capability_rejected` enter only through
   explicit `--judgment` after review, never inferred from prose.
4. **Registry/census.** A run registers pid, route, packet id, owned paths, and
   start under the state directory; an intersecting live run is refused.
   `census` lists live rows and cleans stale pids with a note. Parallel work is
   permitted only for disjoint owned paths.
5. **Supervisor usage.** It is `unavailable` unless the harness reports it;
   the attested route is recorded. Per-session attribution remains Phase 5.
6. **Acceptance.** A different Sol Low Codex process receives only the
   installed `/supervise` body, `docs/staffing/phase3-acceptance-plan.md`, and
   `crew sol-low-glm-pi`. Both real items must be reviewed commits; the ledger,
   not its narrative, proves every attempt, verification, repair/escalation,
   selection basis/reason, route, usage basis, verdict, and next action.
7. **Install.** Dry-run precedes the D189-authorized `shims install --apply`;
   record all targets and preserve `/crew` except for parity verification.
8. **Limits/closure.** Refresh sessions about every three hours, keep metered
   spend at or below $10, and leave D214 for the Chief after an independent
   gate rerun and acceptance-ledger read.

## Execution invariants

- Before every worker or reviewer dispatch, inspect the packet contract and
  run `catalog explain` or `staff`; record its selection and exclusions.
- Apply Rule B before dispatch. Every packet has explicit owned paths and a
  finite oracle. Concurrent packets must have disjoint owned paths.
- The supervisor reads every candidate diff and classifies review findings as
  contract-blocking defects, non-blocking hardening, or future concerns.
  Blocking findings cite the violated requirement and a reproducer.
- Remediation follows `next-action`; one same-route capability repair precedes
  escalation. Exclusions and never-automatic policy are never bypassed.
- No usage is invented. Provider-reported, observed, calculated, and
  unavailable facts stay distinct; subscription equivalents never count as
  metered spend.
- Do not stop at packet boundaries or while a worker is running. A genuine
  stop requires an authority boundary, unresolved contradiction, missing
  credential, material irreversible risk, or an external dependency that
  makes useful progress impossible, after reconciling D204–D213.

## P3-6 acceptance ownership correction

The first independent acceptance session correctly stopped after finding that
the original A2 packet owned only the ledger primitive and its unit test while
the D213-ruling-6 outcome also requires the production read/decide/append
callers to hold that primitive. D213 authorizes concurrency control for the
multiple import writers as the acceptance item; it does not restrict that item
to two files. The narrower boundary was introduced by P3-0 packetization, not
by Lee or the Chief. After reconciling D204–D213, the build supervisor therefore
corrected A2 to own `staffing/import_evidence.py` and its benchmark and
agent-orch tests, with a 520-line bound and a focused three-file test oracle.
This is the one P3-6 rerun; the skill's fail-closed authority guard is unchanged.
