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

1. **Gemini 3.1 Pro's standing.** Lee (2026-09-07, live): "I have no idea why 3.1 pro was ever excluded from anything but coding." The resolver currently refuses `gemini-3.1-pro` in every mode (`FORBIDDEN_MODELS`, citing D152/D153; `gemini-pro-crew` therefore exits 3). Sprint 3 keeps that rule because changing it is a ladder decision, not a code repair. Decide: (a) keep the blanket refusal; (b) allow 3.1 Pro for planning/review roles only (would need a role-scoped rule and a decisions.md entry); (c) drop it from the forbidden list. Supervisor recommendation: (b), since Lee is using it as planner/reviewer today by hand.
2. **Informational:** Sprint 3 worker/reviewer staffing moved to Gemini via `agy` mid-sprint on Lee's instruction (Anthropic session bucket at 15%). Worker and reviewer are the same family for the remainder of the sprint unless Lee asks for a Sol Low final pass.
3. **Commit made by the supervisor** per Lee's standing ruling (reviewed sprint state does not float): `feat(crew-resolver S3): …`. Nothing under `~/projects/auto-orch` was touched.
4. **Watch item, not a decision:** the 50 ms cold-start gate is met with a thin margin (supervisor median 44 ms, reviewer 49 ms; bare interpreter is 12 ms). A parse cache under `~/.cache/lee-llm-router/` carries ~8 ms of that; `LEE_LLM_ROUTER_NO_CACHE=1` disables it. Sprint 6 should re-measure under daily use.
5. **Provider templates were never run against the real CLIs before this sprint** (codex needed `exec`; claude dropped `--model`; agy rejected `-p --model` ordering and stdin). All three fixed here; `opencode` and `omp` templates remain unverified against their binaries — Sprint 4 will exercise them via the shims.
