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
| P1-5a corrected-contract author | impl | fresh explain after Chief answer 1; governed first rung eligible | channel likely-exhausted 7; never-automatic 4; Gemini Pro role-scoped 1; unpriced/pricing unavailable 1 (overlap) | `pi-z-ai-glm-5-3-flash-openrouter` | 13:50 / 13:59 | 0 | `provider_reported`, `pi --mode json events`; input 426122, output 41204, cached 4102464, reasoning 15835, total 4569790; list/marginal $0.042260150 | implemented corrected always-role/class CLI and 21 fake-boundary tests; 1039 full passed/1 skipped; disclosed one accidental real Codex launch during test development; awaits review |
| P1-5a accidental child launch | impl subprocess, **not router staffed** (process violation; no explain snapshot) | worker test draft bypassed its intended fake Popen and invoked the explicit `codex-gpt-5-6-sol-low-openai-sub` harness directly | not evaluated; this was not an authorized dispatch | `codex-gpt-5-6-sol-low-openai-sub` | within corrected-contract author attempt | 0 | `provider_reported`, `codex exec --json usage`; input 56068, output 297 observed in captured test output; other token fields unavailable; marginal/list execution estimate $0.172659 from P0-4 terms | synthetic scratch prompt only; no extra repository diff or ledger state observed; final tests unconditionally fake Popen; logged as a defect caught before acceptance |
| P1-5a review | review | `catalog explain --role review --class review/judge/none/m/python --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; Go ladder rung excluded as likely-exhausted; governed DeepSeek fallback eligible/independent (Gemini eligible but reserved by D209 consumption identity for one live proof) | author independence; Go likely-exhausted; never-automatic and remaining policy exclusions | `pi-deepseek-deepseek-v4-flash-openrouter` | 14:00 / 14:08 | 0 | `provider_reported`, `pi --mode json events`; input 112923, output 25307, cached 1137152, reasoning 18811, total 1275382; list/marginal $0.013737108 | PASS; 0 blocking, 5 hardening, 3 future concerns; confirmed every final test path forces fake Popen |

P1-5a's old-contract attempts stopped at the two-round threshold. Chief answer
1 corrected the contract (role/class always required; route optional), making
the new attempt fresh. P1-5a accepted after that corrected-contract author and
one review, about 18 minutes (plus 20 minutes on the superseded design).
Supervisor read the full three-file diff and reproduced 21 focused and 1039
full passes (1 skip), Black/Ruff clean. Phase 1 OpenRouter metered total is
$0.222387757, plus unknown pre-P1-4a text-mode
attempts; the accidental OpenAI-subscription child has a separate $0.172659
list/marginal execution estimate and is not a metered API charge.

## P1-5b — Oracle, cost, and record

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-5b attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/none/m/python --json`; Gemini subscription appeared before GLM but is reserved by D209 for one agy live proof; first authority-eligible implementation rung GLM | Go likely-exhausted; never-automatic and policy exclusions; Gemini held for live-proof consumption identity | `pi-z-ai-glm-5-3-flash-openrouter` | 14:10 / 14:20 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 151132, output 29403, cached 1352448, reasoning unavailable, total 1532983; list/marginal $0.018685650 | partial `run.py` oracle/cost/record types and selection pricing; no CLI/tests; not accepted |
| P1-5b attempt 2 | impl | fresh same implementation explain; GLM remained first authority-eligible implementation rung | same exclusions/consumption reservation as attempt 1 | `pi-z-ai-glm-5-3-flash-openrouter` | 14:21 / 14:32 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 101444, output 2828, cached 268288, reasoning 2288, total 372560; list/marginal $0.008315300 | no additional file beyond partial `run.py`; CLI/tests still absent; not accepted |

P1-5b stopped at two-round non-convergence; partial code remains uncommitted
and unreviewed. Phase 1 OpenRouter metered total is $0.249388707 plus unknown
pre-P1-4a text-mode attempts.

