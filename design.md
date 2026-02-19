# Lee LLM Router — Technical Design

## 1. Context & Goals
Meridian’s `lib/llm/` module and LeeClaw’s `leeclaw.llm` package independently evolved the same primitives: load a YAML config, resolve roles → providers, execute completions across HTTP APIs or CLI wrappers, and log traces. Maintaining two copies has already caused drift. **Lee LLM Router** extracts the shared kernel into a reusable library with a stable API and CLI tooling.

Design goals:
- **Config parity** with existing projects (drop-in replacement).
- **Provider plugability**—new adapters can be registered without touching the core.
- **Traceability**—every request emits structured logs and optional trace files.
- **DX tooling**—doctor command, template generator, mock provider for CI.
- **Minimal dependencies** and pure-Python packaging.

Non-goals: full agent orchestration, prompt templating, hosting an LLM proxy.

### 1.1 Source Alignment
- **Implementation baseline (LeeClaw).** Copy `leeclaw.llm.config`, `leeclaw.llm.provider_registry`, and `leeclaw.llm.client` verbatim in Phase 0 so behavior remains identical.
- **Guardrail baseline (Meridian).** Mirror Meridian’s logging contract, evidence bundle expectations, and failure classification but do not import Meridian modules directly. Instead, restate the rules in this repo’s docs so they stand alone.
- **Isolation requirement.** Kimi Code pulls code into `lee-llm-router` first; downstream adoption in Meridian/LeeClaw only happens after the package is published. No live Meridian files change during this effort.

## 2. Functional Requirements
1. Load and validate YAML config describing providers, roles, default role, and optional fallbacks.
2. Expose `LLMRouter.complete(...)` that wraps provider invocation, prompt compression, retries, JSON mode, and telemetry.
3. Support both HTTP and subprocess providers (OpenRouter, LiteLLM proxies, `codex` CLI).
4. Emit trace files (success & error) compatible with Meridian’s collectors.
5. Provide `lee-llm-router doctor` CLI to validate config + environment + provider binaries.
6. Provide sample config template generator and inline schema documentation.
7. Offer mock provider for unit tests / offline runs.
8. Keep API backward compatible with `LLMClient` used today (`complete(role, messages, **kwargs)`).

### 2.1 Extraction Phases (Same as Product Brief)
1. **Phase 0 – Direct Extraction.** Copy LeeClaw modules, wire basic tests, prove parity. Only edits allowed: import path fixes, packaging glue, docstrings.
2. **Phase 1 – Encapsulation (Additive).** Introduce optional policy/event abstractions while preserving default behavior.
3. **Phase 2 – Enhancements.** Async support, fallback orchestration, budget hooks, etc.
Each pull request must state which phase it belongs to so reviewers can gate scope.

## 3. Architecture Overview
```
lee_llm_router/
├── config.py          # dataclasses + loader + env interpolation
├── router.py          # LLMRouter facade (wraps LLMClient)
├── client.py          # legacy-compatible interface
├── providers/
│   ├── base.py        # Provider protocol + exception types
│   ├── http.py        # Generic REST provider (OpenRouter/OpenAI-compatible)
│   ├── codex_cli.py   # Subprocess provider (Codex CLI)
│   ├── mock.py        # Echo provider for tests
│   └── registry.py    # Registration + discovery
├── compression.py     # optional prompt compression hook (ported from Meridian)
├── response.py        # LLMRequest/LLMResponse dataclasses
├── telemetry.py       # logger + trace file writers
├── doctor.py          # CLI entry (config validation, provider diagnostics)
└── templates/
    └── llm.example.yaml
```
Key layers:
- **Config Layer** — dataclasses + validation.
- **Router Layer** — resolves roles, handles compression/retries, delegates to providers.
- **Provider Layer** — plugins implementing `complete(request, provider_config)`.
- **Telemetry Layer** — structured logging & trace files.
- **Tooling Layer** — CLI + template generator.

## 4. Config Format
Maintain compatibility with Meridian/LeeClaw but add optional fields:
```yaml
llm:
  default_role: planner
  providers:
    openrouter:
      type: openrouter_http
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    codex_cli:
      type: codex_cli
      command: codex
      model_flag: --model
      output_flag: --output-last-message
  roles:
    planner:
      provider: openrouter
      model: gpt-5-codex
      temperature: 0.2
      json_mode: false
      fallback_providers: [codex_cli]
```
Enhancements planned:
- `api_key_env` helper to avoid plaintext keys.
- Optional `fallback_providers` per role (Phase 2).
- `compression_strategy` override per role.

## 5. Router Flow
1. **Resolve role** via `config.roles[role]`, defaulting when absent.
2. **Load provider config**; inject runtime parameters (model, workspace).
3. **Prompt compression** (if enabled globally or via kwargs).
4. **Build LLMRequest** (role, messages, JSON-mode, schema, tokens, temperature, timeout).
5. **Provider invocation** with context-managed timing.
6. **Telemetry** — log `llm.complete.start`, `llm.complete.success` (elapsed_ms, usage) or `llm.complete.error` with trace file path.
7. **Response normalization** — ensure `.text`, `.raw`, `.usage`, `.request_id` fields are populated; raise provider-specific errors upstream.

Pseudo-code:
```python
class LLMRouter:
    def complete(self, role, messages, **overrides):
        role_cfg, provider_cfg = resolve_role(role, self.config)
        request = build_request(role_cfg, messages, overrides)
        provider = get_provider(role_cfg.provider)
        trace = start_trace(request)
        try:
            response = provider.complete(request, provider_cfg)
            record_success(trace, response)
            return response
        except Exception as exc:
            record_error(trace, exc)
            raise
```

