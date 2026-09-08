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
to it. Channel headroom for the workers a crew names is read separately — see
[Availability snapshots](availability.md).

Path resolution order:

1. explicit `load_crews(path=...)` / `resolve_crews_path(explicit)` argument
2. the `LEE_LLM_ROUTER_CREWS_FILE` environment variable
3. the default `~/projects/auto-orch/config/crews.yaml`

```bash
export LEE_LLM_ROUTER_CREWS_FILE=/path/to/crews.yaml
```

### Parse cache

To keep cold-start CLI resolution under 50 ms wall clock, `load_crews()` caches
parsed crews configuration in `${XDG_CACHE_HOME:-~/.cache}/lee-llm-router/`.
The cache is keyed by the resolved file path, file size, and nanosecond modification
timestamp (`mtime_ns`). On a cache hit, YAML parsing is skipped entirely. Writes to
the cache are atomic via a temporary file and replace.

To bypass or disable the cache (e.g. during debugging or benchmarking raw parse time):

```bash
export LEE_LLM_ROUTER_NO_CACHE=1
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
must never enter an *automatic* fallback chain, and `ROLE_SCOPED_MODELS`
(`gemini-3.1-pro`, decisions.md D188) is restricted by role class: forbidden
in coding roles, eligible in planning and review roles. Helpers
`is_never_automatic()`, `is_role_scoped()`, and `role_class()` expose them.
Strict routing returns exactly the worker the crew names, refusing only on
spent channel headroom or a role-scoped model in a coding role.

### Funding channels

A *channel* is the subscription or metered account that pays for a worker's
tokens. It is coarser than a provider: several providers can draw on one
channel, and one harness draws on two. Every `ResolvedWorker` carries a
`channel`, which is what the availability reader looks up headroom against.

`CHANNELS` declares the six known channels; `PROVIDER_CHANNELS` maps each
registered provider to its default:

| Router provider | Funding channel |
|---|---|
| `codex_cli` | `openai-sub` |
| `claude_code_cli` | `anthropic-sub` |
| `antigravity_cli` | `gemini-sub` |
| `opencode_cli` | `opencode-go` |
| `omp_cli` | `openrouter` |

The sixth channel, `gemini-sub-thirdparty`, has no provider default: it covers
the Claude and GPT models Antigravity brokers, which bill to a separate bucket
from Google's own models on the same subscription. A worker like that is pinned
with `WORKER_CHANNEL_OVERRIDES` (`worker_id -> channel`, empty by default),
which wins over the provider default. This mapping lives in `crews.py`, not in
`crews.yaml`: funding is the router's concern, not Auto-Orch's.

A provider with no channel — no override and no `PROVIDER_CHANNELS` entry —
raises `CrewsConfigError` from `resolve_worker()`, so a new harness cannot be
added without deciding who pays for it.

```python
from lee_llm_router.crews import channel_for, load_crews, resolve_worker

resolve_worker(load_crews().workers["codex_sol_high"]).channel  # "openai-sub"
channel_for("codex_sol_high", "codex_cli")                      # "openai-sub"
```

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
OK crews: 14 crews, 23/23 workers resolved, 0 role-scoped warning(s)
```

`--config` is optional when `--crews` is given. Any unresolvable worker or
unknown governed harness is printed as an error (`  x  `, on stderr) and exits 1.

A crew stage whose role class is `coding` and names a worker that resolves to a
role-scoped model in `ROLE_SCOPED_MODELS` (or an unmapped stage name) is reported
as a **warning** (`  !  `, on stdout) citing `decisions.md D188` and does not
change the exit code. The crews file belongs to Auto-Orch, not to this router:
`gemini-pro-crew` names `antigravity_gemini31_pro` only in planning and review
stages (`envision` and `reconsider`), so on the live file `doctor --crews` reports
0 warnings. Warnings are counted in the summary line (`N role-scoped warning(s)`).
`NEVER_AUTOMATIC_MODELS` members are informational only and produce no output.

### `doctor --availability`

Report on the availability snapshot the hourly refresh writes:

