# Provider Adapter Reference

Providers implement the `Provider` protocol from `lee_llm_router.providers.base`.
All built-in providers are auto-registered on import.

## Provider Protocol

```python
class Provider(Protocol):
    name: str
    supported_types: set[str]

    def validate_config(self, config: dict[str, Any]) -> None: ...
    def complete(self, request: LLMRequest, config: dict[str, Any]) -> LLMResponse: ...
```

---

## MockProvider

**Registry name:** `mock`

Deterministic echo provider. Returns a fixed string with no I/O. Safe for all
tests and CI pipelines.

```yaml
providers:
  mock:
    type: mock
    response_text: "optional fixed response"  # default: "mock response for role=<role>"
```

```python
from lee_llm_router.providers.mock import MockProvider

mock = MockProvider()
response = mock.complete(request, {"response_text": "hello"})
```

Controllable error flags (for testing error paths):

| Config key | Raises |
|-----------|--------|
| `raise_timeout: true` | `LLMRouterError(FailureType.TIMEOUT)` |
| `raise_contract_violation: true` | `LLMRouterError(FailureType.CONTRACT_VIOLATION)` |
| `raise_rate_limit: true` | `LLMRouterError(FailureType.RATE_LIMIT)` |

---

## OpenRouterHTTPProvider
## OpenCodeSubscriptionHTTPProvider

**Registry name:** `opencode_subscription_http`

Calls the OpenCode Go subscription API (OpenAI-compatible `/chat/completions`).
Uses the same adapter as `openrouter_http` with `OPENCODE_API_KEY` as the
default credential environment variable.

```yaml
providers:
  opencode:
    type: opencode_subscription_http
    base_url: https://opencode.ai/zen/go/v1
    api_key_env: OPENCODE_API_KEY
```

This provider supports all models available through an OpenCode Go subscription,
including `deepseek-v4-flash` and `deepseek-v4-pro`.

Error mapping is identical to OpenRouterHTTPProvider.

---
**Registry names:** `openrouter_http`, `openai_http`

Calls any OpenRouter or OpenAI-compatible `/chat/completions` endpoint using
`httpx`. Supports JSON mode and custom headers.

```yaml
providers:
  openrouter:
    type: openrouter_http
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
```

Error mapping:

| HTTP / exception | FailureType |
|-----------------|------------|
| `httpx.TimeoutException` | `TIMEOUT` |
| HTTP 429 | `RATE_LIMIT` |
| HTTP 4xx / 5xx | `PROVIDER_ERROR` |
| Missing `choices[0]` | `INVALID_RESPONSE` |
| `httpx.RequestError` | `PROVIDER_ERROR` |

---

## OpenAICodexSubscriptionHTTPProvider

**Registry names:** `openai_codex_subscription_http`, `openai_codex_http`, `chatgpt_subscription_http`

Calls ChatGPT backend Codex Responses API (`/codex/responses`) using subscription
credentials from Codex login.

```yaml
providers:
  codex_sub:
    type: openai_codex_subscription_http
    base_url: https://chatgpt.com/backend-api/codex
    # Optional override for CI:
    # access_token_env: OPENAI_CODEX_ACCESS_TOKEN
```

Credential resolution order:
1. `access_token_env` (if configured)
2. macOS keychain entry `Codex Auth`
3. `CODEX_HOME/auth.json` (or `~/.codex/auth.json`)

Error mapping:

| HTTP / exception | FailureType |
|-----------------|------------|
| `httpx.TimeoutException` | `TIMEOUT` |
| HTTP 429 | `RATE_LIMIT` |
| HTTP 4xx / 5xx | `PROVIDER_ERROR` |
| Missing output text in responses payload | `INVALID_RESPONSE` |
| Missing subscription credentials | `PROVIDER_ERROR` |

---


## OmpCLIProvider

**Registry name:** `omp_cli`

Invokes the omp (oh-my-pi) harness via subprocess with `-p` (print) mode.
The prompt is sent on stdin; the response is read from stdout.  The harness
handles authentication internally through its stored credentials, so no API
key configuration is needed.

```yaml
providers:
  omp:
    type: omp_cli
    command: omp
```

The provider passes `--model <model>` from the role config.  A system
message, if present, is prepended to the user prompt.

```yaml
roles:
  coach:
    provider: omp
    model: opencode-go/deepseek-v4-flash
```

Error mapping is identical to CodexCLIProvider.

---

**Registry name:** `codex_cli`

