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

## Crews

`lee_llm_router.crews` reads Auto-Orch's crew roster (workers plus per-stage and
governed routes). The file is read-only to this package; the loader never writes
to it.

Path resolution order:

1. explicit `load_crews(path=...)` / `resolve_crews_path(explicit)` argument
2. the `LEE_LLM_ROUTER_CREWS_FILE` environment variable
3. the default `~/projects/auto-orch/config/crews.yaml`

```bash
export LEE_LLM_ROUTER_CREWS_FILE=/path/to/crews.yaml
```

Each crew declares the five stages `envision`, `ideate`, `reconsider`, `score`,
and `author`. A stage value may be a single worker id (the form Auto-Orch uses
today) or an **ordered list** of worker ids, which gives a later flex mode an
ordered eligible set. The first entry is always the primary worker:

```yaml
crews:
  mixed-flex:
    stages:
      envision: [codex_luna_max, antigravity_gemini38_flash_high]
      ideate: claude_opus5_high
      reconsider: codex_luna_max
      score: codex_luna_max
      author: codex_sol_high
    governed:
      primary: {harness: claude_code, model: claude-opus-5}
      reviewer: {harness: codex_cli, model: gpt-5.6-sol, effort: low}
      judge: {harness: claude_code}
```

```python
from lee_llm_router.crews import load_crews

config = load_crews()
crew = config.crew("mixed-flex")
crew.eligible("envision")  # ("codex_luna_max", "antigravity_gemini38_flash_high")
crew.primary("envision")   # "codex_luna_max"
```

Validation failures raise `CrewsConfigError` (a `ValueError`): a missing file,
a missing `workers`/`crews` section, an unknown stage name, a stage referencing
an unknown worker id, an empty stage list, or a stage value that is neither a
string nor a list of strings.

### Worker → provider mapping

A crews-file worker is a shell command, not a router provider. `resolve_worker()`
maps one onto a registered provider by reading the `<PREFIX>_STAGE_WORKER_*`
environment variables the command sets before invoking the stage-worker script:

| Command prefix | Router provider |
|---|---|
| `CODEX_STAGE_WORKER_*` | `codex_cli` |
| `CLAUDE_STAGE_WORKER_*` | `claude_code_cli` |
| `OPENCODE_STAGE_WORKER_*` | `opencode_cli` |
| `ANTIGRAVITY_STAGE_WORKER_*` | `antigravity_cli` |

`_MODEL` supplies the model, `_EFFORT` (or `_REASONING_EFFORT`) the effort hint,
and `_BINARY` the harness binary. The worker's raw command template is preserved
verbatim as `dispatch_command`. An unknown prefix, a missing model, or a provider
that is not registered raises `CrewsConfigError`.

`WORKER_PROVIDER_OVERRIDES` (`worker_id -> (provider, model, effort)`, empty by
default) pins an unusual worker without editing the Auto-Orch-owned crews file;
an entry there wins over parsing.

```python
from lee_llm_router.crews import load_crews, resolve_worker

config = load_crews()
resolved = resolve_worker(config.workers["codex_sol_high"])
resolved.provider  # "codex_cli"
resolved.model     # "gpt-5.6-sol"
resolved.effort    # "high"
```

Two declarative constants record the cost guardrails from the crew-aware
resolver plan. `NEVER_AUTOMATIC_MODELS` (Fable 5.1, Fable 5, Luna Max, Opus 5)
must never enter an *automatic* fallback chain, and `FORBIDDEN_MODELS`
(`gemini-3.1-pro`) must never be chosen at all. Helpers `is_never_automatic()`
and `is_forbidden()` expose them. Strict routing does not enforce either: it
returns exactly the worker the crew names.

### `CrewRoutingPolicy` (strict)

```python
from lee_llm_router.policy import CrewRoutingPolicy

policy = CrewRoutingPolicy("mixed-balanced")
choice = policy.choose("author", config)   # role == the stage name
choice.provider_name       # the config provider key of type codex_cli
choice.request_overrides   # {"model": "gpt-5.6-sol", "effort": "high"}
choice.allow_fallback      # False — strict routing never substitutes
```

