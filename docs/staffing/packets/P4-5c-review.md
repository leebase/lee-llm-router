# Review packet — P4-5c (persist worker output per attempt; parse judge/review verdicts)

- Kind: `review`
- Author route (excluded from this review for independence): `agy-gemini-3-8-flash-high-gemini-sub`
- Diff to review: `git -C /home/lee/projects/lee-llm-router diff -- src/lee_llm_router/staffing/run.py tests/test_staffing_run.py config/staffing/schema/attempt-record.schema.json tests/test_staffing_attempt_record.py`

## What changed

`src/lee_llm_router/staffing/run.py` now: (1) writes the worker's captured `DispatchOutcome.stdout`/`.stderr`
verbatim to `<artifacts-root>/<attempt_id>/stdout.txt` and `.../stderr.txt` via a new
`_persist_worker_output()` helper, resolving the artifacts root through a new
`resolve_artifacts_dir()` following the same explicit -> file-env-var -> root-env-var -> default
precedence already used by the attempts/availability/runs state directories, and recording the
resulting path (or `None` on any `OSError`, fail-open) in `provenance["worker_output_dir"]`;
(2) for a `review`/`judge`-role attempt (`_INDEPENDENCE_APPLICABLE_ROLES`, imported from
`lee_llm_router.doctor`), scans the worker's stdout for a final non-blank line matching exactly
`REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT` and, when present, overrides the recorded
`verdict` field to `"judge_pass"`/`"judge_fail"` instead of the oracle-derived value. Two new
enum values (`judge_pass`, `judge_fail`) were added to the schema's `canonicalVerdict` enum
(additive) and a new optional `worker_output_dir` property was added to the shared
`$defs/provenance` object (additive, not required). `tests/test_staffing_run.py` and
`tests/test_staffing_attempt_record.py` were updated accordingly (the latter's
`test_v2_verdict_vocabulary_is_canonical` legitimately extended to the five-value enum — a
supervisor fix after the full suite surfaced it, not part of the original worker diff).

## Requirements to verify

1. Every change is additive: a `router_run` attempt for a role outside `review`/`judge`, or one
   whose stdout has no `REVIEW VERDICT:` marker, must be byte-for-byte unaffected in its
   `verdict` field (still `pass`/`fail`/`unverified` from `_oracle_verdict`).
2. `_parse_judge_verdict` only matches when `REVIEW VERDICT: ACCEPT`/`REJECT` is the **final
   non-blank line** of stdout — a worker that discusses or quotes the marker text earlier in
   its output must not trigger a false match.
3. `_persist_worker_output` never raises past `build_attempt_record`: an artifacts-directory
   write failure must still let the run complete and the ledger record land, with
   `provenance["worker_output_dir"] == None` and a `notes` entry naming the failure.
4. The `attempt_id` used for the artifacts directory name is exactly
   `record["attempt_id"]` — never a different id.
5. The schema change is genuinely additive: `worker_output_dir` is optional, not required, and
   the shared `$defs/provenance` object (referenced by every record kind via `$ref`) is the
   only place edited — check there is no now-broken record-kind-specific provenance shape.
6. Scope confinement: only the four files named in "Diff to review" above are modified — flag
   anything else (including any stray file outside owned paths) as Blocking.
7. Import direction: `run.py` importing `_INDEPENDENCE_APPLICABLE_ROLES` from `doctor.py` (a
   private, underscore-prefixed name, and normally the CLI-layer module) is unusual layering;
   note it as Hardening (not Blocking, since it does not create a circular import in practice —
   `doctor.py` only imports `staffing.run` lazily inside a function body) unless you find it
   actually breaks an import order somewhere.

## Oracle (run yourself; do not trust a summary)

    cd /home/lee/projects/lee-llm-router && env PYTHONPATH=src .venv/bin/python -m pytest -q

Expect: 1705 passed, 1 skipped (the full suite, not just the touched files).

## Required output

End your response with a final line exactly `REVIEW VERDICT: ACCEPT` or
`REVIEW VERDICT: REJECT`, plus a classification of any findings as Blocking, Hardening, or
Future (say "none" for empty categories).
