# Lee LLM Router Result Review

> **Running log of completed work.** Newest entries at the top.
>
> Each entry documents what was built, why it matters, and how to verify it works.

---

## 2026-09-12 - Staffing class derivation for TOML and INI complete

**Result:** PASS. `.toml` and `.ini` owned paths derive the existing
`yaml-config` language class. Mixed configuration formats remain homogeneous,
configuration plus source code derives `mixed`, domain tags remain independent,
and the closed eight-value taxonomy is unchanged. The independent review found
zero Critical, High, Medium, or Low findings.

**Review artifacts:** `code-reviews/review-derive-class-toml-ini.md` and its
machine-readable `.verdict.json` companion record the clean verdict. The review
also confirms all six contract acceptance criteria and five live CLI user
journeys.

**Authoritative preserved validation:** Agent-Orch recorded exit status 0 for
all six checks: `compileall` on the test module (0.128023s); focused pytest at
implementation (1.134916s) and repair verification (1.057359s); Black check
(0.301396s); Ruff check (0.028783s); and `compileall` on production plus tests
(0.031417s). These preserved checks were summarized during closeout and were not
rerun by the closeout worker.

**Disposition:** The slice is closed with no follow-up repairs. The next agent
should wait for an explicitly authorized staffing packet.

---

## 2026-09-08 - Crew Resolver Sprint 6: blocked at observation-window gate

**Result:** FAIL/BLOCKED without implementation. The committed Sprint 6 contract requires two weeks of daily-use evidence. The live append-only event ledger currently contains only 9 events across two calendar days, including four explicit harness acceptance runs and one disclosed reviewer-contamination run. That is insufficient to report actual interactive adoption share or sustained bind, veto, provider-call, and shim-drift behavior without overstating evidence.

**Supervisor-observed baseline:** 601 tests passed; Black/Ruff clean; live doctor reported 14 crews and 23/23 workers with 0 warnings; all four installed shims had zero drift. Fifteen fresh-process live-input `resolve` measurements were 45.399/48.044/46.191/45.106/44.235/47.041/44.043/45.430/37.252/44.428/46.431/40.104/39.214/45.260/39.525 ms, median 45.106 ms. This supports retaining the 50 ms target on A8Max provisionally, not claiming a two-week SLO.

**Disposition:** No Luna packet was dispatched because elapsed adoption evidence is not repairable in code. No independent final review or Sprint 6 commit was appropriate. `docs/crew-resolver/needs-lee.md` asks Lee to let the evidence window run (recommended) or explicitly amend the contract. Sprint 7 was not started.

---

## 2026-09-08 - Crew Resolver Sprint 5: crew page and evidence-safe proposals

**What was built:** `lee-llm-router crews page --out <path>` generates one self-contained responsive HTML page from the authoritative crew roster, the availability snapshot, and the latest optional `benchmark.staffing-evidence/2` sidecar. It shows all crews/stages/workers in declared order, normalized headroom and freshness, benchmark score/cost/run/task evidence, and a run-id appendix. Missing benchmark or availability inputs render explicit unknown/absent states; present malformed inputs exit 3 without a partial page. Proposal selection is deliberately fail-closed: current sources do not prove model-tier and vendor-independence boundaries, so the page says no proposals qualify rather than inventing policy.

**Why it matters:** Lee can inspect staffing evidence and subscription headroom beside the actual crew assignments without querying multiple systems or allowing a generator to edit the routing authority. Publication remains a separate Lee decision.

**Evidence (supervisor-observed):** 601 tests passed; Black/Ruff clean; `doctor --crews --availability` reports 14 crews, 23/23 workers, 0 warnings. Default discovery generated an 80,220-byte page from the current 86-row sidecar. Missing availability generated 70 unknown headroom/observation entries; malformed availability exited 3 with no output. Cold `resolve` median remained 41.00 ms after repairs (<50 ms). Live page body contained no raw provider implementation ids, source paths/names, or run-id wording outside the appendix.

**Review:** Sonnet 5 High rounds 1–3 found three High producer/contract defects; all were reproduced and returned to Luna XHigh. Round 4 PASS with no findings. Opus 5 High final gate PASS with no High, Medium, or Low findings. Seven Luna packets total (three initial, four repair); no model escalation for implementation.

