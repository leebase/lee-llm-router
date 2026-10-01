# Lee LLM Router - Sprint Plan

---

## Staffing multi-account plan — channel instances

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`.
Supervised via `/supervise`. M1 (catalog + schema) committed before this
session. M2 ("headroom per instance") verified and independently reviewed
2026-09-14 across both repos (`chief-of-staff/scripts/ai-subs.sh` — M2a;
`lee-llm-router` `availability.py`/tests — M2b), left uncommitted pending
Lee. **M3 ("selection") is now complete and committed** in three packets:
M3-1 (`eligibility.py`, per-instance D216 reserve/health veto with
channel-record inheritance, commit `34c13c0`), M3-2 (`block.py`, `staff
auto` exposes `selected_instance` + per-candidate `instance_headrooms`,
commit `778d538`), and M3-3 (`run.py`/`doctor.py`, `run --instance` pins an
instance the way `--route` pins a route, `route.channel_instance` on the
attempt record, commit `65e7259`) — each with its own independent review
(ACCEPT, 0 findings) and full-suite pass (1896 passed, 6 skipped after
M3-3). **M4 ("credential staging at dispatch") is now complete and
committed** in two packets: M4-1 (`credentials.py`, new staging module,
`opencode`/`pi` only — `omp` deliberately unsupported, its real auth store
is a SQLite vault not a static file, contradicting the plan's assumption;
commit `dca7f70`) and M4-2 (`run.py`/`doctor.py` wiring, fail-closed before
registration/launch on a missing/malformed credential or unsupported
harness; commit `01e2722`, after 3 independent-review rounds — REJECT
(wrong staged auth.json shape, confirmed against the real files on this
machine, plus 2 hardening gaps) → REJECT (one remaining
`UnicodeDecodeError` gap) → PASS, 0 findings). Full suite: 1913 passed, 6
skipped. The live two-account smoke stays HELD pending Lee's confirmation
of OpenCode's terms. **Next: M5** (evidence report grouped by
route+instance, 20 min bound). See `result-review.md` (2026-09-14 entries)
for the full attempt chain.

---

> ## Sprint 7 Complete: Pi Coding Harness Reliability and Harness Validation
>
> **Status:** Complete - 100% complete.
>
> **Goal:** harden the pi coding harness path so downstream apps can rely on it, add explicit validation and regression coverage for harness execution, and make failures diagnosable before they reach consumers.

---

## Staffing class derivation: TOML and INI

**Status:** Complete — independent review PASS on 2026-09-12, with zero
findings.

**Delivered:** `.toml` and `.ini` map to the existing `yaml-config` class;
homogeneous configuration sets and mixed code/config behavior are covered; the
closed language taxonomy and domain-tag independence are preserved. Contract
AC-1 through AC-6 passed.

**Validation:** Agent-Orch's preserved record reports six successful checks:
test compilation, two focused pytest runs, Black, Ruff, and production/test
bytecode compilation. Closeout did not rerun those authoritative commands.

**Next:** No repair is pending. Do not start another staffing slice without an
authorized packet.

---

## Phase Progress

| Phase | Sprint | Status | Completion |
|-------|--------|--------|------------|
| P0 - Extraction | Sprint 1 - Package Setup | Done | 100% |
| P0 - Extraction | Sprint 2 - Provider Layer | Done | 100% |
| P0 - Extraction | Sprint 3 - Config, Router, Telemetry | Done | 100% |
| P1 - Tooling | Sprint 4 - Doctor CLI, Template, Docs, PyPI | Done | 100% |
| P2 - Enhancements | Sprint 5 - Async, Fallbacks, Extended Telemetry | Done | 100% |
| P3 - Self-Contained Adoption | Sprint 6 - Vendored Source Snapshot Workflow | Done | 100% |
| P4 - Harness Reliability | Sprint 7 - Pi Coding Harness Reliability and Harness Validation | Done | 100% |

---

## Sprint End Protocol

A sprint is done when all of these are true:

1. Acceptance criteria pass.
2. `context.md` is updated.
3. `result-review.md` is updated.
4. `sprint-plan.md` reflects the new state.
5. Code, tests, docs, and user-facing behavior are aligned.

---

## Sprint Summary

### Sprint 1 - Package Setup

Shipped the package skeleton, packaging fixes, smoke tests, and editable install path.

### Sprint 2 - Provider Layer

Shipped request/response contracts, provider protocol, built-in providers, and provider tests.

### Sprint 3 - Config, Router, Telemetry

Shipped config loading, router/client APIs, trace writing, and end-to-end routing tests.

### Sprint 4 - Doctor CLI, Template, Docs, PyPI

Shipped doctor/template tooling, docs, packaging, and public API documentation.

### Sprint 5 - Async, Fallbacks, Extended Telemetry

Shipped async HTTP, fallback execution, richer telemetry, and trace inspection tooling.

### Sprint 6 - Vendored Source Snapshot Workflow

**Goal:** make `lee-llm-router` exportable as a pinned source snapshot so downstream repos can vendor it intentionally.

#### Tasks

- [x] Add `lee-llm-router export-source --dest <path>` CLI command
- [x] Export the full `src/lee_llm_router/` package tree to the destination
- [x] Write a provenance manifest with package version, source commit, and export timestamp
- [x] Refuse to overwrite a populated destination unless `--force` is passed
- [x] Add unit tests for successful export, overwrite protection, and CLI invocation
- [x] Update README and product docs to describe vendored-snapshot adoption
- [x] Update baton docs (`context.md`, `result-review.md`, `WHERE_AM_I.md`)

#### Acceptance Criteria

- [x] `lee-llm-router export-source --dest <tmp>` exits 0 and writes a vendorable package tree
- [x] Export succeeds when the destination already exists but is empty
- [x] Destination contains `__init__.py`, provider modules, templates, and a provenance manifest
- [x] Rerunning without `--force` on a non-empty destination exits non-zero with a clear error
- [x] `pytest` is all-green after the export workflow lands

---

### Sprint 7 - Pi Coding Harness Reliability and Harness Validation

**Goal:** make the pi coding harness path dependable for downstream apps by reproducing the recent failure, validating the harness contract directly, and adding automated and user-style checks that catch regressions before release.

#### Scope Guardrails

- Preserve existing role-based execution APIs while hardening harness behavior.
- Focus first on the pi coding harness failure path that broke a downstream app.
- Treat reproduction and diagnosis as product work, not just ad hoc debugging.
- Add tests and tooling that can run in this repo without depending on the downstream app repo.

#### Tasks

- [x] Reconstruct and document the downstream failure mode for the pi coding harness using a repo-local fixture or simulated harness
- [x] Audit the current pi harness execution path, including command invocation, input/output contract, error mapping, and timeout behavior
- [x] Add or tighten config validation for harness-specific requirements that should fail fast in `doctor`
- [x] Add focused automated tests for successful pi coding harness execution, malformed output, timeout, non-zero exit, and contract-violation handling
- [x] Add a regression test that proves the router surfaces a clear typed failure when pi harness execution breaks
- [x] Add a Test-As-Lee path that exercises the pi coding harness behavior the way a real downstream consumer would
- [x] Update docs and examples so pi harness expectations, limitations, and debugging steps are discoverable
- [x] Capture any follow-on decisions about harness-aware planning only after the pi harness path is proven reliable

#### Acceptance Criteria

- [x] The recent pi coding harness failure mode is reproducible in a repo-local test or fixture
- [x] `doctor` or equivalent validation catches obvious pi harness misconfiguration before runtime where possible
- [x] Automated tests cover both successful pi coding harness execution and the known failure classes
- [x] Router errors from pi harness failures are typed, readable, and traceable
- [x] A user-style validation run demonstrates the pi coding harness path working end-to-end in this repo
- [x] Existing test coverage remains green after the hardening work lands

#### Validation Plan

```bash
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_doctor.py -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml
# plus temp pi-harness config + LLMRouter.complete("pi_local", ...) smoke run
```

#### Suggested Delivery Order

1. Reproduce and document the downstream failure with the smallest local fixture possible.
2. Tighten harness validation and error mapping so failures are diagnosable.
3. Add automated regression coverage for success and failure cases.
4. Run a real user-style pi coding harness check and document the results.
5. Update docs only after behavior and diagnostics are stable.

## Next Candidate Directions

1. Resume downstream migration work now that the pi harness path is proven reliable
2. Decide whether to add optional doctor smoke execution for CLI harness roles
3. Reassess broader harness-aware planning from the stable pi harness baseline

## 2026-09-07 — Crew-aware worker resolver (Sprint 8 lane)

New lane authorized by Chief of Staff decision D187. Plan lives at
`docs/crew-resolver/sprint-plan.md` (six sprints, its own numbering). Start there after a
context reset.

## 2026-09-22 — completed provisional model substitution

- [x] Apply Chief D355 to active staffing routes, crew bindings and never-automatic policy without changing roles, effort or channels. Continue measuring supervised task outcomes before any performance ranking.

## 2026-09-22 — FS0 CSS packet classification repair

- [x] Derive existing `mixed` language for CSS-only and TSX+CSS packets; retain unsupported-extension rejection.
- [x] Focused class oracle: 33 passed; FS5.1a staff JSON: nine owned paths, class language `mixed`.
- [ ] Chief independent oracle, exact five-path delta and CLI check, and final Opus 0H/M review pending.


## 2026-09-29 — isolated supervise owner repair candidate

Direct owner assignment `supervise-remediation-0929`; amended diagnosis implemented
in isolated copies only. Bounded generated contract, parent acceptance/method
record and additive version-1 `run` admission retain legacy records/routing policy.
WORK.md records gaps and verification. Source baseline includes canonical dirty
changes; candidate delta is against isolated HEAD. No installation, live ledger
mutation, provider/worker/reviewer dispatch or acceptance claim. Independent exact
Opus-5.5 medium code/behavior review and Lee adoption decision remain outstanding.

## 2026-09-29 — reviewer-directed repair round 1 (same parent)

Initial independent review REJECTED H1–H3/M1–M4. This isolated delta adds
truthful missing-record reconciliation with shutdown evidence, frozen inception
gaps/review gate, capability denial continuity and review-driven round transitions.
Instructions disclose serial opted-in accounting and accurate manual-primary
fallback policy. Verification and disposition are retained in WORK.md and the
evidence directory. Independent final/delta review, consuming evidence and adoption
remain outstanding; no live install or self-acceptance.

## 2026-09-29 — final directed repair round 2 (same parent)

Second independent review rejected only the H1 Linux process scan. The isolated
candidate now excludes unreadable environments only with readable creation ticks
strictly older than the recorded controller. Equal/newer or missing/unknown
creation identities refuse precisely; marked workers and original-controller
checks remain enforced. Consumed starts, conservative time and unknown outcome
remain unchanged. Focused sandbox checks and refreshed packaging are recorded in
WORK.md/test-results.json. Chief’s two production-host CLI checks, final-contract
offline decisions and independent final Opus review remain outstanding. The
retained 72 baseline failures remain; no broad rerun, adoption or self-acceptance.

## 2026-09-30 — accepted supervise publication

Lee accepted the rollout and authorized commit/push. The publication includes
exact reviewed runtime bytes and necessary accepted reserve/launch dependencies,
with catalog-compatible focused tests. Model replacements, CSS work and other
canonical dirt remain outside this commit. See [user instructions](docs/supervise-rollout.md).

## 2026-09-30 — Bonnie delegated owner continuation

Complete protected Staff consumption of the reviewed router executor seam;
exercise an employee-owned native Board assignment with deliberately failed
worker launch, same-parent recovery, independent artifact review and reconciled
receipts. Preserve all original attempts and limits, including earlier review
classification correction. Freeze the reviewed candidate and state-preserving
installation/rollback instructions for Lee before any Bonnie environment change.


## Chief owner repair — Bonnie, October1

Lee explicitly authorized router-owner work for the original Bonnie parent. Added immutable opted-in economical checkpoint with one finite D268 extension; installed supervise guidance requires adoption. Final router210 checks passed. Independent source review72 approved its exact frozen revision; later two-field assignment-binding compatibility delta remains independently unapproved after final review75 launcher failed before the model. Original parent retains75 starts/75 finishes and exhaustion refuses another start. No76, no deployment, no parent acceptance. Evidence: /home/lee/projects/chief-of-staff/plans/bonnie-architecture-upgrade/RESULT.md. This scoped continuation does not supersede unrelated router work.


## 2026-10-01 — Bonnie explicitly authorized continuation accepted

This supersedes the exhausted75-attempt Bonnie disposition above for technical predeployment scope only. Lee granted12 additional routed starts/10800 aggregate worker-seconds under the original parent. The host admission seam now validates append-only authority-attributed continuation grants without changing counters or the old checkpoint. `close_outcome` rejects OPEN gaps and unaccounted starts, records evidenced parent closure, and prevents new starts on a closed parent. Independent final parent review87 approved the final candidate; actual original-parent closure succeeded after the unattended same-parent failure/recovery, owner handoff, review and employee-result evidence reconciled. All87 starts/finishes retained; continuation used581.412 recorded worker-seconds. Focused closure/checkpoint/continuation checks:37 passed; prior210 router/119 Staff accepted checks retained without redundant reruns. No deployment, customer acceptance or general restoration of failed staffing methods. No unrelated repository changes published. Evidence: `/home/lee/projects/chief-of-staff/plans/bonnie-architecture-upgrade/RESULT.md`, `proof/PARENT-INDEPENDENT-ACCEPTANCE.md`, `proof/FINAL-GUARDED-CLOSURE.json`. Frozen credential-free release manifest and limitations are in that outcome directory.
