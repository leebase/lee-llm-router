# Lee LLM Router — Sprint Plan

---

> ## ✅ SPRINT 5 COMPLETE: Async, Fallbacks, Extended Telemetry
>
> **Status:** 100% complete — All acceptance criteria met, 54/54 tests passing.
>
> See [Sprint 5 details](#sprint-5--async-fallbacks-extended-telemetry) below.

---

## Phase Progress

| Phase | Sprint | Status | Completion |
|-------|--------|--------|------------|
| P0 — Extraction | Sprint 1 — Package Setup | ✅ Done | 100% |
| P0 — Extraction | Sprint 2 — Provider Layer | ✅ Done | 100% |
| P0 — Extraction | Sprint 3 — Config, Router, Telemetry | ✅ Done | 100% |
| P1 — Tooling | Sprint 4 — Doctor CLI, Template, Docs, PyPI | ✅ Done | 100% |
| P2 — Enhancements | Sprint 5 — Async, Fallbacks, Extended Telemetry | ✅ Done | 100% |

---

## Sprint End Protocol (pinned)

A sprint is **done** when ALL of these are true:

1. ✅ All acceptance criteria for the sprint pass (`pytest` green)
2. ✅ `context.md` updated (Recently Completed, Next Actions, Last Updated)
3. ✅ `result-review.md` updated (new entry at TOP)
4. ✅ `sprint-plan.md` tasks checked `[x]` and next sprint marked Active
5. ✅ Git commit made with message `feat(sprintN): <summary> [Phase N]`

**Do not mark a sprint complete until all five conditions are met.**

---

## Phase 0 — Direct Extraction

> **Phase Rule:** Copy LeeClaw modules verbatim. Only permitted changes: import path fixes, packaging glue, docstrings. No new abstractions.

---

### Sprint 1 — Package Setup

**Goal:** Rename scaffold, fix `pyproject.toml`, create full `src/lee_llm_router/` skeleton (empty modules), prove `import lee_llm_router` and `pip install -e .` work.

#### Tasks

- [x] Rename `src/Lee LLM Router/` → `src/lee_llm_router/` (move files, delete old directory)
- [x] Fix `pyproject.toml`:
  - [x] `name = "lee-llm-router"` (no space)
  - [x] `packages = [{include = "lee_llm_router", from = "src"}]`
  - [x] Add runtime deps: `pyyaml>=6.0`, `requests>=2.28`
  - [x] Add console script entry point: `lee-llm-router = "lee_llm_router.doctor:main"`
- [x] Create empty module files matching `design.md` layout:
  - [x] `src/lee_llm_router/__init__.py` (exports: `LLMRouter`, `LLMClient`, `load_config`, `LLMRequest`, `LLMResponse`)
  - [x] `src/lee_llm_router/config.py`
  - [x] `src/lee_llm_router/router.py`
  - [x] `src/lee_llm_router/client.py`
  - [x] `src/lee_llm_router/response.py`
  - [x] `src/lee_llm_router/compression.py`
  - [x] `src/lee_llm_router/telemetry.py`
  - [x] `src/lee_llm_router/doctor.py`
  - [x] `src/lee_llm_router/providers/__init__.py`
  - [x] `src/lee_llm_router/providers/base.py`
  - [x] `src/lee_llm_router/providers/http.py`
  - [x] `src/lee_llm_router/providers/codex_cli.py`
  - [x] `src/lee_llm_router/providers/mock.py`
  - [x] `src/lee_llm_router/providers/registry.py`
  - [x] `src/lee_llm_router/templates/llm.example.yaml` (placeholder)
- [x] Create `tests/` directory:
  - [x] `tests/__init__.py`
  - [x] `tests/conftest.py` (shared fixtures: tmp config path, env var cleanup)
  - [x] `tests/test_smoke.py` (import test + version check)
- [x] Verify `pip install -e ".[dev]"` succeeds
- [x] Verify `pytest tests/test_smoke.py` passes

#### Acceptance Criteria

- `pip install -e .` exits 0
- `python -c "import lee_llm_router; print(lee_llm_router.__version__)"` prints a version string
- `pytest tests/test_smoke.py` — all tests green
- No `src/Lee LLM Router/` directory remains

---

### Sprint 2 — Provider Layer

**Goal:** Port `response.py`, `providers/base.py`, `registry.py`, `mock.py`, `http.py`, `codex_cli.py`. Full unit test coverage. No real HTTP calls (all mocked).

#### Tasks

- [x] Port `response.py` — `LLMRequest` + `LLMResponse` dataclasses with all fields from LeeClaw
- [x] Port `providers/base.py` — `Provider` Protocol + `LLMRouterError` + `FailureType` enum
- [x] Port `providers/registry.py` — `register()` + `get()` + auto-discovery of built-ins
- [x] Port `providers/mock.py` — deterministic echo provider; configurable response text
- [x] Port `providers/http.py` — OpenRouter/OpenAI-compatible REST (requests-based)
- [x] Port `providers/codex_cli.py` — subprocess provider; mock subprocess in tests
- [x] Update `__init__.py` exports to include `LLMRequest`, `LLMResponse`, `LLMRouterError`
- [x] Write `tests/test_providers.py` with ≥5 tests:
  - [x] `test_mock_provider_returns_response`
  - [x] `test_registry_roundtrip` (register + get)
  - [x] `test_http_provider_success` (requests mocked)
  - [x] `test_http_provider_timeout_raises_llm_router_error`
  - [x] `test_failure_type_contract_violation_not_retried`

#### Acceptance Criteria

- `pytest tests/test_providers.py` — all tests green
- Registry round-trip: `register("mock", MockProvider)` → `get("mock")` returns `MockProvider`
- `MockProvider` callable: `mock.complete(request, {})` returns `LLMResponse`
- `LLMRouterError` carries `failure_type` attribute

---

### Sprint 3 — Config, Router, Telemetry

**Goal:** Port `config.py`, `router.py`, `client.py`, `telemetry.py`, `compression.py`. End-to-end test: load config → `router.complete()` → verify log events + `LLMResponse`.

#### Tasks

- [x] Port `config.py` — YAML loader, `LLMConfig` dataclass, env var interpolation (`api_key_env` pattern)
- [x] Port `router.py` — `LLMRouter` facade: resolve role → build request → compress → invoke provider → telemetry → return/raise
- [x] Port `client.py` — `LLMClient` legacy wrapper: `complete(role, messages, **kwargs)`
- [x] Port `telemetry.py` — structured `logging.extra` fields; JSON trace file writer; event names: `llm.complete.start`, `llm.complete.success`, `llm.complete.error`; trace path: `<workspace>/.agentleeops/traces/YYYYMMDD/<request_id>.json` or `.lee-llm-router/traces/` fallback
- [x] Port `compression.py` — stub hook (pass-through by default; interface preserved)
- [x] Update `src/lee_llm_router/templates/llm.example.yaml` with real commented example from `design.md` §4
- [x] Write `tests/fixtures/llm_test.yaml` — minimal valid config using `MockProvider`
- [x] Write `tests/test_config.py` with ≥4 tests:
  - [x] `test_load_config_valid`
  - [x] `test_env_interpolation` (api_key_env resolved from os.environ)
  - [x] `test_missing_required_field_raises`
  - [x] `test_role_inherits_provider_defaults`
- [x] Write `tests/test_router.py` with ≥4 tests:
  - [x] `test_complete_success` (end-to-end with MockProvider)
  - [x] `test_complete_logs_telemetry_events` (caplog)
  - [x] `test_complete_writes_trace_file` (tmp_path)
  - [x] `test_complete_error_raises_llm_router_error`

#### Acceptance Criteria

- `from lee_llm_router import LLMRouter, LLMClient, load_config, LLMRequest, LLMResponse` — no ImportError
- `pytest` all-green (all three test files)
- `LLMClient.complete(role, messages)` returns `LLMResponse` using `MockProvider`
- Trace file written to tmp dir on success
- **P0 complete** at end of this sprint

---

## Phase 1 — Tooling Additive

> **Phase Rule:** Additive only — no breaking changes to P0 APIs.

---

### Sprint 4 — Doctor CLI, Template, Docs, PyPI

**Goal:** Complete the full `product-definition.md` acceptance checklist.

#### Tasks

- [x] `doctor.py`: `lee-llm-router doctor --config <path>` validates YAML structure, resolves env vars, checks CLI binaries exist, dry-run with MockProvider; exit code 0 = healthy
- [x] `doctor.py`: `lee-llm-router template` sub-command prints `llm.example.yaml` to stdout
- [x] Populate `src/lee_llm_router/templates/llm.example.yaml` — full annotated example (providers + roles + fallbacks)
- [x] Add `RoutingPolicy` Protocol + `SimpleRoutingPolicy` default in `policy.py` (logs `policy.choice` telemetry event)
- [x] Add `TraceStore` Protocol + `LocalFileTraceStore` default in `telemetry.py`
- [x] Write `tests/test_doctor.py` with ≥4 tests:
  - [x] `test_doctor_valid_config_exit_0`
  - [x] `test_doctor_missing_env_var_reports_error`
  - [x] `test_doctor_missing_binary_reports_error`
  - [x] `test_template_command_outputs_yaml`
- [x] `README.md` — API usage + CLI usage + quick-start
- [x] `docs/config.md` — config schema reference
- [x] `docs/providers.md` — provider adapter reference
- [x] `pyproject.toml` PyPI-ready: classifiers, description, `python_requires`, `[build-system]`
- [x] Verify `python -m build` produces `.whl` + `.tar.gz`

#### Acceptance Criteria

- Every item in `product-definition.md` acceptance checklist checked off
- `pytest` all-green
- `lee-llm-router doctor --config tests/fixtures/llm_test.yaml` exits 0
- `lee-llm-router template` prints valid YAML to stdout
- `python -m build` succeeds

---

## Phase 2 — Enhancements

---

### Sprint 5 — Async, Fallbacks, Extended Telemetry

**Goal:** `httpx` async HTTP, fallback chain orchestration, token accounting hook, `lee-llm-router trace --last N`, `EventSink` telemetry protocol.

#### Tasks

- [x] Replace `requests` with `httpx` in `providers/http.py`; add `async def complete_async(...)` to `Provider` protocol
- [x] Add `await router.complete_async(role, messages)` to `LLMRouter`
- [x] Fallback chain: when primary provider raises, try `fallback_providers` in order; log `policy.fallback` event per attempt
- [x] Token accounting hook: `on_token_usage(request_id, usage)` callback in `LLMRouter`
- [x] `EventSink` protocol in `telemetry.py` + wire existing loggers through it
- [x] `lee-llm-router trace --last N` CLI sub-command (reads local trace files)
- [x] Tests for all above

#### Acceptance Criteria

- `await router.complete_async(role, messages)` works
- Fallback chain executes + logs `policy.fallback` telemetry event
- `lee-llm-router trace --last 5` prints last 5 trace summaries
- `pytest` all-green

---

## Notes for Agents Starting Cold

**Quick-start (6 steps):**

1. Read `AGENTS.md` — conventions and guardrails
2. Read this file — find the `🟢 CURRENT SPRINT` block at the top
3. Read `context.md` — current state and Next Actions Queue
4. Read `result-review.md` — what was most recently completed
5. Find the first unchecked `[ ]` task in the current sprint above
6. Do that task, then update `context.md` + `result-review.md` before stopping

**Key files:**
- Package source: `src/lee_llm_router/` (does not exist yet — Sprint 1 creates it)
- Tests: `tests/` (does not exist yet — Sprint 1 creates it)
- Config: `pyproject.toml` (exists but has wrong package name — Sprint 1 fixes it)
- Design reference: `design.md` (full architecture, module layout, config format)