**How to Verify**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check src && .venv/bin/ruff check src
lee-llm-router doctor --crews --availability
lee-llm-router crews page --out /tmp/crews.html
```

---

## 2026-09-07 - Crew Resolver Sprint 4: D188 role-scoped Gemini 3.1 Pro, four harness shims

**What was built:** (1) The blanket Gemini 3.1 Pro refusal became a role-scoped rule (chief-of-staff D188): `ROLE_CLASS_BY_ROLE` in `crews.py` maps stage names to `coding` or `planning_review`; for coding roles a role-scoped model is refused in strict and bind (exit 3, citing D188) and skipped-and-named in flex; for planning/review roles it is an ordinary worker. `doctor --crews` warns only where a crew names it in a coding stage. (2) `resolve CREW ROLE` positionals (equivalent to `--crew/--role`, exit 3 on mixed forms) so one shim line works in every harness via `$ARGUMENTS`. (3) `shims.py` renders one template (`templates/shims/crew.md.tmpl`) into four targets — Claude Code `~/.claude/commands/crew.md`, Codex `~/.codex/prompts/crew.md`, OMP `<project>/.omp/prompts/crew.md`, OpenCode `~/.config/opencode/command/crew.md` — each carrying a `sha256` marker; `lee-llm-router shims install --dry-run|--apply [--force] [--harness TAG] [--project PATH]` and `shims diff` (exit 1 on drift or missing). Shims recommend and never dispatch.

**Why it matters:** Lee can type `/crew <crew> <role>` in any of the four harnesses and get the same worker the CLI would choose, with the harness tag on the ledger line. 3.1 Pro is usable where Lee actually uses it (planning/review) and still never writes code automatically.

**Evidence (supervisor-observed):** 557 tests (from 521); Black/Ruff clean on `src/`. Live: `doctor --crews` → 14 crews, 23/23, 0 role-scoped warnings; `gemini-pro-crew envision` strict/bind → exit 0 on 3.1 Pro; scratch-file `author` strict/bind → exit 3, flex → skipped and named. Shims: apply/refuse/force/diff cycle run in a temp home; real home directories untouched. Parity test runs each rendered shim's exact `resolve` line as a subprocess: four events, four harness tags, one `route_id`. Cold `resolve` ×5 at close: 45/49/47/49/45 ms (median 47).

**Review:** Sol Low (Codex, read-only). Round 1 **PASS**, no findings. Ledger: `docs/crew-resolver/execution-log.md`; open items: `docs/crew-resolver/needs-lee.md` (D188 mapping confirmation, `--apply`, in-harness acceptance).

**How to Verify**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q                                   # 557 passed
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor doctor --crews        # 0 role-scoped warning(s)
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor resolve gemini-pro-crew envision --mode flex --no-event
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor shims install --dry-run --project ~/projects/chief-of-staff
```

---

## 2026-09-07 - Crew Resolver Sprint 3: resolve CLI, flex/bind, event ledger, dispatch watchdog

**What was built:** `resolver.py` — a pure `resolve()` over the loaded crews and the availability snapshot with three modes. `strict` returns the crew's named worker and vetoes (exit 2) only on `exhausted`/`likely_exhausted`; `degraded`/`unknown` pass with the state named in the reason, so a dead availability cron cannot halt governed runs. `flex` walks the stage list in declared order by tier (healthy, then degraded, then unknown as a stated last resort), skips never-automatic workers (Fable 5.1, Luna Max, Opus 5) unless the stage names only one, and exits 2 with a remedy (`refresh availability` or `wait for reset at <time>`) when nothing is eligible. `bind` requires `--worker --authorized-by --reason`, may name any worker, reports headroom and never vetoes. Gemini 3.1 Pro is refused in every mode (exit 3, D152/D153). `events.py` appends one compact JSON line per successful resolution to `~/.local/state/lee-llm-router/events/<host>.jsonl` with a single `O_APPEND` write, 4 KB cap, 17 fixed fields including `route_id` (`provider:model:effort`) and `harness`. `lee-llm-router resolve` and `lee-llm-router dispatch` expose this; `dispatch` runs the provider harness argv with the prompt on argv or stdin (writer thread, no pipe deadlock), streams stdout/stderr, and supervises it with `watchdog.py` (stall flag after `--stall-minutes` of no output and no watched-file activity, never kills; `--max-minutes` ceiling kills, exit 124). Provider dispatch templates were corrected against the installed CLIs (`codex exec …`, `claude --model … --effort … -p`, `agy --dangerously-skip-permissions --model … -p`). Cold start: package `__init__` is lazy (PEP 562), `httpx` deferred, C YAML loader, and an mtime/size-keyed crews parse cache under `~/.cache/lee-llm-router/` (`LEE_LLM_ROUTER_NO_CACHE=1` disables).

