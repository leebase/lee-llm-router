# Review Packet — auto_crew owned-paths + harness-resolution fix (round 2)

Independent review (read-only). Supervisor-authored fix, revised after a first review round
found the initial fix insufficient.

## What to inspect

`git -C /home/lee/projects/auto-orch diff -- src/auto_orch/auto_crew.py tests/test_auto_orch_auto_crew.py tests/fixtures/fake_lee_llm_router.py`

(Ignore any other modified/untracked files in that repo's working tree — they belong to an
unrelated lane's in-progress work, noted and left untouched throughout this phase's ledger.)

## Background

Round 1 of this fix changed the packet's placeholder owned-path from `.` to
`` `unspecified-scope.py` `` (a bare `.` collapses to the empty string under the router's
`_parse_owned_paths` stripping, and the packet's language is derived from the extension
before any `--language` override applies). Independent review then found that fix
insufficient: `resolve_role_route`'s harness-metadata lookup read the wrong top-level key
(`"workers"`/`"eligible"` instead of the real CLI's `"routes"`), and even after that key is
corrected, `lee-llm-router catalog explain --json`'s per-route entries deliberately never
include `harness`/`model`/`effort` (`_explain_route_json`'s own docstring: "the route id is
the only route label") — so the mandate could never actually resolve through the router for
any mission.

This round: fixes the `"routes"` key; derives `harness` from `selected_route`'s own
hyphen-prefix naming convention (verified against all 28 rows in
`lee-llm-router/config/staffing/routes.yaml` with zero mismatches — every route_id is named
`{harness}-...-{channel}`) instead of trying to read it from `catalog explain`; leaves
`model`/`effort` as best-effort `None` (already optional on `RoleRouteResult`) since the real
CLI has no path to supply them today. Updates the `fake_lee_llm_router.py` fixture to match
the real CLI's actual output shape (previously it encoded the same wrong shape the buggy code
expected — the classic mocked-seam trap this repo's own "subprocess seam rule" exists to
catch) and fixes two tests whose assertions depended on the fixture's fabricated
harness/model/effort fields. `test_resolve_role_route_with_real_cli` now genuinely passes
against the real installed `lee-llm-router` binary (confirmed twice, including with
`AUTO_ORCH_ROUTER_CLI` explicitly unset to rule out env leakage from other tests).

**Recorded as a needs-lee/chief architecture question, not resolved here:** which repo should
own exposing a route's dispatch metadata (a new lee-llm-router CLI capability that reveals
harness/model/effort for an already-selected route id, vs. auto-orch reading
`routes.yaml` directly as shared config data) is a real design decision spanning two repos'
committed contracts, out of a bounded proof session's unilateral authority. The route-id-prefix
derivation here is a real, verified, working fix for `harness` specifically (which is
load-bearing for actual dispatch); `model`/`effort` staying `None` is an honest degradation,
not a regression (both fields were always typed optional).

## Your job

1. Confirm the `"routes"` key matches the real CLI's output
   (`lee-llm-router catalog explain --role impl --class impl/none/none/m/mixed --json`).
2. Confirm the route-id-prefix harness derivation is sound: check
   `lee-llm-router/config/staffing/routes.yaml` yourself for any route whose `route_id`'s
   first hyphen-token does not equal its own `harness` field.
3. Confirm the two updated tests' new assertions (`model is None`, `effort is None`) reflect
   real CLI behavior, not test-of-mock convenience.
4. Confirm `test_resolve_role_route_unmapped_harness` still genuinely exercises the "unmapped
   harness" rejection path under the new derivation (it must drive an unmapped `selected_route`
   prefix now, not a catalog-payload harness field).
5. Confirm formatting/lint are clean and nothing outside the three files changed.

Report `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT` with Contract-blocking /
Hardening / Future findings.
