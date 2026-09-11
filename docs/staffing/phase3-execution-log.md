# Phase 3 execution log

## 2026-09-11 — P3-0 contract pass

- Reconciled D204–D213: D213 authorizes the complete Phase 3 scope, D189
  authorizes managed shim apply, and D209's staffing, usage-truth, Rule B,
  review, continuation, and stop doctrine remains controlling. No missing
  authority.
- Read the Phase 3 plan, Rules A–K, Agent-Orch's deterministic failure
  signatures, live `staff --json` and CLI help, `run` dispatch/record boundary,
  shim template mechanics, and Phase 0–2 contracts/logs/needs-Lee history.
- Preserved pre-existing modified `context.md`,
  `docs/crew-resolver/execution-log.md`, `result-review.md`, and untracked
  Chief-answer files; Phase 3 commits must not absorb them.
- Baseline began at `34cf0ee`; expected gate is 1,467 passed / 1 skipped.
- Wrote the exact command/authority contracts and the two-item acceptance plan.
  P3-0 is supervisor-authored and has no worker dispatch.

## Attempt ledger

Every dispatch row records packet/role, staffing evidence, route, time/exit,
usage basis and knowable cost, verdict, findings, next action, and escalation.

| Packet | Role | Staffing / route | Time / exit | Usage / cost | Verdict / findings / next action |
|---|---|---|---|---|---|
| P3-1 author 1 | impl | auto selected Gemini Flash High/agy after live evidence changed | 306 s / worker 0, oracle 4 | provider-reported 448,323 tokens; subscription cost unavailable | No owned files; record's inferred `spec_rejected` rejected by supervisor as unlawful; classified `oracle_failed`; same-route repair |
| P3-1 author 2 | impl | explicit same current auto route, linked parent | 306 s / worker 0, oracle 4 | provider-reported 457,170 tokens; subscription cost unavailable | Partial source only; `oracle_failed`; non-convergence advanced to auto ladder's GLM rung |
| P3-1 author 3 | impl | GLM/Pi OpenRouter, explicit next auto-ladder rung | 221 s / worker 0, oracle 2 | provider-reported 1,351,835 tokens; `$0.03206197` metered | Candidate completed; supervisor repaired one parametrization blocker and formatting/lint; 150 passed |
| P3-1 review 1 | review | auto with GLM author exclusion chose Gemini Pro/agy | 7 s / worker 1, oracle 0 | unavailable usage; subscription | No review produced; advanced to required DeepSeek review |
| P3-1 review 2 | review | DeepSeek/Pi OpenRouter with `--author-route` GLM | 189 s / 0 | provider-reported 573,184 tokens; `$0.0201141864` metered | Verified pass, but supervisor found a contract blocker: subscription-unavailable usage misclassified as metered spend; repaired and re-reviewed |
| P3-1 re-review | review | DeepSeek/Pi OpenRouter with `--author-route` GLM | 328 s / 0 | provider-reported 1,207,855 tokens; `$0.0289177728` metered | Verified pass; 152 focused passed; blocking 0, hardening 0, future 0; accept |

## P3-1 — Deterministic failure classification

- Added the evidence classifier, CLI, exact fixtures for all seven classes,
  and adversarial precedence/judgment tests. Supervisor inspection rejected
  both legacy/inferred `spec_rejected` attempt labels and used `oracle_failed`.
- The accepted classifier proves a metered route before treating unavailable
  usage as `unaccounted_spend`; subscription and absent-metering evidence do
  not fabricate spend. Judgment classes require explicit `--judgment` plus a
  non-passing review verdict and are never inferred from prose.
- Focused gate 152 passed; Black, Ruff, and diff check clean. P3-1 metered
  OpenRouter spend `$0.0810939292`; subscription attempts remain separate.

## P3-3 — Conservative class-key derivation

- The named `sol-low-glm-pi` crew selected GLM/Pi. Its first attempt created
  no files; the same-route repair produced only the keyword table. Both
  failed collection and were classified `oracle_failed`, not the legacy
  runner's inferred `spec_rejected`. GLM usage/cost: 468,951 / `$0.011386385`
  and 835,182 / `$0.02157127`, provider-reported and metered.