## P1-6 — Rollup

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-6 attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; Gemini reserved for live proof, first authority-eligible rung GLM | Go likely-exhausted; never-automatic/policy exclusions; Gemini held for live proof | `pi-z-ai-glm-5-3-flash-openrouter` | 14:34 / 14:44 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 186752, output 5077, cached 1110592, reasoning 2493, total 1302421; list/marginal $0.015275650 | no file changes; broad research did not reach implementation; not accepted |
| P1-6 attempt 2 | impl | fresh same implementation explain; GLM remained first authority-eligible implementation rung | same exclusions/consumption reservation | `pi-z-ai-glm-5-3-flash-openrouter` | 14:45 / 14:55 | watchdog timeout; process group terminated | `provider_reported`, `pi --mode json events`; input 79257, output 8785, cached 217792, reasoning 6335, total 305834; list/marginal $0.008140525 | core-only packet still produced no file changes; not accepted |

P1-6 stopped at two-round non-convergence with no implementation. Phase 1
OpenRouter metered total is $0.272804882 plus unknown pre-P1-4a text-mode
attempts.

## P1-5b1 — Oracle and verdict split

Chief answer 2 resolved the P1-5b non-convergence as an implementation-ladder
escalation. Rule B was applied once, splitting oracle/verdict from cost/record.

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-5b1 escalated author | impl | `catalog explain --role impl --class impl/deterministic/none/m/python --json`; GLM parent had failed two rounds; D209 ladder's Luna XHigh rung eligible; `parent_attempt_id: p1-5b-attempt-2-20260910`; `escalation_reason: non_convergence` | Gemini eligible but reserved for one agy live proof; Go likely-exhausted; never-automatic/policy exclusions; cheaper GLM parent exhausted | `pi-gpt-5-6-luna-xhigh-openai-sub` | about 15:09 / 15:19 | supervisor watchdog termination at 590 seconds before final narrative | `provider_reported`, `pi --mode json events`; input 166912, output 28200, cached 3656192, reasoning 13042, total 3851304; subscription list/marginal execution estimate $0.050416800 | left scoped oracle/verdict implementation and fake tests; supervisor read full diff and independently observed 29 focused and 1047 full passes/1 skip; candidate sent to review as a tested handoff fact |
| P1-5b1 review 1 | review | `catalog explain --role review --class review/judge/none/m/python --author-route pi-gpt-5-6-luna-xhigh-openai-sub --json`; Go excluded; governed independent fallback eligible | Luna/GPT family excluded by independence; Go TOO FAST/likely-exhausted; never-automatic/policy exclusions; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | 15:19 / about 15:28 | 0 | `provider_reported`, `pi --mode json events`; input 237166, output 27724, cached 1219584, reasoning 22360, total 1484474; list/marginal $0.024579576 | FAIL; blocking: workdir deletion between worker completion and oracle launch raised uncaught `RunDispatchError`; timeout-default coupling and redundant `status` classified by supervisor as hardening/scope cleanup; other future concerns logged |
| P1-5b1 repair 1 | impl | fresh implementation explain; same Luna XHigh route remained eligible; one same-route repair with review finding quoted | same implementation exclusions/reservations as escalated author | `pi-gpt-5-6-luna-xhigh-openai-sub` | about 15:28 / about 15:38 | 0 | `provider_reported`, `pi --mode json events`; input 139060, output 19738, cached 2846208, reasoning unavailable, total 3005006; subscription list/marginal execution estimate $0.038623200 | caught governed post-worker oracle setup refusal, added fake race reproducer, removed redundant status, consolidated watchdog defaults; retained tested inherited oracle implementation and discarded only duplicate fields/constants; 31 focused, 1049 full passed/1 skip; Black/Ruff clean |
| P1-5b1 re-review | review | fresh same independent review explain; DeepSeek fallback eligible | same review exclusions/reservation | `pi-deepseek-deepseek-v4-flash-openrouter` | about 15:38 / about 15:42 | 0 | `provider_reported`, `pi --mode json events`; input 98558, output 15999, cached 764928, reasoning 11478, total 879485; list/marginal $0.010966704 | PASS; prior reproducer fixed; 0 blocking, 2 hardening, 3 future concerns |