**Why it matters:** This is the seam every harness shim (Sprint 4) will call: one place that knows who is allowed, who is funded, and who was chosen, with the escalation authority on the record. The event ledger's `route_id` is what the benchmark compares cost-to-accept on.

**Evidence (supervisor-observed):** 517 tests; Black/Ruff clean on `src/`; `resolve` on the live crews file and real snapshot, 5 cold runs: 51/44/42/44/48 ms (median 44 ms; gate < 50). End-to-end dispatch with harmless binaries: 300 KB stdin prompt round-trips; 1 MB output drained with the child's exit code; stall flagged without kill; ceiling kills with 124. Ledger: `docs/crew-resolver/execution-log.md`.

**Review:** Sol Low (Codex, read-only). Round 1 FAIL (one Medium: flex silently skipped a forbidden candidate — supervisor packet/review-prompt inconsistency; repaired so the skip is named in the reason with the D152/D153 citation, and an all-forbidden stage exits 3). Round 2 **PASS**, no findings. Reviewer's own cold-start median 49.1 ms; supervisor's 44 ms. 521 tests.

**How to Verify**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor resolve --crew openai-economy --role author --mode flex --no-event
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor resolve --crew gemini-pro-crew --role envision --no-event   # exit 3, forbidden
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor dispatch --crew openai-economy --role author --prompt hi --no-event --dry-run
for i in 1 2 3 4 5; do s=$(date +%s%N); PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor resolve --crew openai-economy --role author --mode flex --no-event >/dev/null; e=$(date +%s%N); echo $(( (e-s)/1000000 )); done
```

---

## 2026-09-07 - Crew Resolver Sprint 2: Availability Snapshot and Refresh

**What was built:** `availability.py` reads the `ai-subs` snapshot (`~/.local/state/lee-llm-router/availability/<host>.json`, env `LEE_LLM_ROUTER_AVAILABILITY_FILE`) and normalizes it to per-channel headroom (`healthy | degraded | likely_exhausted | exhausted | unknown`) across six funding channels (openai-sub, anthropic-sub, gemini-sub, gemini-sub-thirdparty, openrouter, opencode-go). Fail-closed: snapshots older than 90 minutes, future-skewed beyond 5 minutes, non-finite or out-of-range values, and malformed files all read as `unknown`, never `healthy`; the older of `observed_at`/`written_at` governs age. `crews.py` gains the worker → channel map (`PROVIDER_CHANNELS`, overrides). `scripts/refresh_availability.sh` runs ai-subs, validates, and writes the snapshot atomically; the hourly cron line is documented in `docs/availability-refresh.md`, not installed. `doctor --availability` renders the reader's verdict.

**Why it matters:** "Start cheap, move up only if needed" requires knowing what is available now. This is the "who is actually available?" layer under Sprint 1's "who is allowed?"; Sprint 3's resolver reads it and never calls a provider CLI at decision time.

**Review:** Sol Low (Codex, read-only). Rounds 1-7 FAIL, each finding repaired the same session (non-finite values, future skew, naive UTC, oldest-timestamp staleness, malformed-record fail-closed with the ai-subs badge vocabulary, unroutable Gemini buckets, script validation parity, a test time bomb, a misnamed test). Round 8 PASS (one Low, docs). 356 tests. Ledger: `docs/crew-resolver/execution-log.md`.

**How to Verify**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check src && .venv/bin/ruff check src
scripts/refresh_availability.sh --dry-run
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor doctor --availability --crews
```

---

## 2026-09-07 - Crew Resolver Sprint 1: Crews as a Routing Policy

**What was built:** `crews.py` loads Auto-Orch's `crews.yaml` (env `LEE_LLM_ROUTER_CREWS_FILE`, default `~/projects/auto-orch/config/crews.yaml`) into typed `Crew`/`Stage`/`Worker` objects, accepting single-worker and ordered-list stages, and resolves each worker id to a router provider/model/effort by parsing the worker command (CODEX/CLAUDE/OMP/OPENCODE/ANTIGRAVITY prefixes). `CrewRoutingPolicy` implements strict mode (named worker, `allow_fallback=False`, effort threaded via new `LLMRequest.effort`). New `opencode_cli` and `antigravity_cli` providers; `build_command` dispatch templates on omp/codex/claude/gemini/opencode/antigravity. CLI: `crews list [--json]` and `doctor --crews`.

**Why it matters:** First slice of the crew-aware worker resolver (Chief of Staff D187). Crews are now a routing policy inside the router without forking Auto-Orch's authority file, and the never-automatic / forbidden-model constants are in place for Sprint 3 enforcement.

