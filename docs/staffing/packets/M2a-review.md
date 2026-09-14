# Packet M2a-review — independent review of the uncommitted `ai-subs.sh` instance diff

Kind: review
Declared size: 2 files, approximately 40 changed/added lines
Owned paths: scripts/ai-subs.sh, scripts/ai_subs_instance_check.sh
Oracle: none (judge review; verdict is the deliverable)
Review: n/a (this is the review)

The owned paths above are registered for conflict-freedom only — this is a
read-only review; write nothing.

Runtime bound: 20 minutes.

Scope: the **uncommitted** working-tree diff in `/home/lee/projects/chief-of-staff`
limited to `scripts/ai-subs.sh` and `scripts/ai_subs_instance_check.sh` (run `git
diff -- scripts/ai-subs.sh` and `cat scripts/ai_subs_instance_check.sh` from that
repo root; the new file is untracked so `git diff` alone will not show it). Ignore
every other file — this repo has substantial unrelated dirty state from its own
independent autonomous chief-of-staff process (journal, fingertips, decisions
files); none of that is in scope. Packet under review:
`/home/lee/projects/lee-llm-router/docs/staffing/packets/M2a-ai-subs-instances.md`;
plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
(milestone M2, `chief-of-staff` half).

## Judge (ACCEPT/REJECT each, with what you reproduced)

1. `render_bucket()` gained an `instance=None` keyword parameter, and the dict it
   appends to `AFTER_REPORT` gained an `"instance": instance` key. Confirm no
   existing call site for OpenAI, Anthropic, or Gemini buckets was changed (they
   should all still call `render_bucket` with the same positional arguments as
   before, so their entries carry `"instance": null`).
2. The TOML/snapshot `[opencode]` rendering block now supports an
   `[opencode.instances.<id>]` sub-table shape: when present (a non-empty dict),
   it renders one `section()` + three `render_bucket()` calls per instance, each
   passing `instance=<id>`, iterated in sorted instance-id order. When absent, it
   falls back to treating the old flat `[opencode]` table as a single implicit
   instance named exactly `"opencode-go"` — confirm this literal string, not some
   other default.
3. The **live-fetch** branch (everything under `else:` after `# ── Fetch live
   from CLIs concurrently ──`, and `fetch_opencode()` itself) must be **byte-for-
   byte unchanged** — this packet was explicitly scoped to the TOML/snapshot path
   only. `git diff scripts/ai-subs.sh` should show no hunks touching those lines;
   confirm this directly in the diff.
4. `scripts/ai_subs_instance_check.sh` is executable (`ls -l` shows the `x` bit),
   runs with no network access and no real credential file, and actually proves
   what it claims: run it yourself (`./scripts/ai_subs_instance_check.sh` from
   the chief-of-staff repo root) and confirm it prints a success line and exits
   0. Read the script's assertions and confirm they match points 1–2 above (two
   distinct instance ids with three buckets each and differing `remaining_pct`,
   non-OpenCode entries carrying a null instance, and the single-instance
   backward-compat case).
5. Nothing outside the two owned files was modified by this packet's own work
   (the repo's pre-existing unrelated dirty state — journal/fingertips/decisions
   files with `git status --short` timestamps mostly *outside* this packet's
   ~13:24–13:48 local dispatch window on 2026-09-14 — is not this packet's
   doing; do not flag it, but do flag anything you find with content that
   actually references OpenCode Go, ai-subs, or instances outside the two owned
   files, since that would indicate real scope creep).

Anything that reads live credentials, queries a real OpenCode/Zen usage
endpoint, or changes the live-fetch path is contract-blocking and out of scope
for this packet (that is a later milestone, gated separately).

End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not edit,
commit, stash, or write anything.
