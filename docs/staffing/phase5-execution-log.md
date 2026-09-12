# Staffing migration — Phase 5 (flywheel), first iteration: execution log and closing report

Supervisor: Chief of Staff (Claude Fable 5.1), directly — Lee's amendment on 2026-09-12 to the
Sonnet-headless handoff pattern. Workers: Gemini 3.8 Flash High via `agy`, every dispatch
through `lee-llm-router run` on `agy-gemini-3-8-flash-high-gemini-sub`, so Phase 5's own
attempts are rows in the ledger the Phase 5 report reads. Independent review: GPT 5.6 Sol
low via codex (`codex-gpt-5-6-sol-low-openai-sub`, `--author-route` gemini for independence).
Authority: D220 (Phase 5 authorized), D215/D216/D218 doctrine, D86/D87 for the in-lane
repairs. Plan: `chief-of-staff/docs/staffing-phase5-sprint-plan.md`. Baseline: router
`c4c8263` (D220 seal). Sessions wrote nothing to `decisions.md`.

## Packets

### P5-0 / P5-1 (inherited, committed before the server restart)
`9c50f5e` contracts; `45c9613` `evidence report --month`.

### P5-2 — `evidence ladders --derive` (`c42b68b`)
Inherited as an uncommitted, unreviewed diff (module, CLI hunk, two test files, 19 tests
green). Chief's review against the real ledger found four defects, fixed by P5-2b and P5-2c:
crews diff silently empty (`tuple` vs `list`); router roles (`impl/plan/review`) never joined
the benchmark's `coder/planner/code-review` — the inherited tests passed only by faking an
alias; insufficient evidence rendered as `DISAGREES`; rungs pooled across classes. The live
run then exposed a fifth: routes with `n>=5` and zero verified successes ranked as rungs
(a review class put a 0/9 route at position 0). Now excluded and listed with the reason.
Final: 27 tests, black/ruff clean.

### P5-3 — `scripts/harvest_failed_packets.py` (router `500daea`, benchmark `ad5c9b7`, `62e6494`)
`packet_id` on attempt records is `sha256:` of the packet text, not a path; the script
resolves it by hashing `--packet-dirs`. Live: three failed groups in the window, two resolved
(`h-7674f51c1a1d` impl/s/python, 4 attempts across 4 routes; `h-7905311822e1` impl/m/python,
3 attempts), one unresolved (its packet file no longer exists — reported, not paraphrased).
Both committed additively under `packets/harvested/` with `tests/test_harvested_packets.py`
validating the class block through `workbench.staffing._validated_class`. Benchmark suite
270 tests, one pre-existing error (OpenCode 1.18.30 installed vs pinned 1.18.26), unrelated.

### P5-4 — `scripts/refresh_pricing_snapshot.sh` (`e447b30`)
Captured `openrouter-20260912.json` and `opencode-zen-20260912.mdx` at Zen commit
`70b4ca8c…` with sha256 sidecars and a `.source` sidecar. `terms.yaml`/`channels.yaml`
unchanged (still the 2026-09-11 / 2026-09-09 series); the proposed repoint and the weekly
cron line (Monday 06:15) are appended to `needs-lee.md`, neither applied. 8 tests.

### P5-1b / P5-1c — report truthfulness (`ecc85ae`, `24a737a`, `0ff6b7f`, `1e8e241`)
P5-1b: an empty recommendation set is now printed and explained per reason with class counts;
every group carries `source_attempt_ids` and a `source:` line. P5-1c (review finding 1): the
reviewer-fallback column counted independence *enforcement* as a *fallback*; it now counts
only what the record proves (explicit basis: never; automatic with no independence exclusion:
never; anything else: undecidable with a cause-specific reason, never counted). The Chief's
own follow-up for the no-selection reason landed in two commits after a failed patch and a
stale test expectation; `24a737a`'s message overstated its content and `0ff6b7f` says so.

## In-lane platform repairs (Chief, D87)

