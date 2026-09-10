# Phase 1 execution log

## 2026-09-10 — P1-0 contract pass

- Authority reconciled before dispatch: D204 five-phase approval; D205 class
  guardrail; D206 class metadata prohibition; D207 vendor list-price fallback;
  D208 accepted baseline; D209 Phase 1 execution, staffing, usage, autonomy,
  review, ceiling, and rulings 1–8. No missing authority found.
- Required Phase 0 history read fully: `execution-log.md`, `needs-lee.md`,
  `phase0-contracts.md`, and `chief-answers-1.md` through
  `chief-answers-15.md`. Baseline: 193 attempts, 17 timeouts, 43 reviewer
  fallbacks, 2 Luna escalations, and $0.001 reconciled plus unknown Pi spend.
- Pre-existing work preserved: modified `context.md`,
  `docs/crew-resolver/execution-log.md`, and `result-review.md`; untracked
  `docs/staffing/chief-answers-*.md`. Phase 1 commits must not absorb them.
- Pi JSON capability confirmed from `pi --help`: `--mode <mode>` accepts
  `text`, `json`, or `rpc`. Benchmark event shape confirmed from
  `src/workbench/pi.py`: `_read_json_events` accepts object/JSONL; terminal
  assistant `message_end` events carry `message.usage`; repeated `agent_end`
  state is not counted; complete input/output/cache components are summed.
- P1-0 code pass covered attempt-record v1/schema doc, P0-4 terms, event writer,
  dispatch/watchdog, provider command builders, benchmark Pi/capture, and
  agent-orch Codex/Claude/agy usage parsers. Field placement and exact source
  strings are fixed in `phase1-contracts.md`.

## Attempt ledger

Every subsequent row records packet, role, router explain reference/reason,
excluded summary, route, start/end, exit, usage truth, cost, result,
escalation, and attempts-to-acceptance. P1-0 is supervisor-only and has no
worker attempt.

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-2 attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/data-schema/s/yaml-config --json`; governed ladder first rung eligible, no exclusion reason | 8 excluded: never-automatic 4; OpenCode Go likely-exhausted 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (reasons overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 11:17:26 / 11:27:22 | watchdog timeout; process group terminated | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | partial schema + focused tests; 49 passed, 1 skipped; attempt doc not updated; not accepted |
| P1-2 attempt 2 | impl | same explain; same eligible governed first rung | same excluded summary as attempt 1 | `pi-z-ai-glm-5-3-flash-openrouter` | 11:29 / 11:31 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | completed attempt document; five fixtures equal schema examples; 49 passed, 1 skipped |
| P1-2 review 1 | review | `catalog explain --role review --class review/judge/data-schema/s/yaml-config --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; Go route excluded, governed fallback eligible and independent | author GLM excluded by independence; Go routes likely-exhausted; never-automatic routes excluded; other policy exclusions retained | `pi-deepseek-deepseek-v4-flash-openrouter` | 11:33 / 11:42 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | FAIL: claimed two blockers—unruled pricing snapshot fields and ignored fixtures; supervisor confirmed fields pre-exist in D208 schema, fixtures require force-add; optional-token success-gate issue sent with repair |
| P1-2 repair 1 | impl | same implementation explain; governed first rung remains eligible | same excluded summary as attempt 1 | `pi-z-ai-glm-5-3-flash-openrouter` | 11:45 / 11:48 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | repaired optional-token verified gate, source pairing, and P0 snapshot-field trace; focused 72 passed/1 skipped; full 886 passed/1 skipped |
| P1-2 re-review | review | same independent review explain/fallback | same review exclusions as review 1 | `pi-deepseek-deepseek-v4-flash-openrouter` | 11:50 / 11:54 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | PASS; 0 contract-blocking; 2 hardening, 2 future concerns |

P1-2 accepted after four implementation attempts (one timeout, one bounded
completion, one review repair) and two reviews, about 37 minutes wall clock.
Supervisor read the complete diff, confirmed only owned source/doc/test/fixture
files changed, ran 72 focused tests (1 skipped) and the full 886-test suite
(1 skipped), and force-added the five ignored fixture files. Non-blocking:
pricing snapshot citation fields do not enforce both-or-neither; documentation
says byte equality while tests enforce parsed JSON equality. Future: unpriced
known-token attempts cannot set `verified_success`; imports may carry an
oracle string and the importer must never invent one.

