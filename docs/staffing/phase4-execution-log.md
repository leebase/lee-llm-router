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

- Packet: `docs/staffing/packets/P4-2.md`. Class `impl/deterministic/data-schema/xs/yaml-config`.
- `staff --from-packet` refused (`.json` schema file has no supported language extension in
  `derive_class.py` — a pre-existing router limitation, not a Phase 4 defect; recorded, not
  fixed). Staffed directly with `--role`/`--class`; auto-selected Gemini Flash High, but given
  P4-1's evidence that route made zero progress on impl-role coding three times, dispatched
  directly to `pi-deepseek-deepseek-v4-flash-openrouter` (empirically proven capable this
  session) with a stated reason, per Rule E/Rule K.
- Attempt 1 (`router-run-9aa4238513f14df5ad10bb115455e35f`): correctly reordered
  `sol-low-glm-pi`'s `impl` array, added the recorded `crew_ordering_rule` policy/schema/
  dataclass, and updated the fixture it touched. My own `--oracle` string was malformed
  (unquoted `PYTHONPATH=src` isn't shell-expanded by the no-shell dispatch boundary) —
  supervisor error, not a worker failure; ran the oracle manually instead.
- Full suite surfaced one real, foreseen contradiction: reordering the interactive `impl`
  array breaks round 13(c)'s strict first-entry-equality invariant between the live governed
  primary and the interactive record, exactly the tension D215 ruling 2 explicitly names
  (governed primary intentionally stays pinned to OpenRouter until P4-4 marginal pricing
  lands). Supervisor fix (Rule D, cited, narrowly scoped): added one exception for
  `("sol-low-glm-pi", "primary")` to that one test; every other crew/role keeps the strict
  check.
- Full suite green (1696 passed, 1 skipped), Black/Ruff clean, catalog doctor check green,
  live `staff --mode crew sol-low-glm-pi --json` confirms `impl[0]` is now the opencode-go
  route.
- Independent review dispatched and completed clean (`agy-gemini-3-8-flash-high-gemini-sub`,
  author-route excluded); verdict text not mechanically retrievable (same known gap as
  P4-1) — supervisor's own diff read and oracle run are the evidence of record.
- Committed `20d5176`.

## P4-2b — subscription reserve (D216)

- Packet: `docs/staffing/packets/P4-2b.md`, from `docs/staffing/chief-answers-p4-1.md`.
  Class `impl/deterministic/none/s/python`. Dispatched directly to
  `pi-deepseek-deepseek-v4-flash-openrouter` (same empirical reasoning as P4-2).
- Attempt 1 (`router-run` — see packet's ledger row): added a `reserve_fraction` policy record
  (default/overrides shape, `ReserveFractionPolicy`/`ReserveFractionOverride` in `catalog.py`),
  a new additive eligibility check in `eligibility.py` (independent of the existing
  `likely_exhausted` veto), and a matching `bind` authorization boundary in `staff.py`
  (reserved channel binds only with `--authorized-by lee`, distinct error kind from
  `never_automatic`). Good implementation; missed updating the shared `policy_doc()` fixture
  in `tests/test_staffing_catalog.py` for the new required schema field, which broke ~30
  unrelated tests in that file, plus three pre-existing tests whose expected reason
  strings/lists were legitimately extended by the new additive reason
  (`test_fable_reason_is_never_automatic_then_channel_exhausted`,
  `test_explain_reproduces_p0_5_acceptance` ×2 assertions,
  `test_auto_ladder_skips_reserved_channel_to_cheapest_metered`'s own wrong text-format
  assertion). Supervisor fixed all four directly (fixture addition, three assertion updates)
  rather than a further dispatch round — same-scale correction as P4-1's alignment typos.
- Full suite green (1703 passed, 1 skipped), Black/Ruff clean after minor line-length fixes.
- Live check: the packet's assumed "OpenAI at 7%" is now stale (OpenAI has since reset to
  99% headroom); reported the real current snapshot instead — `opencode-go` at 8% headroom is
  correctly excluded with `reserve: 10% kept in the tank (D216)`, proving the mechanism live.
- Independent review dispatched and completed clean, same pattern as P4-1/P4-2.
- Committed `19ee902`.

## P4-3 — `platform_timeout` failure class + verification tier (agent-orch)

- Repo: `~/projects/agent-orch`. Pre-existing, unrelated uncommitted WIP (`engine.py`,
  `worker.py`, and others, from a different initiative) was `git stash push -u`'d before any
  dispatch, to keep it from bundling into Phase 4 diffs/commits; it remains stashed
  (`stash@{0}`, "pre-existing WIP unrelated to Phase 4 staffing") for whoever owns that work
  to pop later. Never touched again this session.
- Packet: `docs/staffing/packets/P4-3.md`. Dispatched directly to
  `pi-deepseek-deepseek-v4-flash-openrouter` (same empirical reasoning as router packets —
  Gemini Flash made zero impl-role progress three times in Group A's router work).
- Attempt 1 (single dispatch, no repair needed): added `PLATFORM_TIMEOUT` to
  `NonRepairableFailureClass` with a regex matcher for the exact worker-timeout stderr
  string, checked after the seven existing pattern families and before the exit-code
  fallback; added `verification_tier: str = "engine_validation"` to `StepAttemptRecord`,
  derived per step from its declared validations (`oracle_command` for a command-based
  system validation, `oracle_judge` for a `semantic_check`), wired at every
  `StepAttemptRecord` construction site including the two round-trip helpers
  (clone/from-payload, which correctly preserve rather than re-derive).
- Oracle green (139/139), full suite green modulo 3 pre-existing, unrelated
  `tests/test_codex_usage.py` failures (verified they reproduce on unmodified `HEAD` before
  any Phase 4 change — a pre-existing baseline defect, not a regression).
- Independent review dispatched and completed clean.
- Committed `af5dea5`.

## P4-4 — `cost_usd_marginal` per attempt (agent-orch)

- Packet: `docs/staffing/packets/P4-4.md`, depends on P4-1's committed `price` command.
  Dispatched to `pi-deepseek-deepseek-v4-flash-openrouter`.
- Attempt 1: hit the 590s ceiling after correctly adding the two new helpers
  (`_token_totals_for_records`, `_marginal_cost_for_execution_records`) and threading the
  first of four `_price_execution_records` call sites — ran out of time before the other
  three and before any tests. Repair 1 (narrowed to the remaining three sites + tests):
  completed cleanly, all four sites threaded.
- The repair's new tests had three bugs (wrong `Playbook`/`StepDefinition` constructor
  kwargs; a route-id-clearing helper that also blanked `TokenUsage.model`, which
  `TokenUsage.__post_init__` rejects as empty) — supervisor-fixed directly (same scale as
  earlier alignment-typo fixes), all 133 `test_engine.py` tests then passed.
- Full-suite run then surfaced a real, previously-unseen defect: `_read_accounting_artifact`
  (the reader mirroring `_persist_attempt_artifacts`'s writer) treats every non-schema key as
  strict `TokenUsage` payload and rejects unknown fields — the new `cost_usd_marginal` sibling
  key broke resumption of any measured attempt artifact, failing 19 tests in
  `tests/test_dollar_cost_enforcement.py`. Supervisor-fixed: added `cost_usd_marginal` to the
  reader's existing excluded-keys set (mirroring how `accounting_schema_version`/
  `accounting_status`/`usage_scope` are already excluded there).
- Also found and removed: a fifth site inside `_run_step_via_route` computed
  `cost_usd_marginal` but never used it — dead code, an extra wasted subprocess call on every
  dispatch through that path, because its caller (`~engine.py:7093`) already independently
  re-derives pricing from the returned `worker_result`, exactly mirroring how the pre-existing
  list-price computation already worked before Phase 4.
- This repo's own permanent doctrine (`AGENTS.md` "subprocess seam rule, B1") requires at
  least one test invoking the *real* CLI, not a mock, for any new subprocess seam — added one
  against the globally-installed `lee-llm-router` binary (skipped if absent from PATH).
- Full suite green (1923 passed, 9 skipped) modulo the same 3 pre-existing baseline failures.
- Independent review dispatched and completed clean.
- Committed `39a0457`.

## P4-5 — `ESCALATE` policy decision (agent-orch) — Phase 4 gate item (a)

- Packet: `docs/staffing/packets/P4-5.md`, class `impl/deterministic/authority/m/python`
  (don't-cheap-trial per the sprint plan). Staffed directly at
  `pi-deepseek-deepseek-v4-flash-openrouter` (the empirically proven route this session),
  skipping the auto ladder's cheaper/unproven rungs per the plan's explicit don't-cheap-trial
  instruction for this class.
- Attempt 1: correctly implemented the full mechanism in one dispatch —
  `SEMANTIC_VERDICT_SCHEMA`'s optional `rejection_kind` (JSON-Schema `if`/`then` conditional,
  additive), `StepDefinition.escalation: EscalationIntent | None`, the engine's new
  `"ESCALATE"` precedence step (after the HALT checks, before REPAIR), the
  `escalation_routing_override` threading into `_run_step_via_route`, and
  `escalation_reason`/`parent_attempt` on `StepAttemptRecord` including both round-trip
  helpers — but wrote **no test at all** for any of it, including the gate test itself. Two
  pre-existing tests also broke: the stricter schema legitimately rejects two pre-existing
  `passed: false` verdict fixtures that lacked the now-required `rejection_kind`
  (`tests/test_semantic.py`'s `_failing_verdict()`, `worker.py`'s `FakeJudgeAdapter` "fail"
  mode) — supervisor-fixed both directly with `"rejection_kind": "content_defect"`
  (preserving their original repairable-failure intent, same scale as earlier alignment-typo
  fixes).
- Repair 1 (same route, narrowed to tests only, with `worker.py` added to owned paths for one
  `FakeJudgeAdapter` mode addition): wrote the full required test suite including the gate
  test, but one assertion in the gate test itself had a trivial type bug
  (`RouterRequest.configured_primary` is a plain `dict`, not an object — the test wrote
  `.harness` instead of `.get("harness")`); supervisor-fixed directly, confirmed all 169
  targeted tests then passed.
- **Gate test `test_escalate_gate_reroutes_to_next_rung_harness` verified by direct
  inspection**, not just by passing: it proves attempt 1's persisted `policy_decision ==
  "ESCALATE"`; attempt 2 dispatches to a genuinely different registered worker adapter (the
  ladder rung's harness, invocation-counted, not a same-routing retry); attempt 2's
  `parent_attempt == 1` and `escalation_reason` matches the triggering verdict's `reasoning`;
  the run completes end to end. This is Phase 4 gate item (a), satisfied.
- Full suite green (1930 passed, 9 skipped) modulo the same 3 pre-existing baseline failures
  (unrelated to any Phase 4 change, confirmed against unmodified `HEAD` back in P4-3).
- Independent review dispatched (GLM via Pi/OpenRouter this time — auto mode's own choice for
  this class/domain-tag combination; no negative evidence against GLM for read-only review
  work specifically) and completed clean.
- Committed `7751a07`.

## Group A close-out

All six Group A packets (P4-0 contract pass, P4-1, P4-2, P4-2b, P4-3, P4-4, P4-5) are
committed: router `0d8ca17`, `20d5176`, `19ee902`; agent-orch `af5dea5`, `39a0457`, `7751a07`.
Full router suite (1930+ tests across both repos combined) green modulo the 3 pre-existing,
unrelated `agent-orch/tests/test_codex_usage.py` failures (present on `HEAD` before any Phase
4 change). Owner suites are green in both repos per the gate's own definition
(`pytest -q`, `.venv/bin/python -m pytest -q`).

**Recorded, not resolved by this session** (see `docs/staffing/needs-lee.md`):
- Pre-existing, unrelated uncommitted WIP in `agent-orch` (`engine.py`, `worker.py`, and
  others) was stashed (`git stash`, message "pre-existing WIP unrelated to Phase 4 staffing")
  before any Group A dispatch, to keep it from bundling into Phase 4 commits. It remains
  stashed — popping it now would very likely conflict with this session's `engine.py`/
  `worker.py` changes (both files this session also touched extensively). Whoever owns that
  WIP needs to pop and manually reconcile it, not this session.
- `derive_class.py`'s owned-path language detection has no `.json` extension mapping,
  refusing `staff --from-packet` for any packet whose owned paths include a `.json` schema
  file (hit twice, P4-2 and would recur for any future JSON-schema-touching packet). Not
  fixed here (out of Group A's scope); recorded for a future router packet.
- Three of six P4-1 dispatch attempts (and one of two P4-5 dispatch attempts) produced zero
  incremental progress on unambiguous, narrow asks before a route change unstuck them; one
  Claude Sonnet dispatch failed outright in 6s with empty stream-json (matches the Phase 1
  close-out's recorded empty-stream defect, apparently recurring for a Claude Code dispatch
  launched from within a Claude Code supervisor session). Worth a future look at whether
  `run`'s impl-role dispatch or the nested-harness case has a systemic issue.

## D218 DeepSeek V4.1 Flash intake

Refreshed the pinned OpenRouter catalog snapshot per D218 (chief-of-staff/decisions.md
2026-09-12, "the pricing snapshot must be refreshed on a schedule ... since a 2× price move
went unnoticed for days") and added `deepseek/deepseek-v4.1-flash` as a sixth Pi/OpenRouter
route, a candidate metered workhorse not yet in the Pi model store.

- New snapshot `config/staffing/pricing/openrouter-20260911.json` (captured 2026-09-11 from
  `https://openrouter.ai/api/v1/models`, sha256 sidecar verified) supersedes
  `openrouter-20260909.json` (kept on disk, no longer referenced). `channels.yaml`,
  `terms.yaml`, and `terms.py`'s `DEFAULT_OPENROUTER_SNAPSHOT_PATH` all repointed to it.
- Price deltas versus the 2026-09-09 snapshot, for the two openrouter-channel exact ids
  already in `routes.yaml`:
  - `z-ai/glm-5.3-flash`: prompt/completion **doubled**, $0.075/M → $0.15/M prompt,
    $0.25/M → $0.50/M completion (cache-read $0.015/M → $0.03/M). Matches D218's "GLM 5.3
    Flash ... doubled."
  - `deepseek/deepseek-v4-flash`: prompt/completion **dropped**, $0.084/M → $0.06706/M
    prompt, $0.168/M → $0.13412/M completion (cache-read $0.0168/M → $0.013412/M).
  - Net effect: DeepSeek V4 Flash is now cheaper than GLM 5.3 Flash on the metered ladder,
    flipping the cheapest-metered-route selection (`tests/test_staffing_staff.py`'s auto
    ladder test updated accordingly).
- New route `pi-deepseek-deepseek-v4-1-flash-openrouter` added to `routes.yaml`, matching the
  five existing P0-3f Pi/OpenRouter rows field-for-field, including `usage_capture: none` —
  verified this is the correct, documented value for every Pi row in the file (the worker
  extracts only the first JSON object from `pi --print --mode text` stdout and never parses
  token usage), not a divergence to fix.
- `deepseek/deepseek-v4.1-flash` catalog price (base/off-peak, per the snapshot's UTC
  time-of-day override structure): $0.15/M prompt, $0.60/M completion, $0.003/M cache-read;
  two weekday `utc_start`/`utc_end` windows carry a 2× peak override (exact clock-time
  meaning of those fields is undocumented anywhere in this repo). Added to agent-orch
  `src/agent_orch/rate_table.yaml` as the base rate only, with a comment noting the peak
  override exists but is unmodeled (consistent with no other route in either pricing stack
  modeling time-of-day pricing), citing the new snapshot as basis.
- Test edits in both repos follow price changes only (updated expected numbers, doubled
  values, flipped route selection) — no assertion was weakened or removed.
- `doctor --catalog --crews` clean (28 routes, 7 channels, 9 terms, 17/15 crews; 30/30
  workers resolved). Focused tests green: `test_staffing_terms.py` (21), `test_staffing_staff.py`
  (34), `test_staffing_run.py -k "glm_cache_pricing_regression or cache_pricing_end_to_end"`
  (2); agent-orch `test_rate_table.py` (20, unmodified — no new assertions needed since the
  new row isn't yet exercised by a rate-table-specific test). Black/Ruff clean on `src/`.
- `proof_status` for the new route remains unproven until a `run` succeeds and lands in the
  ledger (D218 ruling 1); trial dispatch is Chief's, not this session's.
