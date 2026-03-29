# Lee LLM Router Result Review

> **Running log of completed work.** Newest entries at the top.
>
> Each entry documents what was built, why it matters, and how to verify it works.

---

## 2026-03-29 - Sprint 7 Complete: Pi Coding Harness Reliability and Harness Validation

**What was built:** Added a repo-local simulated pi harness fixture and used it to harden the `codex_cli` provider around real subprocess failure classes. `codex_cli` now supports fixed `args`, optional `response_format: json`, JSON text extraction, usage passthrough, and deterministic `CONTRACT_VIOLATION` failures for malformed harness output. `doctor` now validates the configured provider and role wiring instead of a mock-only path, config loading now rejects unknown `default_role` and fallback providers, and docs/templates were updated to show the pi harness contract.

**Why it matters:** The downstream pi harness problem is now reproducible and diagnosable in this repo. Instead of vague CLI failures, malformed harness output is typed, traceable, and covered by regression tests. Downstream consumers can validate their harness config earlier and rely on a proven local contract for pi-style subprocess execution.

**How to Verify**

```bash
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_doctor.py -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml
# user-style pi harness validation:
# - create a temp codex_cli config with command=/Users/lee/projects/lee-llm-router/.venv/bin/python
# - args=[tests/fixtures/pi_harness.py, success_json]
# - response_format=json
# - run LLMRouter.complete("pi_local", [{"role":"user","content":"ship sprint 7"}])
```

---

## 2026-03-29 - Sprint 7 Planned: Pi Coding Harness Reliability and Harness Validation

**What was built:** Created a new Sprint 7 plan centered on pi coding harness reliability. The sprint now explicitly treats the recent downstream app failure as a first-class repo concern: reproduce the failure locally, harden harness validation and error handling, add regression coverage for success and failure cases, and add a user-style validation path for pi coding harness behavior.

**Why it matters:** A downstream app already failed because the pi coding harness path was not reliable enough. Turning that failure into an official sprint keeps the work grounded in an actual consumer problem and makes “prove the harness works” part of the delivery contract rather than an informal follow-up.

**How to Verify**

```bash
sed -n '1,260p' sprint-plan.md
sed -n '1,220p' context.md
sed -n '1,220p' WHERE_AM_I.md
```

---

## 2026-03-08 - Sprint 6 Complete: Vendored Source Snapshot Workflow

**What was built:** Added `lee-llm-router export-source --dest <path> [--force]` to export the full `src/lee_llm_router/` package tree as a vendorable snapshot. The export writes `.lee_llm_router_export.json` with version, source repo, source commit, and export timestamp. Added overwrite protection for non-empty destinations unless `--force` is provided. Updated README/product/sprint docs to shift downstream adoption toward explicit vendored snapshots instead of requiring a live runtime dependency on this package.

**Why it matters:** Downstream repos can now take intentional, pinned router snapshots without paying the reliability cost of package fetches, SSH auth, or environment-specific install drift. This keeps `lee-llm-router` as the upstream improvement lane while giving consumers local ownership of the runtime code they ship.

**How to Verify**

```bash
PYTHONPATH=src python -m pytest tests/test_doctor.py -q
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml
PYTHONPATH=src python -m lee_llm_router.doctor export-source --dest <temp-dir>
```

---
## 2026-03-02 â€” OpenAI Codex Subscription Provider (ChatGPT Subscription Auth)

**What was built:** Added `OpenAICodexSubscriptionHTTPProvider` with registry type `openai_codex_subscription_http` (aliases: `openai_codex_http`, `chatgpt_subscription_http`). The provider calls ChatGPT backend Codex Responses API, enforces `store: false`, and converts responses payloads into `LLMResponse`. Credential discovery mirrors OpenClaw patterns: `access_token_env` first, then macOS keychain (`Codex Auth`), then `CODEX_HOME/auth.json` / `~/.codex/auth.json`. Added doctor checks for this provider type and updated docs/template examples.

