# Packet D218-intake-review — independent review of DeepSeek V4.1 Flash intake (D218)

- Kind: `review`
- Declared size: review only, no changes
- Owned paths (read-only for you; do not edit): `config/staffing/channels.yaml`,
  `config/staffing/routes.yaml`, `config/staffing/terms.yaml`,
  `src/lee_llm_router/staffing/terms.py`, `tests/test_staffing_run.py`,
  `tests/test_staffing_staff.py`, `tests/test_staffing_terms.py`,
  `config/staffing/pricing/openrouter-20260911.json`,
  `config/staffing/pricing/openrouter-20260911.json.sha256`,
  `/home/lee/projects/agent-orch/src/agent_orch/rate_table.yaml`
- Requirement: independently review the uncommitted working-tree changes in
  `~/projects/lee-llm-router` and `~/projects/agent-orch` (run `git diff` and `git status
  --short` yourself in both repos — do not assume; in `agent-orch` the working tree also
  carries unrelated pre-existing uncommitted WIP by another lane, so check only the
  `rate_table.yaml` diff, nothing else in that repo). Under D218 (chief-of-staff
  `decisions.md`, 2026-09-12), this change:
  1. Captures a fresh OpenRouter catalog snapshot
     `config/staffing/pricing/openrouter-20260911.json` (sha256 sidecar alongside, fetched
     live from `https://openrouter.ai/api/v1/models` 2026-09-11) and repoints every
     `decision_price_ref`/`reporting_price_ref` in `terms.yaml`, every `replacement_price_ref`
     in `channels.yaml`, and `terms.py`'s `DEFAULT_OPENROUTER_SNAPSHOT_PATH` (plus its
     docstring) from the superseded `openrouter-20260909.json` to the new file. The old
     snapshot and its sidecar stay on disk, just no longer referenced.
  2. Updates three tests whose expected dollar amounts were computed from the superseded
     snapshot's prices, since the live catalog changed underneath them (verify each number
     against the new snapshot file yourself, do not trust the packet's arithmetic):
     `tests/test_staffing_terms.py` (GLM per-token prices), `tests/test_staffing_run.py`
     (two GLM cache-pricing regression tests), `tests/test_staffing_staff.py` (the
     cheapest-metered-route test, which now correctly resolves to
     `pi-deepseek-deepseek-v4-flash-openrouter` instead of the GLM route, because GLM's price
     doubled while DeepSeek V4 Flash's dropped — check this is a genuine consequence of the
     real snapshot data, not a test weakened to pass).
  3. Adds route `pi-deepseek-deepseek-v4-1-flash-openrouter` (model
     `deepseek/deepseek-v4.1-flash`, harness `pi`, channel `openrouter`, `status: active`),
     copied from the existing `pi-deepseek-deepseek-v4-flash-openrouter` row with only the
     route id and model changed — check the copy is exact (same `dispatch_template`
     structure, same `usage_capture: none`, same `effort: null`).
  4. Adds the agent-orch rate-table row for `deepseek/deepseek-v4.1-flash` per the P0-6
     convention (`source_url`, `as_of`, `basis`-style comment), immediately after the
     existing `deepseek/deepseek-v4-flash` row — check the per-token/per-1M-token math is
     correct against the pinned snapshot's base rate (ignore the snapshot's UTC-time-of-day
     override bands; neither this rate table nor the router's `terms.py` model time-of-day
     pricing anywhere, so recording only the base rate is correct, not an omission).
- Check specifically: (a) every occurrence of the superseded snapshot filename that is a
  *live pointer* (not a historical citation of a past decision's own text) was updated,
  and none were missed; (b) the new snapshot's sha256 sidecar actually verifies
  (`sha256sum -c` it yourself); (c) the three updated tests' new expected values are
  arithmetically correct against the new snapshot's real `pricing.prompt`/`pricing.completion`
  fields for `z-ai/glm-5.3-flash` (recompute from the JSON yourself); (d) the new route and
  rate-table row are additive only — no other route, channel, or rate-table entry was
  touched; (e) run `python3 -m lee_llm_router.doctor doctor --catalog --crews` yourself and
  confirm exit 0 with 28 routes.
- Oracle: `.venv/bin/python -m pytest -q` in `~/projects/lee-llm-router` (run it yourself; do
  not trust a prior report) — full suite green is required, not just the files listed above.
- Review: this packet is itself the review.
- Commit: none (review only)

## Required evidence

Report PASS or FAIL. On FAIL, list every defect found, each citing the exact file/line/
requirement violated and a reproducer. Classify each as contract-blocking, non-blocking
hardening, or a future concern. On PASS, state that you ran the oracle yourself and it
passed, that you verified the sha256 sidecar yourself, and that you recomputed at least one
of the three updated test assertions from the raw snapshot JSON yourself.

## Stop / escalation condition

If you cannot read the actual git diff or the snapshot JSON (no repository access), say so
explicitly rather than reviewing from the packet description alone.
