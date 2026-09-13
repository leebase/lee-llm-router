# Packet S3 — independent review of the structural anti-loop change (S1 + S2)

- Kind: `review`; Class: `review/judge/concurrency/m/python`; Owned paths: none (read-only).
- Scope: lee-llm-router `f5c63b3` (S2), `b7543c9` (S1) and `8efd6fd` (review dispatch bounds, your finding 5).
  (S1, watchdog stall/no-progress kills, run/CLI plumbing, tests). Authority: Lee 2026-09-13
  ("/supervise should make 'activity ≠ progress' structural"; preserve the 79 s kill of a dead
  transport).

## Judge (ACCEPT/REJECT each, with what you reproduced)
1. Watchdog semantics: `stall_action="kill"` kills at exactly `stall_seconds` of joint silence;
   `progress_seconds` kills when watch dirs are unchanged regardless of output; a watch-dir
   change resets the progress clock; `"warn"` reproduces the old behaviour; the ceiling still
   kills; `kill_reason` is correct in each branch. Run `tests/test_watchdog.py`.
2. Run plumbing: kills of any kind yield exit 124, `timed_out=True`, `failure_class`
   `platform_timeout` (schema untouched — confirm no enum change), and a provenance note
   `dispatch kill: <kind> after <N> s (…)`; the registry deregisters on every kill path. Run
   `tests/test_staffing_run.py -k "stall or progress or ceiling or timeout"`.
3. CLI: `--stall-minutes`, `--progress-minutes` (0 disables), `--stall-action` exist with the
   stated defaults (10 / 20 / kill) and reach `dispatch_route`.
4. Shim: every rendered target carries `--timeout`, `--stall-minutes`, `--progress-minutes`
   in the step-6 command; a stall/no-progress `platform_timeout` is handled as a hung worker
   with exactly one narrowed repair then escalation; the poll rule adds the past-bound census
   check; the provider-binary guard still passes. Run `tests/test_shims_parity.py`.
5. Anything that would let a worker run past its bound, or let a supervisor re-dispatch an
   unchanged packet after a stall kill, is contract-blocking.
End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not run the full suite. Do not
edit, commit, stash, install shims, or write any file.
