# Phase 0 needs Lee

## Blocking

None at restart after Chief round 3. New plan-defined stop items are appended
here if discovered.

## Expected open items

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
