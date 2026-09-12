# Packet P5-1-review — independent review of `evidence report` (P5-1)

- Kind: `review`
- Declared size: review only, no changes
- Owned paths (read-only for you; do not edit): `src/lee_llm_router/staffing/evidence_report.py`,
  `src/lee_llm_router/doctor.py`, `tests/test_staffing_evidence_report.py`,
  `tests/test_doctor_evidence_report.py`
- Requirement: independently review the uncommitted working-tree changes in
  `~/projects/lee-llm-router` (run `git diff` and `git status --short` yourself — do not
  assume; do not run the full test suite in the background and wait on it — run each command
  in the foreground and read its actual output before continuing). This packet adds
  `lee-llm-router evidence report --month YYYY-MM` per
  `docs/staffing/packets/P5-1.md` and `docs/staffing/phase5-contracts.md` §1-§2/§5. It was
  authored by `pi-deepseek-deepseek-v4-flash-openrouter` after a prior attempt by
  `agy-gemini-3-8-flash-high-gemini-sub` produced zero changes (burned its turn watching a
  background baseline pytest run) and a `claude-claude-sonnet-5-high-anthropic-sub` attempt
  failed at CLI dispatch (a router/harness platform defect in
  `auto-orch/scripts/claude_stage_worker.py`, out of this phase's scope). The supervisor then
  fixed two defects live after the oracle first failed: (1) an f-string format spec
  `f"{rf:.4f if rf is not None else 'N/A'}"` is invalid Python (a conditional inside a format
  spec) — replaced with pre-computed `rf_text`/`rv_text` strings; (2) the test file's shared
  `_record()` fixture helper omitted several attempt-record-schema-required fields
  (`router_event`'s full field set, `provenance.source_refs`, `selection`, a real
  `supervisor_route` object on `verified_success: true` records, a valid `usage.source` enum
  value) — rewritten to build from the same fixture base `test_staffing_rollup.py` already
  uses; (3) `_channel_headroom_rows` originally swallowed a bad `--catalog-dir` into a
  fail-soft per-channel row instead of propagating it, so `evidence_report.py` now loads the
  catalog once in `build_evidence_report` (raising on a genuinely bad catalog dir, matching
  `price`/`route show` convention) and passes the loaded catalog into `_channel_headroom_rows`
  (only the *availability snapshot* path stays fail-soft, since that's live-data
  unavailability, not caller error).
- Check specifically: (a) does `evidence_report.py` read cost from `cost.usd_list`/
  `cost.usd_marginal` directly rather than recomputing from usage+route (contract §1); (b)
  does the "unavailable" cost reason name how many of how many verified attempts lack a
  usable cost record, never a fabricated zero or silent partial average; (c) note (not
  necessarily a blocker): `evidence_report.py` reimplements benchmark de-duplication
  (`_deduplicate_benchmarks`, `_run_id_from_payload`, `_is_v6_payload`) and route/class-key
  extraction privately instead of calling `rollup.build_rollup`/`rollup_ledger` — the stated
  reason in the module is "avoid importing private functions; the logic is identical." Verify
  the reimplementation is in fact behaviorally identical to `rollup.py`'s (same benchmark
  preference ranking, same tie-break) — if it has drifted or could drift silently on a future
  `rollup.py` change, flag as non-blocking hardening (extract a shared public helper) rather
  than contract-blocking, since the packet's forbidden-paths section did not require literal
  reuse, only "do not read `read_attempts()` raw and re-group" with no relitigated aggregation
  semantics — confirm the semantics match, which is the substance of that requirement; (d) is
  the headroom/reserve comparison exactly `remaining_fraction <= reserve_fraction`
  (`eligibility.py:573`'s D216 comparison), for all seven `CHANNEL_IDS`; (e) does a class with
  `comparison_eligible` at multiple routes recommend the cheapest by mean `usd_marginal`
  only among routes with `verified_pass/attempts >= 0.8`, with an evidence line naming n/pass
  rate/cost; (f) do `--json` and text mode render the same underlying data (text is not a
  second source of truth); (g) black/ruff clean on every touched file.
- Oracle: `PYTHONPATH=src .venv/bin/python -m pytest -q` (run it yourself; do not trust a
  prior report)
- Review: this packet is itself the review.
- Commit: none (review only)

## Required evidence

Report PASS or FAIL. On FAIL, list every defect found, each citing the exact file/line/
requirement violated and a reproducer. Classify each as contract-blocking, non-blocking
hardening, or a future concern. On PASS, state that you ran the oracle yourself and it
passed, and that you read the full diff including `evidence_report.py`'s benchmark
de-duplication reimplementation.

## Stop / escalation condition

If you cannot read the actual git diff (no repository access), say so explicitly rather than
reviewing from the packet description alone.
