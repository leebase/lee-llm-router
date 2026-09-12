# Packet P4-2-review — independent review of crew reorder + policy ordering rule (P4-2)

- Kind: `review`
- Declared size: review only, no changes
- Owned paths (read-only for you; do not edit): `config/staffing/crews.yaml`,
  `config/staffing/policy.yaml`, `config/staffing/schema/policy.schema.json`,
  `src/lee_llm_router/staffing/catalog.py`, `tests/test_staffing_catalog.py`,
  `tests/test_staffing_catalog_live.py`
- Requirement: independently review the uncommitted working-tree changes in
  `~/projects/lee-llm-router` (run `git diff` and `git status --short` yourself — do not
  assume). This packet (1) reorders the interactive crew `sol-low-glm-pi`'s `impl` array in
  `crews.yaml` per D215 ruling 1 (prepaid opencode-go route first, metered openrouter route
  second — verbatim: "glm-5.3-flash | pi | opencode-go", then "z-ai/glm-5.3-flash | pi |
  openrouter"); (2) adds a new required `crew_ordering_rule` object to `policy.yaml`,
  `policy.schema.json`, and `PolicyCatalog` in `catalog.py` per D215 ruling 3, recorded data
  only (documents an authoring convention, computes/enforces nothing at runtime); (3) adds a
  narrowly-scoped, explicitly-commented exception to
  `tests/test_staffing_catalog_live.py::test_round13_live_backed_interactive_records_resolve_governed_roles`
  for exactly `("sol-low-glm-pi", "primary")`, citing D215 ruling 2 (the live governed
  primary intentionally stays pinned to the metered OpenRouter lane until agent-orch's P4-4
  marginal-cost work lands, so it no longer needs to equal the interactive record's
  now-reordered `impl[0]`) — check this exception is scoped to exactly that one
  crew/role pair and does not weaken the strict first-entry-equality check for any other
  crew or role.
- Check specifically: (a) is the crew reorder exactly what D215 ruling 1 specifies, and are
  no other crews or fields touched; (b) is `crew_ordering_rule` genuinely recorded-data only
  (no new selection/ranking code path was added); (c) is the round-13(c) test exception
  precisely scoped to `("sol-low-glm-pi", "primary")` and does it correctly cite D215 ruling
  2's stated reason, rather than being a general weakening to membership (a general
  membership weakening was explicitly rejected once already in this migration's history —
  see `docs/staffing/decisions.md` D204 round 13's contradiction note if you want the
  precedent, but the check itself is simply: does every other live-backed interactive
  record/role still require exact first-entry equality?); (d) do the schema and dataclass
  changes follow the existing file's conventions exactly (nonempty string fields, frozen
  dataclass, `additionalProperties: false`).
- Oracle: `PYTHONPATH=src .venv/bin/python -m pytest -q` (run it yourself; do not trust a
  prior report)
- Review: this packet is itself the review.
- Commit: none (review only)

## Required evidence

Report PASS or FAIL. On FAIL, list every defect found, each citing the exact
file/line/requirement violated and a reproducer. Classify each as contract-blocking,
non-blocking hardening, or a future concern. On PASS, state that you ran the oracle yourself
and it passed, and that you read the full diff including the test-exception scoping.

## Stop / escalation condition

If you cannot read the actual git diff (no repository access), say so explicitly rather than
reviewing from the packet description alone.
