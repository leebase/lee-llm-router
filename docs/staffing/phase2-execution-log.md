# Phase 2 execution log

## 2026-09-11 — P2-0 contract pass

- Authority reconciled: D204–D208 baseline/policy; D209 staffing, usage truth,
  autonomy, review classification, Rule B, and acceptance doctrine; D210
  Phase 1 state/lessons; D211 rulings 1–9, consumption identities, $10 ceiling,
  and D212 seal. D189 authorizes shim reinstall. No missing authority.
- Read fully: Phase 2 plan, D204–D211, Phase 1 handoff/log/needs-Lee section,
  and Chief answers P1-1…P1-4.
- Preserved pre-existing modified `context.md`,
  `docs/crew-resolver/execution-log.md`, `result-review.md`, and untracked
  Phase 0/1 Chief-answer files; Phase 2 commits must not absorb them.
- Observed rollup, attempt v2, live explain JSON, crew blocks, policy, cost
  formula, and five traces. Exact bindings/replay facts are in contracts.
- Baseline gate started from `e09d80a`: expected 1,355 passed / 1 skipped.
- P2-0 is supervisor-authored, no worker dispatch. Its D211 policy constant
  and strict schema shape are reviewed with P2-1.

## Attempt ledger

Each staffed row records packet/role, explain and selected route, selection
reason, exclusion summary, start/end, exit, provider usage truth, knowable
cost, result, parent/escalation reason, and attempts to acceptance. Hand
dispatches record the same fields as `run`.

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P2-1 author 1 | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; Phase 2 implementation ladder first rung eligible | likely-exhausted 7; never-automatic 4; Gemini Pro role-scope 1; unpriced/pricing 1 (overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 08:25 / 08:35 | 590 s ceiling, process group terminated | `provider_reported`, `pi --mode json events`; input 231, output 78, cached 55,744, reasoning 0, total 56,053; provider event cost `$0.000872985` | implemented evidence source/tests; supervisor focused gate found 2 evidence-test blockers plus concurrent P2-6 blocker; repair required |
| P2-2 author 1 | impl | `catalog explain --role impl --class impl/deterministic/none/xs/python --json`; ladder first rung eligible | same exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | 08:25 / 08:35 | 590 s ceiling, process group terminated | `provider_reported`; input 718, output 2,454, cached 41,216, reasoning 52, total 44,388; `$0.00128559` | partial `proof.py`, no tests; timed-out packet escalates |
| P2-6 author 1 | impl | same XS explain; ladder first rung eligible | same exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | 08:25 / 08:35 | 590 s ceiling, process group terminated | `provider_reported`; input 22,467, output 54, cached 704, reasoning 1, total 23,225; `$0.001709085` | source/tests; supervisor reproducer: trailing whitespace incorrectly enters `platform_*`; repair required |
| P2-7 author 1 | impl | same S explain; ladder first rung eligible | same exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | 08:25 / 08:28 | 0 | `provider_reported`; input 517, output 799, cached 14,784, reasoning 73, total 16,100; `$0.000460285` | five fixtures + 42 tests; 37 passed/5 dependency skips pending P2-6 |

## First-wave remediation and acceptance

- P2-1 same-route repair corrected two supervisor-found test expectations
  (16,549 provider-reported tokens, `$0.00042791`). The first broad DeepSeek
  review reached the 590 s ceiling after 120,007 tokens/`$0.002965585208` and
  no verdict. Supervisor/reviewer probes exposed route-global evidence and
  benchmark double-count blockers. Luna XHigh escalation (parent P2-1 repair,
  `non_convergence`) completed route-scoped, supersession-aware evidence:
  83,237 provider-reported subscription tokens, `$0.0052596` execution
  equivalent. Split DeepSeek re-review PASS, 0 blockers (96,540 tokens,
  `$0.001985606176`). P2-1: 3 author attempts + 2 reviews, about 31 min.
- P2-2 GLM ceiling partial escalated with `platform_timeout` to Luna XHigh;
  101,797 provider-reported subscription tokens, `$0.0038252` execution
  equivalent; 37 focused passed. DeepSeek PASS, 0 blockers; 2 hardening and 2
  future concerns (55,841 tokens, `$0.001539377394`). P2-2: 2 authors + 1
  review, about 18 min.
- P2-6 same-route repair closed the whitespace reproducer (13,180 tokens,
  `$0.000350455`). DeepSeek PASS, 0 blockers; invisible-control-character
  handling is non-blocking hardening (45,060 tokens, `$0.001191192946`).
  P2-6: 2 authors + 1 review, about 15 min.
- P2-7 dependency rerun is 42 passed/0 skipped. DeepSeek PASS, 0 blockers
  (74,847 tokens, `$0.001723904`). P2-7: 1 author + 1 review, about 10 min.
- P2-0 full-suite check exposed 23 synthetic-catalog failures and the schema's
  erroneous frozen `$5` value. GLM repair made the current value data,
  finite/nonnegative schema, and typed catalog field (37,898 tokens,
  `$0.001932`). Split DeepSeek review PASS, 0 blockers; 3 documentation/type
  hardening notes (74,920 tokens, `$0.001918465362`). Reviewer full gate:
  1,515 passed/1 skipped. P2-0: 1 repair + 1 review after supervisor contract
  pass, about 10 min.
- Supervisor read every owned diff. No out-of-scope worker change accepted.
  OpenRouter metered receipts through this wave total `$0.018362441086`;
  Luna subscription execution equivalents are separate, never counted as
  metered spend. All usage above is provider-reported from Pi JSON events.

## P2-3 — Ladder arithmetic

- `catalog explain --role impl --class impl/deterministic/none/s/python
  --json` selected the eligible GLM/Pi OpenRouter first rung; exclusions were
  likely-exhausted 7, never-automatic 4, Gemini Pro role-scope 1, and one
  unpriced/pricing row. The GLM attempt exited before its 590 s ceiling with
  no file candidate (76,743 provider-reported tokens, `$0.00318172`).
- Three Luna XHigh/Pi native launches entered harness I/O stalls before any
  edit; all processes were terminated and verified absent. Their terminal
  subscription usage events were retained as harness-calculated evidence,
  not provider billing; the launches did not create a candidate. Rule B was
  already satisfied because P2-3 was one pure arithmetic topic, so the packet
  advanced to Sol High.
- A fresh explain showed `codex-gpt-5-6-sol-high-openai-sub` eligible with the
  same exclusions. Sol High authored only `staffing/ladder.py` and its focused
  tests; its final Pi event reported 69,751 tokens and a `$0.08135`
  subscription execution equivalent. Supervisor inspection and 17 focused
  tests found the arithmetic coherent.
- Independent review explain used `--role review --class
  review/judge/none/s/python --author-route
  codex-gpt-5-6-sol-high-openai-sub`; DeepSeek/Pi OpenRouter was eligible and
  cross-family. First review FAIL: one blocker, the candidate read invented
  `supervisor_overhead_usd`, absent from attempt v2, so real ledgers could
  never compute `E`; one Decimal hardening note. Supervisor repair now
  cross-references attested `supervisor_route` ids to those routes' real
  schema-valid `cost.usd_marginal` observations and keeps the five-sample
  gate. Focused tests, Black, Ruff, and diff check pass.
- DeepSeek re-review PASS, 0 blockers; it ran adversarial identity, ineligible,
  missing-cost, nonfinite, and sample-gate probes. The last review event
  reported 32,098 tokens / `$0.000737284382`; intermediate OpenRouter review
  events were provider-reported but their aggregate was not retained by the
  attached no-session harness, so no invented aggregate is claimed. P2-3:
  5 author launches (1 GLM, 3 stalled Luna, 1 Sol), 2 reviews, about 34 min.

## P2-4 — Staffing block

- Implementation explain selected `pi-z-ai-glm-5-3-flash-openrouter`; excluded
  summary remained likely-exhausted 7, never-automatic 4, role-scope 1, and
  unpriced/pricing 1. The first GLM attempt completed within its ceiling and
  owned only `staffing/block.py` plus golden tests: 40 finalized Pi events,
  1,599,140 provider-reported tokens (1,439,232 cached) and `$0.037481105`.
- Supervisor read the complete files and identified fallback/independence
  trust boundaries. Independent review explain with the GLM author route
  selected DeepSeek/Pi. Review FAIL: one blocker (an independence-excluded
  route was called independent), three hardening findings (nonfinite facts,
  ineligible selection, available status without numeric E), and two future
  notes. Receipt: 34 finalized events, 1,924,042 tokens / `$0.048118502778`.
- Supervisor repair makes reviewer wording truthful, consumes the ladder's
  proof-first/marginal-price fallback argmin even when expected cost is
  unavailable, rejects ineligible explicit/argmin selection, converts
  nonfinite facts to explicit unknown/unavailable, and exposes eligibility
  plus exact reasons in text as well as JSON. The dependency-focused gate is
  136 passed; Black/Ruff/diff check clean.
- DeepSeek re-review PASS, zero blockers after 16 adversarial probes and 17
  focused tests: 23 finalized events, 406,035 tokens / `$0.011077041726`.
  P2-4: 1 author + 2 reviews, about 13 min. Cumulative newly metered P2-4
  spend `$0.096676649504` (running OpenRouter total `$0.118958094972`, including
  P2-3's retained GLM and last re-review receipts only where knowable).

## P2-5 — Staffing service and CLI

- Rule B split the packet once into P2-5a service and P2-5b CLI. Both author
  explains used the implementation class and selected the eligible first-rung
  `pi-z-ai-glm-5-3-flash-openrouter`; exclusions remained likely-exhausted 7,
  never-automatic 4, Gemini Pro role-scope 1, and unpriced/pricing 1.
- P2-5a GLM reached the 590 s ceiling with a partial candidate (23 finalized
  events, 583,424 provider-reported tokens / `$0.019297505`). Luna XHigh then
  reached its 590 s ceiling after producing source without an accepted test
  result (37 events, 5,647,369 subscription tokens / `$0.18599264` execution
  equivalent). Sol High completed the bounded service and tests (20 events,
  1,719,479 subscription tokens / `$1.830847` execution equivalent).
- Supervisor read the complete service and tests. The service composes the
  accepted eligibility, evidence, proof, ladder, and block modules; preserves
  independent review and fixed-point judge-cost rules; returns exact saved
  crews; and accepts bind only through the explicit human authorization path,
  with exactly one normal event append. A DeepSeek/Pi cross-family review
  PASSed with zero findings (58 events, 4,975,401 tokens / `$0.104628590268`).
- P2-5b GLM implemented only `doctor.py` and the focused CLI tests. It reached
  its 590 s ceiling while running the full suite, after its focused suite was
  18/18 (49 events, 1,459,334 tokens / `$0.03326191`). Supervisor read the
  complete diff and reran the combined gate: 44 focused passed, Black/Ruff
  clean, and 1,593 passed/1 skipped repository-wide.
- Combined independent review explain used `--author-route
  pi-z-ai-glm-5-3-flash-openrouter`; DeepSeek/Pi was eligible and
  cross-family. Its read-only review independently exercised both focused
  suites and returned PASS — zero findings (23 events, 2,013,806 tokens /
  `$0.054584700280`). P2-5: 4 author attempts + 2 reviews. Newly metered
  OpenRouter spend `$0.211772705548`; running knowable OpenRouter total
  `$0.330730800520`. Subscription execution equivalents remain separate.

## P2-8 — Four-harness staffing shims

- Implementation explain for `impl/deterministic/none/xs/python` selected
  eligible first-rung `pi-z-ai-glm-5-3-flash-openrouter`; exclusions retained
  the standard likely-exhausted 7, never-automatic 4, role-scope 1, and
  unpriced/pricing 1 summary. GLM completed within its ceiling, changing only
  the shim module/template and shim/parity tests: 33 finalized events,
  656,603 provider-reported tokens / `$0.016567535`.
- Supervisor read the complete diff and made two localized test-truth repairs:
  wrapped two owned-file lint violations and wired parity subprocesses to the
  scratch event/attempt paths they claimed to inspect. Related gate 40 passed;
  Black/Ruff clean. The one template now maps `/crew auto` to a task-derived,
  already-planned canonical role/class and `/crew NAME` to the exact saved
  crew; both print `staff` blocks, never dispatch, and only offer `run`.
- Review explain used `review/judge/none/xs/python` with `--author-route
  pi-z-ai-glm-5-3-flash-openrouter`; DeepSeek/Pi remained eligible and
  independent. Read-only review exercised the rendered instructions, actual
  CLI spellings, safe marker update/refusal path, and subprocess parity, then
  returned PASS — zero findings: 77 events, 3,244,168 tokens /
  `$0.078711216834`.
- D189-authorized live apply updated all four managed targets without force:
  Claude Code, Codex, OMP under the Chief project, and OpenCode. Immediate
  `shims diff` exited 0 with no drift. Full repository gate: 1,602 passed/1
  skipped. P2-8 newly metered spend `$0.095278751834`; running knowable
  OpenRouter total `$0.426009552354`.
