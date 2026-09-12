# Crew Resolver — Execution Log (append only)

Supervisor: Fable 5.1 (low). Worker: Opus 5 high (Claude Code subagent). Reviewer: Sol Low via Codex CLI (read-only).

## 2026-09-07 — Sprint 1 opened

Baseline observed before any packet (fresh `.venv`, `pip install -e ".[dev]"`):
- `PYTHONPATH=src .venv/bin/python -m pytest -q` → `89 passed in 0.65s`
- `black --check src` → 2 files would be reformatted (pre-existing)
- `ruff check src` → 3 fixable findings (pre-existing)
- Live crews file: `~/projects/auto-orch/config/crews.yaml`, 356 lines, 23 workers, 14 crews.
- Registry already has `claude_code_cli` (aliases `claude_code`, `claude`), `codex_cli`, `omp_cli`, `gemini_cli`. Missing for Sprint 1: `opencode_cli`, `antigravity_cli`.

Packets planned:
- P1 `crews.py` loader + typed objects + fixture + tests.
- P2 `opencode_cli` and `antigravity_cli` providers (validate_config + dispatch template, no calls) + registry + tests + docs.
- P3 worker→provider/model mapping, `CrewRoutingPolicy` (strict), `crews list`, `doctor --crews`, tests, docs, pre-existing lint cleanup.

### P1 — crews loader — Opus 5 high — ACCEPTED (supervisor-verified)
- Files touched: `src/lee_llm_router/crews.py`, `tests/fixtures/crews.yaml`, `tests/test_crews.py`, `docs/config.md` (+50). Within allowed set.
- Observed: `pytest -q tests/test_crews.py` → `19 passed`; `black --check` on both files → unchanged; `ruff check` → all passed.
- Read diff: frozen dataclasses, order preserved, list-valued stages, all error classes raise `CrewsConfigError`. Live-file test asserts 14 crews and ran (not skipped).
- Minor nit for a later packet: two implicit string concatenations in error messages (cosmetic).

### P2 — opencode_cli + antigravity_cli providers — Opus 5 high — ACCEPTED (supervisor-verified)
- Files touched: `providers/opencode_cli.py`, `providers/antigravity_cli.py`, `providers/registry.py`, `providers/omp_cli.py` (lint only), `tests/test_providers.py`, `docs/providers.md`. Within allowed set.
- Observed: full `pytest -q` → `143 passed`; `black --check src` → 20 files unchanged; `ruff check src` → 2 fixable remain, both pre-existing in `__init__.py`/`telemetry.py`/`router.py` (outside P2 scope; assigned to P3).
- Read diff: `build_command` is pure argv; agy uses stdin, opencode uses `{prompt}` positional; failure typing matches omp. No real binaries in tests.

### P3 — worker mapping, strict CrewRoutingPolicy, `crews list`, `doctor --crews` — Opus 5 high — ACCEPTED (supervisor-verified)
- Files touched: `crews.py`, `policy.py`, `doctor.py`, `__init__.py`/`router.py`/`telemetry.py` (lint only, verified diff is import-sort + docstring wrap), `tests/test_crews.py`, `tests/test_doctor.py`, `tests/test_policy.py`, `tests/fixtures/crews.yaml`, `docs/config.md`, `README.md`. Within allowed set.
- Observed: `pytest -q` → `169 passed`; `black --check src` → 20 unchanged; `ruff check src` → all passed.
- Live: `crews list` → 14 crew headers; `crews list --json` → 14 entries; `doctor --crews` → `OK crews: 14 crews, 17 workers resolved`, exit 0; existing `doctor --config tests/fixtures/llm_test.yaml` still passes.
- Note: 17 of 23 workers are referenced by crews; the 6 unreferenced (opencode_go_* and gemini37 aliases) are not exercised by `doctor --crews`. Unit tests cover all four prefixes.
- Pre-existing: `sprint-plan.md` was dirty before this sprint began (not touched by any packet).

## Review round 1 — Sol Low via `codex exec -s read-only`
- First attempt stalled (codex waited on stdin without a TTY); rerun with prompt on stdin, exit 0. Reviewer could not run pytest (read-only sandbox has no writable tmp) but ran both live CLI commands successfully.
- Findings: VERDICT FAIL.
  - H1 `router.py:167/254` strict policy choice still gets role fallback_providers appended → silent substitution; violates never-automatic rule. Supervisor confirmed by reading code.
  - H2 `router.py:77` `_build_request` discards `effort` override → workers not dispatched at declared effort. Supervisor confirmed.
  - H3 `crews.py` no OMP prefix in `WORKER_ENV_PREFIX_PROVIDERS` though `omp_cli` is a required target. Accepted (no OMP worker in live file today, but contract incomplete).
  - H4 `omp_cli`/`codex_cli` providers lack `build_command` dispatch template. Accepted for contract consistency.
  - M1 `doctor --crews` validates only stage-referenced workers (17/23). Accepted.
- Disposition: all five → repair packet P4.

### P4 — repair H1–H4, M1 — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `193 passed`; black/ruff clean; `doctor --crews` → `OK crews: 14 crews, 23/23 workers resolved, 1 forbidden-model warning(s)` (gemini-3.1-pro, exit 0); `crews list` → 14; `auto-orch/config/crews.yaml` git-clean.
- Read diff: router honors `ProviderChoice.allow_fallback` on sync+async; `LLMRequest.effort` threaded; strict policy sets `allow_fallback=False`.

