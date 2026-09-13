# Packet S2 — `/supervise` shim: bounded runtime, stall/no-progress as a first-class failure, one repair then escalate

- Kind: `impl`
- Class: `impl/deterministic/none/s/markdown`
- Declared size: 3 files, at most 200 changed lines
- Owned paths: `src/lee_llm_router/templates/shims/supervise.md.tmpl`, `tests/test_shims_parity.py`,
  `docs/staffing/supervise-antiloop.md` (new, short)
- Forbidden paths: everything else, including `crew.md.tmpl`, `shims.py`, any `src/lee_llm_router/staffing/*`.
- Authority: Lee 2026-09-13 (see S1). The router (S1, running in parallel) is adding
  `--stall-minutes`, `--progress-minutes`, `--stall-action` to `lee-llm-router run`, killing a
  worker on joint silence or on no owned-file change, recorded as `platform_timeout` with a
  provenance note `dispatch kill: <ceiling|stall|no_progress> …`. This packet makes the
  supervisor use them so the anti-loop rule is structural, not remembered.

## Changes to `supervise.md.tmpl`

1. **Step 2 (packetize):** every packet declares a **runtime bound in minutes** next to its
   oracle; a packet without one is not dispatchable.
2. **Step 6 (dispatch):** the `run` command always carries `--timeout <bound×60>`,
   `--stall-minutes 10`, `--progress-minutes 20` (or the packet's own smaller values), never
   omitted. Say in one sentence why: "activity is not progress; a worker that streams without
   touching its owned files is killed by the router, not by the supervisor noticing."
3. **Step 8 (classify):** a `platform_timeout` whose provenance note says `stall` or
   `no_progress` is a *hung or looping worker*, not slowness: the supervisor never re-dispatches
   the same packet unchanged. Step 9's single repair for this case is one of: halve the packet,
   or tighten the owned paths/oracle, or pass a smaller `--timeout`; then dispatch once; if it
   times out again for any kind, escalate up the ladder immediately.
4. **Dispatch pattern:** keep the detached start + ≤90 s poll text; add: if a poll shows the
   log without `done=` past the packet's bound plus 5 minutes, run `lee-llm-router census --json`
   and report the live run instead of waiting further (the router's own kill will land; the
   supervisor never kills processes itself).
5. **Doctrine guardrails:** add a quoted line: "Activity ≠ progress. A hung worker is
   terminated by the router within its stall bound; a supervisor that waits past the bound is
   the loop." Keep the hard command boundary (six router commands only) unchanged.

## `tests/test_shims_parity.py`

Extend `test_supervise_bodies_are_parity_checked_against_d213` (or the equivalent compact-string
assertions) so every rendered target contains `--stall-minutes`, `--progress-minutes`, the
phrase `never re-dispatches the same packet unchanged`, and the guardrail line. Keep the provider
-binary guard intact (do not name `claude`, `codex`, `agy`, `opencode`, `omp`, `pi` in the body).

## `docs/staffing/supervise-antiloop.md`

Twenty lines: the three kill kinds, what each means, the one-repair rule, and the exact
flags. Cite Lee's sentence above and the 2026-09-12 observation (Pi transport hang: 30 min
before, 79 s with the ceiling).

## Oracle

`python3 -m pytest -q tests/test_shims_parity.py tests/test_shims.py`

## Required evidence

Oracle output; black/ruff on the test file; `lee-llm-router shims diff --command supervise`
against a temp home (`LEE_LLM_ROUTER_SHIM_HOME`) showing five rendered targets containing the
new flags. Do not run `shims install --apply` against the real home. Do not commit. Do not
stash. Do not write `decisions.md`.
