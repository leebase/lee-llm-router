# Lee LLM Router - Sprint Plan

---

> ## Sprint 7 Complete: Pi Coding Harness Reliability and Harness Validation
>
> **Status:** Complete - 100% complete.
>
> **Goal:** harden the pi coding harness path so downstream apps can rely on it, add explicit validation and regression coverage for harness execution, and make failures diagnosable before they reach consumers.

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