## Review round 2 — Sol Low via `codex exec -s read-only`
- Two harness-level kills of the background reviewer ("low on memory" guard; 13 GB actually available). Ran detached via `setsid nohup`; completed exit 0.
- Findings: none (High/Medium/Low). Reviewer verified all five round-1 fixes in code and tests, ran both live CLI checks (14 crews; 23/23 workers, 1 forbidden-model warning). Reviewer's pytest was sandbox-limited (63 `tmp_path` errors from read-only tmp); supervisor's own run is authoritative: `193 passed`.
- **VERDICT: PASS. Sprint 1 closed 2026-09-07.** Nothing committed (commit is Lee's call; tree is clean of crews.yaml edits).

## 2026-09-07 — Sprint 2 opened (Lee: commit S1 `bea61bd`, proceed)

Inputs observed: `ai-subs.sh` live run emits `AFTER_REPORT_JSON` then one JSON line
`{observed_at, source, subscriptions:[{provider, bucket, status, used_pct, remaining_pct, pace_ratio, pace_ratio_infinite, resets_at, resets_in_hours} | {provider, status:"UNAVAILABLE"|"NO_DATA", error?}]}`.
Providers seen: `OpenAI/Codex`, `Anthropic/Claude`, `Gemini/agy` (Gemini has both "Gemini models" and "Claude/GPT models" buckets). No cron for ai-subs exists today. Host: A8Max. Saved a real sample to `tests/fixtures/availability/live-sample-2026-09-07.json` (supervisor, fixture seed only).

Snapshot contract (binding for P5/P6): `~/.local/state/lee-llm-router/availability/<host>.json` = the AFTER_REPORT object plus `host` and `written_at` (ISO, UTC) added by the refresh script. Reader tolerates their absence.

Packets: P5 `availability.py` reader/normalizer + tests. P6 channel map in `crews.py` + `scripts/refresh_availability.sh` + cron line doc + `doctor --availability`.

### P5 — `availability.py` reader/normalizer — Opus 5 high — ACCEPTED (supervisor-verified)
- Files: `availability.py`, `tests/test_availability.py`, 13 synthetic fixtures + `.gitignore` negation in `tests/fixtures/availability/` (root `.gitignore` `*.json` would otherwise hide them), `docs/availability.md`, `docs/config.md`. Within allowed set.
- Observed: `pytest tests/test_availability.py` → `40 passed`; black/ruff clean. Real load of the live sample: openai-sub degraded (HOT), anthropic-sub degraded (TOO FAST), gemini-sub degraded (5h bucket HOT at 97%), gemini-sub-thirdparty healthy, openrouter/opencode-go unknown; stale=False.
- Supervisor error corrected by worker: packet text predicted gemini-sub healthy; the sample's 5-hour bucket is HOT, so degraded is right under the stated rule.
- Calibration note for Sprint 3 (not a defect): HOT/TOO FAST are *pace* badges; degrading a channel on pace alone at 97% remaining may over-veto in flex mode. `Bucket.pace_ratio` is preserved, so Sprint 3 can separate headroom from pace if daily use shows it matters.

### P6 — channel map, refresh script, `doctor --availability` — Opus 5 high — ACCEPTED (supervisor-verified)
- Files within allowed set. Observed: full `pytest -q` → `263 passed`; black/ruff clean; `bash -n` OK; script's only external process is ai-subs.
- Real run: `scripts/refresh_availability.sh` exit 0 → wrote `~/.local/state/lee-llm-router/availability/A8Max.json` (9 buckets); `doctor --availability` → OK age 0 min; `load_availability()` accepts it (stale=False; openai-sub/anthropic-sub degraded, gemini-sub healthy, thirdparty healthy, openrouter/opencode-go unknown).
- Sprint 2 done condition observed satisfied. No cron installed (cron line documented in `docs/availability-refresh.md`).
- Sprint 3 note (worker-raised): `WORKER_CHANNEL_OVERRIDES` is empty; any agy worker running a brokered Claude/GPT model must be pinned to `gemini-sub-thirdparty` when the reader is wired to the resolver. No such worker exists in crews.yaml today.

## Sprint 2 review round 1 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL. Findings: H1 `availability.py` non-finite (`nan`/`inf`) remaining passes coercion → healthy (supervisor reproduced); H2 future timestamp → negative age, never stale (reproduced); M1 naive `now` interpreted via local tz; M2 refresh script accepts a JSON object lacking `subscriptions` and can overwrite a good snapshot; M3 no cleanup trap for `.tmp.<pid>` on failure. Reviewer pytest sandbox-limited again; supervisor run authoritative (263 passed).
- Disposition: all five → repair packet P7.

### P7 — repair S2 H1/H2/M1/M2/M3 — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `295 passed`; black/ruff clean; `bash -n` OK. Supervisor re-ran the two reproductions: `nan` → unknown; future timestamp → stale=True, unknown, reason "timestamp is in the future"; naive `now` treated as UTC. Real snapshot still accepted. `trap` present in script; no `.tmp.*` in state dir.
- Worker judgment accepted: negative fraction reaching `bucket_health()` directly returns `exhausted` (fail-closed), while parsed `-5%` is rejected upstream to `unknown`.

## Sprint 2 review round 2 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL (2 Medium, both `doctor.py check_availability`): future timestamp reports OK; naive `now` raises TypeError. Root cause is supervisor's P6 instruction to implement doctor's check with plain `json` (reader did not exist yet) → duplicated, weaker staleness logic. Disposition: P8 replaces the duplicate with `availability.load_availability`.

### P8 — doctor uses the availability reader — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `298 passed`; black/ruff clean on src; supervisor reproduced: future +10 min → warning (no OK); naive `now` → no exception. Real `doctor --availability` OK with six channel lines.

## Sprint 2 review round 3 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL. H1 `availability.py`: fresh `written_at` overrides old/future `observed_at` → stale observations can read healthy. Root cause: supervisor's P5 contract said "prefer written_at"; correct rule is the *older* of the two governs staleness. M1 script accepts unparseable `observed_at`. M2 `context.md`/`result-review.md` not yet updated (supervisor's close-out duty; will be done before round 4). Disposition: P9 for H1+M1.

### P9 — oldest timestamp governs staleness; script validates `observed_at` — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: availability+refresh tests green; black/ruff clean; `bash -n` OK. Supervisor reproduction: 3-hour-old `observed_at` with 1-minute-old `written_at` → stale, unknown, reason names observed_at.
- Worker flagged two out-of-scope follow-ups (hardcoded absolute `observed_at` in `tests/test_doctor.py` helper that would begin failing within the hour; one stale sentence in `docs/config.md`) → P10.
- Supervisor updated `context.md` and `result-review.md` (round-3 M2).

### P10 — test time bomb + doc line — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `309 passed`; no absolute timestamps remain in `tests/test_doctor.py`; black/ruff clean.

## Sprint 2 review round 4 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL (1 High): `tests/test_crews.py::test_channel_for_uses_override_without_a_provider_default` tests nothing it claims (no override installed, provider default present). Supervisor confirmed by reading the test. → P11.

### P11 — channel override test fixed — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `309 passed`; test now installs an override and removes the default. Worker correctly declined to add duplicate tests (equivalents at lines 451/464).

## Sprint 2 review round 5 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL (1 Medium): recognized provider entry lacking `bucket`/`status`, or with an unrecognized status, still normalizes to healthy (supervisor reproduced three variants). → P12: require bucket name + status from the ai-subs badge vocabulary; script rejects malformed records.

### P12 — malformed records fail closed — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `336 passed`; black/ruff clean; `bash -n` OK; the three reproduced payloads now → unknown with `malformed` count 1 each; real snapshot still OK, same six healths.

## Sprint 2 review round 6 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL (1 Medium, 1 Low): script validation weaker than reader (unknown statuses, non-finite/out-of-range pct accepted); `context.md` said three rounds. → P13 (script parity); supervisor fixes context.md.

### P13 — script validation parity + KNOWN_STATUSES drift guard — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `351 passed`; black/ruff clean; `bash -n` OK; script's `KNOWN_STATUSES` literal is asserted equal to the reader's by a test that parses the script text.

## Sprint 2 review round 7 — Sol Low via `codex exec -s read-only` (detached)
- VERDICT FAIL (1 Medium): `Gemini/agy` record with an unrecognized non-empty bucket name is ignored rather than clouding the Gemini channels. → P14 (resume P12 worker).

### P14 — unroutable Gemini bucket names cloud both Gemini channels — Opus 5 high — ACCEPTED (supervisor-verified)
- Observed: `pytest -q` → `356 passed`; black/ruff clean; supervisor reproduction: healthy "Gemini models — weekly" + "Gemini flash — weekly" at 0% → both Gemini channels unknown, record in `malformed`. Real snapshot unchanged.

## Sprint 2 review round 8 — Sol Low via `codex exec -s read-only` (detached)
- **VERDICT: PASS** (one Low: `context.md` round count; fixed by supervisor at close). Sprint 2 closed 2026-09-07. Final: `pytest -q` 356 passed; black/ruff clean on src; real snapshot accepted; cron not installed.
- Supervisor retrospective: three of the eight rounds traced to supervisor packet wording (prefer `written_at`; doctor with plain json; "same way" validation promise). Lesson for Sprint 3 packets: state fail-closed invariants as contracts, not implementation hints.
- 2026-09-07 post-close: Lee installed the hourly cron on A8Max (PATH-prefixed; `$HOME` form replaced in docs since cron does not reliably set it). Supervisor ran the exact line under `env -i` with cron's PATH: exit 0, `doctor --availability` age 0 min.

## 2026-09-07 — Sprint 3 opened (Lee: proceed; supervisor pre-prompt commit `1fe82d2`)

Baseline observed: `pytest -q` → `356 passed`; `black --check src` → 21 unchanged; `ruff check src` → all passed; `doctor --crews --availability` → 14 crews, 23/23 workers, 1 forbidden warning; snapshot age 5 min, openai-sub degraded (HOT 48%), anthropic-sub healthy (session 31%, pace 2.13 — "USE IT" is not a degrading badge), gemini-sub healthy, openrouter/opencode-go unknown. All five CLI providers expose `build_command`. Live crews file has only single-worker stages (flex will be exercised by the fixture's list stages).

Packets planned:
- P15 (Opus 5 high) `resolver.py`: strict/flex/bind semantics, refusal rules, headroom rules, route identity, dispatch argv. Pure, no I/O, tests.
- P16 (Opus 5 high) `events.py`: append-only event ledger, schema, O_APPEND single write ≤ 4 KB, tests.
- P17 (Sonnet 5 high) `resolve` CLI subcommand + exit codes + `--json` + docs.
- P18 (Sonnet 5 high) `watchdog.py` stall watchdog with injected clock, fake subprocess tests.
- P19 (Sonnet 5 high) `dispatch` CLI subcommand wiring watchdog + resolver + docs.
Supervisor decision (not in plan text): `dispatch_command` returned by `resolve` is the provider harness argv from the provider's `build_command` (worker's harness binary, model, effort), with prompt delivery mode reported; the raw crews.yaml stage-worker template is returned separately as `worker_command`. Rationale: the crews template invokes Auto-Orch stage-worker scripts that need `{stage} {prompt_path} {response_path}` context an interactive harness does not have.

### P16 — `events.py` event ledger — Opus 5 high — ACCEPTED (supervisor-verified)
- Files: `events.py`, `tests/test_events.py` only (git status confirms). Observed: `pytest tests/test_events.py` → `21 passed`; black/ruff clean on both files.
- Supervisor reproduction: two appends → 2 physical lines with an embedded `\n` in reason escaped; file 0o600, dir 0o700; unknown key rejected; `authorized_by` on non-bind rejected; 3000×`é` reason → `EventTooLarge`; `read_events` → 2. Single `os.write` on `O_WRONLY|O_CREAT|O_APPEND`; short write raises. Host key = `socket.gethostname()` (matches availability).

### P18 — `watchdog.py` stall watchdog — Sonnet 5 high — ACCEPTED (supervisor-verified)
- Files: `watchdog.py`, `tests/test_watchdog.py` only. Observed: `13 passed`; black/ruff clean; stdlib-only imports.
- Supervisor reproduction with injected clock: 599 s quiet → CONTINUE, 600 s → STALLED (on_stall fired once), 700 s → STALLED (not re-fired), file touched under watch dir → CONTINUE, second quiet episode → STALLED (fired second time), output bytes → CONTINUE, ceiling → KILLED. Stall never kills; ceiling does.

### P15 — `resolver.py` strict/flex/bind semantics — Opus 5 high — ACCEPTED (supervisor-verified)
- Files: `resolver.py`, `tests/test_resolver.py` only. Worker declined to extend `tests/fixtures/crews.yaml` because three existing tests assert exact fixture counts; used synthetic crews YAML in `tmp_path` instead. Accepted (safer than the packet's allowance).
- Observed: full `pytest -q` → `434 passed`; black/ruff clean on `src`. Read the mode functions: strict veto set = {exhausted, likely_exhausted}; flex tiers healthy→degraded→unknown in list order, never-automatic skipped unless sole, forbidden skipped unless sole; bind requires worker+authorized_by+reason, forbidden refused in all modes citing D152/D153.
- Live reproduction (real crews + snapshot): strict openai-economy/envision → codex_luna_max on degraded openai-sub (reason states no veto on degraded); strict anthropic-flagship/author → claude_opus5_high healthy; flex mixed-flagship/author → codex_sol_high degraded; gemini-pro-crew envision strict and flex → exit 3 forbidden; bind to gemini31_pro → exit 3; bind claude_fable51_high authorized_by=lee → chosen. `resolve()` itself 0.08 ms.
- Two supervisor findings outside P15's scope, routed to new packets:
  - **Perf gate at risk**: `import lee_llm_router` eagerly pulls `client → router → registry → providers.http → httpx` (~100 ms); `yaml.safe_load` uses the pure-Python loader (16 ms for crews.yaml) though `CSafeLoader` is available. Total import+load 120 ms vs the 50 ms gate. → P20.
  - **Claude dispatch argv lacks the model**: `ClaudeCodeCLIProvider.default_model_flag = None` (pre-existing), so the bind dispatch command for claude_fable51_high was `claude --effort high -p {prompt}` with no `--model`; a dispatch would run the harness default model, not the crew's. → P21.

### P21 — Claude Code CLI provider passes `--model` — Sonnet 5 high — ACCEPTED (supervisor-verified)
- Files: `providers/codex_cli.py` (one line), `tests/test_providers.py` (+4 tests, one updated), `docs/providers.md`. Worker confirmed `claude --help` lists `--model <model>`.
- Supervisor reproduction: bind claude_fable51_high → `['/home/lee/.local/bin/claude', '--model', 'claude-fable-5-1', '--effort', 'high', '-p', '{prompt}']`.
- Note: at verification time 9 `test_providers.py` tests failed with `module 'lee_llm_router.providers.http' has no attribute 'httpx'` — caused by P20's concurrent in-flight edit, not P21. Contract sent to P20: the `httpx` module attribute must remain monkeypatchable while import stays lazy.

## 2026-09-07 ~14:25 CT — Staffing change (Lee, live): stop Anthropic workers
- Lee's ai-subs read: Anthropic session bucket 15% remaining, TOO FAST (pace 2.2), resets 17:29 CT. Instruction: "stop using anthropic models if you can … agy --dangerously-skip-permissions with gemini-3.8-flash max for worker and gemini-3.1-pro max for planner reviewer."
- Applied: P17 and P20 (Sonnet 5, already mid-flight) are allowed to finish; every dispatch from here is `agy -p --dangerously-skip-permissions --model gemini-3.8-flash-high --effort high` (worker) and `--model gemini-3.1-pro-high` (reviewer), prompt on stdin, detached via `setsid nohup`, `--print-timeout 60m`. `agy` exposes no `max` effort (low|medium|high; `agy models` lists `-high` as the top variant), so `high` is used.
- Reviewer family note: worker and reviewer are now both Gemini; the plan's "different family" review rule is relaxed by Lee's instruction for this bucket state. Sol Low (Codex, openai-sub 48%) remains available for the final gate if Lee wants a cross-family pass.
- agy smoke (supervisor): `agy -p --dangerously-skip-permissions …` fails ("-p took --dangerously-skip-permissions as its prompt"); bare `-p` with stdin prints help. Working form: `agy --dangerously-skip-permissions --model <m> --effort high --print-timeout 90m -p "<prompt>"` → `READY`, exit 0. **Sprint 1 defect surfaced:** `AntigravityCLIProvider.build_command` emits `[agy, -p, --model, …, --dangerously-skip-permissions]` with stdin delivery — the real CLI rejects both. → P22 (agy Flash).

### P17 — `resolve` CLI subcommand — Sonnet 5 high — ACCEPTED (supervisor-verified)
- Files: `doctor.py` (+224), `tests/test_doctor.py` (+12 tests), `docs/config.md`, `README.md`. Observed: `tests/test_doctor.py` → `51 passed`; full suite (worker) `455 passed`; black/ruff clean.
- Live: `resolve --crew anthropic-balanced --role envision --harness codex --events-file <tmp>` → exit 0, ten text lines, one JSONL event with `harness=codex`, all 17 fields, `route_id=claude_code_cli:claude-sonnet-5:high`; `gemini-pro-crew` strict `--json` → exit 3, error object on stdout with `kind=forbidden`, stderr message + remedy; bind without `--reason` → exit 3; event file still 1 line (refusals write nothing).
- **Supervisor finding (pre-existing, Sprint 1 provider template):** codex dispatch argv is `codex --model m -c model_reasoning_effort=high --output-last-message '{prompt}'` — no `exec` subcommand and `--output-last-message` takes a FILE. Against codex-cli 0.153.4 this would open the TUI or misparse. → P23 after P22 lands (both touch `tests/test_providers.py`).

### P22 — Antigravity provider argv order + argv prompt delivery — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `providers/antigravity_cli.py`, `tests/test_providers.py`, `docs/providers.md`. Observed: `tests/test_providers.py` → `96 passed`; black/ruff clean. `build_command` → `[agy, --dangerously-skip-permissions, --model, m, --effort, high, --print-timeout, 90m, -p, {prompt}]`; `complete()` uses `stdin=DEVNULL`.
- Expected consequence: `tests/test_resolver.py::test_dispatch_command_for_an_antigravity_worker_uses_stdin_delivery` now fails (asserts the old stdin contract). → P24 (test update only; omp remains the stdin example).

### P20 — cold-start perf, round 1 (lazy package init, lazy httpx, C YAML loader) — Sonnet 5 high — ACCEPTED on contracts; GATE NOT YET MET
- Files: `__init__.py` (PEP 562 lazy exports), `providers/http.py` + `openai_codex_subscription.py` (lazy httpx with module `__getattr__` so monkeypatching still works — fixed the 9 P21-time failures), `crews.py` (CSafeLoader with SafeLoader fallback), `tests/test_smoke.py` (+4), `tests/test_crews.py` (+2). Observed: 185 passed across the five touched suites; black/ruff clean on src; `LLMRouter is router.LLMRouter` True; `httpx` not in `sys.modules` after resolver import chain.
- Supervisor measurement (`date +%s%N`, 5 runs, `resolve --mode flex --no-event` on live inputs): 79/75/80/81/78 ms → median **79 ms** vs 50 ms gate. Breakdown: bare interpreter 12 ms; `import lee_llm_router.doctor` +20 ms (argparse, subprocess, shutil, typing 8 ms); `main()` 34 ms (lazy crews/availability/resolver/yaml imports ~20 ms + load + output). → P25 after P19 (both touch `doctor.py`).
- Worker's ruff report of 9 pre-existing errors in `tests/conftest.py`/`tests/test_async.py`: outside `src/`; the sprint's lint gate is `ruff check src`. Not a P20 defect.

### P23 — Codex provider default argv is `codex exec …` — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `providers/codex_cli.py`, `tests/test_providers.py`, `docs/providers.md`. Observed: providers+resolver suites `153 passed`; black/ruff clean. Defaults: codex → `[codex, exec, --model, m, -c, model_reasoning_effort=high, {prompt}]`; `subcommand: null` drops `exec`; Claude `[claude, --model, m, --effort, high, -p, {prompt}]` and Gemini `[gemini, -p, {prompt}]` unchanged.

### P24 — resolver test updated for argv delivery on Antigravity — Gemini 3.8 Flash high via agy — ACCEPTED
- `tests/test_resolver.py` only; antigravity test asserts argv delivery, omp remains the stdin example. Suite green.

### P19 — `dispatch` CLI + `dispatch.py` — Gemini 3.8 Flash high via agy — ACCEPTED WITH A HIGH FINDING → P26
- Files: `dispatch.py` (new), `doctor.py`, `tests/test_dispatch.py` (new), `docs/config.md`, `README.md`. Observed: `tests/test_dispatch.py`+`test_doctor.py` → `68 passed`; black/ruff clean; live `--dry-run` correct.
- Supervisor end-to-end with harmless harness binaries via a scratch crews file (`LEE_LLM_ROUTER_CREWS_FILE`): argv worker (`/bin/echo`) → prompt substituted, exit 0, one event line; 1 MB output worker → all 1,000,001 bytes forwarded, child exit 5 preserved; `sleep 3` with `--stall-minutes 0.02` → stall line on stderr, child continued, exit 0; `--max-minutes 0.02` → killed, exit 124.
- **High (reproduced):** stdin-delivery worker (`cat` wrapper) with a 300 KB prompt → deadlock (parent writes the whole prompt to the stdin pipe before reading stdout; child blocks on a full stdout pipe); killed by `timeout 20`. Small prompt works. Also: `except TypeError: proc = popen(argv)` and `hasattr(proc, "stdin_bytes")` are fake-accommodating seams in production code; `stderr=STDOUT` merges the child's stderr into stdout, contrary to the packet ("streamed to the parent's stdout/stderr"). → P26.

### P25 — cold-start perf round 2 (lazy doctor imports, mtime/size-keyed crews parse cache) — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `doctor.py`, `crews.py`, `availability.py`, `resolver.py`, `events.py` (import placement), `tests/test_crews.py` (+7 cache tests), `tests/test_smoke.py`, `docs/config.md`. Full suite `516 passed`; black/ruff clean on src.
- Gate (supervisor, `date +%s%N`, 5 runs, live inputs): 51/44/42/44/48 ms → **median 44 ms < 50** (cache disabled via `LEE_LLM_ROUTER_NO_CACHE=1`: 51/52/52). Cache at `~/.cache/lee-llm-router/crews_<hash>.json`, 0o600, keyed by path+size+mtime_ns; corrupt live cache → parse fell through, exit 0, cache rewritten valid.

### P26 — dispatch repair (stdin writer thread, separate stderr, no fake seams) — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified) with one follow-up
- Files: `dispatch.py`, `tests/test_dispatch.py`. E2E (scratch crews, harmless binaries): 300 KB stdin prompt → 300000 bytes back, exit 0 (was deadlock); `echo out; echo err >&2; exit 3` → stdout `out`, stderr `err`, exit 3; 1 MB output fully drained, exit 5; stall line once, ceiling exit 124.
- **Finding:** `dispatch.py:20` injects `builtins.re = re` — a hack masking a missing `import re` somewhere on a lazy path. → P27.

### P27 — remove `builtins.re` hack — Sonnet 5 high — ACCEPTED (supervisor-verified)
- `dispatch.py`, `tests/test_dispatch.py` (same vestigial hack removed), `tests/test_smoke.py` (+1 subprocess test asserting no module mutates `builtins`). `517 passed`; black/ruff clean on src; `grep builtins` → 0 hits in both files. Known Low: four E501 lines in `tests/test_smoke.py` from P25 (outside the `src/` lint gate; queued for the next repair packet if any).

## Sprint 3 review round 1 — Sol Low via `codex exec -s read-only` (detached)
- Dispatched after all packets P15–P27 supervisor-verified. Tree: 517 passed; black/ruff clean on src; gate median 44 ms.
- VERDICT FAIL (1 Medium): `resolver.py:323` flex silently skips a forbidden (Gemini 3.1 Pro) candidate when a peer exists; reviewer reproduced with a synthetic stage `[antigravity_gemini31_pro, codex_sol_high]` → exit 0, codex_sol_high. Reviewer's live checks: strict openai-economy → codex_luna_max degraded no veto; dispatch dry-run OK; doctor 14 crews 23/23; cold resolve 45.1/45.2/47.9/43.9/42.6 ms (median 45.1); black/ruff clean. Reviewer pytest sandbox-limited (no writable tmp); supervisor run authoritative: 517 passed.
- **Root cause: supervisor.** P15's packet text said "in flex, a forbidden candidate is skipped (not fatal) unless it is the only candidate"; the review prompt said "refused in every mode." Both are mine. Ruling: the plan's binding rule is "never chosen by the resolver," which skipping satisfies, but silence is the defect — a skipped forbidden worker must appear in the reason (and therefore the event line) with the rule cited, so a crews.yaml violation is visible on every resolution that walks past it. Disposition → P28 (Opus 5 high): flex reason names each skipped forbidden candidate citing D152/D153; test; also the four E501 lines in `tests/test_smoke.py`. Review prompt contract text corrected for round 2.

### P28 — flex names skipped forbidden candidates; all-forbidden → exit 3 — Opus 5 high — ACCEPTED (supervisor-verified)
- `resolver.py`, `tests/test_resolver.py` (+5), `tests/test_smoke.py` (E501 wraps). `521 passed`; black/ruff clean (src + test_smoke). Reviewer's reproduction re-run: `[gemini31_pro, codex_sol_high]` flex → codex_sol_high with reason "…; skipped antigravity_gemini31_pro (forbidden model gemini-3.1-pro, decisions.md D152/D153)"; all-forbidden two-candidate stage → exit 3 forbidden (was exit 2; accepted as the contract's intent).

## Sprint 3 review round 2 — Sol Low via `codex exec -s read-only` (detached)
- **VERDICT: PASS** (no High/Medium/Low). Reviewer reproduced the round-1 repair independently; live checks: strict degraded no-veto, forbidden exit 3 with citation, bind Claude/agy argv forms, dispatch dry-run, doctor 14 crews 23/23; cold resolve 50.9/49.1/49.0/48.7/50.7 ms (median 49.1). Reviewer pytest sandbox-limited; supervisor's final run authoritative: `521 passed`, black/ruff clean on src. **Sprint 3 closed 2026-09-07.** Committed as `feat(crew-resolver S3): …` (Lee's standing ruling: reviewed sprint state does not float).
- Supervisor retrospective: 14 packets, 2 review rounds. The one review finding traced to supervisor text (P15 packet vs. review prompt disagreeing on forbidden-in-flex). Five packets (P20–P23, P25, P26) were supervisor-discovered defects outside the plan's bullets — three of them pre-existing provider templates that had never been run against the real CLIs. Lesson: before a CLI-facing sprint, run each provider's `build_command` argv against `<tool> --help` once; it costs a minute and would have folded P21/P22/P23 into Sprint 1. Perf margin is thin (44–49 ms median against 50 on a 12 ms interpreter floor); Sprint 6 should watch it.

