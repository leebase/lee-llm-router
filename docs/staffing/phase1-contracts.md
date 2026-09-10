# Phase 1 staffing contracts

Authority: D204–D209, with D209 controlling Phase 1 and D208 accepting the
Phase 0 baseline. These contracts resolve field placement and harness evidence
before implementation; they do not create routing policy.

## Attempt record v2 placement

`schema_version` is `2`. Existing route identity remains nested under `route`.
D209 ruling 2 is represented without duplicate top-level aliases:

- `packet_id`, `parent_attempt_id`, `escalation_reason`, `oracle_cmd`, and
  `verdict` are top-level attempt facts. `parent_attempt_id` and
  `escalation_reason` are nullable/optional for an initial attempt; an
  escalation requires both. `verdict` is `pass | fail | unverified`.
- `usage.basis` is `observed | provider_reported | calculated | unavailable`.
  A non-unavailable basis requires `usage.source`; unavailable requires
  `usage.unavailable_reason`. Token counters are nonnegative integers when
  reported and null/absent when unknown. Zero is evidence only when the source
  actually reports zero; it is never an unknown sentinel.
- `cost.basis` contains the applicable members of `list`, `marginal`, or the
  sole member `unavailable`. Known cost carries `cost.usd_list` and
  `cost.usd_marginal`; unavailable cost carries neither figure. Cost figures
  are JSON numbers derived from known tokens and selected dated P0-4 terms.
- New `selection` contains `basis` (`explicit | explain_cheapest_eligible`),
  `reason`, `explain_ref`, and an excluded-route summary. The summary preserves
  route ids and explain reasons, not a new selection judgment.
- Existing `provenance` remains the source-history object. Imports add
  `provenance.source: benchmark | agent-orch`; live router attempts use
  `provenance.source: router-run`. Imported agent-orch records may omit
  `class_record`/`class_key` only with `class_source: none`.

The v1 source-specific payloads remain provenance evidence, not competing
locations for v2 usage, cost, selection, or verdict. `verified_success` may be
true only for `verdict: pass` with the required route, usage, cost (when usage
permits it), oracle, duration, and provenance evidence.

## Usage evidence taxonomy

Use the narrowest truthful basis and these exact source strings:

| Harness | Basis when present | `usage.source` |
|---|---|---|
| Pi JSON events | `provider_reported` | `pi --mode json events` |
| Codex JSONL | `provider_reported` | `codex exec --json usage` |
| Claude Code result event | `provider_reported` | `claude -p --output-format stream-json result event` |
| agy print receipt | `provider_reported` | `agy -p usage line (agent-orch worker.py)` |
| OpenCode JSON event | `provider_reported` | `opencode run JSON usage event` |
| OpenCode worker artifact | `provider_reported` only when copied from provider output | `opencode worker-written usage.json from provider output` |
| OMP JSON event | `provider_reported` | `omp -p --mode json events` |
| Benchmark v6 CSV | `provider_reported` | `benchmark v6 CSV usage_*_tokens` |
| Agent-Orch accounted artifact | basis preserved from authoritative artifact, otherwise `provider_reported` | `agent-orch usage.json/accounting_status` |

Pi capability evidence checked before P1-4a: `pi --help` names output mode
`json`; benchmark `src/workbench/pi.py::_read_json_events` reads a JSON object or
JSON-lines, and `pi_stream_observation` sums complete, deduplicated assistant
`message_end.message.usage` components. P1-4a uses those assistant terminal
events and must not count repeated `agent_end` state. Until P1-4a is accepted,
supervisor Pi attempts record `usage.basis: unavailable` and
`usage.unavailable_reason: text mode`.

If a documented stream contains no authoritative usage, record `unavailable`
and the specific missing-event/output reason. No parser estimates tokens from
text, context length, cost, or elapsed time.

## Cost rule

Cost exists only when the tokens needed by the selected dated P0-4 price terms
are known. List cost applies list input/output/cache rates. Marginal cost applies
the same token quantities after the channel badge multiplier selected at the
attempt timestamp. Store both figures and `cost.basis: [list, marginal]`.
Unknown usage produces `cost.basis: [unavailable]` and no numeric cost. Harness
cost estimates and subscription fees are provenance notes, never attempt-token
cost substitutes. D207 remains the source rule where OpenRouter has no row.

## `run` command

`lee-llm-router run (--route ID | --role R --class C) --packet FILE
[--oracle CMD] [--workdir DIR] [--parent ATTEMPT_ID --escalation-reason R]
[--timeout S] [--json]` selects exactly one eligible route, dispatches its
provider `build_command` under the watchdog, captures authoritative harness
usage, runs the optional oracle, computes cost when possible, appends exactly
one validated v2 record, and prints a compact summary. Oracle exit 0 means
`pass`, nonzero means `fail`, and no oracle means `unverified`.

Explicit selection still evaluates eligibility; an excluded explicit route
exits 3 with its explain reason and writes no attempt. Role/class selection uses
the first eligible route in `catalog explain --json` marginal-price order and
records the explain reference, selection reason, and all excluded summaries.
`run` never escalates. A supervisor creates a linked attempt with both parent
and escalation reason.

## Ledger, rollup, and imports

The ledger is append-only JSONL at
`~/.local/state/lee-llm-router/attempts/<host>.jsonl`, with a test-only state
root environment override. Each validated record is encoded once and written
by one `O_APPEND` call; a short write raises `ShortWriteError` and no rewrite
path exists. `read_attempts()` validates every line as v2.

Rollup keys are `(route_id, class_key)` and values are attempts, verified pass,
pass counts by oracle type, token sums and medians, median wall clock,
`usage_known`, and `comparison_eligible` only at five or more attempts, matching
`performance.py` semantics. It creates no probabilities or ladders.

Imports are idempotent by deterministic attempt id. Benchmark rows carry
`provenance.source: benchmark`; agent-orch rows carry
`provenance.source: agent-orch`. Source usage is preserved exactly. An
`accounting_status: unaccounted` row is unavailable, never zero. Historical
agent-orch rows without class metadata use `class_source: none`.

## Live proof and review

After P1-5 and P1-6, run three small proofs: explain-selected Pi GLM via
OpenRouter, explicit Codex Sol Low, and Claude Code Sonnet only while
`anthropic-sub` is not `likely_exhausted`; otherwise use at most one eligible
agy Gemini Flash proof if headroom covers demand. Never bypass an exclusion.
Each proof must yield one record with provider-reported or observed tokens,
list and marginal cost figures, selection evidence, duration, oracle verdict,
and rollup visibility.

Every packet receives an independent router-selected review. Blocking findings
cite this contract or the packet requirement and a reproducer; hardening and
future concerns are logged without blocking acceptance. One same-route repair
is allowed after failed review; a second failure moves to the next eligible
implementation ladder rung with a linked escalation reason. The supervisor
also rejects out-of-scope changes or weakened invariants regardless of review.
