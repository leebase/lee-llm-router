# Phase 4 execution log — Group A (router, agent-orch)

Session: Sonnet 5 headless supervisor, 2026-09-12/13. Authority: D215 rulings 4-6, D216.
Ceiling $10 metered for the phase. All router commands run in the foreground, one packet
group per session, per D215 ruling 6.

## P4-0 — contract pass

Read agent-orch `engine.py` retry/policy path, `failure_classification.py`, `worker.py`
usage receipts, `rate_table.py`; auto-orch `routing.py`/`routing_authority.py`; router
`terms.py`/`eligibility.py`. Wrote `docs/staffing/phase4-contracts.md` with exact seams and
five recorded contradictions/resolutions. No authority blocker. Committed with P4-1
(`0d8ca17`).

## P4-1 — `lee-llm-router price` command

- Packet: `docs/staffing/packets/P4-1.md`. Class `impl/deterministic/none/s/python`.
- Attempt 1 (`router-run-40746f16f6774804b6053d646e418a02`, `agy-gemini-3-8-flash-high-gemini-sub`,
  auto-selected): made **zero owned-path changes**; instead appended an unrelated,
  out-of-scope note to `docs/staffing/needs-lee.md` (reverted before any further work).
  `verdict: fail`, `oracle_not_passed`.
- Repair 1 (`docs/staffing/packets/P4-1-repair1.md`, same route): produced
  `src/lee_llm_router/staffing/price.py` and a `_run_price` handler in `doctor.py`, but no
  CLI subparser wiring and no tests. Oracle failed (pytest: files not found).
- Repair 2 (`docs/staffing/packets/P4-1-repair2.md`, same route, narrowed to exactly
  "wire the subparser + write two test files"): **zero incremental changes** — identical
  state to repair 1. `classify-failure` -> `oracle_failed`; `next-action` -> `supervisor_judgment`.
- Escalation 1 (same repair2 packet, `pi-z-ai-glm-5-3-flash-openrouter`): also zero
  incremental changes.
- Escalation 2 (same packet, `claude-claude-sonnet-5-high-anthropic-sub`): dispatch itself
  failed in 6s, "Claude stream-json output was empty" (`worker_dispatch_failed`) — the
  same empty-stream defect recorded in Phase 1's close-out, apparently recurring for a
  nested Claude Code dispatch from within a Claude Code supervisor session.
- Escalation 3 (same packet, `pi-deepseek-deepseek-v4-flash-openrouter`): dispatch hit the
  500s ceiling (`exit 124`, platform timeout) but **did** produce the subparser wiring and
  both test files before being killed, plus five stray scratch/debug files at the repo root
  (`_cleanup.py`, `_explore_*.py`, `_run_oracle.py`) outside owned paths.
- Supervisor cleanup (Rule D/Rule G — not a new dispatch): removed the five stray scratch
  files; fixed two trivial text-alignment typos in the worker's own test assertions
  (`"output_tokens:  50"` -> `"output_tokens: 50"`, `"cached_tokens:  0"` -> `"cached_tokens: 0"`
  — the worker's `render_text()` right-pads labels to a consistent column width and its own
  tests mis-copied the spacing). Full oracle then passed 36/36; full router suite
  1696 passed, 1 skipped; Black/Ruff clean after auto-formatting; live `price` invocation
  verified in both JSON and text mode against the real committed catalog.
- Independent review dispatched (`router-run-506c7a80da074ffaa5882cb72fd55c4a`,
  `agy-gemini-3-8-flash-high-gemini-sub`, author-route `pi-deepseek-deepseek-v4-flash-openrouter`
  excluded for independence): completed without touching any file, `verdict: unverified`
  (no machine-checkable oracle for a judge-role review — the reviewer's own verdict text is
  not retrievable from the ledger, a known gap already recorded in the Phase 3 close-out:
  "give reviewers test-execution tools; record judge verdicts as judge outcomes rather than
  `unverified`"). Per Rule D, the supervisor's own personally-run oracle, full-suite run, and
  diff read are the evidence of record for this packet, not the worker's summary.
- Committed `0d8ca17` (`feat(staffing P4): add price command`), bundling the P4-0 contract
  doc and every packet/review record.
- **Observation for a future phase (not a Phase 4 blocker):** three of six dispatch attempts
  for this one packet produced zero incremental progress on an unambiguous, narrow ask, and a
  fourth (Claude Sonnet) failed dispatch outright with empty stream-json. This consumed
  roughly 25 minutes of wall-clock and ~1.3M tokens across failed attempts before converging.
  Worth a future look at whether `run`'s impl-role dispatch has a systemic issue distinct
  from ordinary model capability variance.

## P4-2 — crew reorder + policy ordering rule

(pending)

## P4-2b — subscription reserve (D216)

(pending)

## P4-3 — `platform_timeout` failure class + verification tier

(pending)

## P4-4 — `cost_usd_marginal` per attempt

(pending)

## P4-5 — `ESCALATE` policy decision

(pending)