**Review:** Sol Low (Codex, read-only). Round 1 FAIL (4 High, 1 Medium: fallback inheritance, dropped effort, missing OMP prefix, missing dispatch template on omp/codex, partial doctor coverage). All repaired. Round 2 PASS, no findings. Ledger: `docs/crew-resolver/execution-log.md`.

**How to Verify**

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q            # 193 passed
.venv/bin/black --check src && .venv/bin/ruff check src
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor crews list
PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor doctor --crews   # 14 crews, 23/23 workers, 1 warning
```

---

## 2026-03-29 - Sprint 7 Follow-Up: Documentation Sweep

**What was built:** Swept the public docs after the Sprint 7 implementation and review-fix passes to ensure the published behavior matches the shipped pi harness contract. Updated the config schema docs to state that `default_role` must reference an existing role and that `model_flag` / `output_flag` can be set to `null` to disable default CLI flags. Expanded the LLM coder guide with a pi-style subprocess harness example and clarified what `doctor` validates for `codex_cli` roles.

**Why it matters:** The public docs now match the real invocation and validation behavior that shipped in Sprint 7, so downstream consumers can copy the pi harness config safely without discovering contract details only by reading source or test fixtures.

**How to Verify**

```bash
sed -n '1,220p' docs/config.md
sed -n '1,220p' docs/llm-coder-guide.md
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q
```

---

## 2026-03-29 - Sprint 7 Follow-Up: Review Fixes for Pi Harness Contract

**What was built:** Fixed the two code review findings from the Sprint 7 hardening pass. `codex_cli` now allows wrappers to disable the default `model_flag` by setting it to `null`, and the docs/examples were updated so the pi harness configuration no longer implies unsupported default flags. The JSON parsing path also now validates `usage` fields as part of the harness contract, raising `CONTRACT_VIOLATION` instead of leaking `ValueError` into the router's generic `UNKNOWN` bucket. Added regression tests for both cases.

**Why it matters:** Real pi-style wrappers can now opt out of Codex-specific CLI flags explicitly, which makes the published config examples actually safe to copy. Malformed usage metadata also stays inside the typed contract-failure lane, so traces and fallback behavior remain consistent with the Sprint 7 reliability goal.

**How to Verify**

```bash
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_providers.py tests/test_router.py tests/test_doctor.py -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m ruff check src/lee_llm_router/providers/codex_cli.py tests/fixtures/pi_harness.py tests/test_providers.py tests/test_router.py tests/test_doctor.py
```

---

## 2026-03-29 - Sprint 7 Complete: Pi Coding Harness Reliability and Harness Validation

**What was built:** Added a repo-local simulated pi harness fixture and used it to harden the `codex_cli` provider around real subprocess failure classes. `codex_cli` now supports fixed `args`, optional `response_format: json`, JSON text extraction, usage passthrough, and deterministic `CONTRACT_VIOLATION` failures for malformed harness output. `doctor` now validates the configured provider and role wiring instead of a mock-only path, config loading now rejects unknown `default_role` and fallback providers, and docs/templates were updated to show the pi harness contract.

**Why it matters:** The downstream pi harness problem is now reproducible and diagnosable in this repo. Instead of vague CLI failures, malformed harness output is typed, traceable, and covered by regression tests. Downstream consumers can validate their harness config earlier and rely on a proven local contract for pi-style subprocess execution.

**How to Verify**

```bash
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_doctor.py -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q
PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml
# user-style pi harness validation:
# - create a temp codex_cli config with command=/Users/lee/projects/lee-llm-router/.venv/bin/python
# - args=[tests/fixtures/pi_harness.py, success_json]
# - response_format=json
# - run LLMRouter.complete("pi_local", [{"role":"user","content":"ship sprint 7"}])
```

---

## 2026-03-29 - Sprint 7 Planned: Pi Coding Harness Reliability and Harness Validation

**What was built:** Created a new Sprint 7 plan centered on pi coding harness reliability. The sprint now explicitly treats the recent downstream app failure as a first-class repo concern: reproduce the failure locally, harden harness validation and error handling, add regression coverage for success and failure cases, and add a user-style validation path for pi coding harness behavior.

**Why it matters:** A downstream app already failed because the pi coding harness path was not reliable enough. Turning that failure into an official sprint keeps the work grounded in an actual consumer problem and makes “prove the harness works” part of the delivery contract rather than an informal follow-up.

**How to Verify**

```bash
sed -n '1,260p' sprint-plan.md
sed -n '1,220p' context.md
sed -n '1,220p' WHERE_AM_I.md
```

---

## 2026-03-29 - Sprint 6 Bugfix: Export Source Supports Existing Empty Destinations

**What was built:** Fixed `lee-llm-router export-source` so it now succeeds when the destination directory already exists but is empty. The implementation now allows `copytree()` to populate an existing empty destination, and the test suite includes a regression test for that exact case.

**Why it matters:** The Sprint 6 contract said the command should refuse non-empty destinations unless `--force` is passed. An already-created empty destination is a normal and safe setup, but the previous implementation failed there unexpectedly. This bugfix makes the export workflow match the intended contract.

**How to Verify**

```bash
.venv/bin/python -m pytest tests/test_doctor.py -q
.venv/bin/python -m pytest -q
```

---

## 2026-03-08 - Sprint 6 Complete: Vendored Source Snapshot Workflow

**What was built:** Added `lee-llm-router export-source --dest <path> [--force]` to export the full `src/lee_llm_router/` package tree as a vendorable snapshot. The export writes `.lee_llm_router_export.json` with version, source repo, source commit, and export timestamp. Added overwrite protection for non-empty destinations unless `--force` is provided. Updated README/product/sprint docs to shift downstream adoption toward explicit vendored snapshots instead of requiring a live runtime dependency on this package.

**Why it matters:** Downstream repos can now take intentional, pinned router snapshots without paying the reliability cost of package fetches, SSH auth, or environment-specific install drift. This keeps `lee-llm-router` as the upstream improvement lane while giving consumers local ownership of the runtime code they ship.

**How to Verify**

```bash
PYTHONPATH=src python -m pytest tests/test_doctor.py -q
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml
PYTHONPATH=src python -m lee_llm_router.doctor export-source --dest <temp-dir>
```

---
## 2026-03-02 â€” OpenAI Codex Subscription Provider (ChatGPT Subscription Auth)

**What was built:** Added `OpenAICodexSubscriptionHTTPProvider` with registry type `openai_codex_subscription_http` (aliases: `openai_codex_http`, `chatgpt_subscription_http`). The provider calls ChatGPT backend Codex Responses API, enforces `store: false`, and converts responses payloads into `LLMResponse`. Credential discovery mirrors OpenClaw patterns: `access_token_env` first, then macOS keychain (`Codex Auth`), then `CODEX_HOME/auth.json` / `~/.codex/auth.json`. Added doctor checks for this provider type and updated docs/template examples.

**Why it matters:** Projects can route through OpenAI ChatGPT subscription credentials directly from `lee-llm-router` without forcing usage-based OpenAI API keys. This enables the same Codex-subscription connectivity pattern used in OpenClaw while preserving router telemetry/fallback behavior.

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/providers/openai_codex_subscription.py` | New subscription-backed HTTP provider with env/keychain/auth.json credential resolution |
| `src/lee_llm_router/providers/registry.py` | Built-in registration + aliases |
| `src/lee_llm_router/doctor.py` | Provider validation for subscription auth config |
| `tests/test_providers.py` | Provider success + auth file + missing credential coverage |
| `tests/test_doctor.py` | Alias + token env validation coverage |
| `src/lee_llm_router/templates/llm.example.yaml` | New provider example stanza |
| `docs/config.md` | Provider type + key schema docs |
| `docs/providers.md` | Adapter behavior and failure mapping docs |
| `README.md` | Provider matrix and architecture list updated |

