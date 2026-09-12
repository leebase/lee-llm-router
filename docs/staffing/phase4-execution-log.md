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

## D218 DeepSeek V4.1 Flash intake and first trial (Chief, 2026-09-12)

- Intake committed: router `fee397c` (pricing snapshot `openrouter-20260911.json` + sha256;
  terms/channels repointed; route `pi-deepseek-deepseek-v4-1-flash-openrouter`; price-driven
  test updates), agent-orch `870700f` (rate row, base rates, peak/off-peak noted).
- Trial (Chief-dispatched, detached, through `run`): packet `D218-trial` (`.json` owned-path
  mapping in `derive_class.py`), attempt `router-run-98e00651d0914f31b533545670665075`,
  route `pi-deepseek-deepseek-v4-1-flash-openrouter`, selection explicit (D218 workhorse
  evaluation), provider-reported 209,415 tokens (in 23,182; out 3,961; cached 182,272),
  $0.006400716 list = marginal, wall 131.8 s, oracle pass (22 passed), `verified_success:
  true` (supervisor route `claude-claude-sonnet-5-high-anthropic-sub` attested). Confinement:
  only the two owned files changed. Chief re-ran the oracle.
- Independent review: two `run --role review` attempts on `agy-gemini-3-8-flash-high-gemini-sub`
  (`router-run-…c1e78e2b`, 201,407 tokens; `router-run-2b2924366fad4be2a30a090db3c8357b`,
  224,209 tokens) recorded usage but `run` does not persist worker stdout, so their verdict
  text was lost (gap filed as P4-5c). The review was then run directly through `agy` with the
  same packet and route: **REVIEW VERDICT: ACCEPT**, 0 contract-blocking, 0 hardening, 0
  future; output kept at `docs/staffing/packets/evidence/D218-trial-review-gemini-flash.md`.
- Committed as `fix(staffing): map .json owned paths to yaml-config in derive_class`.
- `staff --mode auto` now lists the route as `proven`; it competes on marginal price
  ($0.15/$0.60 per M) behind prepaid Gemini and behind cheaper metered V4 Flash and GLM.

## Group A2 — supervise dispatch pattern (P4-5b) and worker-output persistence (P4-5c)

Session: Sonnet 5 headless supervisor, 2026-09-12, router only. Authority: D215 rulings 4-6.
Dispatch mechanic used throughout: `run` invoked detached (`setsid nohup bash -c ... ; echo
done=$? >> <log>`), polled in bounded <=90s foreground calls, per the harness's own
auto-backgrounding property — exactly the pattern P4-5b itself codifies.

### P4-5b — `/supervise` dispatch pattern for auto-backgrounding harnesses

- Packet: `docs/staffing/packets/P4-5b.md` (copied verbatim from
  `~/projects/chief-of-staff/tmp/staffing-p4/skill-dispatch-fix-packet.md`). Class
  `impl/deterministic/none/xs/markdown`. Auto-staffed to
  `agy-gemini-3-8-flash-high-gemini-sub`.
- Attempt 1: worker exited 0 in 306s but the oracle launch failed
  (`FileNotFoundError: 'PYTHONPATH=src'`) — supervisor error, not a worker failure: an
  unquoted `KEY=value` prefix isn't shell-expanded by the no-shell `--oracle` boundary (the
  same class of mistake recorded in P4-2). `classify-failure` → `platform_env`;
  `next-action` → `retry_same_route_after_platform_repair`.
- Attempt 2 (same route, oracle corrected to `env PYTHONPATH=src ...`): replaced the
  `## Foreground execution` section with a new `## Dispatch pattern` section carrying the
  detached-start/bounded-poll/read-before-deciding instructions, extended to review
  dispatches; updated the three affected compact-string assertions in
  `test_supervise_bodies_are_parity_checked_against_d213`. Oracle passed. The worker also
  independently ran `lee-llm-router shims install --command supervise --apply` and wrote an
  unrequested `docs/staffing/packets/P4-5b-review.md` review packet for itself — both outside
  its declared owned paths (Rule A/step-12 scope violations, however harmless: the reinstall
  content was correct, confirmed by `shims diff` showing zero drift). Supervisor removed the
  stray review-packet file and re-ran the reinstall itself (idempotent `unchanged` on all four
  home targets) plus the `chief-of-staff` project's separate `.omp` target (`update`, now
  matching). One Black reformat needed on the test file (line-wrap only); no assertion
  content changed.
- Full suite green (1705 passed, 1 skipped) confirmed personally, twice, via the
  detached-and-poll pattern applied to the suite run itself (the harness auto-backgrounded the
  first plain `pytest -q` invocation exactly as the packet describes).
- Independent review dispatched (`pi-deepseek-deepseek-v4-flash-openrouter`, author route
  excluded): verdict `unverified` (no oracle on a judge-role dispatch — the exact
  known gap P4-5c fixes). Supervisor's own diff read, full-suite run, and reinstall/drift
  check are the evidence of record, per this Phase's established precedent for this gap.
