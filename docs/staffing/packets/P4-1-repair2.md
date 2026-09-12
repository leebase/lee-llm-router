# Packet P4-1-repair2 — finish the `price` command (wiring + tests only)

Your prior attempt (`docs/staffing/packets/P4-1-repair1.md`) correctly added
`src/lee_llm_router/staffing/price.py` (a `compute_price` function and `PriceResult`
dataclass) and a `_run_price` handler function in `src/lee_llm_router/doctor.py`. This is
good work — keep it as-is. Exactly two things are missing:

1. **The `price` subcommand is never registered.** `_run_price` exists but nothing calls
   `subparsers.add_parser("price", ...)`. Running `lee-llm-router price --help` currently
   fails with `invalid choice: 'price'`. Add a `price_parser` block in `main()` following the
   exact pattern of the neighboring `staff_parser` block (`src/lee_llm_router/doctor.py`,
   search for `staff_parser = subparsers.add_parser(`): arguments `--route` (required,
   metavar ROUTE_ID), `--input` (required, metavar N), `--output` (required, metavar N),
   `--cached` (optional, default None, metavar N), `--at` (optional ISO date, metavar DATE),
   `--availability-file` (optional, metavar PATH), `--catalog-dir` (optional, metavar PATH),
   `--json` (`action="store_true"`). End with `price_parser.set_defaults(func=_run_price)`.
   Give the subparser a one-line `help=` string describing what it does.
2. **No tests exist.** `tests/test_staffing_price.py` (unit tests for `compute_price` in
   `src/lee_llm_router/staffing/price.py`) and `tests/test_doctor_price.py` (CLI-level tests
   for the new `price` subcommand: argument parsing, exit codes, JSON vs text output, unknown
   route id, invalid `--at` date, negative/non-integer token counts) do not exist. Write
   both, covering: a known `active` route from `config/staffing/routes.yaml` computing a
   correct list/marginal price for given token counts; an unknown route id exiting 3 with a
   `price: ` stderr message; a missing/invalid `--at` date exiting 3; a negative or
   non-integer `--input`/`--output`/`--cached` exiting 3; `--cached` behavior when the
   resolved model has a cache-read rate versus when it does not (fail closed, per
   `docs/staffing/phase4-contracts.md` §5).

Do not modify `price.py`'s or `_run_price`'s actual logic unless writing the tests reveals a
genuine bug — if you find one, fix it minimally and say so in your report.

- Kind: `impl`
- Declared size: 3 files, at most 250 changed lines
- Owned paths: `src/lee_llm_router/doctor.py`, `tests/test_staffing_price.py` (new),
  `tests/test_doctor_price.py` (new)
- Oracle: `.venv/bin/pytest -q tests/test_staffing_price.py tests/test_doctor_price.py`
- Review: independent review required after the oracle passes.
- Commit: `feat(staffing P4): add price command`

## Forbidden paths

Any file not listed in Owned paths above, including `src/lee_llm_router/staffing/price.py`
(already correct — do not touch unless a genuine bug surfaces while writing tests, in which
case make the minimal fix and say so explicitly), `docs/staffing/needs-lee.md`, and every
other staffing module.

## Required evidence

- Full output of the Oracle command above (all tests passing).
- `PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor price --help` showing the new
  subcommand is registered.
- Full suite: `PYTHONPATH=src .venv/bin/python -m pytest -q` (report exact pass/fail counts).
- `.venv/bin/black --check` and `.venv/bin/ruff check` on every touched file.
- One live invocation against the real committed catalog and current availability snapshot
  for an `active` route from `config/staffing/routes.yaml`, both `--json` and text mode,
  pasted into your report.

## Stop / escalation condition

Stop and report back without guessing if wiring the subparser or writing the tests reveals
that `compute_price` cannot resolve a price for some `active` catalog route.