## P1-3 — Ledger writer

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-3 author | impl | `catalog explain --role impl --class impl/deterministic/persistence/s/python --json`; governed ladder first rung eligible | channel likely-exhausted 7; never-automatic 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (reasons overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 11:55 / 11:59 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | two owned files only; 31 focused and 917 full tests passed, 1 full-suite skip; Black/Ruff clean |
| P1-3 review | review | `catalog explain --role review --class review/judge/persistence/s/python --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; independent fallback eligible | author family independence; Go likely-exhausted; never-automatic and remaining policy exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 12:00 / 12:04 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | PASS; 0 blocking; 3 hardening, 1 future concern |

P1-3 accepted in one author attempt and one review, about nine minutes wall
clock. Supervisor read both complete new files and reproduced 31 focused
passes plus Black/Ruff clean. Non-blocking: raw write `OSError` is not wrapped,
invalid UTF-8 lacks ledger line diagnostics, and one test regex is loose.
Future: repository-relative schema discovery matches current project convention
but a wheel would need packaged schema data.

## P1-4a — Pi usage capture

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-4a attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; governed first rung eligible | channel likely-exhausted 7; never-automatic 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 12:06 / 12:16 | watchdog timeout; process group terminated | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | no output and no file changes; split under Rule B |
| P1-4a parser | impl | same explain and eligible first rung | same excluded summary | `pi-z-ai-glm-5-3-flash-openrouter` | 12:18 / 12:21 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | parser authored; 18 focused, 935 full passed/1 skipped; Black/Ruff clean |
| P1-4a mode | impl | same explain and eligible first rung | same excluded summary | `pi-z-ai-glm-5-3-flash-openrouter` | 12:22 / 12:23 | 0 | `usage.basis: unavailable`; `unavailable_reason: text mode`; tokens unknown; no cost | build command changed to JSON; 29 builder + 18 parser tests passed; Black/Ruff clean |
| P1-4a review 1 | review | `catalog explain --role review --class review/judge/none/s/python --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; independent fallback eligible | author family independence; Go likely-exhausted; never-automatic and remaining exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 12:24 / 12:27 | 0 | `provider_reported`, `pi --mode json events`; input 258023, output 23288, cached 1223702, reasoning 16308, total 1505013; list/marginal $0.025586316 from P0-4 terms | FAIL: parser flattened `assistant_messages`, `cache_write_tokens`, and `reasoning_reason` into strict v2 usage; 4 hardening, 2 future concerns |
| P1-4a repair 1 | impl | same implementation explain, first rung eligible | same implementation exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | 12:28 / 12:31 | 0 | `provider_reported`, `pi --mode json events`; input 120338, output 9682, cached 426240, reasoning 2030, total 556260; list/marginal $0.011445850 | returned schema-valid usage only; 24 parser + 94 builder tests passed; Black/Ruff clean |
| P1-4a re-review | review | same independent review explain/fallback | same review exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 12:32 / 12:34 | 0 | `provider_reported`, `pi --mode json events`; input 118836, output 10503, cached 410006, reasoning 6665, total 539345; list/marginal $0.011746728 | PASS; 0 blocking/hardening/future findings |

P1-4a accepted after four author attempts (one timeout, two bounded split
completions, one review repair) and two reviews, about 28 minutes wall clock.
Supervisor read the diff and reproduced 118 focused passes, full suite 941
passed/1 skipped, Black/Ruff clean. Phase 1 provider-reported metered total is
now $0.048778894 plus the explicitly unknown text-mode attempts before P1-4a.

## P1-4b — Codex usage capture

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-4b author | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; governed first rung eligible | channel likely-exhausted 7; never-automatic 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 12:36 / 12:43 | 0 | `provider_reported`, `pi --mode json events`; input 72128, output 32196, cached 1820352, reasoning 19744, total 1924676; list/marginal $0.013458600 | Codex JSONL parser + opt-in governed JSON flag; 39 focused, 980 full passed/1 skipped; Black/Ruff clean |
| P1-4b review | review | `catalog explain --role review --class review/judge/none/s/python --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; independent fallback eligible | author family independence; Go likely-exhausted; never-automatic and remaining exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 12:43 / 12:48 | 0 | `provider_reported`, `pi --mode json events`; input 105882, output 18904, cached 360192, reasoning 14484, total 484978; list/marginal $0.012069960 | PASS; 0 blocking; 3 hardening, 1 future concern |

P1-4b accepted in one author attempt and one review, about 12 minutes wall
clock. Supervisor inspected the complete diff and reproduced 80 focused/relevant
passes plus Black/Ruff clean. Non-blocking: untagged JSON objects are skipped,
one helper name is terse, and parser assembly is indirect. Future: P1-5 must
set `json_flag: --json` and call the standalone capture path deliberately.
Phase 1 provider-reported metered total is $0.074307454 plus unknown pre-P1-4a
text-mode attempts.

## P1-4c — Claude Code usage capture

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-4c attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; governed first rung eligible | channel likely-exhausted 7; never-automatic 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 13:13 / 13:23 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 27023, output 590, cached 9792, reasoning 193, total 37405; list/marginal $0.002174225 | stalled during broad evidence search; no owned-file change; not accepted |
| P1-4c attempt 2 | impl | fresh same implementation explain; governed first rung remained eligible | same implementation exclusions as attempt 1 | `pi-z-ai-glm-5-3-flash-openrouter` | 13:24 / 13:34 | 0 | `provider_reported`, `pi --mode json events`; input 143297, output 43182, cached 1236480, reasoning 24199, total 1422959; list/marginal $0.021542775 | Claude governed stream-json command + result usage parser; 36 focused, 1016 full passed/1 skipped reported; supervisor reproduced 184 relevant passes, Black/Ruff clean |
| P1-4c review 1 | review | `catalog explain --role review --class review/judge/none/s/python --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; author excluded for independence, Go excluded, governed fallback eligible | author independence; Go likely-exhausted; never-automatic and remaining policy exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 13:36 / 13:42 | 0 | `provider_reported`, `pi --mode json events`; input 120729, output 22154, cached 529152, reasoning 17892, total 672035; list/marginal $0.013863108 | reviewer PASS with 2 hardening/1 future; supervisor rejects: trailing malformed JSON is ignored after a valid result (violates malformed fail-closed), and present empty `modelUsage` incorrectly falls back despite absent-only fallback contract |
| P1-4c repair 1 | impl | fresh same implementation explain; governed first rung remained eligible | same implementation exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | 13:43 / 13:45 | 0 | `provider_reported`, `pi --mode json events`; input 57469, output 4786, cached 172800, reasoning 2236, total 235055; list/marginal $0.005506675 | both quoted reproducers now unavailable with specific reasons; 38 focused/1018 full passed, 1 skipped; supervisor reproduced 186 relevant, Black/Ruff clean |
| P1-4c re-review | review | same independent review explain; DeepSeek fallback eligible | same review exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 13:46 / 13:48 | 0 | `provider_reported`, `pi --mode json events`; input 44279, output 12107, cached 457216, reasoning 8171, total 513602; list/marginal $0.005753412 | PASS; both supervisor reproducers fixed; 0 blocking, 0 hardening, 0 future concerns |

P1-4c accepted after three author attempts (one no-change timeout, one bounded
implementation, one review repair) and two reviews, about 35 minutes wall
clock. Supervisor read the complete owned-file diff, reproduced 186 relevant
passes and the 1018-pass full suite (1 skip), and confirmed Black/Ruff clean.
Phase 1 provider-reported metered total is $0.166390499 plus unknown pre-P1-4a
text-mode attempts.

## P1-5a — Selection and dispatch foundation

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-5a attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/none/m/python --json`; governed first rung eligible | channel likely-exhausted 7; never-automatic 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 12:51 / 13:01 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 117453, output 48043, cached 2506368, reasoning 36787, total 2671864; list/marginal $0.020819725 | partial `staffing/run.py` only, truncated at `run_json_record`; no CLI or tests; not accepted |
| P1-5a attempt 2 | impl | fresh same implementation explain; governed first rung remained eligible | same implementation exclusions as attempt 1 | `pi-z-ai-glm-5-3-flash-openrouter` | 13:02 / 13:12 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 229175, output 20940, cached 2232576, reasoning 15434, total 2482691; list/marginal $0.022423125 | completed syntactically valid `run.py` and modified `doctor.py`, but added no tests; author spent material time on the explicit-route/class-context ambiguity; not accepted |

P1-5a stopped at the two-round non-convergence threshold. Its unaccepted
changes remain uncommitted pending the design question in `needs-lee.md`.
Phase 1 provider-reported metered total is $0.117550304 plus unknown pre-P1-4a
text-mode attempts.
