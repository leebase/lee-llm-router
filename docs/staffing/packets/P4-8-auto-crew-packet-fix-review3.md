# Review Packet — auto_crew model resolution via `price` (round 3)

Independent review (read-only).

## What to inspect

`git -C /home/lee/projects/auto-orch diff -- src/auto_orch/auto_crew.py tests/test_auto_orch_auto_crew.py tests/fixtures/fake_lee_llm_router.py`

(This is a follow-up to the already-committed `d6fcb66` fix; diff it against `HEAD`, i.e. the
current uncommitted working-tree changes on top of that commit. Ignore other modified/
untracked files in the repo — an unrelated lane's in-progress work.)

## Background

Round 2's fix (committed `d6fcb66`) made the `auto` crew's mandate genuinely resolve through
`lee-llm-router staff` for the first time, deriving `harness` from `selected_route`'s
hyphen-prefix naming convention since `catalog explain --json` deliberately omits it. That
fix left `model`/`effort` as `None`, recorded as a "future" architecture question. Running an
actual live cycle immediately afterward (Phase 4 P4-8 proof mission, cycle
`20260912T100049Z`) proved that was **not** merely cosmetic: the governed run failed with
"pricing admission refused before provider invocation: metered route has no trusted model
identity" — `model: null` blocks real dispatch outright.

This round resolves `model` via the already-committed `lee-llm-router price --route ID
--input 0 --output 0 --json` command (P4-1), which reports the route's `model` directly
(confirmed live: `codex-gpt-5-6-sol-low-openai-sub` -> `model: "gpt-5.6-sol"`), replacing the
`catalog explain` round trip entirely. `effort` still has no CLI disclosure path and stays
`None` — genuinely a lower-stakes gap now that `model` is resolved (nothing observed live so
far has required `effort` to dispatch).

## Your job

1. Confirm `price --route <a real route id> --input 0 --output 0 --json` really does return
   `model` for a live route (run it yourself against a couple of real route ids from
   `lee-llm-router/config/staffing/routes.yaml`).
2. Confirm the zero-token-count call is harmless (doesn't error, doesn't misrepresent real
   attempt cost — it's used only to read the static `model` field, never recorded as an
   attempt's actual usage).
3. Confirm the updated tests (`test_resolve_role_route_success`, the mandate-resolution test,
   the unmapped-harness test, the fake CLI fixture) are internally consistent and actually
   exercise what they claim.
4. Confirm formatting/lint clean and diff scope is exactly the three files.
5. Judge whether leaving `effort: None` indefinitely is acceptable to ship now, or whether it
   should block acceptance — your call, with reasoning.

Report `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT` with Contract-blocking /
Hardening / Future findings.