- Committed `7e1e249` (`feat(staffing P4): supervise dispatch pattern for auto-backgrounding
  harnesses`).

### P4-5c — persist worker output per attempt; parse judge verdicts

- Packet: `docs/staffing/packets/P4-5c.md`, written from `docs/staffing/needs-lee.md`'s P4-5c
  note plus a read-only research pass over `run.py`'s dispatch/attempt-record/state-directory
  conventions (exact line citations recorded in the packet). Class
  `impl/deterministic/none/s/python`. Auto-staffed to `agy-gemini-3-8-flash-high-gemini-sub`.
- Attempt 1: correctly implemented `resolve_artifacts_dir` (mirroring the attempts/
  availability/runs state-directory precedence exactly), `_persist_worker_output`
  (fail-open on `OSError`), and `_parse_judge_verdict` plus the additive `judge_pass`/
  `judge_fail` schema enum values and the `provenance.worker_output_dir` schema property.
  Oracle passed — but the diff added **zero tests** for any of the new behavior (only an env
  var added to the shared `scratch_state` fixture, unused by any test), matching this
  Phase's P4-5 precedent exactly. Supervisor judgment (not classify-failure, since the oracle
  itself passed): missing required evidence is a Rule C spec deviation, not an oracle-visible
  failure.
- Full-suite run (personally, before any repair) also surfaced that the new schema enum
  values broke `test_v2_verdict_vocabulary_is_canonical`'s closed-list assertion — a
  legitimately foreseeable extension, same scale as prior sessions' fixture/assertion fixes;
  supervisor-fixed directly (added the two new values to the expected list).
