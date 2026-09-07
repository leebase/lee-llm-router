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
