# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable + dev dependencies)
pip install -e ".[dev]"

# Run tests
pytest

# Run a single test file or test
pytest tests/test_config.py
pytest tests/test_router.py::test_complete_success

# Format and lint
black src/
ruff check src/

# Doctor CLI (once implemented)
python -m lee_llm_router.doctor --config config/llm.yaml
```

## Project Status

Early-stage (Phase 0). The `src/Lee LLM Router/` scaffold is a placeholder. The real package will live at `src/lee_llm_router/` once the LeeClaw module extraction begins.

## Architecture

The goal is to extract a shared LLM routing kernel from two internal projects (LeeClaw = implementation source, Meridian = guardrail reference) into a standalone Python package `lee_llm_router`.

**Planned package layout** (from `design.md`):
```
src/lee_llm_router/
├── config.py          # YAML loader + dataclasses + env interpolation
├── router.py          # LLMRouter facade (high-level entry point)
├── client.py          # Legacy-compatible LLMClient interface
├── response.py        # LLMRequest / LLMResponse dataclasses
├── compression.py     # Optional prompt compression hook
├── telemetry.py       # Structured logger + JSON trace file writers
├── doctor.py          # CLI: config validation, provider diagnostics
├── providers/
│   ├── base.py        # Provider Protocol + exception types
│   ├── http.py        # OpenRouter / OpenAI-compatible REST provider
│   ├── codex_cli.py   # Subprocess provider (Codex CLI)
│   ├── mock.py        # Deterministic echo provider for tests/CI
│   └── registry.py    # register() + discovery
└── templates/
    └── llm.example.yaml
```

**Key design decisions:**
- Config is YAML with `llm.providers` and `llm.roles` sections; roles map to providers with per-role overrides (model, temperature, json_mode, fallback_providers).
- `api_key_env` pattern — config references env var names, not plaintext keys.
- `Provider` is a `Protocol` — new adapters register via `registry.register(name, cls)`.
- All exceptions wrap to `LLMRouterError` with a `failure_type` enum (TIMEOUT, RATE_LIMIT, PROVIDER_ERROR, INVALID_RESPONSE, CONTRACT_VIOLATION, CANCELLED, UNKNOWN). Never retry on `CONTRACT_VIOLATION`.
- Telemetry event names follow Meridian's `llm.complete.start / .success / .error` convention; trace files go to `<workspace>/.agentleeops/traces/YYYYMMDD/<request_id>.json` or `.lee-llm-router/traces/` fallback.
- Router flow: resolve role → build request → (optional) compress → invoke provider → record telemetry → return/raise.

**Phase gating:**
- **Phase 0** — copy LeeClaw modules verbatim (only fix imports/packaging); no new abstractions.
- **Phase 1** — additive: `RoutingPolicy` abstraction, `TraceStore` abstraction, doctor CLI, template generator.
- **Phase 2** — async HTTP, fallback chains, token accounting hooks, metrics exporter.

PRs must state which phase they belong to.

## Agent Workflow

### Session Start (every session, in order)

1. Read `AGENTS.md` — conventions and guardrails
2. Read `context.md` — current state, what's happening now, next actions
3. Read `result-review.md` — what was recently completed
4. Read `sprint-plan.md` — current sprint tasks and priorities

### Session End (critical — another agent may pick up next)

**`context.md`** — update every field:
- Move completed items to "Recently Completed"
- Update "Next Actions Queue"
- Add new "Decisions Locked"
- Update "Last Updated" timestamp
- Keep "Open Questions" ≤ 5

**`result-review.md`** — add a new entry at the TOP (newest first):
- What was built, why it matters, how to verify

**`sprint-plan.md`** — mark completed tasks, update statuses

> `context.md` is the handoff document. Lee switches between Claude Code and Kimi Code mid-project. If `context.md` is stale, the next agent starts blind.

### Document Reference

| File | Read when | Update when |
|------|-----------|-------------|
| `AGENTS.md` | Every session start | Conventions change |
| `context.md` | Every session start | Every session end |
| `result-review.md` | Every session start | Work completed |
| `sprint-plan.md` | Every session start | Tasks complete |
| `WHERE_AM_I.md` | First time only | Rarely |
| `project-plan.md` | Direction unclear | Strategic changes only |
| `product-definition.md` | Scope unclear | Product changes only |
| `feedback.md` | When given feedback | Human adds feedback |
| `backlog/schema.md` | Creating backlog items | Never (reference) |
| `backlog/template.md` | Creating backlog items | Never (copy-paste) |

### Backlog System

```
backlog/candidates/   ← AI writes here (read-only after write)
backlog/approved/     ← Human moves items here
backlog/parked/       ← Human moves items here (deferred)
backlog/implemented/  ← Builder moves items here when done
```

Create items as `backlog/candidates/BI-NNN-{kebab-title}.md` using `backlog/template.md`.

### Guardrails

**Allowed:** write/modify code, create/update docs, add tests, research, update context and decision logs, create backlog items in `candidates/`.

**Not allowed without explicit permission:**
- Add external runtime dependencies
- Make breaking changes to existing APIs
- Delete files without confirming necessity
- Skip tests or documentation updates
- Commit directly to protected branches
- Move files out of `backlog/candidates/` (human curates)

### Communication Style

- **Concise** — get to the point
- **Specific** — include file paths, line numbers, exact commands
- **Actionable** — provide clear next steps
- **Honest** — flag concerns or blockers immediately

### Decision Log

When locking a significant decision, record it in `AGENTS.md`'s Decision Log table with: what was decided, rationale, date, alternatives considered.

### Constraints

- No external runtime deps without permission (target: `pyyaml`, `requests`/`httpx`, optionally `rich`)
- No breaking API changes; config must stay backward-compatible with Meridian/LeeClaw
- Pure Python — no compiled extensions
- Use `MockProvider` in all tests; real HTTP tests require `--run-http` marker