P1-5b1 accepted after one split escalation, one review repair, and two reviews,
about 33 minutes wall clock. Supervisor read every owned diff, confirmed no
out-of-scope file change, reproduced 31 focused tests plus Black/Ruff clean,
and had independently completed the full suite before review. Non-blocking:
the CLI catch could be widened if future oracle errors gain other subclasses.
Future P1-5b2 must create the canonical top-level attempt-record placement.
Phase 1 OpenRouter metered total is $0.308351162 plus unknown pre-P1-4a
text-mode attempts; Luna subscription execution has a separate $0.089040000
list/marginal estimate and is not a metered API charge.

## P1-5b2 — Cost and final record split

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-5b2 Luna author | impl | fresh `catalog explain --role impl --class impl/deterministic/none/m/python --json`; P1-5b GLM parent had failed two rounds and split escalation remained on eligible Luna; `parent_attempt_id: p1-5b-attempt-2-20260910`; `escalation_reason: non_convergence` | Gemini reserved for live proof; Go likely-exhausted; never-automatic/policy exclusions; GLM parent exhausted | `pi-gpt-5-6-luna-xhigh-openai-sub` | about 15:44 / about 15:54 | supervisor watchdog termination at 590 seconds | `provider_reported`, `pi --mode json events`; input 258923, output 26661, cached 7826432, reasoning 16855, total 8112016; subscription list/marginal execution estimate $0.062833350 | scoped partial in run.py/doctor.py but no tests or completion; supervisor read full diff; retained as handoff only |
| P1-5b2 Sol escalation | impl | fresh implementation explain; final ladder rung `codex-gpt-5-6-sol-high-openai-sub` eligible; parent is timed Luna P1-5b2 attempt; `escalation_reason: platform_timeout` | Gemini reserved; Go likely-exhausted; never-automatic/policy exclusions; cheaper GLM and Luna packet attempts exhausted | `codex-gpt-5-6-sol-high-openai-sub` | about 15:55 / about 16:05 | supervisor watchdog termination while full suite ran, after author reported implementation and 37 focused passes | `usage.basis: unavailable`; `usage.source: codex exec --json usage` unavailable because watchdog preceded terminal `turn.completed` receipt; tokens unknown; no cost | kept only schema/API-proved handoff concepts; replaced path packet id with content hash, corrected route/provider/failure/duration facts, added 6 final-record tests; supervisor reproduced 37 focused and 1055 full passes/1 skip, Black/Ruff clean |
| P1-5b2 review | review | `catalog explain --role review --class review/judge/none/m/python --author-route codex-gpt-5-6-sol-high-openai-sub --json`; Go excluded, independent DeepSeek fallback eligible | Sol/GPT family excluded by independence; Go TOO FAST/likely-exhausted; never-automatic/policy exclusions; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | about 16:07 / about 16:11 | 0 | `provider_reported`, `pi --mode json events`; input 106715, output 14682, cached 1050624, reasoning 9104, total 1172021; list/marginal $0.011430636 | PASS; 0 blocking; 4 hardening, 3 future concerns |

P1-5b2 accepted after two author ladder attempts and one review, about 27
minutes wall clock. Supervisor read the complete three-file diff, confirmed
only owned files changed, and reproduced the full and focused gates. Hardening:
remove or wire the latent `attempt_id` injection and retire old intermediate
result helpers later. Future: explicit-null supervisor route and minimum
nonzero duration are consumer choices, not P1 blockers. Phase 1 OpenRouter
metered total is $0.319781798 plus unknown pre-P1-4a text-mode attempts; Luna
subscription execution totals a separate $0.151873350 list/marginal estimate.