**How to Verify**

```bash
.venv/bin/pytest -q
.venv/bin/pytest -q tests/test_providers.py tests/test_doctor.py
.venv/bin/lee-llm-router doctor --config tests/fixtures/llm_test.yaml
```

---

## 2026-02-18 â€” Sprint 6 Prep: Provider Aliases, Policy Overrides, Trace Integrity

**What was built:** Added `openai_http` as a first-class alias in the provider registry plus doctor + router tests; policies can now override request attributes via `ProviderChoice.request_overrides` (without colliding with provider config overrides), and per-call kwargs now win over policy defaults. Trace attempts are persisted individually (`<request>-<attempt>-<provider>.json`), fallback runs write one file per attempt, and `lee-llm-router trace --last` shows attempt metadata.

**Why it matters:** Configs copied from OpenAI examples work without edits, cost-aware policies can enforce cheaper models reliably, and trace archives finally capture every failure/success along a fallback chainâ€”making the new `trace --last` output actionable during incident review.

**How to Verify**

```bash
pip install -e ".[dev]"            # ensures httpx is available
pytest tests/test_doctor.py \
       tests/test_router.py \
       tests/test_async.py -k "policy or alias or trace"
lee-llm-router doctor --config tests/fixtures/llm_test.yaml
```

---

## 2026-02-18 â€” Repository Guidelines Refresh

