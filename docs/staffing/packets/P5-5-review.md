# Packet P5-5 — independent review of the Phase 5 first iteration

- Kind: `review`
- Class: `review/judge/none/m/python`
- Owned paths: none (read-only review; write nothing in any repo). Put your whole review in
  your final reply.
- Author route of everything under review: `agy-gemini-3-8-flash-high-gemini-sub` (Gemini
  3.8 Flash High), supervised by the Chief of Staff (Claude Fable 5.1), who also made the
  `d9d6809` print-timeout fix directly.

## Scope

lee-llm-router commits `c4c8263..ecc85ae` (`git log --oneline c4c8263..ecc85ae`) and
ai-workforce-benchmark commit `ad5c9b7` (`/home/lee/projects/ai-workforce-benchmark`).
Plan: `/home/lee/projects/chief-of-staff/docs/staffing-phase5-sprint-plan.md`; contracts:
`docs/staffing/phase5-contracts.md`; packets: `docs/staffing/packets/P5-*.md`.

## What to judge (answer each with ACCEPT / REJECT and the evidence you reproduced)

1. **Gate 1** — `lee-llm-router evidence report --month 2026-09`: per class and route it
   prints attempts, verified successes, cost per verified success at list and marginal (or
   UNAVAILABLE with a reason), tokens per verified success, escalations, reviewer fallbacks;
   per channel headroom against the terms file and the 10% reserve; route changes recommended
   by evidence (or an explained none); a source row per group. Run it. Check three numbers
   against the raw ledger (`~/.local/state/lee-llm-router/attempts/A8Max.jsonl`) by your own
   script, and say which.
2. **Gate 2** — `lee-llm-router evidence ladders --derive --output-dir /tmp/p5-review-ladders`:
   derived per class at n>=MINIMUM_SAMPLE_SIZE from the rollup, cheapest-first among
   verified-success attempts, zero-success routes excluded, insufficient-evidence classes
   say so verbatim, diff against both `ai-workforce-benchmark/config/escalation-ladders.json`
   (via model_aliases, unmapped never guessed) and `config/staffing/crews.yaml`
   `escalation_ladder`. Nothing hand-authored is edited. Verify one derived rung's n and
   cost against the ledger yourself.
3. **Gate 3** — `scripts/harvest_failed_packets.py`: production-only (router_run), 30-day,
   fail/capability_rejected, grouped by packet sha + class, packet text resolved by hashing
   `docs/staffing/packets`, skeletons under the benchmark's `packets/harvested/<id>/v1/`
   with the class block verbatim from the ledger and briefing byte-identical to the source
   packet. Two real packets committed additively; frozen packets untouched
   (`git show --stat ad5c9b7`); benchmark suite state honestly reported (one pre-existing
   OpenCode-version-pin error, unrelated).
4. **Gate 4** — `scripts/refresh_pricing_snapshot.sh`: captures OpenRouter and the Zen docs
   table at a pinned commit with sha256 sidecars, refuses to overwrite a date, never edits
   terms/channels, never installs cron; proposals appended to `docs/staffing/needs-lee.md`
   only. Verify `sha256sum -c` on the 2026-09-12 sidecars and that `terms.yaml` still
   points at the 2026-09-11/2026-09-09 series.
5. **Suite and hygiene** — `python3 -m pytest -q` in the router (report exact counts);
   black/ruff clean on every touched file; each commit touches only its packet's owned paths;
   no `decisions.md` written by any worker.
6. **The d9d6809 fix** — agy dispatch now carries `--print-timeout` = run ceiling. Is the
   default (watchdog DEFAULT_MAX_MINUTES) sound, and is the test adequate?

## Findings format

List contract-blocking findings first (each: file:line, what is wrong, how you reproduced
it), then non-blocking hardening notes. End with a single line `REVIEW VERDICT: ACCEPT` or
`REVIEW VERDICT: REJECT`. Do not defer to long-running commands: the full suite takes ~3
minutes, run it once in the foreground and wait for it. Do not edit, commit, stash, or
write any file.