## P1-6 — Rollup escalation and acceptance

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-6 Luna escalation | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; after two GLM no-change rounds, Luna XHigh eligible; `parent_attempt_id: p1-6-attempt-2-20260910`; `escalation_reason: non_convergence` | Gemini reserved; Go likely-exhausted; never-automatic/policy exclusions; GLM parent exhausted | `pi-gpt-5-6-luna-xhigh-openai-sub` | about 16:12 / about 16:22 | supervisor watchdog termination while full suite was near completion | `provider_reported`, `pi --mode json events`; input 252045, output 21779, cached 5564416, reasoning 12417, total 5838240; subscription list/marginal execution estimate $0.057407850 | complete scoped rollup, CLI, and 4 focused tests; no prior partial retained because GLM left none; supervisor read every file and reproduced 4 focused and 1059 full passes/1 skip, Black/Ruff clean |
| P1-6 review | review | `catalog explain --role review --class review/judge/none/s/python --author-route pi-gpt-5-6-luna-xhigh-openai-sub --json`; Go excluded; independent DeepSeek eligible | Luna/GPT family independence; Go TOO FAST/likely-exhausted; never-automatic/policy exclusions; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | about 16:24 / about 16:28 | 0 | `provider_reported`, `pi --mode json events`; input 97269, output 11773, cached 550656, reasoning 6309, total 659698; list/marginal $0.010148460 | PASS; 0 blocking; 5 hardening, 2 future concerns |

P1-6 accepted after three author attempts total (two GLM no-change timeouts and
one Luna implementation) and one review, about 54 minutes including the prior
rounds. Rollup now emits deterministic per-route/class counts, truthful token
and wall-clock aggregates, usage-known counts, and the exact five-attempt gate,
with no routing judgment. Hardening gaps are tests for mixed verdicts, imported
null keys, and CLI wiring; behavior itself was reviewed as correct. Phase 1
OpenRouter metered total is $0.329930258 plus unknown pre-P1-4a text-mode
attempts; Luna subscription execution totals a separate $0.209281200
list/marginal estimate.

## P1-4e — OpenCode usage capture

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-4e GLM | impl | explained `impl/deterministic/none/s/python`; first authority-available metered rung | Go likely-exhausted; proof subscriptions reserved; never-automatic/policy exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | about 17:14 / 17:24 | watchdog, zero output | provider-reported; input 57180, output 5780, cached 866816, reasoning 2713, total 929776; $0.005733500 | `platform_timeout`; no split useful |
| P1-4e Luna | impl | fresh explain; Luna eligible; parent GLM, `platform_timeout` | same, cheaper rung failed | `pi-gpt-5-6-luna-xhigh-openai-sub` | about 17:25 / 17:35 | watchdog | provider-reported; input 442752, output 24527, cached 3985408, reasoning 13814, total 4452687; subscription estimate $0.088487100 | large partial but no tests; handoff only |
| P1-4e Sol | impl | fresh explain; final Sol High rung eligible; parent Luna, `platform_timeout` | same; cheaper rungs exhausted | `codex-gpt-5-6-sol-high-openai-sub` | about 17:36 / 17:46 | watchdog during final checks | `usage.basis: unavailable`; terminal `turn.completed` absent after watchdog; no cost | retained only evidence-proved parser; 44 focused/63 relevant passed; supervisor full 1134 passed/1 skip, Black/Ruff clean |
| P1-4e review | review | explained with Sol author; Go excluded; independent DeepSeek eligible | GPT independence; Go likely-exhausted; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | about 17:48 / 17:51 | 0 | provider-reported; input 83013, output 12184, cached 713216, reasoning 7430, total 808413; $0.009020004 | PASS; 0 blocking; 4 hardening |

P1-4e accepted after three author ladder attempts and one review. OpenCode now
uses opt-in `--format json`, parses authoritative `step_finish` usage, and
accepts a worker artifact only with explicit provider-copy provenance. Phase 1
OpenRouter metered total is $0.382932125 plus unknown pre-P1-4a text-mode
attempts; Luna subscription execution totals $0.363461550 estimated.

## P1-4f — OMP usage capture

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-4f author | impl | explained `impl/deterministic/none/s/python`; first authority-available GLM | Go likely-exhausted; proof subscriptions reserved; policy exclusions | `pi-z-ai-glm-5-3-flash-openrouter` | about 17:53 / 17:59 | 0 | provider-reported; input 184306, output 21966, cached 1175040, reasoning 7677, total 1381312; $0.019314450 | governed JSON parser; 35 focused and supervisor 1169 full passed/1 skip; Black/Ruff clean |
| P1-4f review | review | explained with GLM author; Go excluded; independent DeepSeek eligible | author independence; Go likely-exhausted; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | about 18:00 / 18:03 | 0 | provider-reported; input 80745, output 10128, cached 671232, reasoning 5401, total 762105; $0.008484084 | PASS; 0 blocking, 4 hardening |

