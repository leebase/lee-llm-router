# Configuration and command reference

Lee LLM Router is a deterministic staffing service. Its current selection and
execution interfaces are the `staff` and `run` commands. The former
`LLMRouter`, `LLMClient`, `resolve`, and `dispatch` interfaces are not part of
the current product.

There are three separate configuration inputs:

1. the committed staffing catalog under `config/staffing/`, used by `staff`,
   `run`, and `catalog explain`;
2. availability and evidence snapshots/ledgers, used to make staffing
decisions fail closed; and
3. the legacy-shaped `llm:` YAML read only by `doctor --config` and emitted by
   `template`. It remains so those diagnostics and templates continue to work;
   it is not a high-level routing API.

## Doctor/template provider config

Generate the diagnostic template with:

```bash
lee-llm-router template > config/llm.yaml
lee-llm-router doctor --config config/llm.yaml
lee-llm-router doctor --config config/llm.yaml --role planner
```

The schema is:

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
      json_mode: false
      max_tokens: null
      timeout: 60.0
      fallback_providers: []
```

`default_role` must name a role. Every role's `provider` must name an entry in
`providers`. Provider entries require `type`; their remaining keys are passed
to that adapter's configuration validator.

Common provider types are:

| Type | Adapter |
|---|---|
| `openrouter_http`, `openai_http` | OpenAI-compatible HTTP |
| `openai_codex_subscription_http`, `openai_codex_http`, `chatgpt_subscription_http` | Codex subscription HTTP |
| `codex_cli` | Codex-compatible subprocess |
| `gemini_cli`, `gemini` | Gemini subprocess |
| `claude_code_cli`, `claude_code`, `claude` | Claude Code subprocess |
| `omp_cli` | OMP subprocess |
| `opencode_cli`, `opencode` | OpenCode subprocess |
| `antigravity_cli`, `antigravity`, `agy` | Antigravity subprocess |
| `mock` | deterministic test adapter |

See [providers.md](providers.md) for adapter-level fields and behavior.

### Provider fields checked by doctor

HTTP adapters use `base_url`, credential environment-variable names such as
`api_key_env` or `access_token_env`, optional `headers`, and `timeout`. Secret
values are read from the environment and should not be stored in YAML.

CLI adapters commonly use `command`, fixed `args`, model/output/prompt flags,
`response_format`, `text_field`, and `timeout`. `doctor --config` validates the
adapter config and checks configured binaries or credentials where applicable.
For a wrapper that does not accept the normal Codex flags, disable them
explicitly:

```yaml
llm:
  default_role: worker
  providers:
    pi_harness:
      type: codex_cli
      command: python3
      subcommand: null
      args: [./scripts/pi_harness.py]
      model_flag: null
      output_flag: null
      response_format: json
      text_field: output_text
  roles:
    worker:
      provider: pi_harness
      model: governed-by-wrapper
```

There is deliberately no package-level `load_config` export. The exact current
runtime consumer is `lee_llm_router.doctor.check_config`; `tests/test_config.py`
is the retained direct test consumer.

## Staffing catalog

The authoritative repository-local catalog is `config/staffing/`:

- `routes.yaml` defines route identities and dispatch templates;
- `channels.yaml` defines funding-channel kinds;
- `classes.yaml` defines valid class dimensions and route capability policy;
- `policy.yaml` defines policy constants and automatic boundaries;
- `terms.yaml` defines dated subscription/metered terms; and
- `crews.yaml` defines saved crew blocks.

Use a scratch catalog with `--catalog-dir PATH`; otherwise commands use the
repository's committed directory. Catalog details are documented in
[staffing/catalog.md](staffing/catalog.md).

A canonical work class has five segments:

```text
role/oracle_type/domain_tags/size_band/language
```

For example, `impl/deterministic/none/s/python`. A class key joins comparable
evidence and gates eligibility; it never maps directly to a model or route.

## Availability

`staff`, `run`, and `catalog explain` read `--availability-file PATH`, then the
normal per-host default when the option is absent. `doctor --availability`
shows the selected snapshot's age and channel health:

```bash
lee-llm-router doctor --availability
lee-llm-router doctor --availability --availability-file /path/to/snapshot.json
```

A snapshot is stale when its effective observation timestamp is more than 90
minutes old or beyond the five-minute future-skew tolerance. Missing snapshots
and stale snapshots normalize channel health to `unknown`; doctor reports a
warning and exits 0. A present unusable snapshot is an error.

**P2-9 availability rule:** an automatic route that depends on subscription
channel availability is ineligible when that channel is `unknown`, including
when the snapshot is missing or stale. Metered/local channels are not falsely
vetoed merely because no quota record exists. Saved named crews are different:
`staff --mode crew NAME` renders the exact recorded block and authority. It does
not invent, replace, reorder, or silently feed those routes into automatic
selection.

See [availability.md](availability.md) and
[availability-refresh.md](availability-refresh.md) for the snapshot schema and
refresh procedure.

## `staff`: compute a block, never dispatch

Automatic staffing:

```bash
lee-llm-router staff --mode auto \
  --role impl --class impl/deterministic/none/s/python
