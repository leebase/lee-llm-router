# Packet M3-3-review — independent review of the uncommitted run --instance diff

Kind: review
Declared size: 4 files, approximately 800 changed/added lines
Owned paths: src/lee_llm_router/staffing/run.py, src/lee_llm_router/doctor.py, tests/test_staffing_run.py, tests/test_doctor.py
Oracle: none (judge review; verdict is the deliverable)
Review: n/a (this is the review)

The owned paths above are registered for conflict-freedom only — this is a
read-only review; write nothing.

Runtime bound: 25 minutes.

- Scope: the **uncommitted** diff in `/home/lee/projects/lee-llm-router` limited to
  `src/lee_llm_router/staffing/run.py`, `src/lee_llm_router/doctor.py`,
  `tests/test_staffing_run.py`, and `tests/test_doctor.py` (`git diff -- <those four>`). Ignore
  every other file, including untracked files elsewhere in the repo.
- Packet under review: `docs/staffing/packets/M3-3-run-instance-selection.md`; plan:
  `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md` (milestone M3, per the
  M3 design ruling, 2026-09-14). M1/M2/M3-1/M3-2 are already committed and must not appear
  changed in this diff.

## Judge (ACCEPT/REJECT, with what you reproduced)

1. `SelectionOutcome` gained an additive `channel_instance: str | None = None` field. Confirm
   both branches of `select_route()` (explicit `--route`, and the no-`--route`
   cheapest-eligible fallback) set it via the new `_resolve_channel_instance()` helper, using
   the already-computed `EligibilityRow`'s `instance_headrooms` — no second eligibility
   evaluation was added.
2. Without `--instance`: confirm the resolved instance is the *first* entry in
   `instance_headrooms` whose `eligible` is `True`, even when that entry is not first in
   supply order — reproduce this against a two-instance fixture yourself, not just by reading
   the loop. Confirm `channel_instance` is `None` when `instance_headrooms` is empty
   (non-subscription channel) or when no instance is eligible.
3. With `--instance ID`: confirm three failure paths, each `RunSelectionError` with
   `exit_code == 3` and **nothing launched or recorded** (no dispatch, no run-registry entry, no
   ledger append) — reproduce at least one CLI-level case yourself, not just the unit-level
   exception: (a) the route's channel has no instance concept (`instance_headrooms` empty) and
   `--instance` was still given; (b) `ID` does not match any entry in `instance_headrooms`
   (covers both a genuinely unknown id and a *disabled* instance, since M3-1 excludes disabled
   instances from `instance_headrooms` entirely); (c) `ID` matches an entry but that entry's
   `eligible` is `False` (e.g. at D216 reserve) — confirm the raised message cites that
   instance's own `reasons`.
4. Confirm `build_attempt_record()`'s `"route"` dict gained exactly one additive key,
   `"channel_instance": outcome.channel_instance`, and that every other route-dict key
   (`model`/`effort`/`harness`/`channel`/`provider`) is unchanged. Confirm the now-dead
   `run_json_record()` function was **not** touched (it has no callers besides its own export;
   out of scope for this packet — flag it as a defect if the diff did touch it).
5. Confirm the CLI wiring in `doctor.py`: the new `--instance` argument defaults to `None` and
   is threaded into `select_route(...)` as `instance_id=getattr(args, "instance", None)`, with
   no other behavior change to `_run_run()`'s existing argument handling.
6. Confirm a channel with **no declared `instances`** in `channels.yaml` (the implicit
   single-instance case) still resolves `channel_instance` to that implicit instance id
   (equal to the channel id) when the channel is a subscription channel, and that this is
   covered by a test — reproduce it.
7. Confirm no route-selection arithmetic changed (which route wins is untouched) — this diff
   only resolves *which instance of the already-chosen route*. Confirm the diff does not touch
   `eligibility.py`, `block.py`, `staff.py`, credential staging, or dispatch argv construction
   (`build_dispatch_command`) — all M4 concerns, out of scope here.

## Evidence you must reproduce yourself

```bash
cd /home/lee/projects/lee-llm-router
git status --short
git diff --stat -- src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_run.py tests/test_doctor.py -q
.venv/bin/black --check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
.venv/bin/ruff check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
```

Report exact pass/fail counts. End with the literal line `REVIEW VERDICT: ACCEPT` or
`REVIEW VERDICT: REJECT`, and if REJECT, name the exact defect and which owned file/line it is
in.
