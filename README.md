# Lee LLM Router

A lightweight, battle-tested LLM routing kernel extracted from LeeClaw and Meridian. Drop in one YAML config, point at multiple providers, and inherit consistent routing, tracing, and governance.

## Installation

```bash
pip install lee-llm-router
# or, for development:
pip install -e ".[dev]"
```

## Quick Start

```python
from lee_llm_router import LLMRouter, load_config

config = load_config("config/llm.yaml")
router = LLMRouter(config)

response = router.complete(
    role="planner",
    messages=[{"role": "user", "content": "Summarise the project plan."}],
)
print(response.text)
```

Or use the legacy-compatible `LLMClient`:

```python
from lee_llm_router import LLMClient, load_config

client = LLMClient(load_config("config/llm.yaml"))
response = client.complete("planner", messages=[...])
```

## Config File

Generate a commented template:

```bash
lee-llm-router template > config/llm.yaml
```

Minimal example:

```yaml
llm:
  default_role: planner
  providers:
    openrouter:
      type: openrouter_http
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY   # env var name, not the secret
  roles:
    planner:
      provider: openrouter
      model: openai/gpt-4o
      temperature: 0.2
```

See [`docs/config.md`](docs/config.md) for the full schema.

## CLI

### Doctor

Validates your config, checks environment variables, verifies CLI binaries, and performs a mock dry-run:

```bash
lee-llm-router doctor --config config/llm.yaml
lee-llm-router doctor --config config/llm.yaml --role planner
```

Exit code 0 = healthy. Non-zero = blocking errors found.

### Template

```bash
lee-llm-router template > config/llm.yaml
```

## Providers

| Type | Description |
|------|-------------|
| `openrouter_http` | OpenRouter / OpenAI-compatible REST API |
| `codex_cli` | Subprocess wrapper for Codex CLI |
| `mock` | Deterministic echo provider for tests and CI |

See [`docs/providers.md`](docs/providers.md) for configuration details.

## Telemetry

Every completion emits structured log events and writes a JSON trace file:

- **Events**: `llm.complete.start`, `llm.complete.success`, `llm.complete.error`, `policy.choice`
- **Trace files**: `<workspace>/.agentleeops/traces/YYYYMMDD/<request_id>.json`

```python
# Control trace location
router = LLMRouter(config, workspace="/path/to/project")
router = LLMRouter(config, trace_dir=Path("/tmp/traces"))  # test override
```

## Custom Routing Policy (Phase 1)

```python
from lee_llm_router import LLMRouter, ProviderChoice
from lee_llm_router.policy import RoutingPolicy

class CheapFirstPolicy:
    def choose(self, role, config):
        # Route to cheap provider by default
        return ProviderChoice(provider_name="openrouter",
                              overrides={"model": "openai/gpt-4o-mini"})

router = LLMRouter(config, policy=CheapFirstPolicy())
```

## Custom Trace Store (Phase 1)

```python
from lee_llm_router import LLMRouter
from lee_llm_router.telemetry import TraceStore, TraceRecord

class MyS3Store:
    def write(self, trace: TraceRecord) -> None:
        s3.put_object(Key=trace.request_id, Body=json.dumps(...))

router = LLMRouter(config, trace_store=MyS3Store())
```

## Development

```bash
# Install with dev deps (creates .venv first if needed)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Format / lint
black src/
ruff check src/

# Validate your own config
lee-llm-router doctor --config config/llm.yaml

# Build distribution
python -m build
```

## Architecture

```
lee_llm_router/
├── config.py       — YAML loader + dataclasses (LLMConfig, RoleConfig, ProviderConfig)
├── router.py       — LLMRouter facade (resolve → policy → compress → invoke → trace)
├── client.py       — LLMClient legacy wrapper (same interface as LeeClaw)
├── response.py     — LLMRequest / LLMResponse / LLMUsage dataclasses
├── policy.py       — RoutingPolicy protocol + SimpleRoutingPolicy default
├── telemetry.py    — Structured logging + TraceStore + LocalFileTraceStore
├── compression.py  — Prompt compression hook (pass-through in Phase 0)
├── doctor.py       — CLI entry point
└── providers/
    ├── base.py     — Provider protocol + LLMRouterError + FailureType
    ├── registry.py — register() / get() / available()
    ├── mock.py     — Deterministic echo provider
    ├── http.py     — OpenRouter / OpenAI-compatible REST
    └── codex_cli.py — Subprocess provider
```

## License

MIT