**What was built:** Replaced the sprawling agent instructions with a 384-word `AGENTS.md` titled â€œRepository Guidelines.â€ The document now covers structure, commands, style, testing, PR etiquette, and security tips with concise bullets and concrete examples (`pip install -e ".[dev]"`, `lee-llm-router doctor --config ...`).

**Why it matters:** Contributors now have a single reference that matches the current repo state (async providers, 54 tests, doc layout). Short guidance reduces onboarding time and prevents divergence from the established workflow documents.

**How to Verify**

```bash
wc -w AGENTS.md         # â†’ 384 (within 200â€“400 target)
cat AGENTS.md           # confirm sections + commands listed in spec
```

---

## 2026-02-18 â€” Sprint 5: Async, Fallbacks, Extended Telemetry â€” P2 Complete

**What was built:** Full async support via `httpx` (`complete_async()` in `OpenRouterHTTPProvider` and `LLMRouter`), provider fallback chain with `policy.fallback` telemetry events, token accounting hook (`on_token_usage` callback), `EventSink` protocol for external event consumption, and `lee-llm-router trace --last N` CLI subcommand. Added `complete_async` to `MockProvider` for testability.

**Why it matters:** Consumers can now use `await router.complete_async()` for non-blocking I/O. The fallback chain provides resilience â€” if a primary provider fails (rate limit, timeout), the router automatically tries configured fallbacks. Token accounting enables budget tracking. `EventSink` allows integration with external telemetry systems (LeeClaw/Meridian session logs).

**Key design choices:**
- `complete_async()` in router checks `hasattr(provider, "complete_async")` and calls natively; falls back to `asyncio.to_thread()` for sync-only providers â€” no breaking changes to existing providers
- Fallback chain respects `should_retry()` â€” `CONTRACT_VIOLATION` never retries, preserving the Phase 0 guarantee
- Token hook and EventSink exceptions are swallowed (with `try/except: pass`) â€” buggy callbacks can't break requests
- Trace CLI reads from the same directory structure used by `LocalFileTraceStore` â€” no config duplication

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/providers/http.py` | Replaced `requests` with `httpx`; added `complete_async()` native async method |
| `src/lee_llm_router/providers/mock.py` | Added `complete_async()` for test parity with HTTP provider |
| `src/lee_llm_router/router.py` | Added `complete_async()` with fallback chain; wired `on_token_usage` hook and `EventSink` |
| `src/lee_llm_router/telemetry.py` | Added `EventSink` Protocol, `RouterEvent` dataclass |
| `src/lee_llm_router/doctor.py` | Added `trace --last N --dir` subcommand |
| `tests/test_async.py` | 16 tests covering async, fallback, hooks, EventSink, trace CLI |

**How to Verify**

```bash
.venv/bin/pytest -v                          # â†’ 54 passed
.venv/bin/pytest tests/test_async.py -v      # â†’ 16 passed (Sprint 5)

# Async works
.venv/bin/python -c "
import asyncio
from lee_llm_router import LLMRouter, load_config
from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig

cfg = LLMConfig(
    default_role='test',
    providers={'mock': ProviderConfig(name='mock', type='mock', raw={})},
    roles={'test': RoleConfig(name='test', provider='mock', model='m')}
)
router = LLMRouter(cfg)
resp = asyncio.run(router.complete_async('test', [{'role': 'user', 'content': 'hi'}]))
print('Async OK:', resp.text)
"

