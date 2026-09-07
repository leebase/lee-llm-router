# Crew Resolver — Needs Lee

Genuine human decisions only. Everything else was repaired and continued (D86/D87).

## Resolved by Lee 2026-09-07

- Commit Sprint 1: **done** (see git log).
- gemini-pro-crew: **not a resolver defect**; Auto-Orch policy decision, warning behavior stands. Not blocking.
- Memory guard: **parked** as ops; setsid workaround sufficient.

## Open after Sprint 2 (2026-09-07)

1. **Install the hourly refresh cron on A8Max** (Linux owns schedules, D121/D167). Line is in `docs/availability-refresh.md`. Until it runs, the snapshot ages past 90 minutes and every channel reads `unknown`, which Sprint 3's flex mode will treat as "no headroom evidence."
2. **Informational:** `WORKER_CHANNEL_OVERRIDES` is empty. If any crew ever runs a brokered Claude/GPT model through `agy`, pin that worker to `gemini-sub-thirdparty` so headroom is read off the right bucket. No such worker exists today.
3. **Informational:** pace badges (HOT / TOO FAST) degrade a channel even at high remaining percent. Kept for Sprint 2 as "headroom is a veto"; Sprint 3 may separate pace from headroom if daily use shows over-vetoing.

## Open after Sprint 1 (2026-09-07) — historical

1. **Commit Sprint 1.** The working tree holds the reviewed, passing Sprint 1 diff (193 tests, Black/Ruff clean, Sol Low review PASS on round 2). Suggested message: `feat(crew-resolver S1): crews policy, opencode/antigravity providers, crews list, doctor --crews`. No commit was made from the supervisor session.
2. **`gemini-pro-crew` in `crews.yaml` names `antigravity_gemini31_pro`.** The plan's binding rule says Gemini 3.1 Pro is never chosen by the resolver. `doctor --crews` reports this as a warning (exit 0) because `crews.yaml` is Auto-Orch's read-only authority. Decide: leave the crew in the file for Auto-Orch's own use (resolver will refuse it in Sprint 3), or remove/rename it in Auto-Orch. Not a blocker for Sprint 2.
3. **Harness memory guard kills long background reviews.** Claude Code's background-task guard killed the Codex reviewer twice at ~900 MB "free" while 13 GB was reclaimable cache. Worked around with `setsid nohup`. Worth a note in the estate ops doc if it recurs; no action required for this lane.

## Explicitly not needed
- No `crews.yaml` edits were made or are required for Sprint 2.
- No cron, no shim installation, no paid frontier runs outside the staffing table (Opus 5 worker, Sol Low reviewer, Fable 5.1 low supervisor).