### 5.1 Routing Policy Layer
- Define `RoutingPolicy` abstraction (Phase 1) that accepts a `RouterRequest` + config snapshot and returns a `ProviderChoice` (provider name + overrides). Default implementation simply resolves `role.provider`, preserving current behavior.
- Policies live under `lee_llm_router.policy` and are optional; callers can inject custom policies (e.g., cost-aware, A/B testing) without touching the router core.
- Policy decisions must be logged in telemetry as `policy.choice` events with request-id linkage for auditability.

### 5.2 Failure Taxonomy & Guardrails
Wrap all provider exceptions in `LLMRouterError` that carries `failure_type`. Initial enum:
- `TIMEOUT`
- `RATE_LIMIT`
- `PROVIDER_ERROR`
- `INVALID_RESPONSE`
- `CONTRACT_VIOLATION` (schema mismatch, JSON parse failure)
- `CANCELLED`
- `UNKNOWN`

Rules:
1. Provider adapters map native errors into this taxonomy.
2. Router never retries on `CONTRACT_VIOLATION` unless caller overrides.
3. Telemetry + trace files must include `failure_type` so downstream platforms (Meridian) can distinguish infra issues from prompt issues.

## 6. Provider Plugin Interface
`providers/base.py` defines:
```python
class Provider(Protocol):
    name: str
    supported_types: set[str]

    def validate_config(self, config: dict[str, Any]) -> None: ...
    def complete(self, request: LLMRequest, config: dict[str, Any]) -> LLMResponse: ...
```
`registry.register(name, provider_cls)` for built-ins. Third parties can `lee_llm_router.providers.registry.register("my_provider", MyProvider)` before calling router.

Built-in adapters (Phase 1):
- `OpenRouterHTTPProvider` (requests-based, supports API key headers, streaming future)
- `CodexCLIProvider` (subprocess invocation, used by Meridian + LeeClaw)
- `MockProvider` for tests

Future adapters: LiteLLM, vLLM, generic OpenAI, Anthropic.

## 7. Telemetry & Evidence
- Use Python `logging` with structured `extra` fields identical to Meridian (event names: `llm.complete.*`). Emit the following minimum metadata: `request_id`, `work_package_id` (if provided), `role`, `provider`, `model`, `elapsed_ms`, `failure_type`, `policy_choice`.
- Event stream doubles as the “evidence bundle.” Each completion writes one JSON trace file plus per-stage logs when embedded inside Meridian.
- Trace files stored under `<workspace>/.agentleeops/traces/YYYYMMDD/<request_id>.json` when `workspace` provided; fallback to `$PROJECT/.lee-llm-router/traces/` if not. Storage location can be overridden via config/env so other consumers retain control.
- `TraceStore` abstraction (Phase 1) allows swapping local filesystem writers for custom sinks (S3, sqlite). Default implementation mirrors current Meridian folder layout.
- Provide optional hook to integrate with LeeClaw’s `SessionLogger` or any `EventSink` implementing `emit(event: RouterEvent)`. This keeps router self-contained but extensible.

## 8. CLI & Tooling
Entry points:
- `lee-llm-router doctor --config config/llm.yaml [--role planner]`
  - Validates file structure, provider types, resolves env vars, checks CLI binaries exist, performs a dry-run using mock provider.
- `lee-llm-router template > config/llm.yaml` — outputs example YAML with comments.
- `lee-llm-router trace --last` (Phase 2) — display last N traces.

## 9. Testing Strategy
- Unit tests mirroring LeeClaw’s coverage: config loader, provider registry, HTTP + CLI provider success/error cases, router-level tests verifying telemetry log capture, doctor CLI.
- Use `MockProvider` in tests & CI; optionally run real HTTP smoke tests behind `--run-http` marker.
- Provide fixtures for env vars and temporary config files.

## 10. Integration Plan
1. Publish `lee-llm-router` as editable dependency. Update Meridian/LeeClaw to import from library.
2. Remove duplicated modules in both repos once migration is stable.
3. Document migration steps & compatibility notes in `docs/migration.md`.

### 10.1 Implementation Notes for Kimi Code
1. Operate exclusively inside `/Users/leeharrington/projects/lee-llm-router` for this task; Meridian repo changes are out-of-scope until the package is ready.
2. Start by copying LeeClaw modules into `src/lee_llm_router/` preserving git history via `cp` + attribution notes in PR description.
3. Port LeeClaw tests into `tests/` and update import paths; run `pytest` locally.
4. Only after parity, layer in policy/failure/telemetry abstractions as described above.
5. Keep `design.md`, `product-definition.md`, and `project-plan.md` in sync whenever scope changes.

## 11. Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Config drift between projects | keep config schema backward-compatible; add schema validation + doc strings |
| Provider differences (e.g., CLI options) | provider-specific config sections with validation; doctor command enforces required keys |
| Telemetry path assumptions | allow workspace override; default to project-local `.lee-llm-router` folder |
| Future async requirements | design provider interface to support sync/async wrappers (Phase 2) |

## 12. Open Questions
1. Should fallback chains be part of Phase 1 or deferred?
2. Do we need built-in token accounting or leave hooks for host apps?
3. Where should trace files live when no workspace is provided (project root vs user cache)?

---
This design keeps the core small, surfaces the same API both Meridian and LeeClaw already rely on, and adds enough tooling to make the router reusable across future Tiny/Turbo projects.