Invokes a CLI binary via subprocess and returns its stdout. Used for local
model wrappers (Codex, Ollama scripts, etc.).

```yaml
providers:
  codex_local:
    type: codex_cli
    command: codex
    model_flag: --model
    output_flag: --output-last-message
```

The last `user` message is passed as the final positional argument to the command.
Built command: `<command> [args...] [model_flag model] [output_flag] [prompt_flag] <prompt>`

For pi-style harness wrappers, add fixed args and require a JSON envelope:

```yaml
providers:
  pi_harness:
    type: codex_cli
    command: python3
    args:
      - ./scripts/pi_harness.py
    model_flag: null
    output_flag: null
    response_format: json
    text_field: output_text
```

When `response_format: json` is enabled, stdout must be a JSON object containing a
non-empty `output_text` or `text` field. Optional `model` and `usage` fields are
passed through into `LLMResponse`.

Set `model_flag: null` and `output_flag: null` for wrappers that do not accept the
default Codex CLI flags.

## GeminiCLIProvider

**Registry names:** `gemini_cli`, `gemini`

Invokes the Gemini CLI via subprocess and returns stdout. Defaults are tuned for the
installed `gemini` binary.

```yaml
providers:
  gemini_local:
    type: gemini_cli
    command: gemini
    model_flag: null
    output_flag: null
    prompt_flag: -p
```

Defaults:
- `command`: `gemini`
- `model_flag`: `null` (disabled)
- `output_flag`: `null` (disabled)
- `prompt_flag`: `-p`

## ClaudeCodeCLIProvider

**Registry names:** `claude_code_cli`, `claude_code`, `claude`

Invokes the Claude CLI via subprocess and returns stdout.

```yaml
providers:
  claude_code_local:
    type: claude
    command: claude
    model_flag: null
    output_flag: null
    prompt_flag: -p
```

Defaults:
- `command`: `claude`
- `model_flag`: `null` (disabled)
- `output_flag`: `null` (disabled)
- `prompt_flag`: `-p`

Error mapping:

| Condition | FailureType |
|-----------|------------|
| `subprocess.TimeoutExpired` | `TIMEOUT` |
| `FileNotFoundError` (binary missing) | `PROVIDER_ERROR` |
| Non-zero exit code | `PROVIDER_ERROR` |
| Empty stdout | `INVALID_RESPONSE` |
| Malformed / missing required JSON fields | `CONTRACT_VIOLATION` |

Debugging tips:
- Run `lee-llm-router doctor --config <path>` to catch missing binaries and invalid
  `codex_cli` config before execution.
- For harness wrappers, prefer structured JSON output over free-form text so schema
  breaks are surfaced deterministically.
- Include wrapper-specific fixed args under `args:` instead of shell-quoting them into
  `command:`.

---

## Registering a Custom Provider

```python
from lee_llm_router.providers.registry import register
from lee_llm_router.providers.base import LLMRouterError, FailureType
from lee_llm_router.response import LLMRequest, LLMResponse, LLMUsage

class MyProvider:
    name = "my_provider"
    supported_types = {"my_provider"}

    def validate_config(self, config):
        if "endpoint" not in config:
            raise LLMRouterError("Missing 'endpoint'", FailureType.PROVIDER_ERROR)

    def complete(self, request: LLMRequest, config: dict) -> LLMResponse:
        # ... call your backend ...
        return LLMResponse(text="...", provider="my_provider", request_id=request.request_id)

register("my_provider", MyProvider)
```

Then use `type: my_provider` in your config YAML.

---

## Failure Types

All provider errors are raised as `LLMRouterError` with a `failure_type`:

| FailureType | Meaning | Retryable |
|-------------|---------|-----------|
| `TIMEOUT` | Request timed out | Yes |
| `RATE_LIMIT` | Provider rate-limited | Yes (with backoff) |
| `PROVIDER_ERROR` | Server error or config issue | Yes |
| `INVALID_RESPONSE` | Unexpected response structure | Yes |
| `CONTRACT_VIOLATION` | JSON schema / parse failure | **Never** |
| `CANCELLED` | Request cancelled | No |
| `UNKNOWN` | Unclassified exception | Yes |

Use `should_retry(error)` from `lee_llm_router.providers.base` to check:

```python
from lee_llm_router.providers.base import should_retry

try:
    response = router.complete(role, messages)
except LLMRouterError as exc:
    if should_retry(exc):
        # safe to retry
        ...
```
