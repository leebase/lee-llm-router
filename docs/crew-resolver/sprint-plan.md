# Crew-Aware Worker Resolver — Sprint Plan

Project: `lee-llm-router` (home per Chief of Staff decision D187, 2026-09-07).
Author: Chief of Staff. Status: authorized to plan and execute; each sprint ends with an
independent review before the next starts.

Start here after a context reset. Read this file, then `AGENTS.md`, `WHERE_AM_I.md`, and
`context.md`. The router's Sprint 1–7 history in `sprint-plan.md` is the baseline; this plan is
additive and does not rewrite it.

## Outcome we are producing

From any of Codex, Claude Code, OMP, or OpenCode, Lee can name a crew and a role and get the
right worker chosen for him, using subscription headroom he did not have to look up, with
frontier escalation only when he says so and always on the record. A public page shows the crews
by name with the benchmark evidence behind each assignment. The ethos throughout is **start cheap,
move up only if needed.**

Not a rewrite. The router already has role-based YAML config, fallback chains, telemetry, a
doctor command, and `codex_cli`, `omp_cli`, and Pi providers. This adds a policy, a snapshot
reader, a CLI, four shims, and a page generator.

## Authorities and inputs (read, never fork)

| Input | Path | Owner |
|---|---|---|
| Crews (routing authority) | `~/projects/auto-orch/config/crews.yaml` | Auto-Orch |
| Ladder rules | `~/projects/chief-of-staff/decisions.md` D152–D158 | Lee |
| Availability | `~/projects/chief-of-staff/scripts/ai-subs.sh` → `AFTER_REPORT_JSON` | Chief of Staff |
| Benchmark evidence | `~/projects/ai-workforce-benchmark/exports/staffing-evidence-<date>.json` (when it exists) | Benchmark |
| Public page target | `~/projects/webroot/docs/pages/crews.html` | webroot (nginx-web) |

Rules that bind every sprint:
- `crews.yaml` is the only routing authority. The router loads it; nothing here edits it.
- `ai-subs` runs by cron at most hourly. The resolver reads the snapshot and never calls a
  provider CLI at decision time.
- Fable 5.1, Luna Max, and Opus 5 are never in an automatic fallback chain. Gemini 3.1 Pro is
  never chosen by the resolver.
- Every resolution writes one event line: crew, role, mode, chosen worker, reason, and any
  escalation authority. One writer per machine, append-only, Syncthing-safe.

## Modes

- **strict** — the crew's named worker for the stage; headroom is a veto. Used by governed
  Auto-Orch runs. Behaves exactly as today plus the check.
- **flex** — the stage's ordered eligible set; first worker with headroom wins. Used by
  interactive sessions. Default for the four harness shims.
- **bind** — explicit escalation to a worker outside the set, requires `--authorized-by` and a
  reason; written to the ledger. Never implicit.

## Sprints

Each sprint: one bounded packet, tests green (`pytest`), Black/Ruff clean, docs updated, an
independent review by a different model family, `context.md` and `result-review.md` updated.
Stop at the end of each sprint and report; do not roll into the next without a review verdict.

### Sprint 1 — Crews as a routing policy
- Add `crews.py`: load `crews.yaml` (path from `LEE_LLM_ROUTER_CREWS_FILE`, default to the
  Auto-Orch path) into typed `Crew`, `Stage`, `Worker` objects. Accept both today's single-worker
  stages and ordered lists (`envision: [codex_luna_max, antigravity_gemini38_flash_high]`) so
  flex mode has something to choose from without changing Auto-Orch's parser contract.
- Add `CrewRoutingPolicy` implementing `RoutingPolicy.choose(role, config)` for strict mode only.
- Map crew worker ids to router providers: `codex_cli`, `claude_code` (new thin CLI provider if
  absent), `omp_cli`, `opencode` (new), `antigravity` (new, via `agy`), Pi (existing).
  Providers only need `validate_config` and a dispatch command template in this sprint; no paid
  calls in tests.
- `doctor` gains a `--crews` check: every worker in every crew resolves to a known provider and
  model string.
- Done when: `lee-llm-router crews list` prints the 14 crews with stages, and `doctor --crews`
  passes against the live file.

### Sprint 2 — Availability snapshot and hourly cron
- Add `availability.py`: read `ai-subs` `AFTER_REPORT_JSON` from a snapshot file
  (`~/.local/state/lee-llm-router/availability/<host>.json`), normalize to per-channel headroom
  (`healthy | degraded | likely_exhausted | exhausted | unknown`, remaining fraction, observed
  time). Snapshots older than 90 minutes degrade to `unknown`, never to "healthy."