## 2026-09-07 — Sprint 4 opened (Lee: proceed; supervisor pre-prompt commit `21ca265`)
- Baseline re-verified before any packet: `pytest -q` → `521 passed`; `black --check src` → 25 unchanged; `ruff check src` → clean.
- **Real-binary survey (done before packet 1, per the Sprint 3 retrospective):**
  - `omp --help` (v18.1.13): `-p/--print` non-interactive, `--mode json`, prompt as positional. Binary strings show the prompt-template loader keyed `case "prompts"` resolving `<agentDir>/prompts/*.md` and `<cwd>/.omp/prompts/*.md`, substituting `$ARGUMENTS`, `$@`, `$N`, with `argument-hint` frontmatter. **The plan's `.omp/commands/crew.md` is not a path OMP reads; the target is `.omp/prompts/crew.md`.** Flagged in needs-lee.
  - `opencode --help` / `opencode run --help`: `run [message..]`, `--command <name>` (runs a command file with the message as args), `--agent`, `-m provider/model`, `--variant`. Binary strings: `~/.config/opencode/command/*.md` and `<project>/.opencode/command/`, body substitutes `$ARGUMENTS`. `~/.config/opencode/opencode.jsonc` is `{"$schema":..., "permission":"allow"}` only; a sidecar command file needs no jsonc edit.
  - `claude --help` and binary strings: `~/.claude/commands/*.md`, frontmatter `allowed-tools`, `argument-hint`, body `$ARGUMENTS`.
  - `codex --help` and binary strings: custom prompts use `$ARGUMENTS`, `$ARGUMENTS[N]`, `$N`; directory `~/.codex/prompts/` (does not exist yet, nor does `~/.claude/commands/`).
  - `$ARGUMENTS` is the one token all four support → C2 adds `resolve CREW ROLE` positionals so one template line serves all four.