P1-4f accepted in one author attempt and one review. OMP's opt-in JSON mode
now captures assistant terminal usage while excluding repeated agent-end state;
missing evidence stays unavailable. Phase 1 OpenRouter metered total is
$0.410730659 plus unknown pre-P1-4a text-mode attempts.

## P1-7a — benchmark v6 import

| Attempt | Role | Explain / selection | Excluded summary | Route | Result | Usage / cost |
|---|---|---|---|---|---|---|
| P1-7 combined | impl | `impl/deterministic/none/m/python`; GLM first authority-available after reserving Gemini/Anthropic proofs | Go likely-exhausted; never-automatic/policy exclusions; proof subscriptions reserved | `pi-z-ai-glm-5-3-flash-openrouter` | 590s watchdog, zero repo output; Rule-B split by source | provider_reported: input 5,213, output 1,066, cached 76,032, reasoning 977, total 82,311; governed non-cached $0.000657475 |
| P1-7a split retry | impl | fresh explain; same governed selection | same | `pi-z-ai-glm-5-3-flash-openrouter` | 590s watchdog, zero repo output; `parent_attempt_id: P1-7-combined`; `escalation_reason: platform_timeout` | provider_reported: input 1,648, output 2,850, cached 92,224, reasoning 2,807, total 96,722; governed non-cached $0.000836100 |
| P1-7a Luna | impl | fresh explain; Luna Pi XHigh eligible | cheap route failed after required split | `pi-gpt-5-6-luna-xhigh-openai-sub` | 590s watchdog, zero repo output; `parent_attempt_id: P1-7a-split`; `escalation_reason: platform_timeout` | provider_reported: input 1,071, output 5,570, cached 219,648, reasoning 5,530, total 226,289; subscription execution estimate $0.005173650 |
| P1-7a Sol | impl | fresh explain; final Sol High rung eligible | lower ladder rungs failed | `codex-gpt-5-6-sol-high-openai-sub` | completed; real v6 scratch smoke 93 imported/9 unknown skipped; re-import 0; 1172 passed/1 skip; Black/Ruff clean | observed terminal Codex JSON: input 6,063,980, cached 5,920,768, output 28,355, reasoning 10,368; subscription execution estimate $0.854961000 |
| P1-7a review | review | fresh explain with Sol author; independent DeepSeek fallback selected | Go likely-exhausted; Gemini reserved; author independence | `pi-deepseek-deepseek-v4-flash-openrouter` | PASS; 0 blockers, 2 non-blocking hardening, 1 future concern | provider_reported: input 613, output 1,715, cached 87,040, reasoning 201, total 89,368; governed non-cached $0.000339612 |

P1-7a accepted after four author attempts and one review. Supervisor read the
complete owned diff and found no out-of-scope changes. Non-blocking findings:
malformed sidecar metadata can surface an internal `_RowError`; one usage-status
diagnostic is imprecise. Future concern: agent-orch CLI wiring must replace the
currently required benchmark option with a mutually exclusive source choice.

## P1-1 — Effective tier in explain

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-1 author | impl | `catalog explain --role impl --class impl/deterministic/none/xs/python --json`; Gemini and Anthropic eligible but reserved by D209 consumption identities for live proofs; first authority-available metered rung GLM | Go likely-exhausted; never-automatic/policy exclusions; Gemini/Anthropic held for their at-most-one live proofs | `pi-z-ai-glm-5-3-flash-openrouter` | about 16:29 / about 16:39 | supervisor watchdog termination while focused tests were starting | `provider_reported`, `pi --mode json events`; input 81228, output 7525, cached 507840, reasoning 3700, total 596593; list/marginal $0.007973350 | complete scoped effective-tier projection and tests; supervisor read diff and reproduced 43 focused/1062 full passes, 1 skip, but rejected Black failure before review |
| P1-1 formatting repair | impl | fresh same implementation explain; GLM remained first authority-available rung | same exclusions/reservations | `pi-z-ai-glm-5-3-flash-openrouter` | about 16:41 / 16:42 | 0 | `provider_reported`, `pi --mode json events`; input 4787, output 811, cached 17088, reasoning 118, total 22686; list/marginal $0.000561775 | formatting-only repair; 43 focused passed; Black/Ruff clean |
| P1-1 review | review | `catalog explain --role review --class review/judge/none/xs/python --author-route pi-z-ai-glm-5-3-flash-openrouter --json`; Go excluded; independent DeepSeek fallback eligible | author independence; Go TOO FAST/likely-exhausted; never-automatic/policy exclusions; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | about 16:42 / about 16:45 | 0 | `provider_reported`, `pi --mode json events`; input 85834, output 11492, cached 617216, reasoning 7772, total 714542; list/marginal $0.009140712 | PASS; 0 blocking, 0 hardening, 0 future concerns |

