# Config Schema Reference

Lee LLM Router loads config from a YAML file via `load_config(path)`.

## Top-level structure

```yaml
llm:
  default_role: <string>       # required — used when role not specified
  providers:
    <name>: <ProviderConfig>   # one or more provider entries
  roles:
    <name>: <RoleConfig>       # one or more role entries
```

---

## ProviderConfig

Every provider entry requires `type`. All other keys are provider-specific and are
passed verbatim to the provider adapter's `complete()` call.

```yaml
providers:
  my_provider:
    type: openrouter_http   # required — maps to registry name
    base_url: ...           # provider-specific
    api_key_env: MY_KEY     # provider-specific
```

### `type` values

| Value | Adapter | Description |
|-------|---------|-------------|
| `openrouter_http` | `OpenRouterHTTPProvider` | OpenRouter / OpenAI-compatible REST |
| `openai_http` | `OpenRouterHTTPProvider` | Alias — same adapter |
| `codex_cli` | `CodexCLIProvider` | Subprocess provider |
| `mock` | `MockProvider` | Deterministic echo — tests only |

### openrouter_http / openai_http keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `base_url` | yes | — | API base URL |
| `api_key_env` | yes | — | **Name** of env var holding the API key |
| `headers` | no | `{}` | Extra HTTP headers |
| `timeout` | no | role timeout | Request timeout in seconds |

> `api_key_env` stores the variable *name*, not the secret. The value is read from
> `os.environ` at call time so secrets never appear in config files or logs.

### codex_cli keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `command` | yes | — | Binary name or path (e.g. `codex`) |
| `model_flag` | no | `--model` | Flag used to pass the model name |
| `output_flag` | no | `--output-last-message` | Flag for output format |
| `timeout` | no | role timeout | Subprocess timeout in seconds |

### mock keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `response_text` | no | `"mock response for role=<role>"` | Fixed text returned |
| `raise_timeout` | no | `false` | If true, raise TIMEOUT error |
| `raise_contract_violation` | no | `false` | If true, raise CONTRACT_VIOLATION |
| `raise_rate_limit` | no | `false` | If true, raise RATE_LIMIT |

---

## RoleConfig

```yaml
roles:
  my_role:
    provider: my_provider     # required — key in providers dict
    model: openai/gpt-4o      # optional
    temperature: 0.2          # optional, default: 0.2
    json_mode: false          # optional, default: false
    max_tokens: null          # optional, default: null (no limit)
    timeout: 60.0             # optional, default: 60.0 seconds
    fallback_providers: []    # optional, default: [] (Phase 2)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | string | required | Provider name (key in `providers`) |
| `model` | string | `""` | Model identifier passed to provider |
| `temperature` | float | `0.2` | Sampling temperature |
| `json_mode` | bool | `false` | Request JSON-formatted output |
| `max_tokens` | int \| null | `null` | Max completion tokens |
| `timeout` | float | `60.0` | Request timeout in seconds |
| `fallback_providers` | list[str] | `[]` | Ordered fallback chain (Phase 2) |

---

## Per-call overrides

Any `RoleConfig` field can be overridden at call time:

```python
router.complete(
    role="planner",
    messages=[...],
    model="openai/gpt-4o-mini",   # override
    temperature=0.0,               # override
    timeout=30.0,                  # override
)
```

---

## Full example

```yaml
llm:
  default_role: planner

  providers:
    openrouter:
      type: openrouter_http
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY

    codex_local:
      type: codex_cli
      command: codex
      model_flag: --model
      output_flag: --output-last-message

    mock:
      type: mock

  roles:
    planner:
      provider: openrouter
      model: openai/gpt-4o
      temperature: 0.2
      fallback_providers: [codex_local]

    extractor:
      provider: openrouter
      model: openai/gpt-4o-mini
      temperature: 0.0
      json_mode: true
      max_tokens: 2048

    local:
      provider: codex_local
      model: o3

    test:
      provider: mock
```
