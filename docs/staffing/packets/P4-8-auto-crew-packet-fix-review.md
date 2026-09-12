# Review Packet — auto_crew owned-paths placeholder fix

Independent review (read-only). Supervisor-authored fix (not worker-dispatched — small,
mechanical, confirmed live against the real router CLI).

## What to inspect

`git -C /home/lee/projects/auto-orch diff -- src/auto_orch/auto_crew.py tests/test_auto_orch_auto_crew.py`

## Background

Phase 4 P4-8's live proof cycle (chief-of-staff/decisions.md D215 ruling 5, gate item (b))
discovered that `write_backlog_packet`'s fixed placeholder `- Owned paths: .` always causes
`lee-llm-router staff --from-packet` to fail with `packet class invalid: Owned paths must
name at least one path` — the router's own `_parse_owned_paths` strips leading/trailing
`.,;:` from every candidate, so a bare `.` collapses to the empty string. Every real
`auto`-crew cycle was therefore silently falling back to the mission's `fallback_crew`
instead of actually resolving through the router — the exact opposite of what P4-6/gate (b)
require. The fix changes the placeholder to `` `unspecified-scope.py` `` (needs a real
extension too, since the packet's language is derived from the extension before any
`--language` CLI override applies) and updates the one test assertion that hard-coded the old
literal. It also narrows `test_resolve_role_route_with_real_cli`'s exception handling: it
previously caught `RouteUnavailable` and skipped, which is exactly what let this defect go
undetected by the repo's own "real CLI" subprocess-seam test (AGENTS.md B1) — since
`shutil.which` already gates the skip on the binary being absent, a `RouteUnavailable` raised
after that check now fails the test instead of skipping.

## Your job

1. Confirm independently that a bare `.` really does collapse to empty under
   `lee_llm_router.staffing.derive_class._parse_owned_paths` (read that function; you may also
   invoke `lee-llm-router staff --from-packet` directly against a throwaway packet with
   `- Owned paths: .` to reproduce, and again with `` - Owned paths: `unspecified-scope.py` ``
   to confirm the fix).
2. Confirm the placeholder's base name (`unspecified-scope`) matches nothing in
   `lee-llm-router/config/staffing/classes.yaml`'s `domain-keyword-table`, so `domain_tags`
   stays `()` as originally intended.
3. Confirm the `test_resolve_role_route_with_real_cli` change is sound: does removing the
   `except RouteUnavailable: pytest.skip(...)` risk making CI flaky in an environment where
   `lee-llm-router` is on PATH but has no eligible routes for the `impl`/`m`/`mixed` class
   (e.g. all channels exhausted)? If so, is that an acceptable, honest trade-off (a hard
   failure exposing a real problem) versus the prior silent skip that hid this exact defect?
4. Confirm nothing outside the two files changed, and check formatting/lint.

Report `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT` with Contract-blocking /
Hardening / Future findings.