P1-1 accepted after two author attempts and one review, about 16 minutes wall
clock. Both gate dates expose each channel's effective fee, `kind` tier label,
and `effective_from` from the committed terms lookup; Anthropic/Gemini change
from the 2026-09-09 $100 terms to the 2026-09-30 $20 terms. Eligibility,
ordering, reasons, and text output remain unchanged. Phase 1 OpenRouter metered
total is $0.347606095 plus unknown pre-P1-4a text-mode attempts.

## P1-4d — agy usage capture

| Packet | Role | Explain / selection | Excluded summary | Route | Start / end | Exit | Usage / cost | Result |
|---|---|---|---|---|---|---:|---|---|
| P1-4d attempt 1 | impl | `catalog explain --role impl --class impl/deterministic/none/s/python --json`; Gemini/Anthropic reserved for live proof; first authority-available metered route GLM | Go likely-exhausted; never-automatic/policy exclusions; subscription proof reservations | `pi-z-ai-glm-5-3-flash-openrouter` | about 16:46 / about 16:56 | watchdog timeout, zero repository output | `provider_reported`, `pi --mode json events`; input 112314, output 14210, cached 1503424, reasoning 10992, total 1629948; list/marginal $0.011976050 | `escalation_reason: platform_timeout`; no source change; single-topic packet required no Rule-B split |
| P1-4d Luna escalation | impl | fresh implementation explain; Luna XHigh eligible; parent is P1-4d attempt 1; `escalation_reason: platform_timeout` | same exclusions/reservations; GLM failed to complete | `pi-gpt-5-6-luna-xhigh-openai-sub` | about 16:57 / about 17:07 | supervisor watchdog termination during final checks | `provider_reported`, `pi --mode json events`; input 276861, output 26849, cached 5927424, reasoning 14450, total 6231134; subscription list/marginal execution estimate $0.065693250 | implemented governed JSON receipt capture and 28 fake-boundary tests; supervisor read entire diff, reproduced 28 focused and 1090 full passes/1 skip, Black/Ruff clean |
| P1-4d review | review | `catalog explain --role review --class review/judge/none/s/python --author-route pi-gpt-5-6-luna-xhigh-openai-sub --json`; Go excluded; independent DeepSeek eligible | Luna/GPT independence; Go TOO FAST/likely-exhausted; never-automatic/policy exclusions; Gemini reserved | `pi-deepseek-deepseek-v4-flash-openrouter` | about 17:09 / about 17:12 | 0 | `provider_reported`, `pi --mode json events`; input 81351, output 10494, cached 949760, reasoning 4387, total 1041605; list/marginal $0.008596476 | PASS; 0 blocking; 3 hardening, 2 future concerns |

P1-4d accepted after two author attempts and one review, about 26 minutes.
agy JSON receipts now produce strict provider-reported usage with the exact
taxonomy source; missing receipts remain unavailable and contradictions fail
closed. Non-blocking: parser is deliberately stricter than the reference for
multiple receipts and reasoning consistency. P1-5's agy dispatch integration
remains a seam to verify before the optional Gemini live proof. Phase 1
OpenRouter metered total is $0.368178621 plus unknown pre-P1-4a text-mode
attempts; Luna subscription execution totals a separate $0.274974450
list/marginal estimate.
