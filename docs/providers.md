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

Built command: `omp -p [--model <model>]`

`build_command(config, model=None, effort=None)` returns exactly that argv list;
`complete()` runs the same builder, so the dispatch template and the executed
command cannot drift. Because the prompt is delivered on stdin, the list carries
no prompt placeholder. `effort` is accepted for interface parity only — the omp
harness has no reasoning-effort flag, so `LLMRequest.effort` is ignored here.

```yaml
roles:
  coach:
    provider: omp
    model: opencode-go/deepseek-v4-flash
```

Error mapping is identical to CodexCLIProvider.

---

## OpenCodeCLIProvider

**Registry name:** `opencode_cli` (alias: `opencode`)

Invokes the OpenCode CLI via subprocess. The prompt is passed as the final
positional argument; the response is read from stdout. The CLI handles
authentication internally through its stored credentials, so no API key
configuration is needed.

```yaml
providers:
  opencode:
    type: opencode_cli
    command: opencode          # optional, defaults to "opencode"
    model: opencode-go/deepseek-v4-flash   # required, provider/model form
    agent: build               # optional
    timeout: 120               # optional, seconds
```

Built command: `opencode run -m <provider/model> [--agent <agent>] <prompt>`

`build_command(config, model=None, effort=None)` returns that argv list with the
literal `{prompt}` placeholder as the final positional, and `complete()` runs the
same builder. `effort` is accepted for interface parity only — OpenCode has no
effort flag, so `LLMRequest.effort` is ignored here. A `model` override must
still be in `provider/model` form. A system message, if present, is prepended to
the user prompt.

Error mapping:

| Condition | FailureType |
| --- | --- |
| Missing/invalid `command`, `model`, `agent`, or `timeout` | `PROVIDER_ERROR` |
| Binary not found | `PROVIDER_ERROR` |
| Non-zero exit | `PROVIDER_ERROR` |
| Subprocess timeout | `TIMEOUT` |
| Empty stdout | `INVALID_RESPONSE` |

---

## AntigravityCLIProvider

**Registry name:** `antigravity_cli` (aliases: `antigravity`, `agy`)

Invokes the Antigravity CLI (`agy`) in print mode. The prompt is passed as the
argument to `-p`; the response is read from stdout. Per D155, Google subscription
models are reachable only through this harness, so `--dangerously-skip-permissions`
is always included for non-interactive dispatch.

```yaml
providers:
  agy:
    type: antigravity_cli
    command: agy               # optional, defaults to "agy"
    model: gemini-3.7-flash    # required
    effort: high               # optional: low | medium | high
    print_timeout: 90m         # optional, wait timeout for print mode (e.g. "90m")
    timeout: 300               # optional, seconds
```

Built command:
`agy --dangerously-skip-permissions --model <model> [--effort <low|medium|high>] [--print-timeout <dur>] -p <prompt>`

`build_command(config, model=None, effort=None)` returns that argv list with the
literal `{prompt}` placeholder as the final positional element (matching
`PROMPT_PLACEHOLDER = "{prompt}"`), and `complete()` runs the same builder,
substituting the placeholder with the prompt text and closing stdin
(`subprocess.DEVNULL`). `LLMRequest.effort` (set from a crew worker's effort by
`CrewRoutingPolicy`) overrides the config's `effort`. Reasoning effort accepts
only `low`, `medium`, or `high` (`agy` has no `max` level). A system message, if
present, is prepended to the user prompt.

Error mapping:

| Condition | FailureType |
| --- | --- |
| Missing/invalid `command`, `model`, `effort`, `timeout`, or `print_timeout` | `PROVIDER_ERROR` |
| Binary not found | `PROVIDER_ERROR` |
| Non-zero exit | `PROVIDER_ERROR` |
| Subprocess timeout | `TIMEOUT` |
| Empty stdout | `INVALID_RESPONSE` |

---

**Registry name:** `codex_cli`

Invokes a CLI binary via subprocess and returns its stdout. Used for local
model wrappers (Codex, Ollama scripts, etc.). Non-interactive runs default
to the `exec` subcommand.

```yaml
providers:
  codex_local:
    type: codex_cli
    command: codex
    subcommand: exec             # optional, defaults to "exec" (null to disable)
    model_flag: --model          # optional, defaults to "--model"
    output_flag: null            # optional, defaults to null (e.g. "--output-last-message")
    output_path: null            # optional file path when output_flag is used
```

The last `user` message is passed as the final positional argument to the command.
Built command: `<command> [args...] [subcommand] [model_flag model] [output_flag [output_path]] [prompt_flag] <prompt>`
Default invocation: `codex exec --model <model> -c model_reasoning_effort=<effort> <prompt>`

For pi-style harness wrappers, add fixed args and require a JSON envelope:

```yaml
providers:
  pi_harness:
    type: codex_cli
    command: python3
    subcommand: null
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

Set `subcommand: null`, `model_flag: null`, and `output_flag: null` for wrappers that do not accept the
default Codex CLI flags.

When `output_flag` and `output_path` are both configured (for example,
`output_flag: "--output-last-message"` and `output_path: "/path/to/last_msg.txt"`),
both are placed in argv before `{prompt}`, and `complete()` reads the response from that file
after the run if it exists, falling back to stdout.

### `build_command` and effort

`build_command(config, model=None, effort=None)` returns the argv list with the
literal `{prompt}` placeholder as the final positional, and `complete()` runs the
same builder — the dispatch template and the executed command cannot drift.

```python
CodexCLIProvider().build_command({"command": "codex"}, model="gpt-5.6-sol")
# ["codex", "exec", "--model", "gpt-5.6-sol", "{prompt}"]

CodexCLIProvider().build_command({"command": "codex", "model": "m"}, effort="high")
# ["codex", "exec", "--model", "m", "-c", "model_reasoning_effort=high", "{prompt}"]

CodexCLIProvider().build_command(
    {"command": "codex", "model": "m", "subcommand": None}, effort="high"
)
# ["codex", "--model", "m", "-c", "model_reasoning_effort=high", "{prompt}"]
```

`effort` falls back to the config's `effort` key when not passed explicitly, and
`complete()` supplies `LLMRequest.effort`. Each subclass renders it with its own
flag, via the `_effort_args()` hook:

| Class | Effort argv |
| --- | --- |
| `CodexCLIProvider` | `-c model_reasoning_effort=<effort>` |
| `ClaudeCodeCLIProvider` | `--effort <effort>` |
| `GeminiCLIProvider` | none — the Gemini CLI has no effort flag |

When effort is `None` (or empty) no flag is emitted at all.

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
- `model_flag`: `--model`
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
