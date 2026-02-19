# Lee LLM Router Result Review

> **Running log of completed work.** Newest entries at the top.
>
> Each entry documents what was built, why it matters, and how to verify it works.

---

## 2026-02-18 — Sprint 6 Prep: Provider Aliases, Policy Overrides, Trace Integrity

**What was built:** Added `openai_http` as a first-class alias in the provider registry plus doctor + router tests; policies can now override request attributes via `ProviderChoice.request_overrides` (without colliding with provider config overrides), and per-call kwargs now win over policy defaults. Trace attempts are persisted individually (`<request>-<attempt>-<provider>.json`), fallback runs write one file per attempt, and `lee-llm-router trace --last` shows attempt metadata.

**Why it matters:** Configs copied from OpenAI examples work without edits, cost-aware policies can enforce cheaper models reliably, and trace archives finally capture every failure/success along a fallback chain—making the new `trace --last` output actionable during incident review.

**How to Verify**

```bash
pip install -e ".[dev]"            # ensures httpx is available
pytest tests/test_doctor.py \
       tests/test_router.py \
       tests/test_async.py -k "policy or alias or trace"
lee-llm-router doctor --config tests/fixtures/llm_test.yaml
```

---

## 2026-02-18 — Repository Guidelines Refresh

**What was built:** Replaced the sprawling agent instructions with a 384-word `AGENTS.md` titled “Repository Guidelines.” The document now covers structure, commands, style, testing, PR etiquette, and security tips with concise bullets and concrete examples (`pip install -e ".[dev]"`, `lee-llm-router doctor --config ...`).

**Why it matters:** Contributors now have a single reference that matches the current repo state (async providers, 54 tests, doc layout). Short guidance reduces onboarding time and prevents divergence from the established workflow documents.

**How to Verify**

```bash
wc -w AGENTS.md         # → 384 (within 200–400 target)
cat AGENTS.md           # confirm sections + commands listed in spec
```

---

## 2026-02-18 — Sprint 5: Async, Fallbacks, Extended Telemetry — P2 Complete

**What was built:** Full async support via `httpx` (`complete_async()` in `OpenRouterHTTPProvider` and `LLMRouter`), provider fallback chain with `policy.fallback` telemetry events, token accounting hook (`on_token_usage` callback), `EventSink` protocol for external event consumption, and `lee-llm-router trace --last N` CLI subcommand. Added `complete_async` to `MockProvider` for testability.

**Why it matters:** Consumers can now use `await router.complete_async()` for non-blocking I/O. The fallback chain provides resilience — if a primary provider fails (rate limit, timeout), the router automatically tries configured fallbacks. Token accounting enables budget tracking. `EventSink` allows integration with external telemetry systems (LeeClaw/Meridian session logs).

**Key design choices:**
- `complete_async()` in router checks `hasattr(provider, "complete_async")` and calls natively; falls back to `asyncio.to_thread()` for sync-only providers — no breaking changes to existing providers
- Fallback chain respects `should_retry()` — `CONTRACT_VIOLATION` never retries, preserving the Phase 0 guarantee
- Token hook and EventSink exceptions are swallowed (with `try/except: pass`) — buggy callbacks can't break requests
- Trace CLI reads from the same directory structure used by `LocalFileTraceStore` — no config duplication

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/providers/http.py` | Replaced `requests` with `httpx`; added `complete_async()` native async method |
| `src/lee_llm_router/providers/mock.py` | Added `complete_async()` for test parity with HTTP provider |
| `src/lee_llm_router/router.py` | Added `complete_async()` with fallback chain; wired `on_token_usage` hook and `EventSink` |
| `src/lee_llm_router/telemetry.py` | Added `EventSink` Protocol, `RouterEvent` dataclass |
| `src/lee_llm_router/doctor.py` | Added `trace --last N --dir` subcommand |
| `tests/test_async.py` | 16 tests covering async, fallback, hooks, EventSink, trace CLI |

**How to Verify**

```bash
.venv/bin/pytest -v                          # → 54 passed
.venv/bin/pytest tests/test_async.py -v      # → 16 passed (Sprint 5)

# Async works
.venv/bin/python -c "
import asyncio
from lee_llm_router import LLMRouter, load_config
from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig

cfg = LLMConfig(
    default_role='test',
    providers={'mock': ProviderConfig(name='mock', type='mock', raw={})},
    roles={'test': RoleConfig(name='test', provider='mock', model='m')}
)
router = LLMRouter(cfg)
resp = asyncio.run(router.complete_async('test', [{'role': 'user', 'content': 'hi'}]))
print('Async OK:', resp.text)
"