```

`--mode auto` is the default. It evaluates catalog policy, availability, dated
terms, evidence joins, proof status, expected cost, escalation, and reviewer
independence. It never chooses an unproven route while a proven eligible route
exists. Never-automatic routes remain outside the automatic boundary.

Useful options are:

```text
--author-route ROUTE_ID
--supervisor-route ROUTE_ID
--at YYYY-MM-DD
--availability-file PATH
--catalog-dir PATH
--json
```

Named crew staffing requires only the exact saved id:

```bash
lee-llm-router staff --mode crew luna-sol
lee-llm-router staff --mode crew sol-low-glm-pi --json
```

A named crew is resolve-only: it prints the saved supervisor, role routes,
reviewer, escalation ladder, evidence reference, and authority. It is not
availability-filtered and is never silently converted to `auto`.

An explicit human bind is also resolve-only, but appends one authorization
event after all validation succeeds:

```bash
lee-llm-router staff --mode bind ROUTE_ID \
  --role impl --class impl/deterministic/none/s/python \
  --authorized-by lee --reason "approved exception"
```

`--role`, `--class`, `--authorized-by`, and `--reason` are required for bind.
A never-automatic route can be bound only with `--authorized-by lee`. `staff`
never launches a provider in any mode. Success exits 0; a service/configuration
refusal exits 3 and prints `staff: ...` on stderr.

Text mode always emits a compact staffing block; `--json` emits the same facts
as structured data. An auto block includes its selected route when one is
available, which can be passed explicitly to `run`.

## `run`: select, execute once, and record

```bash
lee-llm-router run \
  --role impl \
  --class impl/deterministic/none/s/python \
  --packet packet.md
```

`--role`, `--class`, and `--packet` are always required. The packet must be a
non-empty UTF-8 file and is sent verbatim. Without `--route`, `run` chooses the
first eligible route in `catalog explain` marginal-price order. To execute the
route selected in an evidence-aware `staff auto` block, pass it explicitly:

```bash
lee-llm-router run \
  --route pi-z-ai-glm-5-3-flash-openrouter \
  --role impl \
  --class impl/deterministic/none/s/python \
  --packet packet.md
```

An explicit route still must pass the same current role/class, availability,
terms, and independence eligibility path; refusal exits 3 and launches
nothing. Other options include:

```text
--supervisor-route ROUTE_ID
--author-route ROUTE_ID
--oracle CMD
--workdir DIR
--parent ATTEMPT_ID --escalation-reason REASON
--timeout SECONDS
--at YYYY-MM-DD
--availability-file PATH
--catalog-dir PATH
--json
```

The provider command is constructed as argv, never through a shell. The worker
runs exactly once under the stall watchdog and wall-clock ceiling. An optional
oracle runs once afterward with the remaining timeout budget. `run` does not
retry or escalate. It validates and appends exactly one attempt-record v2 row
for a completed worker, including a truthful oracle setup failure if one occurs
after the worker. Normal completion returns the worker exit code; a ceiling
timeout returns 124; pre-launch and setup refusals return 3.

See [staffing/attempt-record.md](staffing/attempt-record.md) for the ledger
contract.

## Crews diagnostics and page

The separate Auto-Orch crew-roster diagnostics remain available:

```bash
lee-llm-router crews list [--crews-file PATH] [--json]
lee-llm-router doctor --crews [--crews-file PATH]
lee-llm-router crews page --out PATH \
  [--crews-file PATH] [--availability-file PATH] \
  [--benchmark-file PATH] [--events-file PATH]
```

The roster loader is read-only. Its path order is an explicit argument,
`LEE_LLM_ROUTER_CREWS_FILE`, then
`~/projects/auto-orch/config/crews.yaml`. `doctor --crews` validates every
worker and governed harness. The page is a read-only HTML projection; missing
optional availability/benchmark evidence degrades to unknown, while present
malformed inputs fail closed.

These roster commands do not restore the removed crew-stage selection API.
Staffing selection uses the committed staffing catalog and `staff`.

## Harness shims

Managed shims are generated from
`src/lee_llm_router/templates/shims/crew.md.tmpl` for Claude Code, Codex, OMP,
and OpenCode. Their user interface is exactly:

- `/crew auto` — derive an already-planned canonical role/class, run
  `lee-llm-router staff --mode auto --role <role> --class <class>`, and show
  the block;
- `/crew NAME` — run `lee-llm-router staff --mode crew <name>` and show the
  exact saved block.

If the task does not establish enough class facts, the shim asks instead of
guessing. It never invokes a provider, dispatches work, or edits project files.
After displaying the block, it only **offers** a command for the user to run:

```bash
lee-llm-router run --role <role> --class <class> --packet <path>
```

When the block names a selected route, it offers the explicit form:

```bash
lee-llm-router run --route <route-id> --role <role> --class <class> --packet <path>
```

Install or inspect managed targets with:

```bash
lee-llm-router shims install --dry-run [--harness TAG] [--project PATH]
lee-llm-router shims install --apply [--force] [--harness TAG] [--project PATH]
lee-llm-router shims diff [--harness TAG] [--project PATH]
```

Each generated file has a SHA-256 marker. Apply refuses unmanaged or modified
files unless `--force` is explicit; `diff` exits 1 for drift or a missing target.
