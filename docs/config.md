# Config Schema Reference

Lee LLM Router loads config from a YAML file via `load_config(path)`.

## Top-level structure

```yaml
llm:
  default_role: <string>       # required — must reference a role below
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
| `openai_codex_http` | `OpenAICodexSubscriptionHTTPProvider` | Alias — same adapter |
| `chatgpt_subscription_http` | `OpenAICodexSubscriptionHTTPProvider` | Alias — same adapter |
| `opencode_subscription_http` | `OpenRouterHTTPProvider` | OpenCode Go subscription (OpenAI-compatible) |
| `omp_cli` | `OmpCLIProvider` | omp harness subprocess (auth handled internally) |
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

### openai_codex_subscription_http keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `base_url` | no | `https://chatgpt.com/backend-api/codex` | Codex responses base URL |
| `access_token_env` | no | — | Env var containing ChatGPT/Codex access token |
| `account_id_env` | no | — | Optional env var for `ChatGPT-Account-Id` header |
| `account_id` | no | — | Optional fixed `ChatGPT-Account-Id` header |
| `headers` | no | `{}` | Extra HTTP headers |
| `timeout` | no | role timeout | Request timeout in seconds |

Credential resolution order:
1. `access_token_env` (if configured)
2. macOS keychain (`Codex Auth`)
3. `CODEX_HOME/auth.json` or `~/.codex/auth.json`

### codex_cli keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `command` | no | `codex` | Binary name or path (e.g. `codex`) |
| `args` | no | `[]` | Fixed positional args inserted before the prompt |
| `model_flag` | no | `--model` | Flag used to pass the model name; set to `null` to disable |
| `output_flag` | no | `--output-last-message` | Flag for output format; set to `null` to disable |
| `response_format` | no | `text` | Parse stdout as plain text or JSON (`text`, `json`) |
| `text_field` | no | `output_text` / `text` | JSON field containing the returned message text |
| `timeout` | no | role timeout | Subprocess timeout in seconds |

For pi-style harness wrappers, prefer `response_format: json` so malformed output is
treated as a `CONTRACT_VIOLATION` instead of a generic runtime mystery.

Set `model_flag: null` and `output_flag: null` for wrappers that do not accept the
default Codex CLI flags.

### gemini_cli / gemini keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `command` | no | `gemini` | Binary name or path (e.g. `gemini`) |
| `args` | no | `[]` | Fixed positional args inserted before prompt flags |
| `prompt_flag` | no | `-p` | Flag used to pass the prompt (`gemini -p "..."`) |
| `model_flag` | no | `null` | Model flag (left off by default) |
| `output_flag` | no | `null` | Output-format flag (left off by default) |
| `response_format` | no | `text` | Parse stdout as plain text or JSON (`text`, `json`) |
| `text_field` | no | `output_text` / `text` | JSON field containing the returned message text |
| `timeout` | no | role timeout | Subprocess timeout in seconds |

### claude_code_cli / claude_code / claude keys

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `command` | no | `claude` | Binary name or path (e.g. `claude`) |
| `args` | no | `[]` | Fixed positional args inserted before prompt flags |
| `prompt_flag` | no | `-p` | Flag used to pass the prompt (`claude -p "..."`) |
| `model_flag` | no | `null` | Model flag (left off by default) |
| `output_flag` | no | `null` | Output-format flag (left off by default) |
| `response_format` | no | `text` | Parse stdout as plain text or JSON (`text`, `json`) |
| `text_field` | no | `output_text` / `text` | JSON field containing the returned message text |
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

    gemini_local:
      type: gemini_cli
      command: gemini

    claude_code_local:
      type: claude
      command: claude

    pi_harness:
      type: codex_cli
      command: python3
      args:
        - ./scripts/pi_harness.py
      model_flag: null
      output_flag: null
      response_format: json
      text_field: output_text

    codex_subscription:
      type: openai_codex_subscription_http
      base_url: https://chatgpt.com/backend-api/codex

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

    gemini_research:
      provider: gemini_local
      model: gemini-2.5-pro

    claude_research:
      provider: claude_code_local
      model: claude-3.7-sonnet

    pi_local:
      provider: pi_harness
      model: o3

    codex_sub:
      provider: codex_subscription
      model: gpt-5.3-codex

    test:
      provider: mock
```
