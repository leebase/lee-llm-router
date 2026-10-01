# Independent review: native launch/accounting owner repair

**Reviewer:** Root (independent, author AstraLow excluded)
**Scope:** `src/lee_llm_router/staffing/run.py` (native `safe_popen`/`run_supervised_dispatch`
OSError delta), `tests/test_staffing_executor.py` (E2BIG/ENOENT coverage),
`docs/staffing/protected-executor.md` (latest section). No tools used; evaluated only
against the supplied source snapshot, as instructed.

## Verdict: PASS (scoped)

## What was checked against acceptance criteria

1. **Exception attribution is identity-scoped, not type-scoped.** `safe_popen` captures
   the exact `OSError` instance it raised into `nonlocal launch_error`. The outer handler
   re-raises anything that is `is not launch_error` (run.py, except block). This is the
   correct shape to satisfy "do not catch a post-launch unrelated OSError and falsely
   claim no provider started" — any OSError raised later in the dispatch window by
   something other than the captured popen call is a different object and is propagated,
   not swallowed.

2. **No duplicate provider start.** The failure path returns before `run_supervised_dispatch`
   can proceed past the raised exception; `test_actual_cli_binding[e2big]` and `[enoent]`
   assert `len(launch_calls) == 1` and `not launcher.processes`, confirming single-attempt,
   no-retry behavior ("no real oversized provider retry").

3. **No leak of argv/prompt/credential.** `diagnostic = f"native launch failed: OSError
   errno={exc.errno}"` uses only `errno`, never `exc.strerror`/`exc.filename`/`str(exc)`.
   The test injects `OSError(native_errno, "SECRET prompt credential", "SECRET argv")`
   and asserts `"SECRET" not in captured.out + captured.err` — this is an actual negative
   check against the sensitive fields, not just an assumption.

4. **Accounted parent finish, unknown cost/usage, actual duration.** `duration_seconds =
   clock_fn() - started` is a real measured interval (test's fake monotonic `clock()`
   confirms `record["wall_clock_ms"]` matches `clock_ticks[-1] - clock_ticks[0]`). Usage
   dict sets `"basis": "unavailable"` with all token fields `None` — never inferred zero.
   Journal events assert `["start", "finish"]`, `events[1]["accounted"] is True`, matching
   "no fake attempt / no reset" of the parent reservation.

5. **Docs consistency.** `docs/staffing/protected-executor.md`'s native-failure section
   (exit 127, errno-only diagnostic, no retry, unavailable usage/cost, accounted parent
   finish, distinction from an unhandled router crash) matches the code and test behavior
   exactly; no doc/code drift found.

## Scoped limitations (not blocking, explicitly out of this review's visibility)

- `run_supervised_dispatch`'s internal body was not included in the snapshot. The
  identity-match protection in run.py only holds if that function does not itself catch
  the `OSError` raised by `popen_fn` and re-raise a *new* exception object (which would
  both defeat the `is launch_error` check and, worse, propagate uncaught instead of
  producing the schema-2 `DispatchOutcome`). This review cannot confirm or deny that from
  the supplied delta and flags it as an unverified assumption, not a finding against the
  owned files.
- `DispatchOutcome`'s class definition (source of `cost={"basis":["unavailable"]}` and
  `verified_success=False` defaults) was not supplied; the constructor call in the
  provided delta does not pass these fields explicitly, so their correctness rests on the
  test assertions alone, consistent with the review's authorization to trust OR1
  (bootstrap/executor foundation already passed) rather than re-derive it.
- Degenerate case `exc.errno is None` (legal for some `OSError` constructions) would
  render `"errno=None"` in the diagnostic — not a leak, cosmetically odd only; not worth
  blocking.

## Out of scope / not accepted here

Per the task boundary, this review does not accept the Staff-consumer/customer journey
or any of the three new unknown-mode-label regressions (parent C5, separately
Chief-owned). No repairs or provider-dispatch changes were made by this review.

## Evidence basis

Reviewed only the three supplied source excerpts; relied on Root's independently stated
observation of 45 executor tests passing in 4.10s (including the mocked native
error/accounted-finish path) as given, not re-run here (no tools permitted/used).