`policy.mode` is fixed to `"strict"`: the crew's primary worker for the stage is
resolved, and the config provider whose `type` (or registry alias) matches is
selected. An unknown crew or stage, or a config with no provider of the required
type, raises `LLMRouterError(failure_type=PROVIDER_ERROR)` naming the crew,
stage, worker, and required provider type.

#### `allow_fallback`

`ProviderChoice.allow_fallback` (default `True`) decides whether the router may
extend the chosen provider with the role's `fallback_providers` chain:

- `SimpleRoutingPolicy` returns `allow_fallback=True`, preserving the historical
  behaviour — the chosen provider first, then every role fallback in order.
- `CrewRoutingPolicy` returns `allow_fallback=False`. The crew's named worker is
  attempted once; if it fails, the typed `LLMRouterError` propagates and no
  fallback provider is called. This is what "strict" means: the named worker or
  a typed failure, never a silent substitution.

The rule applies identically to `complete()` and `complete_async()`.

#### `effort` threading

`CrewRoutingPolicy` puts the worker's reasoning effort in
`choice.request_overrides["effort"]`. The router copies it onto
`LLMRequest.effort` (per-call `router.complete(..., effort="low")` wins over the
policy's value), and the CLI providers turn it into a flag:

| Provider | Effort flag |
| --- | --- |
| `codex_cli` | `-c model_reasoning_effort=<effort>` |
| `claude_code_cli` | `--effort <effort>` |
| `antigravity_cli` | `--effort <low\|medium\|high>` |
| `gemini_cli` | none — accepted and ignored |
| `omp_cli` | none — accepted and ignored |
| `opencode_cli` | none — accepted and ignored |

When `effort` is `None` the flag is omitted entirely.

### CLI

List the crews, their resolved stage workers, and their governed routes:

```bash
lee-llm-router crews list
lee-llm-router crews list --crews-file /path/to/crews.yaml --json
```

```text
mixed-flagship — Hardest missions.
  envision: codex_sol_high (codex_cli gpt-5.6-sol/high)
  ideate: claude_fable51_high (claude_code_cli claude-fable-5-1/high)
  reconsider: codex_sol_medium (codex_cli gpt-5.6-sol/medium)
  score: codex_luna_max (codex_cli gpt-5.6-luna/max)
  author: codex_sol_high (codex_cli gpt-5.6-sol/high)
  governed: primary=claude_code/claude-opus-5, reviewer=codex_cli/gpt-5.6-sol, judge=codex_cli
```

Validate the whole crews file. Every worker in the top-level `workers` map
must resolve — not only the ones a crew stage references, so a malformed worker
is caught even while unused — every stage reference must name a known worker,
and every governed harness must be one of `codex_cli`, `claude_code`,
`claude_code_cli`, `omp_cli`, `opencode_cli`, `antigravity_cli`:

```bash
lee-llm-router doctor --crews
lee-llm-router doctor --config config/llm.yaml --crews --crews-file /path/to/crews.yaml
```

```text
  !  Worker 'antigravity_gemini31_pro' resolves to forbidden model \
'gemini-3.1-pro'; the resolver must never choose it
OK crews: 14 crews, 23/23 workers resolved, 1 forbidden-model warning(s)
```

`--config` is optional when `--crews` is given. Any unresolvable worker or
unknown governed harness is printed as an error (`  x  `, on stderr) and exits 1.

A worker whose resolved model is in `FORBIDDEN_MODELS` is reported as a
**warning** (`  !  `, on stdout) and does not change the exit code. The crews
file belongs to Auto-Orch, not to this router: the live file declares
`antigravity_gemini31_pro` and a `gemini-pro-crew` that uses it, so a hard error
there would only make `doctor --crews` unusable against real state. Warnings are
counted in the summary line. `NEVER_AUTOMATIC_MODELS` members are informational
only and produce no output.