- **agy print timeout** (`d9d6809`): every governed agy worker was cut at agy's default
  `--print-timeout 5m0s` regardless of `run --timeout`; P5-2b and the first P5-3 attempt died
  mid-work with "returning partial output". `build_dispatch_command` now passes the run
  ceiling (watchdog `DEFAULT_MAX_MINUTES` when none is given). Caveat on the ledger: every
  earlier agy attempt that needed more than five minutes was a harness cut-off, not a model
  failure.
- **Supervisor attestation** (filed in `needs-lee.md`, not changed): `--supervisor-route
  claude-claude-fable-5-1-high-anthropic-sub` is refused as `never_automatic`, so every
  Phase 5 attempt is `supervisor_route_unattested` → unverified in the rollup even with a
  passing oracle. Chief recommends exempting attestation from the selection policy; it is a
  contract change and needs a ruling.
- **agy empty turn**: one dispatch (P5-1b r1) returned SUCCESS after 1.5 s with an empty
  response and no edits; retried once, fine. Recorded as a worker-reliability data point.

## Gate (Chief's re-run, 2026-09-12 ~18:10Z)

1. `evidence report --month 2026-09`: 67 class/route groups with attempts, verified
   successes, cost per verified success at list and marginal or `UNAVAILABLE (<reason>)`,
   tokens per verified success, escalations, reviewer fallbacks (0 certain; undecidable
   counts with reasons); seven channels against the 10% reserve (`opencode-go` inside reserve
   at 8%); `Recommended route changes: none` with reasons (24 classes fewer than 2 routes
   with evidence, 15 fewer than 2 comparison-eligible, 1 fewer than 2 at pass_rate≥0.8);
   a source row per group. **Pass.**
2. `evidence ladders --derive`: `config/staffing/derived-ladders-2026-09-12.json`, 40
   classes, 2 derived at n≥5 (impl/s/python: DeepSeek V4 Flash 1/6 at $0.0046 per verified
   success, then Gemini Flash High 3/12 cost unknown; impl/xs/python: GLM 5.3 Flash 1/5 at
   $0.0003), 1 insufficient with its zero-success route excluded, 37 insufficient; diff
   against the six benchmark ladders and both crew ladders printed; nothing hand-authored
   edited. **Pass** — no hand ladder retired this iteration: no class has enough evidence.
3. Harvest: two real packets committed additively, benchmark validation green on them,
   frozen packets untouched. **Pass.**
4. Pricing refresh: script, snapshots, sha256 verified, proposals only. **Pass.**
5. Router suite `1798 passed, 1 skipped`; independent review of the whole diff:
   first pass REJECT (three findings), repairs, second pass **ACCEPT** with no blocking
   findings (finding 3, packet docs grouped with code in the Chief's early commits, accepted
   as non-blocking supervisor hygiene; separated from `24a737a` on). **Pass.**

Open questions the plan named: the OpenCode Go monthly fee and tier remain unknowable from
observed data (no receipt surface; `ai-subs` shows 8% weekly headroom only) — what would
resolve them is a billing statement or a Zen usage API with plan metadata.

## Economics

Eight Flash dispatches (two cut by the 5-minute defect, one empty turn, five productive) and
two Sol-low reviews (plus two review dispatches the Chief killed before they judged a wrong
tree). Metered spend: $0 — every dispatch on prepaid Gemini or OpenAI headroom (D215).
Gemini weekly headroom 87% at start; OpenCode Go excluded at 8% (D216).

## Non-blocking notes from review (carried, not fixed)

- agy `--print-timeout` equals the watchdog ceiling exactly; a small harness-side grace would
  make the watchdog the sure owner of termination.
- `evidence_report.py` and `ladder_derivation.py` each carry private benchmark
  de-duplication/materialization; one shared helper would prevent drift.
- `(none)`-route legacy groups dominate the report's top; a separate unrouted section would
  read better.
- Derived ladder "agrees" for crew `sol-low-glm-pi` rests on a one-rung overlap; the diff
  should state overlap size.

## Commits this lane (router, since `c4c8263`)
See `git log --oneline c4c8263..HEAD`. Benchmark: `ad5c9b7`, `62e6494`.
