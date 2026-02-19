# Agent Guide: Lee LLM Router

> **For AI agents working on the Lee LLM Router project.**
>
> Read this file first, then read `context.md` for current state.

---

## Project Overview

**Lee LLM Router** is a Python package that provides a reusable, battle-tested LLM routing kernel. It was extracted from LeeClaw and Meridian to provide consistent LLM routing, telemetry, and governance across projects.

### What This Package Does

- **Configuration-driven routing**: Load a YAML config describing roles, providers, fallbacks, and guardrails
- **Multiple provider support**: HTTP APIs (OpenRouter, OpenAI-compatible), CLI wrappers (Codex CLI), and mock providers
- **Consistent telemetry**: Structured logging and JSON trace files for every request
- **CLI tooling**: Doctor command for config validation, template generator, trace viewer
- **Pluggable architecture**: Custom routing policies, trace stores, and event sinks

### Key Use Cases

| User | Needs | Example |
|------|-------|---------|
| Meridian agents | Deterministic routing + JSON contract + trace files | `LLMClient.complete(role="planner", messages=[...])` |
| LeeClaw research | Budget telemetry, fallback to local CLI | `LLMRouter(role="pattern_extractor").complete()` |
| Future projects | Re-use config + CLI doctor without copying directories | `pip install lee-llm-router` |

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Build system | setuptools (via `pyproject.toml`) |
| HTTP client | httpx (sync + async) |
| YAML parsing | PyYAML |
| Testing | pytest |
| Formatting | black (line length: 88) |
| Linting | ruff |

### Runtime Dependencies

```toml
pyyaml>=6.0
httpx>=0.25
```

### Dev Dependencies

```toml
pytest>=7.0
black>=23.0
ruff>=0.1.0
build>=1.0
```

---

## Project Structure

```
lee-llm-router/
├── pyproject.toml              # Package configuration
├── README.md                   # Human-facing documentation
├── AGENTS.md                   # This file
├── context.md                  # Session state (read at start, update at end)
├── sprint-plan.md              # Current sprint tasks
├── result-review.md            # Recently completed work log
├── design.md                   # Technical architecture
├── product-definition.md       # Product requirements
├── src/
│   └── lee_llm_router/
│       ├── __init__.py         # Public API exports
│       ├── config.py           # YAML loader + dataclasses
│       ├── router.py           # LLMRouter facade (main entry point)
│       ├── client.py           # LLMClient legacy wrapper
│       ├── response.py         # LLMRequest / LLMResponse dataclasses
│       ├── policy.py           # RoutingPolicy abstraction
│       ├── telemetry.py        # Structured logging + TraceStore
│       ├── compression.py      # Prompt compression hook
│       ├── doctor.py           # CLI entry point
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py         # Provider protocol + LLMRouterError
│       │   ├── registry.py     # Provider registration/discovery
│       │   ├── mock.py         # Deterministic echo provider
│       │   ├── http.py         # OpenRouter/OpenAI HTTP provider
│       │   └── codex_cli.py    # Subprocess provider
│       └── templates/
│           └── llm.example.yaml
├── tests/
│   ├── conftest.py             # Shared pytest fixtures
│   ├── test_smoke.py           # Import/version tests
│   ├── test_config.py          # Config loader tests
│   ├── test_providers.py       # Provider adapter tests
│   ├── test_router.py          # Router integration tests
│   ├── test_doctor.py          # CLI tests
│   └── test_async.py           # Async completion tests
├── docs/
│   ├── config.md               # Config schema reference
│   └── providers.md            # Provider adapter reference
└── backlog/
    ├── schema.md               # Backlog item schema
    ├── template.md             # Backlog item template
    ├── candidates/             # AI writes here (read-only after)
    ├── approved/               # Human curates
    ├── parked/                 # Deferred items
    └── implemented/            # Completed items
```

---

## Build and Development Commands

### Setup

```bash
# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lee_llm_router

# Run specific test file
pytest tests/test_router.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Format code
black src/

# Check linting
ruff check src/

# Fix auto-fixable issues
ruff check src/ --fix
```

### Building Distribution

```bash
# Build wheel and source distribution
python -m build

# Output goes to dist/
ls dist/
# lee_llm_router-0.1.0-py3-none-any.whl
# lee_llm_router-0.1.0.tar.gz
```

