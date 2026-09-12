# Packet P4-2b-review — independent review of subscription reserve (P4-2b, D216)

- Kind: `review`
- Declared size: review only, no changes
- Owned paths (read-only for you; do not edit): `config/staffing/policy.yaml`,
  `config/staffing/schema/policy.schema.json`, `src/lee_llm_router/staffing/catalog.py`,
  `src/lee_llm_router/staffing/eligibility.py`, `src/lee_llm_router/staffing/staff.py`,
  `tests/test_staffing_catalog.py`, `tests/test_staffing_catalog_explain.py`,
  `tests/test_staffing_eligibility.py`, `tests/test_staffing_staff.py`
- Requirement: independently review the uncommitted working-tree changes in
  `~/projects/lee-llm-router` (run `git diff` and `git status --short` yourself — do not
  assume). This packet implements D216 (subscription reserve): a `reserve_fraction` policy
  record (default 0.10, Anthropic and Gemini explicitly 0.10) in `policy.yaml`/
  `policy.schema.json`/`PolicyCatalog`; a new eligibility check in `eligibility.py` excluding
  a subscription route whose channel's `remaining_fraction` is at or below its reserve, with
  reason `reserve: N% kept in the tank (D216)`; a matching `bind`-mode authorization
  requirement in `staff.py` (reserved channels bind only with `--authorized-by lee`, mirroring
  the existing `never_automatic` boundary with a distinct error kind).
- Check specifically: (a) is the reserve check additive and independent of the existing
  `likely_exhausted` health veto (does removing the reserve check still leave the health veto
  intact, and vice versa — read both checks in `evaluate_eligibility`); (b) does the reserve
  fraction correctly fall back to the 0.10 default for channels with no explicit override, and
  correctly use the override for `anthropic-sub`/`gemini-sub`; (c) is the reason string exactly
  `reserve: N% kept in the tank (D216)` with N as an integer percentage; (d) does `bind` refuse
  a reserved-channel route without `--authorized-by lee` and accept it with that flag, using a
  distinct error `kind` from `never_automatic`; (e) do the new/updated tests actually exercise
  10%-excluded vs 11%-eligible boundary cases for Anthropic, and does the auto ladder test
  prove it proceeds to the cheapest eligible metered route when both subscriptions are
  reserved; (f) are the three pre-existing tests that needed their expected reason
  strings/lists updated for this legitimate additive change (`test_fable_reason_is_never_automatic_then_channel_exhausted`,
  `test_explain_reproduces_p0_5_acceptance`, `test_auto_ladder_skips_reserved_channel_to_cheapest_metered`)
  correctly updated and not weakened.
- Oracle: `PYTHONPATH=src .venv/bin/python -m pytest -q` (run it yourself; do not trust a
  prior report)
- Review: this packet is itself the review.
- Commit: none (review only)

## Required evidence

Report PASS or FAIL. On FAIL, list every defect found, each citing the exact
file/line/requirement violated and a reproducer. Classify each as contract-blocking,
non-blocking hardening, or a future concern. On PASS, state that you ran the oracle yourself
and it passed, and that you read the full diff.

## Stop / escalation condition

If you cannot read the actual git diff (no repository access), say so explicitly rather than
reviewing from the packet description alone.
