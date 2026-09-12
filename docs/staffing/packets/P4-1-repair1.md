# Packet P4-1-repair1 — repair after a scope-violating non-attempt

Your prior attempt at this exact packet (`docs/staffing/packets/P4-1.md`, attempt
`router-run-40746f16f6774804b6053d646e418a02`) made **no changes to any owned path** and
instead appended an unrelated note to `docs/staffing/needs-lee.md`, a file outside your
owned paths and unrelated to this packet. That change has been reverted. The oracle
(`pytest tests/test_staffing_price.py tests/test_doctor_price.py`) failed because neither
test file exists.

Do exactly and only what `docs/staffing/packets/P4-1.md` specifies below. Do not touch
`docs/staffing/needs-lee.md` or any file outside Owned paths. If something in the packet is
unclear, make the smallest reasonable interpretation and implement it — do not write a note
instead of code.

---

- Kind: `impl`
- Declared size: 4 files, at most 400 changed lines
- Owned paths: `src/lee_llm_router/staffing/price.py` (new),
  `src/lee_llm_router/doctor.py`, `tests/test_staffing_price.py` (new),
  `tests/test_doctor_price.py` (new)
- Requirement: add a new `price` CLI subcommand:
  `lee-llm-router price --route ID --input N --output N [--cached N] [--at DATE] [--json]`.
  It computes the total list (replacement) and marginal USD price for the given route and
  token counts. Reuse existing pricing math verbatim — do not reinvent it:
  `lee_llm_router.staffing.terms.route_price(route_id, badge, catalog, ...)` already computes
  per-token list/marginal prices for a route under a badge
  (`src/lee_llm_router/staffing/terms.py:411`); the live badge for a route's channel at a
  date comes from the same availability-snapshot resolution `staff`/`catalog explain`
  already use (see `src/lee_llm_router/staffing/eligibility.py`
  `_availability_badge`/`_dated_terms_entry`) — a channel with no recorded status badge fails
  closed to the committed `NO DATA` badge (multiplier 1.0), never an invented badge. Load the
  catalog and availability snapshot exactly the way `_run_staff`
  (`src/lee_llm_router/doctor.py:1880`) already does, with the same `--catalog-dir`/
  `--availability-file`/`--at` override flags and ISO-date validation. `list_usd` = list
  per-token prices × token counts (input + output, plus `--cached` at the read-cache rate
  when the resolved model has one); `marginal_usd` = the same using the marginal per-token
  prices. Exit 3 with one stderr line `price: <reason>` for an unknown route id, unresolvable
  price, invalid date, or negative/non-integer token counts — never invent a number. Full
  design detail and the exact seam citations are in `docs/staffing/phase4-contracts.md` §5;
  read that section before starting.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_price.py tests/test_doctor_price.py`
- Review: independent review required after the oracle passes.
- Commit: `feat(staffing P4): add price command`

## Forbidden paths

Any file not listed in Owned paths above, including `terms.py`, `eligibility.py`,
`catalog.py`, `availability.py`, `crews.yaml`, `policy.yaml`, `docs/staffing/needs-lee.md`,
or any other CLI subcommand's code path in `doctor.py` beyond adding the new `price`
subparser and its handler function.

## Required evidence

- Full output of the Oracle command above (all tests passing).
- Full suite: `PYTHONPATH=src .venv/bin/python -m pytest -q` (report exact pass/fail counts).
- `.venv/bin/black --check` and `.venv/bin/ruff check` on every touched file.
- One live invocation against the real committed catalog and current availability snapshot
  for an `active` route from `config/staffing/routes.yaml`, both `--json` and text mode,
  pasted into your report.

## Stop / escalation condition

Stop and report back without guessing if `route_price`/`replacement_token_prices` cannot
resolve a price for some `active` catalog route (i.e. you would need to invent a fallback
price), or if you cannot find a clean single seam to compute the live badge without
duplicating `eligibility.py`'s badge-resolution logic in a way that could drift from it.
