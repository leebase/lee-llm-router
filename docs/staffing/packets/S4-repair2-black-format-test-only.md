# Packet S4-repair2 — finish the Black formatting fix (escalation, next ladder rung)

- Kind: `impl`
- Declared size: 1 file, at most 10 changed lines
- Owned paths: `tests/test_staffing_evidence_report.py`
- Forbidden paths: everything else, explicitly including
  `src/lee_llm_router/staffing/evidence_report.py`, `src/lee_llm_router/doctor.py`,
  and `tests/test_doctor_evidence_report.py`.
- Oracle: `python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py && python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py && python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py`
- Domain: none

## Context (verified facts only, inherited from the prior attempt's own story)

Attempt `router-run-a04b0583a9bb485da6bd9e5990792fac` implemented the routed/unrouted
split correctly (pytest 35/35) but left both owned files failing `black --check`.
Repair attempt `router-run-015ffe8e8b9346f1b8a0e9f13f3f06fb` (same route, 8-minute
ceiling) was killed by its timeout (`platform_timeout`, ceiling kill, not stall or
no-progress) but before the kill it had already reformatted
`src/lee_llm_router/staffing/evidence_report.py` to pass `black --check` clean —
confirmed directly by the supervisor running `black --check` on the current working
tree. Only `tests/test_staffing_evidence_report.py` still reports "would reformat".
This escalation packet is scoped to that one remaining file only; do not touch
`evidence_report.py` — it is already correct and is a forbidden path for this packet.

## Objective

Run `python3 -m black` (write mode) on exactly `tests/test_staffing_evidence_report.py`
so `black --check` on both files (the already-clean impl file and this test file)
passes clean together. Do not change any logic, assertions, or test behavior —
formatting only.

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
changing anything beyond whitespace/line-wrapping in the owned file, or would touch
a forbidden file.

## Runtime bound

10 minutes.