# Trace CLI works
.venv/bin/lee-llm-router trace --last 5
```

---

## 2026-02-18 — Sprint 4: Doctor CLI, Abstractions, Docs, PyPI — P1 Complete

**What was built:** Full doctor CLI (`doctor` + `template` subcommands), `RoutingPolicy` protocol + `SimpleRoutingPolicy` default with `policy.choice` telemetry logging, `TraceStore` protocol + `LocalFileTraceStore`, complete README + `docs/config.md` + `docs/providers.md`, PyPI-ready packaging (`python -m build` → `.whl` + `.tar.gz`). Product-definition acceptance checklist is 100% checked off.

**Why it matters:** Adopters can now `pip install lee-llm-router`, run `lee-llm-router doctor --config llm.yaml` to verify setup, inject custom routing policies and trace sinks, and read reference docs without touching source code. The package is distributable.

**Key design choices:**
- `policy.py` is a new file (not bolted onto `router.py`) — keeping the abstraction boundary clean
- `TraceStore` owns file writing; `record_success`/`record_error` now log-only — separation of concerns
- `doctor.check_config()` is a pure function returning `(errors, warnings)` — testable without subprocess
- `main()` accepts `argv` list for direct invocation in tests — no subprocess overhead

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/policy.py` | `RoutingPolicy` Protocol, `ProviderChoice`, `SimpleRoutingPolicy` |
| `src/lee_llm_router/telemetry.py` | `TraceStore` Protocol + `LocalFileTraceStore`; logging separated from file I/O |
| `src/lee_llm_router/router.py` | Policy + TraceStore wired in; `policy.choice` event logged |
| `src/lee_llm_router/doctor.py` | Full CLI: `doctor` + `template` subcommands |
| `src/lee_llm_router/__init__.py` | Phase 1 names exported |
| `pyproject.toml` | PyPI-ready: keywords, classifiers, package-data, urls |
| `README.md` | Full API + CLI + architecture docs |
| `docs/config.md` | Config schema reference |
| `docs/providers.md` | Provider adapter + failure type reference |
| `product-definition.md` | All acceptance items checked `[x]` |
| `tests/test_doctor.py` | 7 doctor + CLI tests |
| `dist/` | `.whl` + `.tar.gz` artifacts |

**How to Verify**

```bash
.venv/bin/pytest -v                                                    # → 38 passed
.venv/bin/lee-llm-router doctor --config tests/fixtures/llm_test.yaml # → exit 0
.venv/bin/lee-llm-router template | head -3                            # → YAML output
ls dist/                                                               # → .whl + .tar.gz
```

---

## 2026-02-18 — Sprint 3: Config, Router, Telemetry — P0 Complete

**What was built:** Full end-to-end stack — YAML config loader, `LLMRouter` facade, `LLMClient` legacy wrapper, structured telemetry with JSON trace files, pass-through compression stub. `from lee_llm_router import LLMRouter, LLMClient, load_config, LLMRequest, LLMResponse` now works. **P0 extraction is complete.**

**Why it matters:** Any downstream consumer (Meridian, LeeClaw, future projects) can now install `lee-llm-router`, point it at a config YAML, and call `LLMRouter.complete()` with the same interface they already use. Trace files are written automatically on every call.