- Add `scripts/refresh_availability.sh` that runs `ai-subs.sh`, extracts the JSON block, writes
  the snapshot atomically. Provide the cron line; do not install it from a worker session
  (Lee or Chief installs; Linux owns schedules per D121).
- Channel mapping table: each crew worker → funding channel (openai-sub, anthropic-sub,
  gemini-sub, openrouter). Lives in `crews.py` config, not in `crews.yaml`.
- Done when: a fixture snapshot drives deterministic tests for every health state, and a real
  run of the refresh script produces a snapshot the reader accepts.

### Sprint 3 — `resolve` CLI, flex mode, bind, and the event ledger
- `lee-llm-router resolve --crew <name> --role <stage> [--mode strict|flex] [--json]`
  returns worker id, provider, model, effort, dispatch command, and a one-line reason.
  Exit 0 chosen; exit 2 nothing eligible (with the reason and the remedy); exit 3 config error.
- `--mode bind --worker <id> --authorized-by <who> --reason "<why>"` for escalation. Refuses
  workers on the never-automatic list unless bind is used. Refuses Gemini 3.1 Pro always.
- Event ledger: append one JSON line per resolution to
  `~/.local/state/lee-llm-router/events/<host>.jsonl`. Includes route identity so the benchmark
  and the LEPR seam can compare like with like later.
- Stall watchdog in the dispatch wrapper (`lee-llm-router dispatch ...`): flag after N minutes
  of no output *and* unchanged activity signature (bytes written, files touched); protect
  long-running legitimate tools up to a configurable ceiling. Unit-tested with a fake clock.
- Done when: strict, flex, bind, and each refusal path have tests; a `resolve` call on the live
  crews file and a real snapshot returns a sensible worker in under 50 ms.

### Sprint 4 — Four harness shims
- Claude Code: `/crew` slash command in `~/.claude/commands/` that calls `resolve` and either
  prints the recommendation or dispatches via the returned command.
- Codex: matching custom prompt in `~/.codex/prompts/`.
- OMP: `.omp/commands/crew.md` in chief-of-staff (and a reusable template in this repo).
- OpenCode: command or agent entry in `~/.config/opencode/`.
- All four are generated from one template by `lee-llm-router shims install --dry-run|--apply`
  so they can never drift from each other. Apply is Lee's call.
- Done when: each shim, invoked in its harness, produces the same resolution for the same
  crew/role as the CLI, and the event ledger shows four entries with distinct harness tags.

### Sprint 5 — Crew page and proposals
- `lee-llm-router crews page --out <path>`: static HTML projection of crews.yaml + availability
  snapshot + benchmark sidecar (if present). Each crew card: name, purpose, stage roster. Each
  worker: channel headroom pip with snapshot time; benchmark best score, cost-to-accept, run
  count, task count, and a "one task" label where that is true. No machinery names in the
  prose; run ids in an appendix.
- Proposals block: compare benchmark sidecar against current assignments; list candidate
  swaps that satisfy the proposal rule (same role, same task family, at least one accepted
  run, never crossing a tier or vendor-independence boundary). Proposals are text on the page.
  Applying one is a `crews.yaml` edit by Lee or Chief, never by the generator.
- Publish target `~/projects/webroot/docs/pages/crews.html`; add to the docs navigation the
  same way other pages are registered (check `~/projects/webroot/docs/index.html`). Hourly
  regeneration rides the same cron as the availability refresh.
- Done when: the page renders in light and dark, on desktop and at 390 px, from the live inputs;
  with the benchmark sidecar absent it still renders and says so.

### Sprint 6 — Hardening and adoption evidence
- Two weeks of daily use. Report: share of interactive dispatches resolved by the resolver,
  count of bind events and their reasons, count of headroom vetoes, any decision-time provider
  calls (must be zero), and any drift between shims (must be zero).
- Decide with evidence whether Auto-Orch should call `resolve --mode strict` instead of its own
  stage lookup. That is an Auto-Orch owner change; file it, do not patch it from here.
- Retire or archive `~/projects/labor-ladder` if Lee rules so (open item on D187).

## Staffing

Supervisor: Fable 5.1 at low effort (plans, reviews, never implements); raise to high only for the
Sprint 3 and Sprint 5 review gates. Worker: Opus 5 high for Sprints 1–3,
where the contract is being set and a wrong shape is expensive; Sonnet 5 high is the cheap first
rung for Sprints 4–5 with Opus 5 as escalation on a failed review. Independent reviewer: Sol Low
(different family). Same pattern as D174.

## Definition of done for the whole plan

Lee names a crew and a role in any harness and gets a worker without looking anything up.
The crew page shows the crews by name with evidence and headroom beside them. Every frontier
use has a ledger line with a name on it. The benchmark can compute cost-to-accept from the
event ledger's route identity.
