# Packet S5 — `run` refuses an unchanged re-dispatch after a stall/no-progress kill

- Kind: `impl`; Class: `impl/deterministic/concurrency/s/python`; Declared size: 2 files, ≤ 220 lines
- Owned paths: `src/lee_llm_router/staffing/run.py`, `tests/test_staffing_run.py`
- Forbidden: everything else (`doctor.py`, schema, shims, `failure.py`, `next_action.py`).
- Runtime bound: 25 minutes. Oracle: `python3 -m pytest -q tests/test_staffing_run.py`
- Authority: Lee 2026-09-13 ("activity ≠ progress structural, not something you have to remember
  to put in prompts"); D229. Observed 2026-09-14 17:27Z: the router killed a Flash worker on M1
  at the 10-min stall bound (attempt with note `dispatch kill: stall after 600.383 s`), and the
  supervising session re-dispatched the **identical** packet (same `packet_id`
  `…5f5a7620501e`, same route, same owned paths, same `--timeout`) — the shim's "never
  re-dispatch unchanged" rule was ignored. The rule must live in the router.

## Rule (implement exactly)

Before registration, `run` reads the per-host attempt ledger (`read_attempts(resolve_attempts_path())`,
already imported in this module) and finds the most recent attempt whose `packet_id` equals this
dispatch's packet sha **and** whose `router_event.route_id` equals the chosen route. If that attempt
has `failure_class == "platform_timeout"` **and** its `provenance.notes` contains a
`dispatch kill: stall` or `dispatch kill: no_progress` line, then this dispatch is refused with
exit 3 (`RunSelectionError`, kind `"unchanged_redispatch"`, message naming the prior attempt id and
the kill kind) **unless at least one of these differs from that attempt**: the packet text
(different sha — the normal case after a narrowed packet), the owned-path set, or a strictly
smaller `--timeout` than the prior attempt's ceiling, or `--parent <that attempt id>` with an
`--escalation-reason` (an explicit, recorded escalation on the same route). A ceiling kill
(`dispatch kill: ceiling`) does not trigger the refusal (that is slowness, handled by the shim's
one-repair rule), and neither does any non-timeout failure. The check is read-only, tolerant of a
missing/empty ledger (no ledger → no refusal), and must run before any process launches or any
registry write. Record the prior attempt id on the refusal's stderr.

## Tests

In `tests/test_staffing_run.py`: seed a ledger with a stall-killed attempt for packet P on route R;
(a) identical re-dispatch → exit 3, nothing launched, no registry write, stderr names the prior
attempt and `stall`; (b) same with `no_progress`; (c) changed packet text → proceeds; (d) same
packet with smaller `--timeout` → proceeds; (e) `--parent <id> --escalation-reason …` → proceeds;
(f) prior kill kind `ceiling` → proceeds; (g) empty ledger → proceeds; (h) different route →
proceeds. Use the existing `_run_cli`/LaunchRecorder fixtures.

## Required evidence

Oracle output; `python3 -m black --check` and `ruff check` on both files; `git diff --stat`. Do not
commit. Do not stash. Do not write `decisions.md`.