```bash
lee-llm-router doctor --availability
lee-llm-router doctor --availability --availability-file /path/to/snapshot.json
lee-llm-router doctor --crews --availability
```

The snapshot path is the `--availability-file` argument, else
`LEE_LLM_ROUTER_AVAILABILITY_FILE`, else
`~/.local/state/lee-llm-router/availability/<host>.json`. A healthy check prints:

```
OK availability: /home/lee/.local/state/lee-llm-router/availability/A8Max.json, age 12 min, 9 buckets
  openai-sub: degraded
  anthropic-sub: degraded
  gemini-sub: healthy
  gemini-sub-thirdparty: healthy
  openrouter: unknown
  opencode-go: unknown
```

The summary line is followed by one line per funding channel, in the order of
`availability.CHANNELS`, carrying the health the resolver would see. A channel
with no bucket in the snapshot reads `unknown`.

The check is a thin renderer over `availability.load_availability()`, so the
staleness and clock-skew rules are the reader's, not the doctor's — see
[docs/availability.md](availability.md). Age is the **older** of the snapshot's
two timestamps: `observed_at` (when the provider data was observed) and
`written_at` (when the snapshot was written). Either one being more than 90
minutes old, or more than 5 minutes in the future, makes the snapshot stale and
every channel `unknown` — a fresh `written_at` cannot rescue a stale
`observed_at`. A snapshot that is missing or stale is a **warning**
(`  !  `, exit 0) — absence is a valid state before the refresh cron has ever
run, and the reader degrades such a snapshot to `unknown` rather than to
"healthy." A future-stamped snapshot is never reported as fresh. Only a file
that exists but cannot be used at all — not valid JSON, no `subscriptions`
list, an unparseable or wholly absent timestamp — is an **error** (exit 1).

`--config` is optional when `--availability` is given, and the flag composes
with `--crews`. See [docs/availability-refresh.md](availability-refresh.md) for
the refresh script and its cron line.

## Resolving a worker

`lee-llm-router resolve` answers "which worker runs this crew's stage right
now, and why" — it loads the crews file and the availability snapshot, calls
`lee_llm_router.resolver.resolve()`, prints the answer, and records one line to
the event ledger. It never invokes a provider binary.

```bash
lee-llm-router resolve openai-economy author
lee-llm-router resolve openai-economy author --mode flex
lee-llm-router resolve openai-economy author --mode flex --json
lee-llm-router resolve --crew openai-economy --role author
lee-llm-router resolve openai-economy author \
  --mode bind --worker codex_terra_high \
  --authorized-by lee --reason "quota exhausted, escalate for the demo"
```

`--mode` is `strict` (default), `flex`, or `bind` — see
[resolver.py](../src/lee_llm_router/resolver.py)'s module docstring for the
semantics of each. `--harness` (default `cli`) is recorded on the event line;
Sprint 4's shims pass `claude-code`, `codex`, `omp`, or `opencode`.
`--crews-file` and `--availability-file` mirror the `doctor` flags and the same
default-resolution order. `--events-file` mirrors `--crews-file` for the event
ledger (default: `events.resolve_events_path()`, which honours
`LEE_LLM_ROUTER_EVENTS_FILE`). A missing or unreadable availability snapshot is
not fatal — every channel reads `unknown` and each mode's unknown-headroom rule
applies.

Text output, one field per line, in this order:

```
worker: codex_terra_high
provider: codex_cli
model: gpt-5.6-terra
effort: high
channel: openai-sub
headroom: degraded (48% remaining)
route_id: codex_cli:gpt-5.6-terra:high
dispatch: /home/lee/.local/bin/codex --model gpt-5.6-terra -c model_reasoning_effort=high --output-last-message '{prompt}'
reason: flex mode: codex_terra_high chosen on degraded headroom (channel openai-sub degraded (HOT, 48% remaining)); no candidate had healthy headroom
event: /home/lee/.local/state/lee-llm-router/events/A8Max.jsonl
```

