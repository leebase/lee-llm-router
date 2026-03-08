# Lee LLM Router - Sprint Plan

---

> ## Sprint 6 Complete: Vendored Source Snapshot Workflow
>
> **Status:** 100% complete - source export and vendoring workflow delivered.
>
> **Verification:** `PYTHONPATH=src python -m pytest -q` -> `71 passed`

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
- [x] Destination contains `__init__.py`, provider modules, templates, and a provenance manifest
- [x] Rerunning without `--force` on a non-empty destination exits non-zero with a clear error
- [x] `pytest` is all-green after the export workflow lands

---

## Next Candidate Directions

1. Downstream migration tooling for LeeClaw and Meridian
2. A documented sync/update workflow for vendored snapshots
3. Optional release tagging/versioning for post-Sprint-6 adoption
