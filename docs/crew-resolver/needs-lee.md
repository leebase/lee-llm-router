# Crew Resolver — Needs Lee

Genuine human decisions only. Everything else was repaired and continued (D86/D87).

## Resolved by Lee 2026-09-07

- Commit Sprint 1: **done** (see git log).
- gemini-pro-crew: **not a resolver defect**; Auto-Orch policy decision, warning behavior stands. Not blocking.
- Memory guard: **parked** as ops; setsid workaround sufficient.

## Open after Sprint 2 (2026-09-07)

1. ~~Install the hourly refresh cron on A8Max~~ **Done by Lee 2026-09-07** (`7 * * * *`, with explicit PATH so ai-subs can find codex/claude/agy). Supervisor verified by running the line under a cron-equivalent environment: exit 0, snapshot age 0 min.
2. **Informational:** `WORKER_CHANNEL_OVERRIDES` is empty. If any crew ever runs a brokered Claude/GPT model through `agy`, pin that worker to `gemini-sub-thirdparty` so headroom is read off the right bucket. No such worker exists today.
3. **Informational:** pace badges (HOT / TOO FAST) degrade a channel even at high remaining percent. Kept for Sprint 2 as "headroom is a veto"; Sprint 3 may separate pace from headroom if daily use shows over-vetoing.

## Open after Sprint 1 (2026-09-07) — historical

1. **Commit Sprint 1.** The working tree holds the reviewed, passing Sprint 1 diff (193 tests, Black/Ruff clean, Sol Low review PASS on round 2). Suggested message: `feat(crew-resolver S1): crews policy, opencode/antigravity providers, crews list, doctor --crews`. No commit was made from the supervisor session.
2. **`gemini-pro-crew` in `crews.yaml` names `antigravity_gemini31_pro`.** The plan's binding rule says Gemini 3.1 Pro is never chosen by the resolver. `doctor --crews` reports this as a warning (exit 0) because `crews.yaml` is Auto-Orch's read-only authority. Decide: leave the crew in the file for Auto-Orch's own use (resolver will refuse it in Sprint 3), or remove/rename it in Auto-Orch. Not a blocker for Sprint 2.
3. **Harness memory guard kills long background reviews.** Claude Code's background-task guard killed the Codex reviewer twice at ~900 MB "free" while 13 GB was reclaimable cache. Worked around with `setsid nohup`. Worth a note in the estate ops doc if it recurs; no action required for this lane.

## Explicitly not needed
- No `crews.yaml` edits were made or are required for Sprint 2.
- No cron, no shim installation, no paid frontier runs outside the staffing table (Opus 5 worker, Sol Low reviewer, Fable 5.1 low supervisor).

## Open after Sprint 3 (2026-09-07) — sprint closed, review PASS round 2