**Why it matters:** Projects can route through OpenAI ChatGPT subscription credentials directly from `lee-llm-router` without forcing usage-based OpenAI API keys. This enables the same Codex-subscription connectivity pattern used in OpenClaw while preserving router telemetry/fallback behavior.

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/providers/openai_codex_subscription.py` | New subscription-backed HTTP provider with env/keychain/auth.json credential resolution |
| `src/lee_llm_router/providers/registry.py` | Built-in registration + aliases |
| `src/lee_llm_router/doctor.py` | Provider validation for subscription auth config |
| `tests/test_providers.py` | Provider success + auth file + missing credential coverage |
| `tests/test_doctor.py` | Alias + token env validation coverage |
| `src/lee_llm_router/templates/llm.example.yaml` | New provider example stanza |
| `docs/config.md` | Provider type + key schema docs |
| `docs/providers.md` | Adapter behavior and failure mapping docs |
| `README.md` | Provider matrix and architecture list updated |

**How to Verify**

```bash
.venv/bin/pytest -q
.venv/bin/pytest -q tests/test_providers.py tests/test_doctor.py
.venv/bin/lee-llm-router doctor --config tests/fixtures/llm_test.yaml
```

---

## 2026-02-18 â€” Sprint 6 Prep: Provider Aliases, Policy Overrides, Trace Integrity

**What was built:** Added `openai_http` as a first-class alias in the provider registry plus doctor + router tests; policies can now override request attributes via `ProviderChoice.request_overrides` (without colliding with provider config overrides), and per-call kwargs now win over policy defaults. Trace attempts are persisted individually (`<request>-<attempt>-<provider>.json`), fallback runs write one file per attempt, and `lee-llm-router trace --last` shows attempt metadata.

**Why it matters:** Configs copied from OpenAI examples work without edits, cost-aware policies can enforce cheaper models reliably, and trace archives finally capture every failure/success along a fallback chainâ€”making the new `trace --last` output actionable during incident review.

**How to Verify**

```bash
pip install -e ".[dev]"            # ensures httpx is available
pytest tests/test_doctor.py \
       tests/test_router.py \
       tests/test_async.py -k "policy or alias or trace"
lee-llm-router doctor --config tests/fixtures/llm_test.yaml
```

---

## 2026-02-18 â€” Repository Guidelines Refresh

**What was built:** Replaced the sprawling agent instructions with a 384-word `AGENTS.md` titled â€œRepository Guidelines.â€ The document now covers structure, commands, style, testing, PR etiquette, and security tips with concise bullets and concrete examples (`pip install -e ".[dev]"`, `lee-llm-router doctor --config ...`).

**Why it matters:** Contributors now have a single reference that matches the current repo state (async providers, 54 tests, doc layout). Short guidance reduces onboarding time and prevents divergence from the established workflow documents.

**How to Verify**

```bash
wc -w AGENTS.md         # â†’ 384 (within 200â€“400 target)
cat AGENTS.md           # confirm sections + commands listed in spec
```

---

## 2026-02-18 â€” Sprint 5: Async, Fallbacks, Extended Telemetry â€” P2 Complete

**What was built:** Full async support via `httpx` (`complete_async()` in `OpenRouterHTTPProvider` and `LLMRouter`), provider fallback chain with `policy.fallback` telemetry events, token accounting hook (`on_token_usage` callback), `EventSink` protocol for external event consumption, and `lee-llm-router trace --last N` CLI subcommand. Added `complete_async` to `MockProvider` for testability.

**Why it matters:** Consumers can now use `await router.complete_async()` for non-blocking I/O. The fallback chain provides resilience â€” if a primary provider fails (rate limit, timeout), the router automatically tries configured fallbacks. Token accounting enables budget tracking. `EventSink` allows integration with external telemetry systems (LeeClaw/Meridian session logs).

**Key design choices:**
- `complete_async()` in router checks `hasattr(provider, "complete_async")` and calls natively; falls back to `asyncio.to_thread()` for sync-only providers â€” no breaking changes to existing providers
- Fallback chain respects `should_retry()` â€” `CONTRACT_VIOLATION` never retries, preserving the Phase 0 guarantee
- Token hook and EventSink exceptions are swallowed (with `try/except: pass`) â€” buggy callbacks can't break requests
- Trace CLI reads from the same directory structure used by `LocalFileTraceStore` â€” no config duplication

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
.venv/bin/pytest -v                          # â†’ 54 passed
.venv/bin/pytest tests/test_async.py -v      # â†’ 16 passed (Sprint 5)

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

## 2026-02-18 â€” Sprint 4: Doctor CLI, Abstractions, Docs, PyPI â€” P1 Complete

**What was built:** Full doctor CLI (`doctor` + `template` subcommands), `RoutingPolicy` protocol + `SimpleRoutingPolicy` default with `policy.choice` telemetry logging, `TraceStore` protocol + `LocalFileTraceStore`, complete README + `docs/config.md` + `docs/providers.md`, PyPI-ready packaging (`python -m build` â†’ `.whl` + `.tar.gz`). Product-definition acceptance checklist is 100% checked off.

**Why it matters:** Adopters can now `pip install lee-llm-router`, run `lee-llm-router doctor --config llm.yaml` to verify setup, inject custom routing policies and trace sinks, and read reference docs without touching source code. The package is distributable.

**Key design choices:**
- `policy.py` is a new file (not bolted onto `router.py`) â€” keeping the abstraction boundary clean
- `TraceStore` owns file writing; `record_success`/`record_error` now log-only â€” separation of concerns
- `doctor.check_config()` is a pure function returning `(errors, warnings)` â€” testable without subprocess
- `main()` accepts `argv` list for direct invocation in tests â€” no subprocess overhead

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
.venv/bin/pytest -v                                                    # â†’ 38 passed
.venv/bin/lee-llm-router doctor --config tests/fixtures/llm_test.yaml # â†’ exit 0
.venv/bin/lee-llm-router template | head -3                            # â†’ YAML output
ls dist/                                                               # â†’ .whl + .tar.gz
```

