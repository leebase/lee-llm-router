# Lee LLM Router - Product Definition

## Vision

Build a reusable, battle-tested LLM routing kernel that distills the lessons from Meridian's production pipeline and LeeClaw's research agents into one upstream codebase. Projects should be able to adopt it either as a package or as an explicit vendored snapshot while still benefiting from a shared improvement lane.

## Current State Snapshot

- `lee-llm-router` is a working Python package with config loading, provider adapters, telemetry, doctor CLI, async/fallback support, and green tests.
- LeeClaw exposed the main adoption risk: a live external runtime dependency creates avoidable install, auth, and reproducibility friction.
- The current direction is to keep this repo as the upstream improvement lane while making vendored snapshot adoption a first-class downstream path.

## Guiding Principles

1. Start with what already works.
2. No rewrite when extraction or additive improvement is enough.
3. Keep provenance explicit.
4. Validate with docs, tests, and CLI behavior.
5. Shared evolution does not require shared runtime packaging.

## Mission

Provide a lightweight router package and reference source tree that:
1. Loads a declarative YAML config describing roles, providers, fallbacks, and guardrails.
2. Routes completion requests to the right backend with per-role overrides.
3. Emits a consistent telemetry and evidence trail for every request.
4. Ships tooling (`doctor`, `template`, `trace`, `export-source`) so adopters can validate and consume it quickly.

## Users and Use Cases

| User | Needs | Example |
|------|-------|---------|
| Meridian agents | deterministic routing, JSON contract, trace files | `LLMClient.complete(role="planner", messages=[...])` |
| LeeClaw research loops | long-running analysis with fallback and telemetry | `LLMRouter(...).complete()` |
| Future projects | choose package install or vendored snapshot adoption | `lee-llm-router export-source --dest ...` |

## Out-of-the-Box Capabilities

1. Config schema with environment interpolation and templates.
2. Provider registry for HTTP APIs, CLI bridges, and mock providers.
3. High-level router and legacy-compatible client.
4. Structured telemetry and per-request trace files.
5. Doctor CLI for validation and dry-run checks.
6. Trace inspection CLI for recent request summaries.
7. Vendored source export with provenance manifest.

## Non-Goals

- Hosting an LLM proxy or server.
- Owning project-specific prompt templates.
- Owning full agent orchestration or conversation memory.

## Success Metrics

1. Meridian and LeeClaw can both consume the same router capabilities through either a pinned package release or a vendored snapshot.
2. Existing LLM flows migrate without regressions.
3. `lee-llm-router doctor` catches bad config quickly.
4. Vendored exports are reproducible and attributable to a source commit.
5. Test coverage remains strong around providers, routing, and CLI workflows.

## Phasing

| Phase | Deliverables |
|-------|--------------|
| P0 - Extraction | Rehost config, provider registry, router/client, response dataclasses, trace helpers. |
| P1 - Tooling | Doctor CLI, config template generator, docs, PyPI-ready packaging. |
| P2 - Enhancements | Async HTTP, fallback chains, token hooks, richer telemetry. |
| P3 - Self-Contained Adoption | Vendored source export, provenance manifest, downstream adoption workflow. |

## Constraints and Requirements

- Python 3.10+
- Minimal dependencies
- Pure Python only
- Additive compatibility for existing consumers
- MIT license

## Stakeholders

- Lee Harrington - product owner and downstream consumer
- Meridian team - production routing consumer
- LeeClaw team - research workflow consumer
- Future tiny projects - expect simple adoption and validation paths
