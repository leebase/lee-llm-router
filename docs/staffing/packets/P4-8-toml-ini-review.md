# Review Packet — .toml/.ini owned-path extension mapping

Independent review (read-only). Author: real governed Auto-Orch run
(`/home/lee/projects/lee-llm-router-agent-orch-runs/ba56e712bfe2`), dispatched live through
Phase 4 P4-8's `staffing-proof` mission `auto` crew (chief-of-staff/decisions.md D215 ruling
5, gate item (b)), model `gpt-5.6-sol` via `codex_cli`, resolved through
`lee-llm-router staff --mode auto`.

## What to inspect

`git -C /home/lee/projects/lee-llm-router diff -- src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py tests/conftest.py`

## Background

The backlog item: map `.toml` and `.ini` owned-path extensions to the `yaml-config` language
class in `derive_class.py`'s `_EXTENSION_LANGUAGES` table, with tests — closing the gap
recorded in `docs/staffing/packets/evidence/D218-trial-review-gemini-flash.md`'s "Future
Concerns" section (the `.json` mapping's own review flagged `.toml`/`.ini` as the same
unresolved gap).

The governed run's own `evaluate` stage marked the cycle `failed`: a later
user-simulation-gate step reported the tester's claimed CLI exit codes (0) didn't match the
orchestrator's independently observed exit codes (1) for several commands. The supervisor
independently confirmed the actual code diff is correct and `tests/test_staffing_derive_class.py`
passes (28/28) and the full router suite is green (1717 passed, 1 skipped) — this review
exists to independently confirm that before the supervisor lands it despite the mission's own
cycle-level "failed" outcome (which reflects the user-simulation-gate discrepancy, not a
defect in this diff).

## Your job

1. Confirm the `.toml`/`.ini` -> `yaml-config` mapping is correct and matches the existing
   `.json`/`.yaml`/`.yml` mappings' pattern exactly.
2. Confirm the new tests actually exercise `.toml` and `.ini` paths (not just copy the `.json`
   tests with the extension swapped without changing anything meaningful).
3. Confirm `tests/conftest.py`'s addition (inserting `src/` onto `sys.path` if absent) is
   genuinely harmless and doesn't change any existing test's behavior — it should only matter
   when `PYTHONPATH` isn't already set externally.
4. Run `.venv/bin/python -m pytest -q tests/test_staffing_derive_class.py` and the full suite
   yourself; don't just trust the numbers above.
5. Confirm no other file was touched by this diff.

Report `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT` with Contract-blocking /
Hardening / Future findings.
