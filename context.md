# Lee LLM Router Session Context

> **Purpose**: Working memory for session continuity. If power drops, a new AI takes over, or we return after a break - read this first.

---

## Snapshot

| Attribute | Value |
|-----------|-------|
| **Phase** | P4 complete; pi harness reliability shipped |
| **Mode** | 2 (Implementation with approval) |
| **Last Updated** | 2026-03-29 (Sprint 7 documentation sweep complete) |

### Sprint Status
| Sprint | Status | Completion |
|--------|--------|------------|
| Sprint 1 - Package Setup | Done | 100% |
| Sprint 2 - Provider Layer | Done | 100% |
| Sprint 3 - Config, Router, Telemetry | Done | 100% |
| Sprint 4 - Doctor CLI, Template, Docs, PyPI | Done | 100% |
| Sprint 5 - Async, Fallbacks, Extended Telemetry | Done | 100% |
| Sprint 6 - Vendored Source Snapshot Workflow | Done | 100% |
| Sprint 7 - Pi Coding Harness Reliability and Harness Validation | Done | 100% |

---

## What's Happening Now

### Current Work Stream
Sprint 7 is complete. The pi coding harness path now has a repo-local reproduction fixture, stricter CLI harness contract handling, explicit `doctor` validation, regression coverage, and a user-style verification path. No downstream migration work is executed from this repo now; downstream projects are handled separately.

### Recently Completed
- Swept the public docs and coder guide so the shipped Sprint 7 pi harness behavior is documented consistently
- Clarified that `default_role` must reference an existing role and that `model_flag` / `output_flag` can be set to `null` to disable default CLI flags
- Added a pi-style subprocess harness example plus updated `doctor` behavior notes in `docs/llm-coder-guide.md`
- Fixed the Sprint 7 review findings around pi harness flag handling and malformed JSON usage typing
- `codex_cli` now allows `model_flag: null` for wrappers that do not accept the default Codex CLI flags
- Invalid JSON `usage` fields from pi-style harnesses now raise typed `CONTRACT_VIOLATION` errors instead of falling through as `UNKNOWN`
- Added regression coverage for strict wrapper invocation without default flags and router-level malformed usage handling
- Added a repo-local simulated pi harness fixture at `tests/fixtures/pi_harness.py`
- Hardened `codex_cli` with fixed `args`, optional `response_format: json`, JSON text extraction, usage passthrough, and typed `CONTRACT_VIOLATION` failures for malformed harness output
- Improved non-zero exit diagnostics for CLI harness failures and preserved command metadata in raw responses
- Tightened config validation for unknown `default_role` and fallback providers
- Updated `doctor` to validate the configured provider and role wiring instead of a mock-only dry-run path
- Added focused pi harness tests for success, malformed JSON, missing text, timeout, non-zero exit, doctor validation, and router traceability
- Updated README, provider docs, config docs, and the example template with pi harness contract guidance
- Fixed `lee-llm-router export-source` so a pre-created empty destination directory now exports successfully
- Added a regression test covering export into an existing empty destination
- Validation complete:
  - `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_providers.py tests/test_router.py tests/test_doctor.py -q` -> `56 passed`
  - `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_doctor.py -q` -> `60 passed`
  - `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q` -> `85 passed`
  - Test As Lee: `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml`
  - Test As Lee: temp pi harness config + `LLMRouter.complete("pi_local", ...)` -> `{"text":"pi json harness: ship sprint 7","provider":"codex_cli","model":"pi-harness-o3"}`

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
| Treat existing empty export destinations as valid `export-source` targets, and reserve `--force` for replacing non-empty destinations | Matches the Sprint 6 intended contract and avoids surprising failures for pre-created directories | 2026-03-29 |
| Pi coding harness reliability must be proven in this repo before downstream apps rely on it again | A downstream app already failed on this path, so reproduction, validation, and regression coverage are now first-class product work | 2026-03-29 |
| Pi-style subprocess harnesses should use a structured JSON envelope when reliability matters | Contract failures become deterministic `CONTRACT_VIOLATION`s instead of ambiguous free-form subprocess output errors | 2026-03-29 |

---

## Open Questions (keep short)

1. Should a follow-on sprint add an optional doctor smoke-execution mode for CLI harness roles?
2. Does broader harness-aware planning still belong in a follow-on sprint now that the pi path is stable?

---

## Next Actions Queue (ranked)

| Rank | Action | Owner | Done When |
|------|--------|-------|----------|
| 1 | Decide whether to productize an optional doctor smoke-execution mode for CLI harness roles | Human + AI | We know whether runtime smoke tests should become part of the public CLI |
| 2 | Reassess broader harness-aware planning as a separate sprint | Human + AI | Follow-on planning is grounded in a stable pi harness baseline |

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