- Luna XHigh/Pi received the partial candidate and timed out at 590 s after
  restoring/adding most source and tests; 2,467,986 provider-reported
  subscription tokens and `$0.11595296` list-equivalent, not metered. Sol High
  repaired the accidental test-file truncation and finished the candidate,
  then timed out at 590 s; its subscription usage was unavailable.
- DeepSeek review passed the 112-test candidate, but supervisor inspection
  found one contract blocker: overrides were printed by `staff` but absent
  from the eventual attempt. The repair adds validated `run
  --class-derivation FILE`; effective class mismatch refuses before launch,
  and exact override records enter attempt provenance without selecting a
  route. Re-review passed with 200 focused tests. DeepSeek receipts were
  1,997,966 / `$0.0423871224` and 2,155,512 / `$0.044175852`, provider-reported
  metered usage.
- Accepted behavior derives only from explicit packet facts and the reviewed
  `classes.yaml` keyword table, never from model preference. Black, Ruff, and
  diff check are clean. P3-3 metered spend `$0.1195206294`.

## P3-4 — Live-run registry and census

- Named-crew GLM/Pi authored the registry, owned-path run gate, census CLI,
  and tests. Its worker exited 0 but the first oracle exposed three test-only
  defects; supervisor repaired the complete set. Receipt: 4,068,368
  provider-reported tokens / `$0.08108128` metered.
- The accepted registry atomically checks and registers normalized nonempty
  paths under a per-host lock, detects equality and ancestor/descendant
  intersections, records pid plus Linux start-time identity where available,
  refuses before launch, and deregisters on every post-registration boundary.
  `census` lists live rows and removes proven stale rows with reasons.
- Initial DeepSeek review passed 219 tests. Supervisor inspection found one
  contract-blocking fallback race: a fresh non-`fcntl` lock could be unlinked
  at the acquisition deadline. The repair fails closed on fresh locks and
  takes over only a lock older than the documented stale threshold. DeepSeek
  re-review passed the 221-test oracle. Receipts: 1,254,883 /
  `$0.0278569536` and 5,084,744 / `$0.0978310704`, provider-reported metered.
- Post-review live census is empty; all router workers deregistered. Black,
  Ruff, and diff check clean. P3-4 metered spend `$0.206769304`.

## P3-2 — Next-action CLI

- Named-crew GLM/Pi wired `next-action` to the accepted Phase 2 pure function.
  Its worker exited 0; the oracle exposed one parity-test construction defect
  (`None` rendered as an integer argument), which the supervisor repaired
  without changing production policy. Receipt: 1,301,527 provider-reported
  tokens / `$0.02840001` metered.
- The CLI accepts exactly the classifier JSON object and a nonnegative
  completed repair count, translates capability count 0 to pure-function
  attempt 1 and 1+ to escalation, and leaves `oracle_failed`/unknown at
  `supervisor_judgment`. It performs no dispatch or registry operation.
- DeepSeek/Pi review with GLM excluded passed, 0 blockers; 164 focused passed,
  Black/Ruff/diff clean. Receipt: 710,471 provider-reported tokens /
  `$0.0177000432` metered. P3-2 metered spend `$0.0461000532`.

## P3-5 — `/supervise` four-harness skill

- Named-crew GLM/Pi authored the template/library seam; 347,778
  provider-reported tokens / `$0.01419601` metered. Supervisor inspection
  found a blocker: no CLI could select the new command and no new tests
  existed. The same-route repair changed nothing (165,019 tokens /
  `$0.00442148` metered), so the packet escalated for non-convergence.
- Luna XHigh/Pi wired `shims install|diff --command supervise`, added the
  lifecycle/parity/quote/allowlist tests, and timed out at 590 s after leaving
  a usable candidate: 2,798,873 provider-reported subscription tokens /
  `$0.1105432` list-equivalent, not metered. Supervisor corrected one false
  parity assertion; 158 focused tests and Black/Ruff passed.
- DeepSeek/Pi reviewed with the Luna/Sol family excluded and passed the
  literal scratch install/diff and test gate; 7,318,770 provider-reported
  tokens / `$0.1350536208` metered. Blocking 0; no accepted hardening or
  future finding.
- Live dry-run named four `create` targets. D213/D189-authorized apply created
  `/supervise` for Claude Code, Codex, Chief OMP, and OpenCode. Immediate
  `shims diff --command supervise` and default `/crew` diff both exited 0;
  `/crew` remains unchanged. P3-5 metered spend `$0.1536711108`.