- Contracts written once in `docs/crew-resolver/sprint4-contracts.md` (C1 D188 rule, C2 positionals, C3 shims, C4 perf, standing worker rules); packets and review prompts quote it. Packet files under `docs/crew-resolver/packets/`.
- Packet order (sequential; all touch `doctor.py`/`docs/config.md`): P29 D188 → P30 positionals → P31 shims module+CLI → P32 parity test → review.

### P29 — D188 role-scoped Gemini 3.1 Pro — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified) with one unowned-file follow-up → P29b
- Files: `crews.py` (`ROLE_CLASS_BY_ROLE`, `ROLE_SCOPED_MODELS`, `is_role_scoped`, `role_class`, `ROLE_SCOPED_CITATION`), `resolver.py`, `doctor.py` (`check_crews` warning + summary), `tests/test_crews.py`, `tests/test_resolver.py`, `tests/test_doctor.py`, `docs/config.md`. Within allowed set.
- Observed: `pytest -q` → `2 failed, 528 passed`; both failures in `tests/test_dispatch.py` (not in P29's allowed set — worker correctly stopped and reported instead of patching). Root cause is mine: the packet omitted that file; the tests assert the old blanket rule on `--role score`. Black/Ruff clean on src.
- Supervisor reproduction on a scratch crews file (`--crews-file`, `--no-event`): author strict → exit 3 kind forbidden citing D188; author flex `[pro, flash]` → flash chosen, reason `skipped antigravity_gemini31_pro (role-scoped model gemini-3.1-pro is never automatic for coding role 'author', decisions.md D188)`; author flex all-pro → exit 3; author bind pro → exit 3; envision strict / ideate flex / envision bind → pro chosen, exit 0, plain reason. Live: `doctor --crews` → `14 crews, 23/23 workers resolved, 0 role-scoped warning(s)`; `resolve --crew gemini-pro-crew --role envision --mode strict --no-event` → exit 0, antigravity_gemini31_pro.
- Note: the "unmapped role" branch is unreachable from the CLI because the crews loader rejects unknown stage names first (contract §5 says the check runs after that); it is covered at the `role_class` helper level.
- Nit → P29b: `ROLE_SCOPED_CITATION` literal duplicated in `resolver.py` and `crews.py`.

### P29b — dispatch tests to D188; citation single-sourced — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `tests/test_dispatch.py` (two refusal tests moved to `--role author`, cite D188; +1 test proving `--role score` now passes the gate and constructs Popen once), `resolver.py` (imports `ROLE_SCOPED_CITATION` from crews; local literal removed). Within allowed set.
- Observed: `pytest -q` → `531 passed`; `black --check src` → 25 unchanged; `ruff check src` → clean; `grep ROLE_SCOPED_CITATION resolver.py` → import + 2 uses, no definition.

### P30 — `resolve CREW ROLE` positionals (shim substrate, C2) — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `doctor.py` (+115: argparse positionals, fast path, validation), `tests/test_doctor.py` (+13 tests), `docs/config.md`. Within allowed set.
- Observed: `pytest -q` → `544 passed`; black/ruff clean on src. Live: positional vs flag `--json` output byte-identical minus `ts`; five malformed forms (flag+positional mix, one positional, three positionals, none, positional+`--crew`) all exit 3 kind usage with the two accepted forms in the message. Cold `resolve` ×5: 41/46/45/43/48 ms → median 45 (gate 50).

### P31 — shims module, one template, `shims install|diff` (C3) — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `shims.py` (new, 342 lines), `templates/shims/crew.md.tmpl` (new, one source), `pyproject.toml` (package-data glob), `doctor.py` (subparser + lazy handler), `tests/test_shims.py` (new, 360 lines), `docs/config.md`. Within allowed set.
- Observed: `pytest -q` → `555 passed`; black/ruff clean on src. `~/.claude/commands`, `~/.codex/prompts`, `~/.config/opencode/command` still absent after dry-run; `opencode.jsonc` unchanged.
- Supervisor E2E under `LEE_LLM_ROUTER_SHIM_HOME=<tmp>` + `--project <tmp>`: dry-run prints four targets with full bodies; apply creates four files with parents (exit 0); second apply → four `unchanged`; `diff` clean → exit 0; hand-edit codex + delete omp → `diff` shows unified diff and `missing`, exit 1; apply refuses the edited file (`refuse: not generated by lee-llm-router`), recreates the missing one, exit 1; `--force` → `update`, exit 0, diff clean; `--harness codex` filters to one target; neither mode → exit 3. Marker line `<!-- lee-llm-router shim v1 sha256=… -->`; bodies differ only in the harness tag and hash; each contains `lee-llm-router resolve $ARGUMENTS --mode flex --harness <tag> --json` and the `lee-llm-router dispatch …` offer line, and no provider binary.
- Perf after P31 (cold ×5): 49/47/41/44/51 → median 47 ms.

### P32 — four-harness parity test (C3 §5) — Gemini 3.8 Flash high via agy — ACCEPTED (supervisor-verified)
- Files: `tests/test_shims_parity.py` (new, 2 tests). Within allowed set.
- Observed: `pytest -q` → `557 passed`; black/ruff clean on src. Read the test: renders four shims under a tmp home, extracts exactly one `lee-llm-router resolve $ARGUMENTS --mode flex --harness <tag> --json` line per body, substitutes `<crew> <role>`, runs `python -m lee_llm_router.doctor resolve …` as a subprocess with fixture crews/snapshot and a tmp events file; asserts four exit-0 runs, JSON byte-identical minus `ts`/`harness`/`event_path`, four event lines with harness set exactly {claude-code, codex, omp, opencode} and equal `route_id`; second test asserts no provider binary command in any body and the dispatch offer line present.

## Sprint 4 review round 1 — Sol Low via `codex exec -s read-only` (detached)
- Dispatched after P29/P29b/P30/P31/P32 supervisor-verified. Tree: 557 passed; black/ruff clean on src; perf median 47 ms.
- **VERDICT: PASS** ("No High, Medium, or Low findings"). Reviewer log shows it ran the resolve matrix on a scratch crews file (`--json --no-event`), the positional/flag forms, `shims install --dry-run --project /tmp`, and imported `_try_fast_resolve`/`check_crews`/`main` directly; pytest sandbox-limited as before — supervisor's run is authoritative: `557 passed`, black/ruff clean on src. Cold `resolve` at close ×5: 45/49/47/49/45 → **median 47 ms** (gate 50; Sprint 3 close was 44/49). **Sprint 4 closed 2026-09-07.** Committed as `feat(crew-resolver S4): …`.
- Supervisor retrospective: 5 packets (P29, P29b, P30, P31, P32), 1 review round, PASS first time. The one repair packet (P29b) was a supervisor omission — `tests/test_dispatch.py` asserted the old rule and was not in P29's allowed set; the worker did the right thing by stopping instead of patching. The real-binary survey before packet 1 paid off directly: it found that OMP reads `.omp/prompts/`, not the plan's `.omp/commands/`, and that `$ARGUMENTS` is the only substitution token all four harnesses share — which is what made one template line (C2 positionals) possible. Gemini 3.8 Flash handled every packet including the contract-setting D188 one; no Opus escalation was needed. Writing the contracts once (`sprint4-contracts.md`) and quoting them into packets and the review prompt removed the Sprint 3 failure class entirely.

## 2026-09-07 — Sprint 4 live acceptance (Lee's literal gate, D189) — PASS
- Lee: D188 mapping approved unchanged; shim apply approved. Applied: `shims install --apply --project ~/projects/chief-of-staff` → four `create` lines; `opencode.jsonc` untouched. `lee-llm-router` was not on PATH → symlink `~/.local/bin/lee-llm-router` → `.venv/bin/lee-llm-router` (recorded; the template uses the bare name).
- Invoked `/crew gemini-pro-crew envision` once per harness from `~/projects/chief-of-staff`: `claude -p '/crew …' --allowedTools 'Bash(lee-llm-router:*)'`; `codex exec -s danger-full-access '/crew …'`; `omp -p --auto-approve --no-session '/crew …'`; `opencode run --command crew 'gemini-pro-crew envision'` (all `< /dev/null` — the first detached attempt without it left codex/omp/opencode blocked on piped stdin).
- Real ledger `~/.local/state/lee-llm-router/events/A8Max.jsonl`, lines after 2026-09-08T02:17Z: harness set exactly `['claude-code','codex','omp','opencode']`, all `gemini-pro-crew/envision/flex → antigravity_gemini31_pro`, route_id `antigravity_cli:gemini-3.1-pro:default` (one value). Every harness printed worker/model/effort/headroom/reason and the `lee-llm-router dispatch … --harness <tag>` offer; none dispatched. D188 exercised live: 3.1 Pro chosen for a planning role through all four doors.
- **Codex note:** under `codex exec -s workspace-write` the resolver resolved but the event append under `~/.local/state` was denied by the sandbox (Codex's own summary: "exited with an error because its event log is read-only"); no line written, exit non-zero, Codex still displayed the recommendation. Passed with `-s danger-full-access` (interactive Codex prompts for the write). Not a resolver defect; noted in needs-lee for Sprint 6's adoption report.

## 2026-09-07 — Post-sprint: OpenCode Go joins the availability snapshot (Lee's Mac `ai-subs.sh` change)
- Lee upgraded `ai-subs.sh` on the Mac to query the OpenCode Go zen usage API (key from `~/.local/share/opencode/auth.json`). Chief diffed it against the Linux copy: the Mac copy lacked the Linux-side `parse_reset` fixes (Claude "Sep 6, 5:50pm" formats, year wraparound), so the OpenCode hunks were merged onto the Linux parser rather than overwriting. Installed as `chief-of-staff/scripts/ai-subs.sh` (`73eadc4`). Live run: fourth provider `OpenCode/Go`, buckets Rolling 5-hour / Weekly / Monthly, ISO `resets_at` with microseconds. `refresh_availability.sh` exit 0 with the new label; reader tolerated it (12 buckets, `opencode-go: unknown`).
### P33 — reader maps `OpenCode/Go` → `opencode-go` — Gemini 3.8 Flash high via agy — ACCEPTED with follow-up
- `availability.py` (+`OPENCODE_GO_PROVIDER`, one branch in `channels_for`), `tests/test_availability.py` (+10), live-sample fixture +3 entries, `docs/config.md`. Worker stopped on 2 failures in `tests/test_refresh_availability.py` (not in its set; the fixture count 9→12) — supervisor packet omission, same class as P29b.
- Known Low: worker added `is_single_channel = is_routable_bucket` alias because the packet named the helper wrongly; harmless, remove in the next touch of `availability.py`.
### P33b — refresh tests count 12 with 3 `OpenCode/Go` entries — Gemini 3.8 Flash high via agy — ACCEPTED
- Supervisor: `pytest -q` → `569 passed`; black/ruff clean on src. Live `doctor --availability` → 12 buckets, `opencode-go: degraded` (worst-of over buckets; Monthly badge TOO FAST at pace 1.6 with 89% remaining — the Sprint 2 pace-vs-headroom calibration note applies). Flex still prefers healthy channels first, so `opencode-go-economy`/`-balanced` `author` (opencode_go_qwen37_plus) now resolve on a known channel instead of the unknown tier.

## 2026-09-07 — Crew Resolver Sprint 5 opened (Lee-authorized bounded supervisor lane)

Baseline personally observed before dispatch: `PYTHONPATH=src .venv/bin/python -m pytest -q` → 569 passed; `black --check src` → 26 unchanged; `ruff check src` → all passed; `doctor --crews --availability` → 14 crews, 23/23 resolved, 0 role-scoped warnings, snapshot age 7 minutes with 12 buckets. Tree was `main...origin/main [ahead 10]`, clean before the supervisor added the S5 contracts to `context.md`. Live inputs inspected: 14-crew Auto-Orch YAML, A8Max snapshot, `benchmark.staffing-evidence/2` sidecar generated 2026-09-08T00:00:31Z with 45 rows. Webroot convention inspected; publication remains Lee-gated. Current-turn staffing supersedes the older pre-prompt note: Sol Low supervisor; Luna XHigh through Pi for implementation; Sonnet 5 High through Claude for independent review; Opus 5 High final gate.

### P34 — benchmark evidence and proposal core — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- Authority: new `crew_page.py` and `tests/test_crew_page.py` only. Worker stayed within authority; `context.md` was the supervisor's pre-existing edit.
- Worker runtime was approximately 13 minutes; no repair or escalation. Added explicit sidecar validation, deterministic identity mapping, aggregate metrics, and fail-closed proposal predicates.
- Observed: focused 15 passed; full suite 584 passed; Black/Ruff clean; live doctor unchanged. Supervisor read the full production/test files. No live input or event write.

### P35 — self-contained HTML renderer — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- Authority: `crew_page.py` and `tests/test_crew_page.py` only. Worker stayed within authority.
- Worker runtime approximately 8 minutes; no repair or escalation. Added escaped ordered roster rendering, headroom/staleness, evidence metrics, proposal and no-proposal states, run-id appendix, inline light/dark/mobile CSS, and atomic caller-selected output.
- Observed: focused 18 passed; full suite 587 passed; Black/Ruff clean; live doctor unchanged. Direct live API render: 14 crews, 23 workers, 45 evidence rows, 0 qualifying proposals, 73,460 bytes; machinery/source-token scan found `Run ids` only inside the appendix.

### P36 — `crews page` CLI and product documentation — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- Authority: `doctor.py`, `tests/test_doctor.py`, `docs/config.md`, with integration correction authority over P34/P35 files unused. Worker stayed within authority.
- Worker runtime approximately 7 minutes; no repair or escalation. Added lazy CLI wiring, latest-sidecar discovery, optional explicit event-ledger validation, fail-closed errors/no partial output, and publication/refresh handoff documentation. Did not modify refresh script, cron, webroot, crews.yaml, harnesses, or live ledger.
- Observed: focused 93 passed; full suite 595 passed; Black/Ruff clean; live doctor unchanged. Live CLI page: exit 0, 73,460 bytes, 0.06 s. Explicit missing sidecar: exit 0 with `No benchmark evidence yet.` Malformed event JSONL: exit 3 and no output. Cold `resolve` runs 51.64/47.48/40.20/45.96/41.41 ms, median 45.96 ms (<50 ms contract).

## Sprint 5 Sonnet review round 1 — FAIL (1 High, 0 Medium, 2 Low)
- High reproduced and accepted: `WORKER_POLICIES` invents `standard/frontier/economy` tiers and uses distribution channel as `vendor_boundary`. Governing decisions and live crews do not define those fields. Concrete reproduction by inspection: the OMP mapping assigns Gemini/Qwen/GLM/DeepSeek the same `("economy", "openrouter")` boundary, while one OpenAI Luna model receives different boundaries by harness. This could permit a future cross-vendor proposal. Current live sidecar emits 0 proposals, so the defect is latent but real.
- Root cause: supervisor packet P34 incorrectly instructed Luna to encode a local policy map when authoritative metadata was absent. S5-C3 itself supplies the correct fail-closed rule: if every predicate cannot be proved, emit no proposal. P37 removes the invented authority and preserves explicit absence.
- Low 1 accepted as contract hardening: raw provider implementation ids appear in main-card prose. P35's packet text allowed provider/model identities, but S5-C2's exact machinery-name prohibition is stronger. P37 renders human labels without `_cli` machinery ids.
- Low 2 accepted as cleanup: governed-role entries in `BENCHMARK_ROLES_BY_RESOLVER_ROLE` are unreachable because proposals iterate stage roles only. P37 removes the dead entries.

### P37 — remove invented proposal boundaries; public-label cleanup — Luna XHigh via Pi — REPAIR INCOMPLETE, core High fixed
- Luna removed `WORKER_POLICIES`; proposal selection now returns no proposals because current inputs cannot prove the two boundary predicates. It also removed unreachable governed-role mappings and humanized worker-card provider values. Focused 94 passed; full suite 596 passed; Black/Ruff clean.
- Supervisor reproduced the High as fixed: no tier/vendor table remains and live proposals remain explicitly empty. Supervisor then found the Low cleanup incomplete: live mixed-flagship purpose still contained `codex_cli` before the appendix. Root cause was the repair packet/test covering worker cards but not untrusted crew purpose prose. Sent P37b to Luna; no escalation.

### P37b — sanitize known provider implementation ids in crew purposes — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- Files remained within `crew_page.py` and `tests/test_crew_page.py`. Added fixed-token sanitation before escaping purpose prose and a two-token regression test.
- Observed: focused 95 passed; full suite 597 passed; Black/Ruff clean; live doctor passes. Live page main body contains none of the five known `_cli` provider ids, `/home/`, sidecar filename, `run_id`, or `run id`; 14 crew cards remain; 73,037 bytes. Cold resolve 44.58/41.00/43.05/40.94/39.38 ms, median 41.00 ms.

## Sprint 5 Sonnet review round 2 — FAIL (1 High, 0 Medium, 1 Low)
- High reproduced and accepted against the authoritative exporter: `build_rows` uses the earliest valid run for representative `acceptance`/cost, but counts all accepted runs in `accepted_count`. A valid retry group can therefore be `acceptance=not_accepted, accepted_count=1`. Current loader rejects it; supervisor's exact synthetic schema-v2 row raised `BenchmarkEvidenceError` and would make the CLI exit 3.
- Repair also must correct derived semantics: `accepted_count > 0` proves acceptance, but representative cost is cost-to-accept only when representative acceptance is accepted; otherwise accepted cost is unknown in schema v2.
- Low accepted: D188 planning/review-only rendering works but lacks a regression test. P38 adds it.
- Reviewer harness note: `--permission-mode plan` caused Claude to save a plan file under `~/.claude/plans/` despite explicit read-only instructions. No project/live configuration was changed. Future review rounds will use `dontAsk` with Read/Grep/Glob and allowlisted read-only Bash, not plan mode.

### P38 — grouped retry schema semantics + D188 badge regression — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- Files: `crew_page.py`, `tests/test_crew_page.py` only. Loader decouples representative acceptance from aggregate accepted count; accepted-run metrics sum all `accepted_count`; cost-to-accept uses only accepted representatives and otherwise stays unknown. Added exact grouped-retry CLI path and D188 badge test.
- Observed: exact reproducer loads one row, `accepted=True`, accepted count 1, cost None. Focused 97 passed; full suite 599 passed; Black/Ruff clean; live doctor passes. Latest default-discovered live sidecar (`staffing-evidence-20260908.json`, 86 rows) generates 80,220-byte page.

## Sprint 5 Sonnet review round 3 — FAIL (1 High, 0 Medium, 0 Low)
- High reproduced and accepted: `crews page` exits 3 on a missing availability file, while established resolver/doctor behavior treats absence as all channels unknown. This prevents pre-refresh/manual page generation and contradicts S5-C2's legitimate unknown state. Present malformed input must remain fatal. Sent P39 to Luna; no escalation.

### P39 — missing availability renders unknown; malformed remains fatal — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- Files: `doctor.py`, `tests/test_doctor.py`, `docs/config.md`; within authority. Added missing/non-file distinction and documented it.
- Observed: explicit missing snapshot → exit 0, page exists, 70 headroom-unknown and 70 observation-time-unknown entries; input remains absent. Present malformed JSON → exit 3 and no output. Focused 99 passed; full suite 601 passed; Black/Ruff clean; live doctor passes.

## Sprint 5 Sonnet review round 4 — PASS (no High, Medium, or Low findings)
- Reviewer independently observed 601 passed, Black/Ruff clean, live doctor 14 crews/23 workers/0 warnings, live page exit 0 in 0.067 s with 14 crew cards/70 worker cards/current evidence/no proposals, schema and identity mapping alignment, repair integrity, atomic write, and escaping.
- Reviewer-process incident: Sonnet accidentally ran one live `resolve` without `--no-event`, appending a `mixed-flagship/author → codex_sol_high` line to the append-only live ledger at `2026-09-08T10:30:14Z`. The reviewer disclosed it and did not attempt deletion. Supervisor preserves append-only history and classifies the line as review contamination, not product evidence. No code/config/webroot/cron/harness mutation occurred.

## Sprint 5 Opus 5 High final gate — PASS (no High, Medium, or Low findings)
- Opus independently inspected exact git scope, contracts, live artifact, authoritative benchmark producer/schema, identity mapping, availability semantics, HTML escaping, atomic write, publication boundary, and lazy resolve path. Its runtime Bash allowlist prevented rerunning pytest/Black/Ruff/page commands, so supervisor-observed runtime gates remain authoritative.
- Non-blocking operational notes recorded for handoff: generated files use `mkstemp` mode 0600, so publication must set web-readable mode; proposal selection intentionally remains inert until an authoritative tier/vendor-independence source exists.
- Economics retrospective: 7 Luna XHigh/Pi packets attempted. Three initial packets passed immediate supervisor verification, though later independent review found cross-cutting defects. Four repair packets followed: P37 fixed the High but needed P37b for a missed Low path; P38 and P39 passed first repair verification. No implementation escalation. Sonnet required four review rounds; Opus required one final gate. Evidence supports Luna XHigh as economically appropriate: it completed every bounded implementation/repair packet, and stronger models remained supervisors/reviewers rather than implementation fallbacks.

### P38 — grouped retry sidecar semantics + D188 badge regression — Luna XHigh via Pi — ACCEPTED (supervisor-verified)
- `crew_page.py` now accepts independent representative `acceptance` and aggregate `accepted_count`; metrics sum aggregate accepted counts and expose cost-to-accept only when the representative itself was accepted. Tests cover the exact valid retry shape through loader and CLI plus D188 coding-stage badge rendering.
- Observed: exact reproducer → rows 1, accepted true, accepted_count 1, cost None. Focused 97 passed; full suite 599 passed; Black/Ruff clean; live doctor passes. Default discovery selected the current 86-row `staffing-evidence-20260908.json`; CLI exit 0, 80,220 bytes.

## Sprint 5 Sonnet review round 3 — FAIL (1 High, 0 Medium, 0 Low)
- High reproduced and accepted: `crews page` rejects a missing availability file, while established `resolve` and `doctor --availability` semantics treat missing snapshot as all channels unknown. The missing-file condition should permit a manual/fresh-install page with unknown headroom; malformed or unreadable existing inputs remain errors. No test covered missing availability.
- Root cause: P36 grouped missing and malformed availability under one `snapshot.problem` check. P39 is a narrow Luna repair; no escalation.

## 2026-09-08 — Sprint 6 opened and stopped at the committed evidence gate

Supervisor baseline, personally observed before any worker dispatch:
- Repository clean at `1c5a77b` (`feat(crew-resolver S5): add crew staffing page`), `main` ahead of `origin/main` by 11 and behind by 0.
- `PYTHONPATH=src .venv/bin/python -m pytest -q` → `601 passed in 5.00s`.
- `.venv/bin/black --check src` → 27 files unchanged; `.venv/bin/ruff check src` → all checks passed (one pyproject deprecation warning).
- `lee-llm-router doctor --crews --availability` → 14 crews, 23/23 workers, 0 role-scoped warnings; live A8Max snapshot age 47 minutes, 12 buckets.
- Installed shim drift check for all four harnesses → exit 0, no drift.
- Existing hourly schedule refreshes availability only; no page publication/regeneration was silently added.

Performance re-baseline against live crews and availability inputs, 15 separate subprocess invocations of `resolve openai-economy author --mode flex --no-event --json`: 45.399, 48.044, 46.191, 45.106, 44.235, 47.041, 44.043, 45.430, 37.252, 44.428, 46.431, 40.104, 39.214, 45.260, 39.525 ms. Median 45.106 ms; min 37.252; max 48.044. This supports retaining the current 50 ms target on this host for now, but it is not a two-week stability sample. Each invocation was a fresh process; no provider CLI was called and no event was written (`--no-event`).

Adoption evidence available at open:
- Live append-only ledger has 9 valid lines spanning only 2026-09-07T19:50:49Z through 2026-09-08T10:30:14Z: four events on 2026-09-07 and five on 2026-09-08.
- Harness counts: CLI 5, Claude Code 1, Codex 1, OMP 1, OpenCode 1. Modes: flex 5, strict 4. Binds: 0. Recorded chosen headroom states: healthy 9.
- The four harness-tagged lines are the explicit Sprint 4 live acceptance exercise, not two weeks of ordinary adoption. One CLI line at 2026-09-08T10:30:14Z is already disclosed reviewer contamination. The ledger records successful resolutions, not a denominator of all interactive dispatches, and therefore cannot yet prove resolver share.
- No event field can prove that a provider CLI was or was not called at decision time; code/tests establish the architectural separation, while sustained operational evidence still requires the committed observation window.

**Disposition: Sprint 6 FAIL/BLOCKED, not an implementation failure.** The authoritative plan requires “Two weeks of daily use.” Only two calendar days exist, so producing the required report or filing an evidence-backed Auto-Orch adoption recommendation now would fabricate adoption evidence. No Luna packet was dispatched because production code, tests, or product documentation cannot repair elapsed-time evidence. No Sprint 6 commit was made and Sprint 7 was not started.

### Lee ruling, 2026-09-08 — retain the observation window

Lee explicitly declined to amend the two-week requirement. Standing status: **Sprint 6 — ⏳ BLOCKED / EVIDENCE ACCUMULATING; engineering health GREEN; adoption conclusion NOT YET MEASURABLE; earliest meaningful resumption approximately 2026-09-22.** Normal workflow should generate evidence without manufactured `/crew` invocations. If natural use remains sparse, that is itself adoption evidence rather than a reason to inflate the sample. No implementation packet is opened merely to create activity.
