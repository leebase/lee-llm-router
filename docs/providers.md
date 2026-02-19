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

**Registry names:** `openrouter_http`, `openai_http`

Calls any OpenRouter or OpenAI-compatible `/chat/completions` endpoint using
`requests`. Supports JSON mode and custom headers.

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
| `requests.Timeout` | `TIMEOUT` |
| HTTP 429 | `RATE_LIMIT` |
| HTTP 4xx / 5xx | `PROVIDER_ERROR` |
| Missing `choices[0]` | `INVALID_RESPONSE` |
| `requests.RequestException` | `PROVIDER_ERROR` |

---

## CodexCLIProvider

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
Built command: `<command> [model_flag model] [output_flag] <prompt>`

Error mapping:

| Condition | FailureType |
|-----------|------------|
| `subprocess.TimeoutExpired` | `TIMEOUT` |
| `FileNotFoundError` (binary missing) | `PROVIDER_ERROR` |
| Non-zero exit code | `PROVIDER_ERROR` |
| Empty stdout | `INVALID_RESPONSE` |

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
