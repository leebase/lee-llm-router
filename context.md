# Lee LLM Router Session Context

> **Purpose**: Working memory for session continuity. If power drops, a new AI takes over, or we return after a break - read this first.

---

## Snapshot

| Attribute | Value |
|-----------|-------|
| **Phase** | P3 - Self-Contained Adoption complete |
| **Mode** | 2 (Implementation with approval) |
| **Last Updated** | 2026-03-29 (Sprint 6 export bugfix) |

### Sprint Status
| Sprint | Status | Completion |
|--------|--------|------------|
| Sprint 1 - Package Setup | Done | 100% |
| Sprint 2 - Provider Layer | Done | 100% |
| Sprint 3 - Config, Router, Telemetry | Done | 100% |
| Sprint 4 - Doctor CLI, Template, Docs, PyPI | Done | 100% |
| Sprint 5 - Async, Fallbacks, Extended Telemetry | Done | 100% |
| Sprint 6 - Vendored Source Snapshot Workflow | Done | 100% |

---

## What's Happening Now

### Current Work Stream
Sprint 6 is complete. `lee-llm-router` now supports explicit vendored-snapshot adoption in addition to package installation.

### Recently Completed
- Fixed `lee-llm-router export-source` so a pre-created empty destination directory now exports successfully
- Added a regression test covering export into an existing empty destination
- Validation complete:
  - `.venv/bin/python -m pytest tests/test_doctor.py -q` -> `21 passed`
  - `.venv/bin/python -m pytest -q` -> `117 passed`
- Added `lee-llm-router export-source --dest <path> [--force]`
- Export now copies the full `src/lee_llm_router/` package tree for downstream vendoring
- Export writes `.lee_llm_router_export.json` with package version, source repo, source commit, and export timestamp
- Added overwrite protection for non-empty destinations unless `--force` is passed
- Expanded doctor CLI tests for export success, overwrite protection, forced replacement, and CLI summary output
- Updated sprint/product/README docs to shift downstream adoption toward explicit vendored snapshots
- Validation complete:
  - `PYTHONPATH=src python -m pytest tests/test_doctor.py -q` -> `13 passed`
  - `PYTHONPATH=src python -m pytest -q` -> `71 passed`
  - Test As Lee: `python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml`
  - Test As Lee: `python -m lee_llm_router.doctor export-source --dest <temp>`

### In Progress
- None

---

## Decisions Locked

| Decision | Rationale | Date |
|----------|-----------|------|
| TinyClaw methodology | Build from scratch with small primitives; validate before scale | 2026-02-17 |
| httpx over requests | Native async support, modern HTTP client | 2026-02-18 |
| Add Codex subscription HTTP provider | Enable ChatGPT subscription routing without requiring API-key billing | 2026-03-02 |
| Downstream repos should treat `lee-llm-router` as an upstream improvement lane, not a required live runtime dependency | Preserves shared evolution while reducing install/auth/reproducibility friction in consumers | 2026-03-08 |

---

## Open Questions (keep short)

1. Should LeeClaw vendor the exported package under `src/leeclaw/vendor/` or copy it into its primary package tree?
2. Do Meridian and LeeClaw need the same downstream sync cadence, or should each repo update snapshots independently?
3. Should the export manifest grow to include compatibility metadata for consumers (for example required Python floor and known provider deps)?

---

## Next Actions Queue (ranked)

| Rank | Action | Owner | Done When |
|------|--------|-------|----------|
| 1 | Migrate LeeClaw from external router dependency to vendored snapshot consumption | AI | LeeClaw imports the vendored router without runtime package fetches |
| 2 | Document a downstream sync/update protocol for vendored snapshots | AI | README/docs include a repeatable update workflow |
| 3 | Decide whether to tag/release a post-Sprint-6 package version | Human | Release strategy for package vs vendored adoption is explicit |

---

## Working Conventions

### Start of session
1. Read `AGENTS.md`
2. Read `context.md`
3. Read `result-review.md`
4. Read `product-definition.md`
5. Read `sprint-plan.md`
6. Execute the top-ranked item unless explicitly redirected by the user

### End of work unit
1. Move completed work into "Recently Completed"
2. Update "Next Actions Queue"
3. Add any new locked decisions
4. Keep "Open Questions" <= 5

---

## Environment Notes

- **Working Directory**: `C:\Users\leeba\projects\lee-llm-router`
- **Project Name**: Lee LLM Router
- **Profile**: Python package plus vendorable source export reference
- **Primary validation**: `PYTHONPATH=src python -m pytest -q`

---

*This file is a living document - update it frequently.*
