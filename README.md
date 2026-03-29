# Lee LLM Router

A lightweight LLM routing kernel extracted from LeeClaw and Meridian. It supports config-driven routing, provider adapters, telemetry, doctor tooling, and explicit source export for downstream vendoring.

## Installation

```bash
pip install lee-llm-router
# or, for development:
pip install -e ".[dev]"
```

## Vendored Snapshot Workflow

Use this when a downstream repo should own a pinned router snapshot instead of taking a live runtime dependency on this package.

```bash
lee-llm-router export-source --dest ../consumer/src/lee_llm_router
lee-llm-router export-source --dest ../consumer/src/lee_llm_router --force
```

The export copies the full `src/lee_llm_router/` package tree and writes `.lee_llm_router_export.json` with:
- package version
- source repo path
- source git commit
- export timestamp

The destination may be missing or already exist as an empty directory. Use
`--force` only when replacing a non-empty destination.

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
      api_key_env: OPENROUTER_API_KEY
  roles:
    planner:
      provider: openrouter
      model: openai/gpt-4o
      temperature: 0.2
```

See [docs/config.md](docs/config.md) for the full schema.

## CLI

### Doctor

```bash
lee-llm-router doctor --config config/llm.yaml
lee-llm-router doctor --config config/llm.yaml --role planner
```

Validates config, checks env vars, verifies CLI binaries, and validates the
selected role/provider wiring. For `codex_cli` roles, Doctor now also checks the
configured harness contract keys so bad pi-harness wiring fails fast.

### Template

```bash
lee-llm-router template > config/llm.yaml
```

### Trace

```bash
lee-llm-router trace --last 5
```

### Export Source

```bash
lee-llm-router export-source --dest ../consumer/src/lee_llm_router
```

## Providers

| Type | Description |
|------|-------------|
| `openrouter_http` | OpenRouter / OpenAI-compatible REST API |
| `openai_codex_subscription_http` | ChatGPT subscription-backed Codex Responses API |
| `codex_cli` | Subprocess wrapper for Codex CLI |
| `mock` | Deterministic echo provider for tests and CI |

See [docs/providers.md](docs/providers.md) for configuration details.

For pi-style subprocess harnesses, configure `codex_cli` with fixed `args`,
disable the default CLI flags when the wrapper does not accept them, and use
`response_format: json` so malformed harness output is raised as a typed
`CONTRACT_VIOLATION`.

## Telemetry

Every completion emits structured log events and writes a JSON trace file.

- Events: `llm.complete.start`, `llm.complete.success`, `llm.complete.error`, `policy.choice`
- Trace files: `<workspace>/.agentleeops/traces/YYYYMMDD/<request_id>-<attempt>-<provider>.json`

## Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

pytest
black src tests
ruff check src tests

lee-llm-router doctor --config tests/fixtures/llm_test.yaml
python -m build
```

## Architecture

```text
lee_llm_router/
|-- config.py
|-- router.py
|-- client.py
|-- response.py
|-- policy.py
|-- telemetry.py
|-- compression.py
|-- doctor.py
`-- providers/
    |-- base.py
    |-- registry.py
    |-- mock.py
    |-- http.py
    |-- openai_codex_subscription.py
    `-- codex_cli.py
```

## License

MIT