---

## Code Style Guidelines

### General Style

- Follow PEP 8 with black formatting (line length: 88)
- Use type hints throughout (`from __future__ import annotations`)
- Write docstrings in Google style
- Keep functions focused and small

### Imports

```python
from __future__ import annotations  # Always first

# Standard library (alphabetical)
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Third party (alphabetical)
import httpx
import yaml

# Local imports (alphabetical)
from lee_llm_router.providers.base import LLMRouterError
from lee_llm_router.response import LLMRequest
```

### Naming Conventions

| Item | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `LLMRouter`, `TraceStore` |
| Functions | snake_case | `load_config()`, `complete()` |
| Constants | UPPER_SNAKE | `DEFAULT_TIMEOUT` |
| Private | _leading_underscore | `_resolve_role()` |
| Protocols | PascalCase + Protocol suffix | `RoutingPolicy`, `EventSink` |

### Error Handling

- All provider errors wrap in `LLMRouterError` with `FailureType`
- Use exception chaining (`raise ... from exc`)
- Never swallow exceptions silently

---

## Architecture Overview

### Core Flow

```
User Request
     ↓
LLMRouter.complete(role, messages, **overrides)
     ↓
_resolve_role() → policy.choose() → build LLMRequest
     ↓
compress() (optional)
     ↓
provider.complete(request, config)
     ↓
record telemetry → trace_store.write() → return LLMResponse
```

### Key Abstractions

| Component | Purpose | Default Implementation |
|-----------|---------|----------------------|
| `RoutingPolicy` | Choose provider per request | `SimpleRoutingPolicy` |
| `TraceStore` | Persist trace records | `LocalFileTraceStore` |
| `EventSink` | Consume router events | None (optional) |
| `Provider` | Execute completions | Registry-based |

### Failure Types

| Type | Retryable | Meaning |
|------|-----------|---------|
| `TIMEOUT` | Yes | Request timed out |
| `RATE_LIMIT` | Yes | Provider rate-limited |
| `PROVIDER_ERROR` | Yes | Server/config issue |
| `INVALID_RESPONSE` | Yes | Unexpected structure |
| `CONTRACT_VIOLATION` | **No** | Schema/JSON failure |
| `CANCELLED` | No | Request cancelled |
| `UNKNOWN` | Yes | Unclassified |

---

## Testing Strategy

### Test Organization

| File | Scope |
|------|-------|
| `test_smoke.py` | Import/version checks |
| `test_config.py` | YAML loader validation |
| `test_providers.py` | Provider adapter unit tests |
| `test_router.py` | End-to-end router tests |
| `test_doctor.py` | CLI command tests |
| `test_async.py` | Async completion tests |

### Test Patterns

```python
# Use fixtures from conftest.py
@pytest.fixture
def mock_config():
    return load_config(FIXTURES / "llm_test.yaml")

# Mock HTTP calls
def test_http_provider_success(monkeypatch):
    # Mock httpx or use responses library
    ...

# Use tmp_path for file operations
def test_trace_file_written(mock_config, tmp_path):
    router = LLMRouter(mock_config, trace_dir=tmp_path)
    ...

# Capture log output
def test_telemetry_logged(mock_config, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="lee_llm_router"):
        ...
```

### Mock Provider

Use `MockProvider` for tests — it's deterministic and has no I/O:

```python
from lee_llm_router.providers.mock import MockProvider

mock = MockProvider()
# Configurable via raw config:
# - response_text: fixed response
# - raise_timeout: simulate timeout
# - raise_contract_violation: simulate schema error
# - raise_rate_limit: simulate rate limit
```

---

## Configuration Format

Minimal valid config:

```yaml
llm:
  default_role: planner
  providers:
    openrouter:
      type: openrouter_http
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
  roles:
    planner:
      provider: openrouter
      model: openai/gpt-4o
      temperature: 0.2
```

See `docs/config.md` for full schema.

---

## CLI Usage

```bash
# Validate config
lee-llm-router doctor --config config/llm.yaml
lee-llm-router doctor --config config/llm.yaml --role planner

# Generate template
lee-llm-router template > config/llm.yaml

# View recent traces
lee-llm-router trace --last 5
lee-llm-router trace --last 10 --dir /path/to/traces
```

