# Repair packet P4-5c-repair1 — write the required tests (no new production code)

The first P4-5c dispatch correctly implemented `resolve_artifacts_dir`, `_persist_worker_output`,
and `_parse_judge_verdict` in `src/lee_llm_router/staffing/run.py`, and the additive schema
change in `config/staffing/schema/attempt-record.schema.json`, but wrote **zero tests** for any
of that new behavior — the only change to `tests/test_staffing_run.py` was adding an
`LEE_LLM_ROUTER_ARTIFACTS_DIR` env var to the shared `scratch_state` fixture, which no test
actually uses yet. The oracle (`pytest tests/test_staffing_run.py -q`) passed only because it
never exercised the new code paths, not because they are proven correct.

A supervisor fix (not part of this repair) also rewrote `_parse_judge_verdict` after a live
dispatch showed it never matched: the original required the marker to be the literal last line
of `stdout.splitlines()`, but a `pi`/`agy`-harness dispatch's captured stdout is a raw JSON event
stream where the worker's real final text is embedded inside a JSON string field followed by
wire-format closing tokens, so the marker is never literally the last line. The fixed version
(already in `run.py` — read it before writing tests, do not revert it) matches the **last
occurrence** of the exact substrings `"REVIEW VERDICT: ACCEPT"` / `"REVIEW VERDICT: REJECT"`
anywhere in `stdout` via `str.rfind`, comparing the two match positions to pick the later one;
`None` if neither substring appears.

- Kind: `impl` (test-only repair)
- Declared size: 1 file, at most 150 changed/added lines
- Owned paths: `tests/test_staffing_run.py` only. Do not touch `run.py`, the schema file, or
  `tests/test_staffing_attempt_record.py` — they are correct and out of scope for this repair.
- Write tests proving exactly these five behaviors (reuse the existing `scratch_state` fixture
  and whatever `build_attempt_record`/`dispatch_route` test-construction helpers this file
  already has for constructing a fake `DispatchOutcome`/`SelectionOutcome` — do not duplicate
  fixture machinery that already exists in this file):

  1. A successful attempt writes the worker's exact `dispatch.stdout` / `dispatch.stderr` text
     to `<artifacts-dir>/<attempt_id>/stdout.txt` and `.../stderr.txt` (byte-for-byte, no
     truncation), and the record's `provenance["worker_output_dir"]` equals that exact
     directory path as a string. Use the `scratch_state` fixture's `artifacts` path (already
     wired to `LEE_LLM_ROUTER_ARTIFACTS_DIR` by the prior dispatch) to locate where to look.
  2. A role-`review` (or `judge`) attempt whose `dispatch.stdout` contains
     `"REVIEW VERDICT: ACCEPT"` as (or within) its final content records `verdict ==
     "judge_pass"` on the built record — construct a stdout value that plausibly mimics a raw
     JSON-event-stream harness (the marker text followed by trailing JSON/closing punctuation,
     not just a bare last line) to prove the `rfind`-based fix actually handles that shape, not
     only the simpler exact-last-line case.
  3. The `"REVIEW VERDICT: REJECT"` case records `verdict == "judge_fail"`.
  4. A role-`review` attempt whose `dispatch.stdout` has no such marker falls back to the
     existing oracle-derived `verdict` (`pass`/`fail`/`unverified`) completely unchanged.
  5. A role outside `review`/`judge` (e.g. `impl`) is completely unaffected even when its
     `dispatch.stdout` happens to contain the marker text — `verdict` must still be the plain
     oracle-derived value, never overridden.
  6. An artifacts-directory write failure (e.g. point `LEE_LLM_ROUTER_ARTIFACTS_DIR` at a path
     that cannot be created/written — a file where a directory is expected, or an unwritable
     permission bit) does not raise out of `build_attempt_record` and does not prevent the
     record from being built: `provenance["worker_output_dir"]` is `None` and `provenance
     ["notes"]` contains an entry naming the failure.

- Oracle: `env PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_run.py -q`
- Review: independent review required after the oracle passes.
- Commit: none yet — this repair lands in the same commit as the original P4-5c implementation.

## Forbidden paths

Any file not `tests/test_staffing_run.py`. Do not modify `run.py`'s already-correct
`_parse_judge_verdict`/`_persist_worker_output`/`resolve_artifacts_dir` to make a test pass —
if a test seems to require a production-code change, stop and report which one and why rather
than guessing.

## Required evidence

- `env PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_run.py -q` — report exact
  pass count including the new tests.
- `env PYTHONPATH=src .venv/bin/python -m pytest -q` (full suite) — report exact pass/fail
  counts.
- `.venv/bin/black --check tests/test_staffing_run.py` and `.venv/bin/ruff check
  tests/test_staffing_run.py`.

## Stop / escalation condition

Stop and report back without guessing if any of the six required behaviors cannot be tested
without also changing `run.py`'s already-fixed functions (which are out of scope for this
repair).
