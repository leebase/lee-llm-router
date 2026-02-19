# Lee LLM Router — Product Definition

## Vision
Build a reusable, battle-tested LLM routing kernel that distills the lessons from **Meridian's** production pipeline and **LeeClaw's** research agents into a single Python library. Any project should be able to drop in one config file, point to multiple providers, and immediately inherit the same reliability, tracing, and governance we already trust. The first milestone is purely documentation and packaging work so Kimi Code can implement the extraction without touching live Meridian files.

## Current State Snapshot
- **LeeClaw** already ships the most up-to-date router primitives (provider registry, config loader, retries). Treat this as the canonical implementation to extract.
- **Meridian** carries the mature governance patterns (evidence bundle expectations, failure classification, telemetry shape). Use it as a reference for guardrails, not as the code donor.
- **Lee LLM Router repo** currently contains only documentation, project scaffolding, and placeholder tests; there are no shared libraries yet. This keeps Kimi's work isolated from other in-flight changes.

## Guiding Principles
1. **Start with what already works.** Copy LeeClaw's proven modules first, get parity, and only then add abstractions.
2. **No rewrite.** Any change that isn't required to make the code importable should be deferred to Phase 1/2.
3. **Explicit provenance.** Every feature call-out should cite whether it came from LeeClaw (implementation) or Meridian (operational guardrail) so downstream reviews stay crisp.
4. **Documentation-first handoff.** Kimi Code implements; Codex supplies specs, migration notes, and acceptance tests.

## Mission
Provide a lightweight package (`lee_llm_router`) that:
1. Loads a declarative YAML config describing roles, providers, fallbacks, and guardrails.
2. Routes completion requests to the right backend (HTTP APIs, CLI wrappers, proxies) with per-role overrides.
3. Emits a consistent telemetry & evidence trail for every request.
4. Includes tooling (doctor CLI, mock providers, integration tests) so adopters can verify setups quickly.

## Users & Use Cases
| User | Needs | Example |
|------|-------|---------|
| Meridian agents (Ralph/Test/Architect) | deterministic routing + JSON contract + trace files | `LLMClient.complete(role="planner", messages=[...])`
| LeeClaw research loops | run long-lived analysis with budget telemetry, fallback to local CLI | `LLMRouter(role="pattern_extractor").complete()`
| Future Tiny/Turbo projects | re-use config + CLI doctor without copying whole directories | install `lee-llm-router`, run `lee-llm-router doctor`

## Out-of-the-box Capabilities (Phase 1)
1. **Config Schema** – Same role/provider data classes used in Meridian/LeeClaw, but packaged as a standalone module. Supports environment interpolation and includes a generated template.
2. **Provider Registry** – Bundled adapters for:
   - HTTP APIs (OpenRouter, OpenAI-compatible, Anthropic)
   - CLI bridges (Codex CLI, custom shell commands)
   - Local proxies (LiteLLM/vLLM) via generic REST provider
3. **Router / Client** – High-level `LLMRouter.complete(role, messages, **options)` with:
   - Prompt compression hook (optional) from Meridian
   - JSON-mode enforcement + post-processing
   - Timeout & retry policy per role
4. **Telemetry / Evidence** – Structured logging identical to Meridian's `llm.complete.*` events plus optional JSON trace files for each request.
5. **Doctor CLI** – `python -m lee_llm_router.doctor --config config/llm.yaml` validates providers, environment variables, CLI availability.
6. **Mock / Sandbox provider** – deterministic echo provider for tests and CI.

## Nice-to-haves (Phase 2+)
- Token accounting + budget hooks (used in LeeClaw analytics)
- Automatic fallback chain per role (e.g., try OpenRouter → Codex CLI)
- Async API using `httpx`
- Metrics exporter for Prometheus / OpenTelemetry

## Non-Goals (for now)
- Hosting an LLM proxy/server (we rely on external services like LiteLLM/vLLM)
- Prompt templating (projects keep their own prompt stacks)
- Agent orchestration / conversation memory

## Success Metrics
1. **Adoption**: Meridian and LeeClaw both depend on `lee-llm-router` by end of Sprint N.
2. **Reliability**: 0 regressions in existing LLM flows (Meridian test suite passes, LeeClaw research runner unchanged) after migration.
3. **DX**: `lee-llm-router doctor` detects misconfigurations and missing binaries in <5 seconds.
4. **Testing**: 90%+ coverage for provider adapters and config loader; built-in mock provider used in CI for both repos.

## Phasing
| Phase | Deliverables |
|-------|--------------|
| **P0 – Extraction** | Rehost `LLMConfig`, provider registry, `LLMClient`, response dataclasses, trace helpers. Publish as editable install for Meridian/LeeClaw dev environments. |
| **P1 – Tooling** | Add doctor CLI, config template generator, docs (`README`, `docs/config.md`, `docs/providers.md`). |
| **P2 – Enhancements** | Fallback chains, token accounting hook, async HTTP clients, packaged telemetry exporters. |

## Constraints & Requirements
- Python 3.10+ (align with existing repos)
- Dependencies kept minimal: `pyyaml`, `requests`/`httpx`, maybe `rich` for CLI output.
- Must remain pure-Python; no compiled extensions.
- Backwards-compatible config file with Meridian/LeeClaw (only additive changes allowed).
- Provide MIT license for easy reuse.

## Stakeholders
- **Lee Harrington** – product owner, consumer via Meridian/LeeClaw.
- **Meridian team** – relies on router for production agents.
- **LeeClaw team** – research workflows & budgets.
- **Future Tiny projects** – expect simple API & doc-first onboarding.

## Acceptance Checklist (Phase 1)
- [x] `product-definition.md` + `design.md` checked in (this doc + companion design).
- [x] `lee_llm_router` package exposes `LLMRouter`,`LLMClient`,`load_config`,`LLMRequest/Response`.
- [x] Provider registry includes at least: OpenRouter HTTP, Codex CLI, dummy.
- [x] Doctor CLI verifies config, environment variables, CLI binaries.
- [x] Sample `config/llm.example.yaml` template.
- [x] PyPI-ready packaging instructions (`python -m build` → `.whl` + `.tar.gz`).
- [x] README documents API + CLI usage.
- [x] Unit tests for config loader, router, providers, doctor path.
