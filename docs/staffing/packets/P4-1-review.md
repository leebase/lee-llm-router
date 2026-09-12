# Packet P4-1-review — independent review of the `price` command (P4-1)

- Kind: `review`
- Declared size: review only, no changes
- Owned paths (read-only for you; do not edit): `src/lee_llm_router/staffing/price.py`,
  `src/lee_llm_router/doctor.py`, `tests/test_staffing_price.py`, `tests/test_doctor_price.py`
- Requirement: independently review the uncommitted working-tree changes in
  `~/projects/lee-llm-router` touching `src/lee_llm_router/staffing/price.py`,
  `src/lee_llm_router/doctor.py`, `tests/test_staffing_price.py`, and
  `tests/test_doctor_price.py` (run `git diff` and `git status --short` yourself to see the
  exact changes — do not assume). This adds a new `lee-llm-router price --route ID --input N
  --output N [--cached N] [--at DATE] [--json]` CLI command computing total list and marginal
  USD price for a route and token counts, per `docs/staffing/packets/P4-1.md` and
  `docs/staffing/phase4-contracts.md` §5. Check specifically: (1) does it reuse
  `lee_llm_router.staffing.terms.route_price` and the existing badge-resolution convention
  from `eligibility.py` rather than reinventing pricing math or inventing a badge; (2) does it
  fail closed (exit 3, `price: <reason>` on stderr) for an unknown route, invalid date, and
  negative/non-integer token counts, never fabricating a number; (3) is the arithmetic
  correct (list = replacement price × tokens, marginal = marginal price × tokens, cache
  handled correctly and fails closed when no cache rate is available); (4) is the CLI wiring
  consistent with neighboring subcommands (`staff`, `run`) in `doctor.py`; (5) do the tests
  actually exercise the behavior they claim to, with no fabricated assertions.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_price.py tests/test_doctor_price.py` (run
  it yourself; do not trust a prior report)
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
