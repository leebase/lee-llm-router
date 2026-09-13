# Packet S4-repair1 — make the unrouted-legacy-groups change Black-clean

- Kind: `impl`
- Declared size: 2 files, at most 20 changed lines
- Owned paths: `src/lee_llm_router/staffing/evidence_report.py`, `tests/test_staffing_evidence_report.py`
- Forbidden paths: everything else, explicitly including `src/lee_llm_router/doctor.py`
  and `tests/test_doctor_evidence_report.py`.
- Oracle: `python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py && python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py && python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py`
- Domain: none

## Context

Attempt `router-run-a04b0583a9bb485da6bd9e5990792fac` (packet
`docs/staffing/packets/S4-unrouted-legacy-groups.md`) implemented the routed/unrouted
split correctly — `pytest` passes 35/35 — but `python3 -m black --check` on the two
owned files reports "would reformat" for both files (two list-comprehension line-wrap
choices). The packet's own required evidence lists `black --check` and `ruff check` as
must-pass alongside pytest; this repair closes that gap only.

## Objective

Run `python3 -m black` (write mode) on exactly the two owned files so `black --check`
passes clean. Do not change any logic, control flow, string content, or test
assertions — formatting only. `ruff check` and the full owned-file pytest run must
stay green.

## Expected artifact

The same two files, reformatted only, committed to no branch (working tree edit).

## Required evidence

Run and report the exact output of, from the repo root:

```
python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py
```

All three must pass (black/ruff clean, pytest 0 failures) before reporting done.

## Stop / escalation condition

Stop and report back without guessing if satisfying `black --check` would require
changing anything beyond whitespace/line-wrapping, or would touch a forbidden file.

## Runtime bound

8 minutes.
