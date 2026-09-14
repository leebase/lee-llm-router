# Packet S5b — `run` refuses an unchanged re-dispatch after a stall/no-progress kill (corrected seams)

Supersedes S5 (a Sol worker correctly stopped on it: the pre-registration point is in
`doctor.py`, and attempt records do not carry owned paths). Corrections: `doctor.py` is owned;
the comparison drops owned paths.

- Kind: `impl`; Class: `impl/deterministic/concurrency/s/python`; Declared size: 3 files, ≤ 260 lines
- Owned paths: `src/lee_llm_router/staffing/run.py`, `src/lee_llm_router/doctor.py` (the `run`
  handler only, before its `register_run` call), `tests/test_staffing_run.py`
- Forbidden: everything else (schema, shims, `failure.py`, `next_action.py`, other subcommands).
- Runtime bound: 25 minutes. Oracle: `python3 -m pytest -q tests/test_staffing_run.py`
- Authority: Lee 2026-09-13 (activity ≠ progress must be structural); D229. Observed 2026-09-14:
  a stall-killed packet was re-dispatched with the same sha on the same route (the bounds were
  halved that time, which is allowed; a re-dispatch with nothing changed must be impossible).

## Rule (implement exactly)

In the `run` handler, **before** `register_run` and before any process launch: read the per-host
ledger via `lee_llm_router.staffing.ledger.read_attempts(resolve_attempts_path())` (import it; a
missing or empty ledger means no refusal). Find the most recent attempt with the same `packet_id`
(this dispatch's `sha256:` of the packet text) **and** the same `router_event.route_id` as the
chosen route. If that attempt has `failure_class == "platform_timeout"` and a
`provenance.notes` line starting `dispatch kill: stall` or `dispatch kill: no_progress`, refuse
with exit 3 and stderr
`run: refused — unchanged re-dispatch of <packet_id> on <route_id> after a <stall|no_progress> kill (attempt <id>); change the packet, lower --timeout below <prior ceiling>, or escalate with --parent/--escalation-reason`
**unless** one of: this dispatch's `--timeout` is strictly smaller than that attempt's recorded
ceiling (parse the `ceiling <C> min` figure from that same note), or `--parent <that attempt id>`
is given with `--escalation-reason`. A `dispatch kill: ceiling` prior does not trigger the rule;
neither does any other failure class. Put the decision in a pure function in `run.py`
(`unchanged_redispatch_refusal(attempts, packet_id, route_id, timeout_seconds, parent) -> str | None`)
and call it from `doctor.py`; the JSON `--json` error object gets `"kind": "unchanged_redispatch"`.

## Tests (must fail on the unchanged tree)

Unit tests for the pure function: stall prior → refusal; no_progress prior → refusal; ceiling
prior → None; other route → None; smaller timeout → None; parent+reason → None; empty ledger →
None; most-recent-wins when an older stall exists but the latest attempt on that packet/route
succeeded → None. One CLI test with the existing `_run_cli` fixture: seed a ledger file with a
stall-killed attempt, run identical args → exit 3, nothing launched, no registry file written,
stderr contains `unchanged re-dispatch`.

## Required evidence

Oracle output before (new tests failing) and after; black/ruff on the three files; `git diff --stat`.
Do not commit, stash, or write `decisions.md`.