# Trace CLI works
.venv/bin/lee-llm-router trace --last 5
```

---

## 2026-02-18 â€” Sprint 4: Doctor CLI, Abstractions, Docs, PyPI â€” P1 Complete

**What was built:** Full doctor CLI (`doctor` + `template` subcommands), `RoutingPolicy` protocol + `SimpleRoutingPolicy` default with `policy.choice` telemetry logging, `TraceStore` protocol + `LocalFileTraceStore`, complete README + `docs/config.md` + `docs/providers.md`, PyPI-ready packaging (`python -m build` â†’ `.whl` + `.tar.gz`). Product-definition acceptance checklist is 100% checked off.

**Why it matters:** Adopters can now `pip install lee-llm-router`, run `lee-llm-router doctor --config llm.yaml` to verify setup, inject custom routing policies and trace sinks, and read reference docs without touching source code. The package is distributable.

**Key design choices:**
- `policy.py` is a new file (not bolted onto `router.py`) â€” keeping the abstraction boundary clean
- `TraceStore` owns file writing; `record_success`/`record_error` now log-only â€” separation of concerns
- `doctor.check_config()` is a pure function returning `(errors, warnings)` â€” testable without subprocess
- `main()` accepts `argv` list for direct invocation in tests â€” no subprocess overhead

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/policy.py` | `RoutingPolicy` Protocol, `ProviderChoice`, `SimpleRoutingPolicy` |
| `src/lee_llm_router/telemetry.py` | `TraceStore` Protocol + `LocalFileTraceStore`; logging separated from file I/O |
| `src/lee_llm_router/router.py` | Policy + TraceStore wired in; `policy.choice` event logged |
| `src/lee_llm_router/doctor.py` | Full CLI: `doctor` + `template` subcommands |
| `src/lee_llm_router/__init__.py` | Phase 1 names exported |
| `pyproject.toml` | PyPI-ready: keywords, classifiers, package-data, urls |
| `README.md` | Full API + CLI + architecture docs |
| `docs/config.md` | Config schema reference |
| `docs/providers.md` | Provider adapter + failure type reference |
| `product-definition.md` | All acceptance items checked `[x]` |
| `tests/test_doctor.py` | 7 doctor + CLI tests |
| `dist/` | `.whl` + `.tar.gz` artifacts |

**How to Verify**

```bash
.venv/bin/pytest -v                                                    # â†’ 38 passed
.venv/bin/lee-llm-router doctor --config tests/fixtures/llm_test.yaml # â†’ exit 0
.venv/bin/lee-llm-router template | head -3                            # â†’ YAML output
ls dist/                                                               # â†’ .whl + .tar.gz
```

---

## 2026-02-18 â€” Sprint 3: Config, Router, Telemetry â€” P0 Complete

**What was built:** Full end-to-end stack â€” YAML config loader, `LLMRouter` facade, `LLMClient` legacy wrapper, structured telemetry with JSON trace files, pass-through compression stub. `from lee_llm_router import LLMRouter, LLMClient, load_config, LLMRequest, LLMResponse` now works. **P0 extraction is complete.**

**Why it matters:** Any downstream consumer (Meridian, LeeClaw, future projects) can now install `lee-llm-router`, point it at a config YAML, and call `LLMRouter.complete()` with the same interface they already use. Trace files are written automatically on every call.