`effort` reads `default` when the worker declares none. `headroom` is the
channel's health, plus `(N% remaining)` when the snapshot knows a fraction.
`dispatch` is the provider's argv, `shlex.join`-ed, with a trailing
` [prompt on stdin]` when the harness takes its prompt on stdin rather than in
argv. In `--mode bind`, an `authorized_by` line follows `reason`. The last line
is always `event: <path>` after a successful write, or
`event: not recorded (--no-event)` when `--no-event` was passed.

`--json` prints exactly `resolver.Resolution.to_dict()` (which already carries
`pace_ratio`, for Sprint 6's recalibration) with one field added: a top-level
`event_path` — the ledger path written to, or `null` when nothing was
recorded.

Exit codes are exactly `ResolutionError.exit_code`: `0` on success, `2` when
nothing in the candidate set is eligible (e.g. every candidate's channel is
exhausted), `3` for a config, usage, or forbidden-model refusal — including an
unknown crew or stage, an unmapped role, a bind missing
`--worker`/`--authorized-by`/`--reason`, or a worker resolving to a role-scoped
model in `ROLE_SCOPED_MODELS` for a coding role (cites `decisions.md D188`).
On refusal, stdout stays empty and stderr gets `resolve: <message>`, plus a second
line `remedy: <remedy>` when the resolver suggests one; with `--json`, stderr is
unchanged and stdout gets
`{"error": ..., "exit_code": ..., "kind": ..., "remedy": ...}` instead of the
resolution. A refusal never writes an event.

Every **successful** resolution appends exactly one event via
`events.build_event()` / `events.append_event()` — refusals do not. Pass
`--no-event` to suppress the write for a dry run or a shim self-test. If the
write itself fails (an unwritable path, an oversized encoded line), the
resolution is still printed, but the exit code becomes `3` and stderr explains
why: a resolution that never reached the ledger is not a completed one.

### Resolver rules

| Rule / Condition | Strict mode | Flex mode | Bind mode |
|---|---|---|---|
| Channel health `exhausted` or `likely_exhausted` | Refused (exit 2) | Skipped; falls back to next tier or exit 2 if all exhausted | Allowed (headroom reported, not a veto) |
| Channel health `healthy`, `degraded`, or `unknown` | Dispatched | Dispatched in tier order (`healthy` > `degraded` > `unknown`) | Dispatched |
| Never-automatic model (`NEVER_AUTOMATIC_MODELS`) | Dispatched if named | Skipped if any automatic candidate available; eligible if only candidate | Dispatched (authorized escalation) |
| Role-scoped model in coding role (`ROLE_SCOPED_MODELS`, D188) | Refused (exit 3, kind `forbidden`, cites D188) | Skipped; reason names skipped worker and cites D188; exit 3 if all skipped | Refused (exit 3, kind `forbidden`, cites D188) |
| Role-scoped model in planning/review role (`ROLE_SCOPED_MODELS`, D188) | Dispatched (ordinary worker) | Dispatched (ordinary worker) | Dispatched (ordinary worker) |
| Unmapped role (`ROLE_CLASS_BY_ROLE`, D188) | Refused (exit 3, kind `config`, cites D188) | Refused (exit 3, kind `config`, cites D188) | Refused (exit 3, kind `config`, cites D188) |

### Dispatching

`lee-llm-router dispatch` resolves the worker and executes the harness command
under supervision of the stall watchdog (`StallWatchdog`).

```bash
lee-llm-router dispatch --crew openai-economy --role author --prompt "Draft the release notes"
lee-llm-router dispatch --crew openai-economy --role author --mode flex \
  --prompt-file prompt.txt --watch-dir ./src
lee-llm-router dispatch --crew openai-economy --role author --mode flex \
  --prompt "Draft tests" --stall-minutes 5 --max-minutes 30
lee-llm-router dispatch --crew openai-economy --role author --mode flex \
  --prompt "Preview command" --no-event --dry-run
```

- **Resolution**: Resolution is identical to `resolve` (same exit codes 2/3, same
  refusal lines and remedies) and takes place before any child process starts.
  `--dry-run` prints what `resolve` would print (including the command with prompt
  delivery marker) and exits 0 without running anything.
- **Event ledger**: Exactly one event line is written to the ledger before the
  child starts (honouring `--no-event`). Refusals and usage errors never write an event.
- **Prompt delivery**: Exactly one prompt source must be supplied:
  `--prompt "<text>"`, `--prompt-file PATH`, or standard input when neither is given
  (standard input must not be a TTY, else exit 3). An empty prompt exits 3.
  - When `prompt_delivery` is `"argv"`, `{prompt}` in the command template is
    replaced with the prompt text.
  - When `prompt_delivery` is `"stdin"`, the prompt bytes are written to the
    child's stdin pipe and closed.
- **Streaming & Watchdog Supervision**: Child stdout/stderr are streamed to the
  parent as bytes arrive. `watchdog.run_supervised` checks activity across ticks
  by tracking cumulative output bytes and file modifications in any `--watch-dir`
  paths.
  - **Stall**: If no output and no file changes occur for `--stall-minutes` (default
    `10`), a warning is printed to stderr:
    `dispatch: no output and no file activity for N min (worker <id>, elapsed M min); still waiting, ceiling <max> min`
    The child process continues running.
  - **Ceiling**: If elapsed time reaches `--max-minutes` (default `120`), the child
    is killed, stderr receives `dispatch: killed after <max> min ceiling`, and
    dispatch exits with code `124`.
  - **Normal completion**: Otherwise, dispatch exits with the child's exit code.
- **Exit-code precedence**: Resolution refusal (2/3) > usage error (3) > killed (124) > child exit code.

## Harness shims

Command shims connect external harnesses (Claude Code, Codex, OMP, OpenCode) to
`lee-llm-router`. Shims are generated from a single template source
(`src/lee_llm_router/templates/shims/crew.md.tmpl`) and never hand-written.

### Targets

| Harness tag | Target path | Form / Frontmatter |
|---|---|---|
| `claude-code` | `~/.claude/commands/crew.md` | Claude Code slash command; frontmatter `description`, `argument-hint: <crew> <role>`, `allowed-tools: Bash(lee-llm-router:*)` |
| `codex` | `~/.codex/prompts/crew.md` | Codex custom prompt; frontmatter `description`, `argument-hint: <crew> <role>` |
| `omp` | `<project>/.omp/prompts/crew.md` | OMP prompt template; frontmatter `description`, `argument-hint: <crew> <role>` (default project: cwd; `--project PATH` overrides) |
| `opencode` | `~/.config/opencode/command/crew.md` | OpenCode command file; frontmatter `description`, default agent preserved |

Target home is `Path.home()` by default, or overridden via `LEE_LLM_ROUTER_SHIM_HOME`
(used by tests and sandboxed runs). Directories are created only by `--apply`.

### How shims work

Every shim's rendered body runs the positional resolve command:

```bash
lee-llm-router resolve $ARGUMENTS --mode flex --harness <tag> --json
```

It parses the JSON output, prints `worker`, `model`, `effort`, `headroom`, and
`reason`, and offers the exact `lee-llm-router dispatch ...` command for the user
to run:

```bash
lee-llm-router dispatch --crew <crew> --role <role> --mode flex --harness <tag> --prompt-file <path>
```

A shim never dispatches on its own, never invokes a provider binary, and never
edits files.

### Marker and drift detection

Each generated shim contains an integrity marker line:

```html
<!-- lee-llm-router shim v1 sha256=<hex> -->
```

The SHA256 hex digest covers the markdown body below the marker line.

- **`install --dry-run`**: prints the absolute path, the proposed action
  (`create`, `update`, `unchanged`, or `refuse: not generated by lee-llm-router`),
  and the full content for each target without touching the filesystem (exit 0).
- **`install --apply`**: writes each target and creates parent directories as
  needed. Refuses to overwrite any file whose marker or hash does not match what
  `lee-llm-router` generated unless `--force` is given (exit 0 on success, exit 1
  if any target was refused, exit 3 on usage error).
- **`diff`**: prints a unified diff for each installed target that differs from the
  current render, reports `missing: <path>` for uninstalled targets, and prints
  nothing for identical files. Exits 0 if no drift and none missing; exits 1 if
  any drift or missing.
- **`--harness <tag>`**: repeatable flag limiting `install` or `diff` to the
  specified targets.