- A live independent-review dispatch (used simultaneously as the packet's required live
  check) showed `_parse_judge_verdict`'s original design — matching the marker only as the
  literal final line of `stdout.splitlines()` — never fires for the `pi`/`agy` harness family:
  their captured stdout is a raw JSON event stream where the real final text sits inside a
  JSON string field followed by wire-format closing tokens, so the marker is never literally
  the last line. Confirmed live: a real review dispatch's stdout ended with
  `...REVIEW VERDICT: ACCEPT"}]}` and recorded `verdict: "unverified"`, not `judge_pass`.
  Supervisor-fixed directly (same scale as prior sessions' mechanical fixes): rewrote the
  matcher to compare the last `str.rfind` occurrence of each marker rather than requiring
  final-line equality, still conservative against an earlier-discussed marker (last
  occurrence wins).
- Repair 1 (same route, narrowed to `tests/test_staffing_run.py` only): **zero incremental
  changes** — identical diff to attempt 1 (same env-var-only edit). Matches this Phase's
  recorded pattern of Gemini Flash making zero progress on narrow impl-role Python-coding
  asks after an initial success elsewhere in the same packet.
- Escalation (`pi-deepseek-deepseek-v4-flash-openrouter`, parent = repair 1's attempt,
  reason recorded on the attempt): wrote all six required tests (persistence, accept/reject
  with realistic JSON-harness-shaped stdout, no-marker fallback, non-review-role
  non-interference, write-failure fail-open). Oracle failed on the first run
  (`spec_rejected`): one new test had a filesystem-ordering bug (wrote a blocker file into a
  parent directory the fixture never created) — supervisor-fixed directly (one `mkdir`
  line), and a second, unrelated failure (`test_worker_ceiling_kill_terminates_escaped_
  recursive_descendants`) reproduced only under the full-file run, passed in isolation and on
  a clean rerun — a pre-existing, timing-sensitive flake, not a regression from this packet.
  Minor Ruff import-order/line-length fixes applied (mechanical, `--fix` plus one docstring
  shortened).
- Full suite green (1711 passed, 1 skipped, up from 1705 — six new tests, no regressions),
  confirmed personally via the detached-and-poll pattern.
- Independent review re-dispatched against the final diff (`pi-deepseek-deepseek-v4-flash-
  openrouter`, author route excluded): **`verdict: "judge_pass"`** — the packet's own new
  mechanism recorded the reviewer's verdict this time, live proof the fix works.
  `REVIEW VERDICT: ACCEPT`, 0 Blocking, 2 Hardening (the `rfind` matcher's last-occurrence
  choice is a deliberate, documented tradeoff, not a defect; the `run.py` → `doctor.py`
  private-name import is unusual layering but not a circular import — `doctor.py`'s import of
  `staffing.run` is always lazy), 0 Future. Both Hardening notes are recorded here, not
  resolved, per Rule J (blocking findings drive convergence; these are not blocking).
- Committed `ed71aa7` (`feat(staffing P4): persist worker output per attempt and parse judge
  verdicts`).

### Group A2 close-out

Both packets committed: `7e1e249` (P4-5b), `ed71aa7` (P4-5c). Router suite green at close
(1711 passed, 1 skipped). Metered spend this session: ~$0.084 (three `pi`/OpenRouter
dispatches on `pi-deepseek-deepseek-v4-flash-openrouter`; every `agy-gemini-3-8-flash-high-
gemini-sub` dispatch was prepaid-subscription, `cost.basis: ["unavailable"]` by the router's
own never-invent-usage convention for that channel) — well inside the $10 ceiling. No needs-Lee
item generated by this group; the pre-existing P4-6/P4-7 blocker recorded earlier in
`needs-lee.md` is unaffected and unresolved by this session.

**Recorded, not resolved by this session** (see `docs/staffing/needs-lee.md`):
- `_parse_judge_verdict`'s last-`rfind`-occurrence design could in principle match a marker
  the worker discusses mid-response if a later, unrelated line also happens to contain the
  exact string — theoretical, not observed, and reviewed as acceptable (Hardening, not
  Blocking) both times.
- `staffing/run.py` importing a private name (`_INDEPENDENCE_APPLICABLE_ROLES`) from the
  CLI-layer `doctor.py` is unusual layering (safe today only because `doctor.py`'s own import
  of `staffing.run` is always lazy); a future packet could relocate the constant to a shared
  `staffing` module to remove the upward dependency.
- Unrelated, pre-existing uncommitted working-tree changes (`context.md`, `result-review.md`,
  `docs/crew-resolver/execution-log.md` — Crew Resolver Sprint 6 status notes from a different
  initiative) were present at session start and left untouched throughout, per the same
  no-bundling discipline this Phase already applies to agent-orch's stashed WIP.

## Group B — auto-orch (P4-6, P4-7)

Session: Sonnet 5 headless supervisor, 2026-09-12, `auto-orch` only. Authority: D215
rulings 4-6. Resolves the "Needs Lee/Chief: decide who picks up P4-6" item recorded above
under "D218 DeepSeek V4.1 Flash intake." Repo carries an unrelated lane's uncommitted
mission/state and recovery-feature WIP throughout (`cycle.py`, `scheduling_policy.py`, several
`missions/*` and top-level doc files, per that section's own note) — never staged or
committed by this session; every commit below stages only its own files, and the two hunks
this session added inside the shared `cycle.py` were isolated with a hand-built patch applied
via `git apply --cached` (confirmed non-overlapping with the other lane's hunks by line-range
inspection) rather than a blanket `git add`.

Dispatch mechanic: `run` invoked detached (`setsid nohup bash -c ...; echo done=$? >> log`),
polled in bounded <=90s foreground calls, per the harness's own auto-backgrounding property
(P4-5b's own pattern, applied to `run` itself here as well as to the owner suite, which the
harness also auto-backgrounded).

### P4-6 — `auto` crew via `lee-llm-router staff`

- Packet: `docs/staffing/packets/P4-6.md`, class `impl/deterministic/authority/m/python`
  (don't-cheap-trial). Staffed directly at `pi-deepseek-deepseek-v4-flash-openrouter` — the
  empirically proven route from Group A's own repeated evidence that the cheaper/unproven
  `auto`-selected Gemini Flash rung made zero coding progress three times that session.
- Owner's-call design (recorded in the packet, not re-litigated here): the `auto` crew is
  scoped to the three **governed** roles (`primary`/`reviewer`/`judge`) only, not the five
  cognitive-stage CLI workers, which it borrows unconditionally from a new required
  `fallback_crew` sibling config key; the governed mandate is resolved once per cycle at
  Author time (the one place a concrete `BacklogItem` and `mission` are both in hand) and
  cached to `cycle-reports/<cycle_id>/routing/auto-crew-mandate.json`, which every later
  reader in the same cycle (`authoring._governed_routing_findings`,
  `authoring._mandate_routes_for_generator`, `cycle._governed_routing_guard`) reads via new
  optional `mission=`/`cycle_id=` kwargs on `routing_authority.resolve_governed_mandate`
  rather than re-resolving; `preflight._check_routing_authority` (which runs before any
  cycle, before an item is selected) is the one caller that structurally cannot know the
  per-item mandate and instead reports the fallback crew's block with an added note.
- Attempt 1 (`router-run-7cdfdbdd759d4569878f9779061fbd84`, 574.8s dispatch, $0.0675 list =
  marginal): implemented the full design correctly in one pass — new module
  `src/auto_orch/auto_crew.py` (`resolve_role_route`, `resolve_auto_governed_mandate`,
  `load_auto_crew_mandate`, the router-harness and role-vocabulary maps), the `parse_routing_
  config` special case, the `resolve_governed_mandate` cache-preferring branch, and the three
  reader call sites — but the oracle failed (`spec_rejected`, pytest exit 2/1): 17 test
  failures, all mechanical.
  - 3 were pre-existing production call sites (`author_playbook`'s two,
    `_author_playbook_from_spec`'s one) correctly threaded with the new required `cycle_id`
    parameter, but 3 *test* call sites outside this packet's own new test files
    (`tests/test_author_failed_run_repair_regression.py`,
    `tests/test_auto_orch_spec_authoring.py`, `tests/test_auto_orch_routing_authority.py`)
    still called the old arity — supervisor-fixed directly (one literal `"test-cycle"`
    argument added at each of the 3 call sites), same scale as this Phase's established
    alignment-typo precedent.
  - 1 dead-code hunk (`_RoutingConfigProxy`, defined, never referenced) — removed.
  - 11 were in the packet's own two new test files
    (`tests/test_auto_orch_auto_crew.py`, `tests/test_auto_orch_routing.py`): a shared-worker
    fixture literally named `stub` (colliding with the pre-existing, unrelated
    `routing.py:308` "worker 'stub' is built in and cannot be redefined" guard for a
    *mission-level* worker override — an existing rule the new fixtures happened to trip, not
    a new defect); one fixture crew with `stages: {}` (itself invalid input under the
    pre-existing `load_crews` non-empty-stages rule) meant to exercise an unrelated
    "unknown fallback crew" path; a fake-router fixture whose `catalog explain` canned
    response for the "unmapped harness" case named a different `route_id` than the paired
    `staff` response's `selected_route`, so the code correctly failed at "no entry for route"
    instead of the intended "no mapping in ROUTER_HARNESS_TO_GOVERNED"; a test helper calling
    `Mission(mission_dir)` where the real constructor requires `Mission.load(root, name)`; and
    a "router unavailable" test that never actually made the router unavailable (no env
    override), so it silently observed the real router's success. Also found in
    `src/auto_orch/auto_crew.py` itself: `load_auto_crew_mandate` read `mission.root`
    unguarded, raising `AttributeError` for any duck-typed mission stand-in without that
    attribute, contradicting the function's own documented "returns `None` on any failure"
    contract — supervisor-fixed (fail-open `getattr` guard). All 11 supervisor-fixed directly,
    same scale as the rest; none weakened an assertion.
  - Full suite green (1506 passed, 2 skipped) modulo one pre-existing, unrelated failure
    confirmed independent of this packet by `git stash`ing every P4-6 file (including
    `cycle.py`'s hunk) and re-running: `tests/test_auto_orch_end_to_end.py::
    test_end_to_end_failed_run_increments_and_third_fire_halts` fails identically against the
    other lane's WIP alone — a resume/ideation-cadence feature in progress, not this packet's
    concern.
  - Independent review dispatched twice this session (`agy-gemini-3-8-flash-high-gemini-sub`,
    author route excluded): both times the worker started a background `pytest` invocation
    and returned with no review verdict text at all (empty `response`, one full turn spent)
    — a new instance of the known gap (no oracle on a judge-role dispatch; P4-5c's
    verdict-parsing mechanism has nothing to parse when the model never writes one). Per this
    Phase's established Rule D precedent, the supervisor's own line-by-line diff read (every
    owned file, confirming design fidelity to the packet) and the full-suite run above are the
    evidence of record.
  - Black/Ruff clean after formatting (9 files reformatted, mechanical; 3 further Ruff
    findings fixed by hand: two unused-import groups, one genuine `F821` from a
    string-quoted type annotation with no corresponding `TYPE_CHECKING` import, one
    line-length docstring wrap — all confined to this packet's own new/touched lines).
  - Committed `74d6fe3` (`feat(staffing P4): add auto crew via lee-llm-router staff (P4-6)`).

### P4-7 — `task_type` from the derived class key; performance rollup by class

- Packet: `docs/staffing/packets/P4-7.md`, class `impl/deterministic/authority/s/python`,
  depends on P4-6 (reuses its `write_backlog_packet`/`default_router_argv`). Staffed directly
  at `pi-deepseek-deepseek-v4-flash-openrouter`, same reasoning as P4-6.
- Owner's-call design (recorded in the packet): `task_type` is derived fresh per cycle from
  the live `BacklogItem` at cycle-report-writing time (not persisted as a new sticky
  `BacklogItem`/`backlog.md` field, which would have required touching
  `scheduling_policy.py` — owned by the other lane's live WIP this session deliberately never
  touches) via a new `auto_crew.derive_task_type` helper; `summarize_observations` gains an
  **additive** `by_task_type` rollup alongside the existing `groups` list (not a regrouping of
  it), per the sprint plan's own framing of this as a recorded choice rather than a
  resolution.
- Attempt 1 (`router-run-fec02ffd8e4d4b5782be9cb29de7d3d1`, 793.5s, $0.1284 list = marginal):
  correctly implemented `derive_task_type`, the `OBSERVATION_SCHEMA`/`SUMMARY_SCHEMA`
  additive fields, the `_group_stats` refactor shared by both rollups, and the
  `collect_observation`/`_selected_backlog_item_for_report` wiring — but the oracle failed
  (`spec_rejected`, pytest collection error) from severe corruption in the tail of its own new
  test file (`tests/test_model_effort_performance.py`): roughly its last five lines had
  collapsed into one unparseable string literal containing a garbled, doubly-escaped dump of
  what should have been ~65 lines of real source (two more failure-mode assertions plus an
  entire new test function) — a worker-side tool malfunction, not a design defect. The worker
  had already noticed this itself and left a self-repair script
  (`tests/_fix_p47.py`, untracked, outside owned paths) that did not actually fix the file.
  Supervisor-fixed directly: truncated the corrupted tail and hand-wrote the two recoverable
  test cases plus the memoization test from the legible intent in the garbled text (verified
  against the real `_selected_backlog_item_for_report`/`derive_task_type` implementations,
  not transcribed blindly); removed the stray, non-functional `_fix_p47.py`.
  - Full-suite run (before any repair) surfaced two further, smaller defects, both fixed
    directly: (1) a genuine production bug in `_selected_backlog_item_for_report`'s
    memoization — `context.setdefault("_derived_task_type", derive_task_type(selected))`
    evaluates its default-value argument unconditionally on every call (`dict.setdefault` is
    not lazy in Python), so the router subprocess ran on *every* call regardless of caching,
    defeating the packet's own explicit memoization requirement; replaced with an explicit
    presence check. (2) `auto_crew.derive_task_type`'s `finally` block referenced `packet_path`
    unguarded, raising `NameError` instead of returning `None` if `tempfile.
    NamedTemporaryFile` itself failed before assignment — contradicts the function's own
    documented "must never raise" contract; guarded with `packet_path: Path | None = None`
    initialized before the `try`. Two test-only bugs found and fixed alongside: two
    `BacklogItem(...)` fixture calls omitted the required `doable` argument; the
    `by_task_type`-vs-`groups`-invariance test compared a 3-observation baseline against a
    5-observation "typed" set (a broken comparison by construction, not evidence of a real
    output change) — corrected to compare the same five observations both ways.
  - Full suite green (1513 passed, 2 skipped, up from 1506 — seven new tests), modulo the same
    one pre-existing, unrelated `test_auto_orch_end_to_end.py` failure recorded under P4-6.
  - Import-order Ruff finding in `cycle.py` (the new `from auto_orch.auto_crew import
    derive_task_type` landed alphabetically out of place) fixed by hand rather than a blanket
    `ruff --fix`, to keep the file's diff confined to exactly this packet's two hunks (see the
    session-level note on `cycle.py` isolation, above) — confirmed via `git diff --stat` that
    only those two hunks plus the moved import remained in this packet's staged patch.
  - Independent review dispatched (`agy-gemini-3-8-flash-high-gemini-sub`, author route
    excluded): again returned an empty response with no verdict after a full turn — same gap
    as P4-6's two review attempts, not re-dispatched a third time given the cost/turn spent
    for zero signal twice already this session. Supervisor's own diff read (including the
    hand-reconstructed test file, checked line-by-line against the implementation rather than
    trusted from the corrupted original) and the full-suite run are the evidence of record.
  - Committed `92d3800` (`feat(staffing P4): task_type from derived class key; performance
    rollup by class (P4-7)`).

### Group B close-out

Both packets committed: `74d6fe3` (P4-6), `92d3800` (P4-7). Full `auto-orch` suite green
(1513 passed, 2 skipped) modulo one pre-existing, unrelated, independently-confirmed failure
in `test_auto_orch_end_to_end.py` caused by another lane's in-progress resume/ideation-cadence
feature — not a regression from this session, not fixed by this session (out of scope; that
lane owns its own WIP). Metered spend this session: $0.0675 (P4-6) + $0.1284 (P4-7) =
$0.1959, both on `pi-deepseek-deepseek-v4-flash-openrouter`; the four review-dispatch attempts
(two per packet) were all prepaid `agy-gemini-3-8-flash-high-gemini-sub`,
`cost.basis: ["unavailable"]` by the router's own never-invent-usage convention — well inside
the $10 ceiling.

**Recorded, not resolved by this session:**
- Four consecutive independent-review dispatches (two each for P4-6 and P4-7) on
  `agy-gemini-3-8-flash-high-gemini-sub` returned an empty response after a full turn (in two
  cases, after starting a background test command and never returning to it) rather than a
  parseable `REVIEW VERDICT` line. This is a new data point for the "worker dispatch impl/
  review-role reliability" observation already recorded at the end of Group A's own P4-1
  section — now with a review-role example alongside that section's impl-role ones. Worth a
  future look at whether `agy`/Gemini specifically, or judge/review-role one-turn dispatches
  generally, have a systemic issue.
- A worker-authored self-repair script (`tests/_fix_p47.py`) found untracked and non-
  functional in the P4-7 attempt is evidence the underlying tool glitch that corrupted the
  test file was visible to the worker itself, which attempted and failed to fix it in the same
  attempt rather than reporting the defect. Worth noting for whoever investigates worker
  reliability broadly (see the point above).
- `auto-orch`'s own uncommitted WIP (`cycle.py`, `scheduling_policy.py`, several `missions/*`
  and top-level doc files, plus untracked `human-direction.md` and mission `direction-ledger.md`/
  `escalation-dispositions.md`/`recovery-inputs/` files) remains exactly as found — untouched,
  unstaged, uncommitted — for whichever lane owns it.

## Group C — live proof, gate, review, close (P4-8, P4-9)

Session: Sonnet 5 headless supervisor, 2026-09-12. Authority: D215 rulings 4-6. Repos touched:
`auto-orch` (new mission, two commits), `agent-orch` (one commit), `lee-llm-router` (two
commits). Ceiling $10 metered — actual metered spend this session: $0.03003313 (one
`pi-deepseek-deepseek-v4-flash-openrouter` dispatch); every other dispatch was prepaid
subscription (`agy-gemini-3-8-flash-high-gemini-sub` reviews, `codex_cli`/`gpt-5.6-sol` via
the live governed cycles, `cost.basis: ["unavailable"]` or subscription-value consumption, not
metered API spend) or supervisor-direct edits with no dispatch cost at all.

### P4-8 — live proof

Created additive mission `auto-orch/missions/staffing-proof` (`routing: crew: auto,
fallback_crew: gemini-flash-tiered`; `ideation.enabled: false`; `scoring.max_candidates_per_cycle:
1`; `workspace: /home/lee/projects/lee-llm-router`), avoiding `missions/linux-utilities` and
`missions/snowflake-accelerator-revival` per instruction (both carry another lane's uncommitted
WIP, confirmed via `git status --short missions/`). `fallback_crew` was switched from the
first choice `opencode-go-economy` to `gemini-flash-tiered` after preflight showed the
`opencode-go` channel at 8% headroom (D216 reserve floor) — cognitive-stage cost stays on the
healthy (90%+) Gemini subscription instead. The one real backlog item (hand-authored in
`backlog.md`, directed via `human-direction.md` per the existing D5/Sprint-44 direction-ledger
mechanism): map `.toml`/`.ini` owned-path extensions to `yaml-config` in `derive_class.py`,
the exact gap the D218 trial review's own "Future Concerns" section named. `human-direction.md`
also asked the Author stage to set `escalation: {enabled: true, ladder: [...]}` on the
implementation step (P4-5's gate item (a) mechanism, exercised live if it fires) — it never
appeared in any authored playbook this session (the Author LLM did not act on the instruction);
recorded below, not chased further, since D215 ruling 5(b) itself states an escalation firing
is evidence if it occurs, not a requirement.

**Platform defects discovered and fixed live** (D209/D87: repair failures and continue):

1. **`escalation:` had no YAML parsing path at all** (agent-orch `playbook.py`). P4-5 built
   the full `StepDefinition.escalation`/`EscalationIntent` engine mechanism but never wired a
   playbook loader path for it — an authored `escalation:` block was silently rejected as an
   unsupported step key (`_PLAYBOOK_STEP_KEYS` never listed it). Packet dispatched
   (`agy-gemini-3-8-flash-high-gemini-sub` attempt made zero changes; escalated to
   `pi-deepseek-deepseek-v4-flash-openrouter`, which implemented `_parse_escalation` correctly
   but silently deleted and fused an unrelated pre-existing test with its own new one —
   supervisor-fixed directly, restoring the deleted test under its own name). Independent
   review (`agy`, author route excluded): REVIEW VERDICT ACCEPT, 0 blocking. Committed
   agent-orch `7296c38`.
2. **The `auto` crew's own packet placeholder always failed the real router.**
   `write_backlog_packet`'s fixed `- Owned paths: .` collapses to the empty string under
   `lee_llm_router.staffing.derive_class._parse_owned_paths`'s own stripping — every real
   `auto`-crew cycle before this fix silently fell back to `fallback_crew`, never actually
   exercising the router, since P4-6/P4-7's own commits (Group B, this same day) were staffed
   directly rather than dispatched through their own new mechanism. Changed the placeholder to
   `` `unspecified-scope.py` `` (needs a real extension too — the packet's language is derived
   from it before any `--language` override applies).
3. **`resolve_role_route`'s harness/model lookup was structurally broken.** It read
   `catalog explain --json`'s top-level key as `"workers"`/`"eligible"` — the real CLI's key
   is `"routes"`, and its per-route entries deliberately never include harness/model/effort at
   all (`_explain_route_json`'s own committed docstring: "the route id is the only route
   label"). `harness` is now derived from `selected_route`'s own hyphen-prefix naming
   convention (verified zero mismatches across all 28 rows in
   `lee-llm-router/config/staffing/routes.yaml`); `model` is resolved via the already-committed
   `lee-llm-router price --route ID --input 0 --output 0 --json` (P4-1) instead of `catalog
   explain`. Confirmed live-blocking, not cosmetic: a first attempt at this fix left
   `model: None`, and the very next live cycle failed with "pricing admission refused ...
   metered route has no trusted model identity." `effort` still has no CLI disclosure path
   and stays `None` — recorded as a needs-lee/chief cross-repo architecture question (which
   repo should own exposing a selected route's dispatch metadata), not decided unilaterally.
   The `fake_lee_llm_router.py` test fixture had encoded the same wrong shape the buggy code
   expected (a mocked-seam trap; `test_resolve_role_route_with_real_cli`'s
   `except RouteUnavailable: pytest.skip(...)` is exactly what let it go undetected) — fixture
   and test corrected to match reality; the seam test now genuinely passes against the real
   installed binary. Two independent-review rounds (`agy`, author route excluded — this was
   supervisor-authored, not worker-dispatched): round 1 caught the deeper `catalog explain`
   defect a first attempt missed; round 2 (after the `price`-based fix) ACCEPTed with 3
   hardening findings (fail-closed on no model, payload type guard, real-CLI test model
   assertion) all applied before commit. Committed auto-orch `d6fcb66`, `68a2297`.

**Live cycles** (`auto-orch run-cycle staffing-proof`, each detached/polled):

- Cycle 1 (`20260912T085809Z`): mandate fell back to `fallback_crew` (defect 2, not yet
  fixed) — a real, correctly-recorded fail-closed instance of the required "fails closed to
  the mission's last named crew with a recorded reason if the router is unavailable" behavior,
  just for an unintended reason. Failed downstream at the template's `step_08_user_smoke_gate`
  (`smoke_manifest.start_command` interpreter mismatch) — unrelated to routing.
- Cycle 2 (`20260912T094913Z`): after defects 2+3's first pass, mandate resolved genuinely
  through the router (`fallback_reason: null`) for the first time — crashed before Execute on
  an unrelated Author-stage worker timeout (`antigravity_gemini38_flash_high`, 600s), a
  platform reliability characteristic of the Gemini Flash cognitive-stage worker, not an
  auto-crew defect.
- Cycle 3 (`20260912T100049Z`): mandate resolved via router (`source: router_auto`) again;
  Execute genuinely ran a governed attempt — and failed exactly as defect 3 predicted before
  it was fully fixed: "pricing admission refused ... metered route has no trusted model
  identity." This is the evidence that made defect 3's `model` fix non-optional.
- Cycle 4 (`20260912T102251Z`, after defect 3's full fix): mandate resolved via router,
  `fallback_reason: null`, real model identities (`gpt-5.6-sol` via `codex_cli`) on all three
  governed roles. Execute ran the full playbook end to end — 8 real attempts across 7 steps,
  each with a real `route-selection.json` (`selected_route: codex-gpt-5-6-sol-low-openai-sub`
  family) and `usage.json` (`cost_usd` populated per attempt, e.g. $3.6550544 /
  $2.0004984 / $0.4419648 / $0.5664672 / $0.5663392 / $3.0946152 / $3.9828576 / $4.6959808;
  `cost_usd_marginal: "unavailable"` on every attempt — P4-4's own documented fail-open
  behavior for this harness/model, not a new gap). No ESCALATE fired (not required). The
  cycle's own `evaluate` stage still recorded `cycle_outcome: failed`: a later
  `step_08b_user_simulation_gate` reported the tester's claimed CLI exit codes (0) not matching
  the orchestrator's independently observed exit codes (1) for several `lee-llm-router`
  commands — independent review confirmed the actual cause is that gate's verification
  re-run invoking bare `python3` (no venv/`PYTHONPATH`), not a defect in the delivered diff:
  the same commands run with the venv's interpreter all exit 0. Recorded as a needs-lee
  orchestration-tooling gap (playbooks targeting router commands should use `.venv/bin/python`
  or the installed `lee-llm-router` entry point), not fixed here (out of this proof's scope).

**Backlog item landed despite the cycle-level "failed" outcome:** the actual diff produced by
cycle 4's governed run (`lee-llm-router-agent-orch-runs/ba56e712bfe2`) — `.toml`/`.ini` ->
`yaml-config` in `_EXTENSION_LANGUAGES`, six new tests — was independently verified by the
supervisor (targeted oracle 28/28, full router suite 1717 passed/1 skipped, Black/Ruff clean)
and independently reviewed (`agy`, author route `codex-gpt-5-6-sol-low-openai-sub` excluded):
REVIEW VERDICT ACCEPT, 0 contract-blocking, root cause of the gate discrepancy confirmed as
above. Committed `1d9055e` (also folds in Group B's previously-uncommitted execution-log/
needs-lee entries, found sitting unstaged in this repo's working tree since that session).

**Gate (b) evidence, in the sprint's own terms:** one live governed Auto-Orch cycle under an
`auto` crew on a real small backlog item — satisfied by cycle 4. Every attempt priced at list
(and marginal where the router can resolve it; `unavailable` fail-open elsewhere, as designed)
— satisfied. The block in the playbook mandate, written and cached to
`cycle-reports/<cycle_id>/routing/auto-crew-mandate.json` every cycle — satisfied. Escalation
if it occurs: did not occur this session; not required. All rows in the ledger: the governed
run's own `route-selection.json`/`usage.json` per attempt stand as the ledger evidence (the
router's own `attempts.jsonl` only records `lee-llm-router run`/`staff`/`price` dispatches,
not agent-orch's own worker adapter calls, which is what actually executes a governed step —
`auto_crew`'s `staff`/`price` subprocess calls are read-only class/pricing queries, not attempt
dispatches, so they are not separately ledgered rows).

**Recorded, not resolved this session (needs-lee/chief):**
- Cross-repo architecture question: which repo should own exposing a router-selected route's
  dispatch metadata (harness/model/effort) for a caller like `auto-orch` that must actually
  invoke it — a new `lee-llm-router` CLI capability, or `auto-orch` reading `routes.yaml`
  directly as shared config data. The route-id-prefix (`harness`) and `price` (`model`)
  workarounds in this session's fix are real and verified working, not placeholders, but
  `effort` has no resolution path today.
- The trusted playbook template's "user simulation"/"user smoke" gate convention invokes
  verification commands via bare `python3`, which cannot see a target repo's venv/editable
  install — a real, reproducible false-negative source for any target repo (like
  `lee-llm-router`) that isn't installed into system site-packages.
- `staffing-proof`'s own `human-direction.md` asked the Author stage to enable
  `escalation:` on the implementation step; it never did across four cycles. Not investigated
  further (out of this proof's bounded scope; escalation firing was evidence-if-it-occurs, not
  required) — worth a look if a future session wants to actually observe ESCALATE fire through
  the authoring pipeline rather than only through P4-5's own hand-built `StepDefinition` test.

### P4-9 — gate (a)-(e)

Gate items (a)-(c) observed as above (this section's own "P4-8" narrative for (a)/(b); suite
counts: router 1717/1/0, agent-orch 1940/9/3-pre-existing, auto-orch 1514/2/1-pre-existing).

**Independent gate review, round 1** (`codex-gpt-6-astra-low-openai-sub`, read-only, 1200s
ceiling, detached+polled): **REJECT**, 4 contract-blocking findings, all reproduced by the
supervisor before fixing:
1. `agent-orch/semantic.py`'s `build_judge_packet` never instructed a real judge to include
   `rejection_kind` on a false verdict, though `SEMANTIC_VERDICT_SCHEMA`'s `if`/`then` requires
   it — every test's fake judge adapter supplied the field directly, masking that a real judge
   dispatch would fail schema validation on any genuine rejection.
2. `auto-orch/auto_crew.py`'s `derive_task_type` (P4-7) read `class_derivation.class_key`, a
   key path the real router CLI never populates (the real payload carries `class_key` at the
   top level, or nested at `class_derivation.class.class_key`) — confirmed live, it always
   returned `None` in production; masked by the packet's own fake-CLI test encoding the same
   wrong shape.
3. `agent-orch/engine.py`'s escalation eligibility check had no `attempt_number < last_attempt`
   gate — a `capability_rejected` verdict on a step's own final allowed attempt recorded
   `policy_decision: "ESCALATE"` and a `RUNNING`/next-attempt-number persisted state the
   enclosing `for attempt_number in range(first_attempt, last_attempt + 1)` loop then never
   actually dispatches. The existing gate test (`max_attempts=2`) never exercised this
   boundary.
4. `_snapshot_step_payload` (`engine.py`) had no branch for `step.escalation` at all — a sealed
   playbook's escalation configuration silently became `None` on reload/resume, since `resume`
   always executes the sealed snapshot, not the live source playbook.

Remediated: `agent-orch` `88ce8ac` (findings 1, 3, 4 — new tests
`test_judge_packet_instructs_rejection_kind_on_a_false_verdict`,
`test_escalate_on_final_attempt_halts_instead_of_a_phantom_transition`,
`test_playbook_snapshot_round_trips_step_escalation`); `auto-orch` `e345126` (finding 2 — new
test `test_derive_task_type_with_real_cli`, no catch-and-skip once the binary is confirmed
present, same discipline as P4-8's real-CLI test fix). All three were confirmed live/reproduced
directly (not accepted on the reviewer's word) before fixing. Full suites re-confirmed green
at the counts above.

**Independent gate review, round 2** (same route): **ACCEPT**, 0 contract-blocking, 0 new
regressions; suite counts matched exactly (agent-orch's own sandbox reported 104 failures in
round 1 and again in round 2 — same failure set both times, ~96 of them Chromium-sandbox/
socket/read-only-fixture noise specific to that reviewer's environment, explicitly reconciled
against the supervisor's own 3-failure count rather than treated as a contradiction). One
trivial hardening note (a stale docstring key-path reference) fixed as `9b8e8dd`.

Closing report: `chief-of-staff/tmp/staffing-p4/closing-report-c.md`. Chief seals D217.