Exit code 0 = healthy (for doctor command).

---

## Document Protocol

### Start of Every Session

1. **Read this file** (`AGENTS.md`) — conventions and guardrails
2. **Read `context.md`** — current state, what's happening now, next actions
3. **Check `result-review.md`** — what was recently completed
4. **Read `sprint-plan.md`** — current sprint tasks and priorities

### End of Every Session

1. **Update `context.md`**:
   - Move completed items to "Recently Completed"
   - Update "Next Actions Queue"
   - Add new "Decisions Locked"
   - Update "Last Updated" timestamp
   - Keep "Open Questions" ≤ 5

2. **Update `result-review.md`**:
   - Add new entry at the TOP (newest first)
   - Document what was built, why it matters, how to verify

3. **Update `sprint-plan.md`**:
   - Mark completed tasks
   - Update task statuses

---

## Guardrails

### ✅ Allowed

- Write and modify code for Lee LLM Router
- Create and update documentation
- Add tests for new functionality
- Research solutions to technical problems
- Update context and decision logs
- Create backlog items in `backlog/candidates/`

### ❌ Not Allowed (Without Explicit Permission)

- Add external runtime dependencies
- Make breaking changes to existing APIs
- Delete files without confirming necessity
- Skip tests or documentation updates
- Commit directly to protected branches
- Move files out of `backlog/candidates/` (human curates)

---

## Communication Style

- **Concise**: Get to the point quickly
- **Specific**: Include file paths, line numbers, exact commands
- **Actionable**: Provide clear next steps
- **Honest**: Flag concerns or blockers immediately

---

## Decision Log

Document significant decisions here. Include:
- What was decided
- Why (rationale)
- When (date)
- Any alternatives considered

| Decision | Rationale | Date | Alternatives |
|----------|-----------|------|--------------|
| TinyClaw methodology | Build from scratch with small primitives; validate before scale | 2026-02-17 | — |
| httpx over requests | Native async support, modern HTTP client | 2026-02-18 | requests + asyncio wrapper |

---

## Document Reference

| File | When to Read | When to Update |
|------|--------------|----------------|
| `AGENTS.md` | Every session start | When conventions change |
| `context.md` | Every session start | Every session end |
| `result-review.md` | Every session start | When work completed |
| `WHERE_AM_I.md` | First time only | Rarely (orientation) |
| `sprint-plan.md` | Every session start | When tasks complete |
| `project-plan.md` | When direction unclear | Strategic changes only |
| `product-definition.md` | When scope unclear | Product changes only |
| `feedback.md` | When given feedback | Human adds feedback |
| `design.md` | When implementing features | When architecture changes |
| `backlog/schema.md` | Creating backlog items | Never (reference) |
| `backlog/template.md` | Creating backlog items | Never (copy-paste) |

### Backlog System

The `backlog/` folder uses this workflow:

```
candidates/  →  AI writes here (read-only after write)
approved/    →  Human moves items here when approved
parked/      →  Human moves items here (deferred)
implemented/ →  Builder moves items here when complete
```

**To create a backlog item**: Copy `backlog/template.md` to `backlog/candidates/BI-NNN-{kebab-title}.md` and fill in all fields.

---

## Quick Reference: Public API

```python
from lee_llm_router import (
    # Phase 0 — Core API
    LLMRouter,           # Main router class
    LLMClient,           # Legacy wrapper
    load_config,         # YAML loader
    LLMConfig,           # Config dataclass
    LLMRequest,          # Request dataclass
    LLMResponse,         # Response dataclass
    LLMUsage,            # Usage stats
    LLMRouterError,      # Exception class
    FailureType,         # Error classification enum
    
    # Phase 1 — Abstractions
    RoutingPolicy,       # Policy protocol
    SimpleRoutingPolicy, # Default policy
    ProviderChoice,      # Policy result
    TraceStore,          # Trace storage protocol
    LocalFileTraceStore, # Default file storage
    
    # Phase 2 — Extensions
    EventSink,           # Event consumer protocol
    RouterEvent,         # Event dataclass
)
```

---

*Generated by init-agent on 2026-02-17. Updated through exploration on 2026-02-18.*
