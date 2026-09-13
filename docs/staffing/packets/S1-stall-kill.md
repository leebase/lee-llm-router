# Packet S1 — "activity ≠ progress" becomes structural in `lee-llm-router run`

- Kind: `impl`
- Class: `impl/deterministic/concurrency/m/python`
- Declared size: 5 files, at most 450 changed lines
- Owned paths: `src/lee_llm_router/watchdog.py`, `src/lee_llm_router/staffing/run.py`,
  `src/lee_llm_router/doctor.py` (the `run` subparser and its `dispatch_route(...)` call only),
  `tests/test_watchdog.py`, `tests/test_staffing_run.py`
- Forbidden paths: everything else — `config/staffing/schema/*` (do not add failure-class enum
  values), `staffing/failure.py`, `staffing/next_action.py`, templates, other CLI subcommands.
- Authority: Lee, 2026-09-13: "/supervise should make 'activity ≠ progress' structural rather
  than something you have to remember to put in prompts. … Preserve [the 79-second termination
  of a dead transport]." Today `StallWatchdog` only *warns* on stall (`watchdog.py` module
  docstring: "a stall never kills"; only `max_seconds` kills). A worker that hangs silently, or
  that streams tokens while never touching its owned files, runs until the ceiling.

## Changes

1. **`watchdog.py`** — `StallWatchdog.__init__` gains `stall_action: str = "warn"` (`"warn"` |
   `"kill"`) and `progress_seconds: float | None = None`. Semantics:
   - *Stall* (existing): no output bytes **and** no watch-dir change for `stall_seconds`. With
     `stall_action="kill"`, `observe()` returns `Verdict.KILLED` on the first stalled tick
     (still firing `on_stall` once before). With `"warn"`, today's behaviour is unchanged.
   - *No progress* (new): the watch-dir signature has not changed for `progress_seconds`
     **regardless of output**. When `progress_seconds` is set and exceeded, `observe()` returns
     `Verdict.KILLED`. Output alone never resets the progress clock; a watch-dir change does.
     With no watch dirs, the progress clock is inactive (nothing to measure — document it).
   - `SupervisedResult` gains `kill_reason: str | None` ∈ {`"ceiling"`, `"stall"`, `"no_progress"`, None}.
     `run_supervised` sets it from the verdict that killed. Keep the ceiling as the absolute bound.
   Update the module docstring: a stall or no-progress verdict now kills when configured; the
   ceiling always kills. Tests: `stall_action="kill"` kills at exactly `stall_seconds`;
   output-only activity with a stale watch dir kills at `progress_seconds`; a watch-dir touch
   resets the progress clock; `"warn"` still never kills; `kill_reason` is right in each case.

2. **`run.py`** — thread the three settings through `run_supervised_dispatch(...)` and
   `dispatch_route(...)` as `stall_minutes`, `progress_minutes: float | None`, `stall_action`.
   `DispatchOutcome` gains `kill_reason: str | None`. A stall-kill or no-progress-kill must
   produce the same exit code as the ceiling kill (`_TIMEOUT_EXIT_CODE`, 124) so `timed_out` is
   true and `_failure_class` yields `platform_timeout` unchanged (the schema's five proven
   values stay; do not add one). Add to the attempt's `provenance.notes` a line
   `"dispatch kill: <ceiling|stall|no_progress> after <N> s (stall <S> min, progress <P> min, ceiling <C> min)"`
   so the report can tell the three apart. Defaults: `stall_minutes` = existing
   `DEFAULT_STALL_MINUTES` (10), `stall_action="kill"`, `progress_minutes=20.0`. The watch
   dirs are the run's `--owned-paths` (already `watch_dirs` today — confirm and cite the line).

3. **`doctor.py` `run` subparser** — add `--stall-minutes N` (float, default 10), `--progress-minutes N`
   (float, default 20; `0` disables), `--stall-action {kill,warn}` (default `kill`); pass them to
   `dispatch_route`. Help text must state the rule in one line each.

4. **Tests in `tests/test_staffing_run.py`** — extend the existing ceiling-kill tests' fixtures:
   a worker that sleeps silently is killed at `--stall-minutes` (use a small value via the
   CLI, e.g. `--stall-minutes 0.02`) with exit 124, `failure_class == "platform_timeout"`, the
   provenance note says `stall`; a worker that prints every 0.2 s but writes no owned file is
   killed at `--progress-minutes 0.03` with the note saying `no_progress`; a worker that writes
   an owned file every tick survives the progress clock and ends normally; `--stall-action warn`
   reproduces today's behaviour. The run registry must be deregistered on every kill path (see
   `test_run_deregisters_on_ceiling_timeout`).

## Oracle

`python3 -m pytest -q tests/test_watchdog.py tests/test_staffing_run.py`

## Required evidence

Oracle output (exact counts); `python3 -m black --check` and `python3 -m ruff check` on the
five owned files; `lee-llm-router run --help | grep -A2 stall`; one live proof: a temp catalog
dir (copy `config/staffing`) whose one active route has a harness whose binary you shadow on
PATH with a script that `sleep 3600`s (do not touch real binaries or the real catalog), run
`lee-llm-router run … --stall-minutes 1 --timeout 600 --catalog-dir <tmp>` and paste the
attempt record showing exit 124 within ~60–70 s and the `dispatch kill: stall` note. End with a
short report. Do not commit. Do not stash. Do not write `decisions.md`.