**Key design choices:**
- `trace_dir` param on `LLMRouter.__init__` keeps tests hermetic (no filesystem side-effects)
- Router wraps all bare `Exception` in `LLMRouterError(FailureType.UNKNOWN)` so callers always get a typed error
- `LLMClient` is a one-liner wrapper â€” callers migrating from LeeClaw change only their import
- `ConfigError(ValueError)` is separate from `LLMRouterError` so config mistakes are distinguishable from runtime failures

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/config.py` | `load_config()`, `LLMConfig`, `ProviderConfig`, `RoleConfig`, `ConfigError` |
| `src/lee_llm_router/router.py` | `LLMRouter.complete()` â€” full flow with telemetry |
| `src/lee_llm_router/client.py` | `LLMClient` legacy wrapper |
| `src/lee_llm_router/telemetry.py` | `start_trace()`, `record_success()`, `record_error()`, `_write_trace()` |
| `src/lee_llm_router/compression.py` | Pass-through stub |
| `src/lee_llm_router/templates/llm.example.yaml` | Fully annotated example config |
| `src/lee_llm_router/__init__.py` | All Phase 0 public names exported |
| `tests/fixtures/llm_test.yaml` | Minimal test config (MockProvider) |
| `tests/test_config.py` | 6 config loader tests |
| `tests/test_router.py` | 8 end-to-end router + client tests |

**How to Verify**

```bash
.venv/bin/python -c "from lee_llm_router import LLMRouter, LLMClient, load_config, LLMRequest, LLMResponse; print('OK')"
.venv/bin/pytest -v   # â†’ 31 passed
```

---

## 2026-02-18 â€” Sprint 2: Provider Layer (P0)

**What was built:** Fully implemented the provider layer â€” `LLMRequest`/`LLMResponse` dataclasses, `FailureType` enum, `LLMRouterError`, `Provider` Protocol, `should_retry()` helper, and all four adapters (`MockProvider`, `OpenRouterHTTPProvider`, `CodexCLIProvider`, built-in registry). 13 unit tests; no real HTTP or subprocess calls in any test.

**Why it matters:** The provider layer is the core abstraction of the router. Sprint 3 (config + router) sits on top of it â€” all provider calls go through these interfaces. `MockProvider` is the test backbone for every future sprint.

**Key design choices (Phase 0 â€” no new abstractions):**
- `should_retry(error)` encodes the "never retry CONTRACT_VIOLATION" rule without touching the router
- `registry._register_builtins()` auto-registers on import so callers never need to wire providers manually
- HTTP and CLI providers map all native errors into `LLMRouterError` + `FailureType` so the router has a single exception type to handle

**Created / Modified**

| File | Purpose |
|------|---------|
| `src/lee_llm_router/response.py` | `LLMRequest`, `LLMResponse`, `LLMUsage` dataclasses |
| `src/lee_llm_router/providers/base.py` | `FailureType`, `LLMRouterError`, `should_retry()`, `Provider` Protocol |
| `src/lee_llm_router/providers/mock.py` | Deterministic echo provider |
| `src/lee_llm_router/providers/http.py` | OpenRouter/OpenAI REST adapter (requests) |
| `src/lee_llm_router/providers/codex_cli.py` | Subprocess adapter |
| `src/lee_llm_router/providers/registry.py` | `register()`, `get()`, `available()`, auto built-in registration |
| `src/lee_llm_router/__init__.py` | Exports `LLMRequest`, `LLMResponse`, `LLMUsage`, `LLMRouterError`, `FailureType` |
| `tests/test_providers.py` | 13 unit tests |

**How to Verify**

```bash
.venv/bin/pytest tests/test_providers.py -v   # â†’ 13 passed
.venv/bin/pytest -v                            # â†’ 17 passed (all)
```

---

## 2026-02-18 â€” Sprint 1: Package Setup (P0)

**What was built:** Renamed the broken scaffold (`src/Lee LLM Router/` with space) to a properly importable Python package (`src/lee_llm_router/`). Fixed `pyproject.toml` (name, runtime deps, entry point). Created the full module skeleton matching `design.md`. Created `.venv` and `tests/`. Sprint plan and context.md created today as well.

**Why it matters:** Nothing in Sprint 2+ can work without an importable package. The skeleton establishes the exact file tree that LeeClaw modules will be ported into â€” no structural decisions needed later.

**Created**

| File/Dir | Purpose |
|----------|---------|
| `src/lee_llm_router/__init__.py` | Package root, `__version__ = "0.1.0"` |
| `src/lee_llm_router/config.py` | Stub (Sprint 3) |
| `src/lee_llm_router/router.py` | Stub (Sprint 3) |
| `src/lee_llm_router/client.py` | Stub (Sprint 3) |
| `src/lee_llm_router/response.py` | Stub (Sprint 2) |
| `src/lee_llm_router/compression.py` | Stub (Sprint 3) |
| `src/lee_llm_router/telemetry.py` | Stub (Sprint 3) |
| `src/lee_llm_router/doctor.py` | Stub `main()` (Sprint 4) |
| `src/lee_llm_router/providers/` | All 5 provider stubs (Sprint 2) |
| `src/lee_llm_router/templates/llm.example.yaml` | Placeholder (Sprint 4) |
| `tests/__init__.py`, `conftest.py`, `test_smoke.py` | 4 smoke tests |
| `pyproject.toml` | Fixed: `lee-llm-router`, pyyaml + requests deps, entry point |
| `.venv/` | Python 3.13 virtualenv for the project |
| `sprint-plan.md` | 5-sprint plan across 3 phases |

**How to Verify**

```bash
source .venv/bin/activate
python -c "import lee_llm_router; print(lee_llm_router.__version__)"  # â†’ 0.1.0
pytest tests/test_smoke.py -v   # â†’ 4 passed
```

---

## 2026-02-17 â€” Project Scaffolded

**Project initialized** with init-agent.

### Created

| File | Purpose |
|------|---------|
| `AGENTS.md` | AI agent guide and conventions |
| `WHERE_AM_I.md` | Quick orientation for agents |
| `feedback.md` | Human feedback capture |
| `README.md` | Project documentation |
| `context.md` | Session working memory |
| `result-review.md` | This file - running log |
| `sprint-plan.md` | Sprint tracking |

### How to Verify

1. Check all files exist: `ls *.md`
2. Read AGENTS.md to understand project conventions
3. Check context.md for current state

---

*Add new entries above this line. Keep the newest work at the top.*
