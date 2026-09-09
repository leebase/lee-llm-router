# Phase 0 needs Lee

## Blocking

None at restart after Chief round 3. New plan-defined stop items are appended
here if discovered.

## Expected open items

- **P0-3 live-route coverage versus D207 exclusion.** The live Auto-Orch file
  includes worker `opencode_go_mimo_v25`, but OpenCode Zen does not price the
  exact `opencode-go/mimo-v2.5` id. D207 requires that id be excluded from
  every Phase 0 route, while P0-3 acceptance requires every live worker map to
  exactly one route and zero unmapped workers. Both cannot hold. Need an
  amended P0-3 snapshot rule that explicitly permits this one D207 exclusion,
  or newly sourced exact-id weights/pricing.
- **P0-8 router acceptance versus prompt-variant worker keys.** The benchmark
  sidecar legitimately carries four D15 keys shaped
  `model|harness|effort|review-protocol-v1`, while router
  `crew_page.load_benchmark` accepts only the three-part `WorkerIdentity`
  shape. The committed v5 sidecar already fails the same reader check, so the
  new additive class/token fields are not the cause. P0-8 nevertheless
  requires router `test_crew_page` green against v6, and P0-8 scope does not
  authorize changing the router reader or discarding prompt-variant identity.
  Need an explicit compatibility rule/scope amendment.

- OpenCode Go monthly plan fee and capacity are unknown (P0-4).
- `opencode-go/mimo-v2.5` remains unpriced: the pinned Zen catalog publishes
  only the distinct `mimo-v2.5-free` id, while OpenRouter publishes
  `xiaomi/mimo-v2.5`. D207 forbids equating either with the Go id without a
  documented identity. It is excluded from Phase 0 routes and remains a
  pre-existing status-quo worker in other crews.
- Three provider parsing/registry constants in `crews.py` have no explicit
  governing decision cited: `WORKER_ENV_PREFIX_PROVIDERS`,
  `_BUILTIN_REGISTERED_PROVIDERS`, and `WORKER_PROVIDER_OVERRIDES`. They are
  route/provider metadata rather than eligibility policy and therefore do not
  block P0-1, but their authority should be named before later phases treat
  them as durable catalog data. P0-2's additions are authorized by D204 and
  the sprint plan; the pre-existing sets are not separately sourced.
- Pi did not emit authoritative token/cost lines for two timed-out GLM
  attempts, the completed GLM attempt, or the DeepSeek review. The phase's
  exact metered spend therefore cannot be reconciled from worker output.
- Any policy constant without a governing decision will be listed here during
  P0-1/P0-3 review.
- P0-8 sidecar schema-version choice (`benchmark.staffing-evidence/2` additive
  versus `/3`) awaits inspection once its P0-1 dependency is unblocked.

## Resolved by Chief (2026-09-09, appended while the supervisor was running)

Both blocking items above are resolved in `docs/staffing/chief-answers-1.md` (same directory):
class value sets are now in the recommendation §3.1 ("Initial value sets") and are to be
copied verbatim; the named-crew `authority` enum is `lee | chief | policy`; and Lee's
prohibition (D206, "Class metadata MUST NOT map directly to a preferred model or route…") is
to be added to `phase0-contracts.md` as its own contract. P0-1 is unblocked. Supervisor: move
the two items to a Resolved list citing that file, then continue.

## Resolved by Chief — round 2

Source: `docs/staffing/chief-answers-2.md`, D204–D207; supersedes round 1.

- **Class enumerations:** resolved by the recommendation §3.1 table “Initial
  value sets” and the deterministic don't-cheap-trial rule. Copied into
  `phase0-contracts.md` with D206's verbatim prohibition.
- **Named-crew authority:** resolved as `lee | chief | policy`; `policy` is
  reserved for the computed `auto` placeholder.
- **OpenCode Go pricing:** resolved by D207. OpenCode Zen's published pricing
  is the authorized same-catalog accounting proxy for `opencode-go/*`; ids
  absent from Zen remain unpriced, are excluded from Phase 0 routes, and are
  newly listed here if found.

## Resolved by Chief — round 3

Source: `docs/staffing/chief-answers-3.md`; Chief-of-Staff commit `1cc6b24`.

- **Canonical `domain_tags` serialization:** structured fields are authoritative;
  the derived lowercase key uses sorted `+`-joined tags and literal `none` for
  an empty set. The earlier empty-segment proposal is rejected.
- **Invalid Phase gate/P0-5 example:** replaced in the committed plan with
  `--role impl --class impl/deterministic/none/s/python`.

## Resolved by Chief, round 3 (2026-09-09)

Both Blocking items above are resolved in `docs/staffing/chief-answers-3.md`: canonical
class-key string is five segments with `domain_tags` sorted and `+`-joined, `none` when empty
(recommendation §3.1 "Canonical class-key string", with regex); the phase-gate example and
P0-5 acceptance now use `impl/deterministic/none/s/python`. Supervisor: move both to Resolved
citing that file and continue P0-1.

## Resolved by Chief, round 4 (2026-09-09)

`jsonschema>=4.26,<5` is authorized as a runtime dependency in `pyproject.toml` (one line, now
inside P0-2's file set) and installed into `.venv`; see `docs/staffing/chief-answers-4.md`.
P0-2 may continue; P0-8 and P0-9 are unblocked by the P0-1 commit `aaefb9a`.

- **P0-2 runtime validator dependency / plan-scope contradiction:** resolved
  by this round under D86/D87. The authorized runtime requirement is exactly
  `jsonschema>=4.26,<5`; vendoring, system-package reliance, and a partial
  validator remain forbidden.

## Resolved by Chief, round 5 (2026-09-09)

See `docs/staffing/chief-answers-5.md`: channel inference for `pi_cli`/`omp_cli` fails open
to `unknown`; four named test files join P0-2's scope for fixture-only updates with a strict
reviewer rule; the benchmark's OpenCode version-pin mismatch is excluded from P0-8's gate and
recorded, pin unchanged.

- **P0-2 channel behavior and fixture scope:** resolved under D86/D87.
  Uninferrable Pi/OMP channels resolve to `unknown` rather than raising. The
  four named router test files are in scope for fixture-only updates under the
  line-by-line review restriction.
- **P0-8 OpenCode environment drift:** resolved as a single permitted gate
  exclusion. Installed `1.18.30` versus pinned `1.18.26` stays recorded; the
  reproducibility pin must not change.

## Resolved by Chief, round 6 (2026-09-09)

See `docs/staffing/chief-answers-6.md`: the catalog maps every `crews.yaml` worker, including
`opencode_go_mimo_v25`; routes gain `status: active | unpriced | retired` (schema field added
under P0-3 scope); `unpriced` routes carry a `status_reason` citing D207 and are excluded by
eligibility, not absent from the catalog. Continue P0-3, split by source per Rule B.
