# Packet S4-repair3 — last line of the Black formatting fix (escalation, 2nd ladder rung)

- Kind: `impl`
- Declared size: 1 file, at most 5 changed lines
- Owned paths: `tests/test_staffing_evidence_report.py`
- Forbidden paths: everything else, explicitly including
  `src/lee_llm_router/staffing/evidence_report.py`, `src/lee_llm_router/doctor.py`,
  and `tests/test_doctor_evidence_report.py`.
- Oracle: `python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py && python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py && python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py`
- Domain: none

## Context (verified facts only)

Two prior repairs (`router-run-015ffe8e8b9346f1b8a0e9f13f3f06fb`, ceiling timeout;
`router-run-a01ec8f4f0d5444a81141cf75d5dceb3`, oracle still failing) narrowed this
down. The supervisor ran `python3 -m black --diff tests/test_staffing_evidence_report.py`
directly just now and confirmed exactly one hunk remains:

```
@@ -874,13 +874,11 @@
 ) -> None:
     """The dict path keeps its existing order and group fields."""
     routed = _record(
         route_id="route-json", class_key="routed-json", attempt_id="routed-json-1"
     )
-    legacy = _record(
-        route_id=None, class_key="legacy-json", attempt_id="legacy-json-1"
-    )
+    legacy = _record(route_id=None, class_key="legacy-json", attempt_id="legacy-json-1")
     monkeypatch.setattr(
```

## Objective

In `tests/test_staffing_evidence_report.py`, find the `legacy = _record(...)`
call that currently spans three lines (the one right after
`routed = _record(route_id="route-json", ...)` inside
`test_build_evidence_report_classes_json_is_unchanged_for_legacy_groups`) and
collapse it onto one line exactly as:
`    legacy = _record(route_id=None, class_key="legacy-json", attempt_id="legacy-json-1")`
Change nothing else in the file — no other line, no test logic, no assertions.

## Required evidence

Run and report the exact output of, from the repo root:

```
python3 -m black --check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
python3 -m ruff check src/lee_llm_router/staffing/evidence_report.py tests/test_staffing_evidence_report.py
python3 -m pytest -q tests/test_staffing_evidence_report.py tests/test_doctor_evidence_report.py
```

All three must pass (black/ruff clean, pytest 0 failures) before reporting done.

## Stop / escalation condition

Stop and report back without guessing if the described line is not found as
described, or if collapsing it does not make `black --check` pass clean.

## Runtime bound

8 minutes.
