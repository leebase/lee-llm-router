# Lee LLM Router

A deterministic staffing service with governed route catalogs, evidence-aware
selection, recorded execution, provider adapters, and doctor tooling.

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

```bash
lee-llm-router staff --role impl \
  --class impl/deterministic/none/s/python --mode auto
lee-llm-router staff --mode crew luna-sol
lee-llm-router run --role impl --class impl/deterministic/none/s/python \
  --packet packet.md
```

`staff` computes a block without launching a provider. `run` dispatches one
eligible route and records its attempt. The old `LLMRouter`, `resolve`, and
`dispatch` selection layers were removed in Phase 2.

## Diagnostic Provider Config

The retained `llm:` config is consumed by `doctor --config` and emitted by
`template`; it is not a replacement high-level routing API. Generate a
commented template:

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

### Staff and Run

```bash
lee-llm-router staff --role impl --class impl/deterministic/none/s/python
lee-llm-router staff --mode crew sol-low-glm-pi
lee-llm-router run --role impl --class impl/deterministic/none/s/python \
  --packet packet.md
```

Automatic staffing applies catalog, availability, dated terms, evidence,
expected-cost, and independence rules. Missing or stale availability makes
subscription-channel-dependent automatic routes unknown/ineligible; it does
not falsely veto metered/local routes with no quota record. Named crews remain
exact saved blocks: they are not availability-filtered, reordered, or silently
fed into automatic selection.

`staff` never launches a provider. `run` always requires role, canonical class,
and a non-empty packet file. Without `--route`, `run` selects the cheapest
eligible explain row; pass the selected route from a `staff auto` block via
`--route ROUTE_ID` to execute that evidence-aware choice. The explicit route
must still be currently eligible. `run` launches once under watchdog
supervision and appends one attempt record; it never retries or escalates.

### Harness Shims

Managed shims expose exactly `/crew auto` and `/crew NAME`. The auto form derives
an already-planned canonical role/class and runs `staff --mode auto`; the named
form prints the exact `staff --mode crew NAME` block. If class facts are
missing, the shim asks rather than guessing. Both forms are resolve-only and
only offer—never execute—a `lee-llm-router run ... --packet <path>` command,
using `--route <route-id>` when the block selected one.

```bash
lee-llm-router shims install --dry-run
lee-llm-router shims install --apply
lee-llm-router shims diff
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
| `gemini_cli` | Subprocess wrapper for Gemini CLI |
| `claude_code_cli` | Subprocess wrapper for Claude Code CLI |
| `mock` | Deterministic echo provider for tests and CI |

See [docs/providers.md](docs/providers.md) for configuration details.

For pi-style subprocess harnesses, configure `codex_cli`, `gemini_cli`, or
`claude_code_cli` with fixed `args`, disable default flags when needed, and use
`response_format: json` so malformed harness output is raised as a typed
`CONTRACT_VIOLATION`.

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
|-- availability.py
|-- crews.py
|-- events.py
|-- config.py
|-- response.py
|-- doctor.py
|-- shims.py
|-- staffing/
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
