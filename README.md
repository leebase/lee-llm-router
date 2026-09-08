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

### Crews

```bash
lee-llm-router crews list
lee-llm-router crews list --crews-file /path/to/crews.yaml --json
lee-llm-router doctor --crews
lee-llm-router doctor --availability
```

`crews list` prints each crew's stage workers with the router provider, model,
and effort each resolves to, plus its governed routes. `doctor --crews` resolves
every worker referenced by every crew (and checks governed harness names),
printing `OK crews: N crews, M workers resolved` or exiting 1 with the failures.
`doctor --availability` reports the availability snapshot's path, age, and
bucket count; a missing or stale snapshot is a warning, not a failure.
`--config` is optional when either flag is given. See
[docs/config.md](docs/config.md#crews) and
[docs/availability-refresh.md](docs/availability-refresh.md).

### Resolve

```bash
lee-llm-router resolve --crew openai-economy --role author
lee-llm-router resolve --crew openai-economy --role author --mode flex --json
lee-llm-router resolve --crew openai-economy --role author --mode bind \
  --worker codex_terra_high --authorized-by lee --reason "quota exhausted"
lee-llm-router dispatch --crew openai-economy --role author --mode flex --prompt "Review plan"
```

Answers "which worker runs this crew's stage right now, and why": resolves via
`strict` (default), `flex`, or `bind` mode, prints the worker, provider, model,
route id, dispatch command, and reason, and appends one line to the event
ledger for every successful resolution (`--no-event` suppresses that write).
Exit `0` on success, `2` when nothing is eligible, `3` for a config, usage, or
forbidden-model refusal. Never invokes a provider binary. `dispatch` resolves
the worker, runs the harness, and supervises execution under the stall watchdog. See
[docs/config.md#resolving-a-worker](docs/config.md#resolving-a-worker) and
[docs/config.md#dispatching](docs/config.md#dispatching).

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
| `gemini_cli` | Subprocess wrapper for Gemini CLI |
| `claude_code_cli` | Subprocess wrapper for Claude Code CLI |
| `mock` | Deterministic echo provider for tests and CI |

See [docs/providers.md](docs/providers.md) for configuration details.

For pi-style subprocess harnesses, configure `codex_cli`, `gemini_cli`, or
`claude_code_cli` with fixed `args`, disable default flags when needed, and use
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