1. ~~**Gemini 3.1 Pro's standing.**~~ **Resolved by Lee 2026-09-07 → chief-of-staff D188:** role-scoped eligibility — planner/reviewer eligible (strict/flex/bind), coding/implementation never automatic and bind refused; skipped workers stay visible. Implementation is packet 1 of the next sprint. Original text follows for the record. — Lee (2026-09-07, live): "I have no idea why 3.1 pro was ever excluded from anything but coding." The resolver currently refuses `gemini-3.1-pro` in every mode (`FORBIDDEN_MODELS`, citing D152/D153; `gemini-pro-crew` therefore exits 3). Sprint 3 keeps that rule because changing it is a ladder decision, not a code repair. Decide: (a) keep the blanket refusal; (b) allow 3.1 Pro for planning/review roles only (would need a role-scoped rule and a decisions.md entry); (c) drop it from the forbidden list. Supervisor recommendation: (b), since Lee is using it as planner/reviewer today by hand.
2. **Informational:** Sprint 3 worker/reviewer staffing moved to Gemini via `agy` mid-sprint on Lee's instruction (Anthropic session bucket at 15%). Worker and reviewer are the same family for the remainder of the sprint unless Lee asks for a Sol Low final pass.
3. **Commit made by the supervisor** per Lee's standing ruling (reviewed sprint state does not float): `feat(crew-resolver S3): …`. Nothing under `~/projects/auto-orch` was touched.
4. **Watch item (Lee's wording, 2026-09-07): "Performance gate passes, but with low headroom; re-baseline after Sprint 4/6 before treating 50 ms as a stable SLO."** The gate is met with a thin margin (supervisor median 44 ms, reviewer 49 ms; bare interpreter is 12 ms). A parse cache under `~/.cache/lee-llm-router/` carries ~8 ms of that; `LEE_LLM_ROUTER_NO_CACHE=1` disables it. Sprint 6 should re-measure under daily use.
5. **Provider templates were never run against the real CLIs before this sprint** (codex needed `exec`; claude dropped `--model`; agy rejected `-p --model` ordering and stdin). All three fixed here; `opencode` and `omp` templates remain unverified against their binaries — Sprint 4 will exercise them via the shims.

## Open after Sprint 4 (2026-09-07) — sprint closed, review PASS round 1

1. ~~**D188 stage → role-class mapping — please confirm.**~~ **Approved unchanged by Lee 2026-09-07 (D189).** Supervisor's judgment, now in `src/lee_llm_router/crews.py::ROLE_CLASS_BY_ROLE` with a D188 comment: `author` → coding; `envision`, `ideate` → planning_review (planning); `reconsider`, `score` → planning_review (review); governed `primary` → coding; `reviewer`, `judge` → planning_review. Effect on the live file: `gemini-pro-crew` (3.1 Pro at envision/reconsider) now resolves and binds normally; `doctor --crews` shows 0 role-scoped warnings. If you want `ideate` treated as coding-adjacent, it is a one-line change to that constant.
2. ~~**`shims install --apply` is yours.**~~ **Approved and applied 2026-09-07 (D189).** `~/.local/bin/lee-llm-router` symlink added so the bare name resolves. Dry-run is verified; nothing under `~/.claude`, `~/.codex`, `~/.config/opencode`, or any `.omp/` was written. To install: `cd ~/projects/lee-llm-router && PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor shims install --apply --project ~/projects/chief-of-staff` (add `--dry-run` first to see the four files). Targets: `~/.claude/commands/crew.md`, `~/.codex/prompts/crew.md`, `~/projects/chief-of-staff/.omp/prompts/crew.md`, `~/.config/opencode/command/crew.md` (`opencode.jsonc` untouched). Note `lee-llm-router` must be on PATH for the shim's command line, or the shim body's `lee-llm-router` needs the venv path — the template uses the bare name.
3. ~~**Acceptance step after apply (yours):**~~ **Done 2026-09-07 — PASS** (execution-log “Sprint 4 live acceptance”): four harness tags, one route_id on the real ledger. Watch item: Codex `exec -s workspace-write` cannot append the ledger under `~/.local/state`; interactive Codex or `danger-full-access` can. Originally: run `/crew openai-economy envision` in Claude Code, `/crew …` (or `/prompts:crew`) in Codex, `/crew …` in OMP inside chief-of-staff, and `/crew …` in OpenCode; then `tail -4 ~/.local/state/lee-llm-router/events/A8Max.jsonl` should show four lines with harness `claude-code`, `codex`, `omp`, `opencode` and the same `route_id`. That is the plan's literal done condition; the sprint's verifiable form (a test running each rendered shim's exact line) already passes.
4. **Plan deviation, recorded:** the plan said OMP's shim lives at `.omp/commands/crew.md`. The OMP binary's template loader reads `.omp/prompts/*.md` (and `~/.omp/agent/prompts/`), so the target is `.omp/prompts/crew.md`. Verified from binary strings, not by an in-harness run — item 3 confirms it.
5. **Shim execution model:** all four shims instruct the harness's agent to run the `lee-llm-router resolve` line rather than using Claude Code's `!`-prefix pre-execution, so the four bodies are identical apart from the harness tag. If you want the Claude Code one deterministic (`!` inline), that is a per-harness template variant — a Sprint 6 hardening call, not done here.
6. **Perf watch item stands:** median 47 ms at close (44 at Sprint 3 close, 12 ms interpreter floor). Re-baseline in Sprint 6 as already recorded.
7. **Memory guard recurred:** Claude Code's low-memory guard killed the supervisor's wait loop once (3 GB "free", 14 GB available); the detached agy worker was unaffected. Same as the Sprint 1 note; no action.
8. **Sprint 5 staffing (Lee, 2026-09-07):** supervisor is Sol Low via Codex, worker is Gemini 3.8 Flash high via `agy`. Pre-prompt at `docs/crew-resolver/supervisor-preprompt-s5.md`. Reviewer is not named by Lee; the pre-prompt proposes Sonnet 5 high via `claude -p` (different family from both) with Opus 5 high for the S5 gate — confirm or override.
9. **Informational (2026-09-07):** OpenCode Go headroom is now in the snapshot (P33). It reads `degraded` today because its Monthly bucket is badged TOO FAST on pace (11% used, ~9% of the month elapsed) while 89% remains — the pace-vs-headroom calibration question from Sprint 2 item 3 is now live for a real channel. No action unless flex starts over-vetoing OpenCode workers in daily use; Sprint 6's report will show it.

## Open after Sprint 5 close (2026-09-08; Sonnet and Opus gates PASS)

1. **Publish the reviewed page and navigation entry.** Candidate generation is verified at `/tmp/lee-router-s5-latest-default.html`; Sprint 5 did not write webroot. The atomic writer creates mode 0600, so publish with a web-readable final mode: `lee-llm-router crews page --out /home/lee/projects/webroot/docs/pages/crews.html && chmod 0644 /home/lee/projects/webroot/docs/pages/crews.html`. Exact navigation entry following the current index convention: `<a href="pages/crews.html">Crews</a>` in `/home/lee/projects/webroot/docs/index.html`.
2. **Attach page regeneration to the existing hourly availability refresh.** Exact fail-closed command is documented in `docs/config.md`: run `scripts/refresh_availability.sh && PYTHONPATH=/home/lee/projects/lee-llm-router/src /home/lee/projects/lee-llm-router/.venv/bin/python -m lee_llm_router.doctor crews page --out /home/lee/projects/webroot/docs/pages/crews.html`. This must be installed only after publication is approved; Sprint 5 did not modify the already-live cron path.
3. **Benchmark sidecar assumption:** the implemented reader accepts the observed `benchmark.staffing-evidence/2` schema and defaults to the lexically latest `staffing-evidence-*.json`. The current 86-row sidecar parses cleanly. This is informational unless Benchmark changes its published schema.
4. **Informational — reviewer ledger contamination:** Sonnet round 4 accidentally ran one live resolution without `--no-event`, appending `mixed-flagship/author → codex_sol_high` at `2026-09-08T10:30:14Z` to `events/A8Max.jsonl`. The ledger is append-only, so the line is retained and explicitly excluded from adoption evidence. No Lee action is recommended unless you want a future event schema field for test/review traffic.
5. **Proposal authority is intentionally absent.** Sprint 5 refuses to propose swaps because neither the crew file nor benchmark schema authoritatively defines both model tier and vendor-independence boundaries. Decide the owning source before proposals can become non-empty; do not encode another local inference table in the router.

## Sprint 6 evidence-window decision (resolved by Lee 2026-09-08)

1. ~~**Wait for the committed two-week daily-use window or amend it.**~~ **Resolved: do not amend it.** Sprint 6 remains `⏳ BLOCKED / EVIDENCE ACCUMULATING`; engineering health is GREEN and the adoption conclusion is NOT YET MEASURABLE. Earliest meaningful resumption is approximately 2026-09-22. Normal workflow should generate evidence naturally; do not manufacture `/crew` usage. If ordinary work largely bypasses the resolver, that sparse usage is itself valid adoption evidence. No Auto-Orch adoption recommendation should be filed before the genuine window is assessed.

## 2026-09-09 — Sprint 6 window closed as superseded; work continues as the staffing migration

Lee approved the staffing architecture recommendation (chief-of-staff `decisions.md` D204,
D205). The Sprint 6 adoption window (D196) is closed as superseded: the resolver-as-lookup is
not the product, so its adoption rate is not the question. The crew resolver's availability
reader, event ledger, shims, watchdog, providers, and `crews.py` loader survive into the
staffing service; `resolver.py`'s selection logic, `dispatch.py` as the loop, and the old
LLMRouter layer are scheduled for removal in Phase 2. Item 5 above ("proposal authority is
intentionally absent") is resolved by D204 item 1: for `auto` mode, evidence plus policy is the
routing authority; named crews stay human. Plan:
`~/projects/chief-of-staff/docs/staffing-migration-sprint-plan.md`; Phase 0 handoff:
`~/projects/chief-of-staff/docs/staffing-phase0-supervisor-handoff.md`; Phase 0 ledgers live in
`docs/staffing/` in this repo.