**Key design choices:**
- `trace_dir` param on `LLMRouter.__init__` keeps tests hermetic (no filesystem side-effects)
- Router wraps all bare `Exception` in `LLMRouterError(FailureType.UNKNOWN)` so callers always get a typed error
- `LLMClient` is a one-liner wrapper — callers migrating from LeeClaw change only their import
- `ConfigError(ValueError)` is separate from `LLMRouterError` so config mistakes are distinguishable from runtime failures

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/config.py` | `load_config()`, `LLMConfig`, `ProviderConfig`, `RoleConfig`, `ConfigError` |
| `src/lee_llm_router/router.py` | `LLMRouter.complete()` — full flow with telemetry |
| `src/lee_llm_router/client.py` | `LLMClient` legacy wrapper |
| `src/lee_llm_router/telemetry.py` | `start_trace()`, `record_success()`, `record_error()`, `_write_trace()` |
| `src/lee_llm_router/compression.py` | Pass-through stub |
| `src/lee_llm_router/templates/llm.example.yaml` | Fully annotated example config |
| `src/lee_llm_router/__init__.py` | All Phase 0 public names exported |
| `tests/fixtures/llm_test.yaml` | Minimal test config (MockProvider) |
| `tests/test_config.py` | 6 config loader tests |
| `tests/test_router.py` | 8 end-to-end router + client tests |

**How to Verify**

```bash
.venv/bin/python -c "from lee_llm_router import LLMRouter, LLMClient, load_config, LLMRequest, LLMResponse; print('OK')"
.venv/bin/pytest -v   # → 31 passed
```

---

## 2026-02-18 — Sprint 2: Provider Layer (P0)

**What was built:** Fully implemented the provider layer — `LLMRequest`/`LLMResponse` dataclasses, `FailureType` enum, `LLMRouterError`, `Provider` Protocol, `should_retry()` helper, and all four adapters (`MockProvider`, `OpenRouterHTTPProvider`, `CodexCLIProvider`, built-in registry). 13 unit tests; no real HTTP or subprocess calls in any test.

**Why it matters:** The provider layer is the core abstraction of the router. Sprint 3 (config + router) sits on top of it — all provider calls go through these interfaces. `MockProvider` is the test backbone for every future sprint.

**Key design choices (Phase 0 — no new abstractions):**
- `should_retry(error)` encodes the "never retry CONTRACT_VIOLATION" rule without touching the router
- `registry._register_builtins()` auto-registers on import so callers never need to wire providers manually
- HTTP and CLI providers map all native errors into `LLMRouterError` + `FailureType` so the router has a single exception type to handle

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/response.py` | `LLMRequest`, `LLMResponse`, `LLMUsage` dataclasses |
| `src/lee_llm_router/providers/base.py` | `FailureType`, `LLMRouterError`, `should_retry()`, `Provider` Protocol |
| `src/lee_llm_router/providers/mock.py` | Deterministic echo provider |
| `src/lee_llm_router/providers/http.py` | OpenRouter/OpenAI REST adapter (requests) |
| `src/lee_llm_router/providers/codex_cli.py` | Subprocess adapter |
| `src/lee_llm_router/providers/registry.py` | `register()`, `get()`, `available()`, auto built-in registration |
| `src/lee_llm_router/__init__.py` | Exports `LLMRequest`, `LLMResponse`, `LLMUsage`, `LLMRouterError`, `FailureType` |
| `tests/test_providers.py` | 13 unit tests |

**How to Verify**

```bash
.venv/bin/pytest tests/test_providers.py -v   # → 13 passed
.venv/bin/pytest -v                            # → 17 passed (all)
```

---

## 2026-02-18 — Sprint 1: Package Setup (P0)

**What was built:** Renamed the broken scaffold (`src/Lee LLM Router/` with space) to a properly importable Python package (`src/lee_llm_router/`). Fixed `pyproject.toml` (name, runtime deps, entry point). Created the full module skeleton matching `design.md`. Created `.venv` and `tests/`. Sprint plan and context.md created today as well.

**Why it matters:** Nothing in Sprint 2+ can work without an importable package. The skeleton establishes the exact file tree that LeeClaw modules will be ported into — no structural decisions needed later.

**Created**

| File/Dir | Purpose |
|----------|---------|
| `src/lee_llm_router/__init__.py` | Package root, `__version__ = "0.1.0"` |
| `src/lee_llm_router/config.py` | Stub (Sprint 3) |
| `src/lee_llm_router/router.py` | Stub (Sprint 3) |
| `src/lee_llm_router/client.py` | Stub (Sprint 3) |
| `src/lee_llm_router/response.py` | Stub (Sprint 2) |
| `src/lee_llm_router/compression.py` | Stub (Sprint 3) |
| `src/lee_llm_router/telemetry.py` | Stub (Sprint 3) |
| `src/lee_llm_router/doctor.py` | Stub `main()` (Sprint 4) |
| `src/lee_llm_router/providers/` | All 5 provider stubs (Sprint 2) |
| `src/lee_llm_router/templates/llm.example.yaml` | Placeholder (Sprint 4) |
| `tests/__init__.py`, `conftest.py`, `test_smoke.py` | 4 smoke tests |
| `pyproject.toml` | Fixed: `lee-llm-router`, pyyaml + requests deps, entry point |
| `.venv/` | Python 3.13 virtualenv for the project |
| `sprint-plan.md` | 5-sprint plan across 3 phases |

**How to Verify**

```bash
source .venv/bin/activate
python -c "import lee_llm_router; print(lee_llm_router.__version__)"  # → 0.1.0
pytest tests/test_smoke.py -v   # → 4 passed
```

---

## 2026-02-17 — Project Scaffolded

**Project initialized** with init-agent.

### Created

| File | Purpose |
|------|---------|
| `AGENTS.md` | AI agent guide and conventions |
| `WHERE_AM_I.md` | Quick orientation for agents |
| `feedback.md` | Human feedback capture |
| `README.md` | Project documentation |
| `context.md` | Session working memory |
| `result-review.md` | This file - running log |
| `sprint-plan.md` | Sprint tracking |

### How to Verify

1. Check all files exist: `ls *.md`
2. Read AGENTS.md to understand project conventions
3. Check context.md for current state

---

*Add new entries above this line. Keep the newest work at the top.*