---

## 2026-02-18 â€” Sprint 3: Config, Router, Telemetry â€” P0 Complete

**What was built:** Full end-to-end stack â€” YAML config loader, `LLMRouter` facade, `LLMClient` legacy wrapper, structured telemetry with JSON trace files, pass-through compression stub. `from lee_llm_router import LLMRouter, LLMClient, load_config, LLMRequest, LLMResponse` now works. **P0 extraction is complete.**

**Why it matters:** Any downstream consumer (Meridian, LeeClaw, future projects) can now install `lee-llm-router`, point it at a config YAML, and call `LLMRouter.complete()` with the same interface they already use. Trace files are written automatically on every call.

**Key design choices:**
- `trace_dir` param on `LLMRouter.__init__` keeps tests hermetic (no filesystem side-effects)
- Router wraps all bare `Exception` in `LLMRouterError(FailureType.UNKNOWN)` so callers always get a typed error
- `LLMClient` is a one-liner wrapper â€” callers migrating from LeeClaw change only their import
- `ConfigError(ValueError)` is separate from `LLMRouterError` so config mistakes are distinguishable from runtime failures

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/config.py` | `load_config()`, `LLMConfig`, `ProviderConfig`, `RoleConfig`, `ConfigError` |
| `src/lee_llm_router/router.py` | `LLMRouter.complete()` â€” full flow with telemetry |
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
.venv/bin/pytest -v   # â†’ 31 passed
```

---

## 2026-02-18 â€” Sprint 2: Provider Layer (P0)

**What was built:** Fully implemented the provider layer â€” `LLMRequest`/`LLMResponse` dataclasses, `FailureType` enum, `LLMRouterError`, `Provider` Protocol, `should_retry()` helper, and all four adapters (`MockProvider`, `OpenRouterHTTPProvider`, `CodexCLIProvider`, built-in registry). 13 unit tests; no real HTTP or subprocess calls in any test.

**Why it matters:** The provider layer is the core abstraction of the router. Sprint 3 (config + router) sits on top of it â€” all provider calls go through these interfaces. `MockProvider` is the test backbone for every future sprint.

**Key design choices (Phase 0 â€” no new abstractions):**
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
.venv/bin/pytest tests/test_providers.py -v   # â†’ 13 passed
.venv/bin/pytest -v                            # â†’ 17 passed (all)
```

---

## 2026-02-18 â€” Sprint 1: Package Setup (P0)

**What was built:** Renamed the broken scaffold (`src/Lee LLM Router/` with space) to a properly importable Python package (`src/lee_llm_router/`). Fixed `pyproject.toml` (name, runtime deps, entry point). Created the full module skeleton matching `design.md`. Created `.venv` and `tests/`. Sprint plan and context.md created today as well.

**Why it matters:** Nothing in Sprint 2+ can work without an importable package. The skeleton establishes the exact file tree that LeeClaw modules will be ported into â€” no structural decisions needed later.

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
python -c "import lee_llm_router; print(lee_llm_router.__version__)"  # â†’ 0.1.0
pytest tests/test_smoke.py -v   # â†’ 4 passed
```

---

## 2026-02-17 â€” Project Scaffolded

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
