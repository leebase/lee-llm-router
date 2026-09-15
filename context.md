# Lee LLM Router Session Context

> **Purpose**: Working memory for session continuity. If power drops, a new AI takes over, or we return after a break - read this first.

---

## Snapshot

| Attribute | Value |
|-----------|-------|
| **Phase** | Staffing multi-account plan (chief-of-staff `docs/staffing-multi-account-plan.md`) — M1, M2, M3, M4 (M4-1/M4-2) all committed; M5 (evidence report) next; live two-account smoke HELD |
| **Mode** | 2 (Implementation with approval) |
| **Last Updated** | 2026-09-14 |

### Sprint Status
| Sprint | Status | Completion |
|--------|--------|------------|
| Sprint 1 - Package Setup | Done | 100% |
| Sprint 2 - Provider Layer | Done | 100% |
| Sprint 3 - Config, Router, Telemetry | Done | 100% |
| Sprint 4 - Doctor CLI, Template, Docs, PyPI | Done | 100% |
| Sprint 5 - Async, Fallbacks, Extended Telemetry | Done | 100% |
| Sprint 6 - Vendored Source Snapshot Workflow | Done | 100% |
| Sprint 7 - Pi Coding Harness Reliability and Harness Validation | Done | 100% |
| Staffing slice - `.toml` / `.ini` class derivation | Done | 100% |
| Crew Resolver S1 - Crews as a routing policy (`docs/crew-resolver/sprint-plan.md`) | Done | 100% |
| Crew Resolver S2 - Availability snapshot and refresh script | Done | 100% |
| Crew Resolver S3 - resolve CLI, flex, bind, event ledger, dispatch watchdog | Done | 100% |
| Crew Resolver S4 - D188 role-scoped rule, resolve positionals, four harness shims | Done | 100% |
| Crew Resolver S5 - Crew page and proposals | Done | 100% |

---

## What's Happening Now

### Current Work Stream
Staffing multi-account plan (`/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
"channel instances — many subscriptions per provider, universally"), supervised
via `/supervise`. M1 (catalog + schema) was already committed before this
session. This session ran M2 ("headroom per instance"), split cross-repo:

- **M2a** (`chief-of-staff` repo, `scripts/ai-subs.sh` +
  `scripts/ai_subs_instance_check.sh`, new): the TOML/snapshot rendering path
  now supports `[opencode.instances.<id>]` sub-tables, emitting a new
  `"instance"` JSON field on every `AFTER_REPORT_JSON` `subscriptions` entry
  (a real id, the literal `"opencode-go"` implicit default, or `null` for
  every non-OpenCode-Go entry and for the unchanged live-fetch path — live
  per-instance fetching against the real second account was deliberately left
  out of scope, deferred to M4, to honor the plan's "M2 touches no account"
  constraint). Verified: attempt `router-run-6765290c76124befb46784befabc5c85`
  (agy/gemini-3.8-flash-high), oracle `scripts/ai_subs_instance_check.sh`
  passed, supervisor re-ran it directly and confirmed exit 0. Independent
  review `router-run-3a2e81fb4d96482b91fb177b6d197fcb` (pi/deepseek-v4-flash):
  **ACCEPT**.
- **M2b** (`lee-llm-router` repo, `src/lee_llm_router/availability.py` +
  `tests/test_availability.py` + `tests/test_refresh_availability.py`;
  `scripts/refresh_availability.sh` deliberately left unchanged — confirmed
  pass-through of unknown JSON keys): `Bucket`/`ChannelHeadroom` gained an
  additive `instance: str | None = None` field; new
  `AvailabilitySnapshot.instance_headroom(channel, instance)` and
  `to_dict()["instances"]` expose per-(channel, instance) headroom via a new
  `_instances_from_buckets()`; the existing channel-wide `headroom(channel)`
  aggregate is provably unchanged (byte-identical against the `LIVE_SAMPLE`
  fixture). The original single M2b packet stalled (10 min silence, killed by
  the router) on `agy-gemini-3-8-flash-high-gemini-sub`; repaired by halving
  into M2b1 (availability.py core) + M2b2 (refresh_availability.sh
  pass-through test), both of which then hit a ceiling timeout on the same
  repair attempt and were escalated one ladder rung to
  `pi-deepseek-deepseek-v4-flash-openrouter`, where both passed. Verified:
  `router-run-ff3ca2dcd4094c71a366d07d28c13efa` (M2b1) and
  `router-run-aed23e4764ca42a7a2907cc6c402c16b` (M2b2); supervisor re-ran the
  oracle (`pytest tests/test_availability.py tests/test_refresh_availability.py
  -q` → 167 passed; full suite → 1856 passed, 6 skipped) and Black/Ruff
  directly. Independent review `router-run-778ed468b1ab48058fe667951c9312df`
  (agy/gemini-3.8-flash-high, author excluded for independence): **ACCEPT**.

M2 does not wire the D216 reserve check or route selection to instances —
that was M3 ("selection"), completed and committed in a later session in
three packets: **M3-1** (`eligibility.py`: per-instance D216 reserve/health
veto — a route is eligible when any enabled instance clears; an instance
with no tagged availability record inherits the channel-level record per
the plan's M3 ruling 2; commit `34c13c0`, combined with S8), **M3-2**
(`block.py`: `staff auto` exposes `selected_instance` — the first eligible
entry of the selected route's `instance_headrooms` — plus per-candidate-row
`instance_headrooms` in `staff --json`; commit `778d538`), and **M3-3**
(`run.py`/`doctor.py`: `run --instance <id>` pins a channel instance the way
`--route` pins a route, failing closed (exit 3, nothing launched) on an
unknown/disabled/ineligible instance or one given for a channel with no
instance concept; without `--instance`, `run` resolves the same
first-eligible-instance rule `staff` used, so a supervisor dispatching with
`staff`'s chosen `--route` gets `staff`'s chosen instance for free;
`build_attempt_record()`'s `route` dict gained the additive
`route.channel_instance` key from M1's schema field; commit `65e7259`). Each
packet had its own independent review (ACCEPT, 0 findings) and full-suite
verification (1896 passed, 6 skipped as of M3-3). Packet/review evidence:
`docs/staffing/packets/M3-1*.md`, `docs/staffing/packets/M3-2*.md`,
`docs/staffing/packets/M3-3*.md`.

M4 ("credential staging at dispatch") is now complete and committed, in two
packets: **M4-1** (`src/lee_llm_router/staffing/credentials.py`, new module:
resolves a channel instance's `credential_ref` and stages a fresh temporary
per-run harness home containing only that credential, for `opencode`/`pi`
only — `omp`'s real auth store turned out to be a SQLite-backed
`omp auth-broker` vault, not a static file, contradicting the plan's
assumption, so it is deliberately unsupported pending a ruling rather than
improvised; commit `dca7f70`) and **M4-2** (`run.py`/`doctor.py` wiring:
`run` stages the selected instance's credential before launch and fails
closed, exit 3, nothing registered or launched, on a missing/malformed
credential, a path-traversal `credential_ref`, or an unsupported harness;
commit `01e2722`). M4-2 took three independent-review rounds (REJECT →
REJECT → PASS) before landing — the first round caught a real defect the
supervisor confirmed against the real `~/.local/share/opencode/auth.json`
and `~/.pi/agent/auth.json` files on this machine (staged credentials
weren't nested under the channel's provider key at all). Full attempt-id
chain and finding text: `result-review.md` (2026-09-14, "M4: credential
staging at dispatch" entry). The live two-account smoke stays explicitly
**HELD** pending Lee's confirmation of OpenCode's terms — nothing in M4
touched a real account. **Next: M5** (evidence report grouped by
route+instance, 20 min bound per the plan). All M2 changes remain verified
but left **uncommitted** in both repos (a separate Lee decision, same
convention M1 and the prior acceptance run used) — M3 and M4 diverged from
that convention and were committed directly after each packet's independent
review passed with 0 findings, matching the git-log precedent set by the
M1 and earlier M3-1/S8 commits. Packet, review, and class-derivation
evidence: `docs/staffing/packets/M2a-*.md`, `docs/staffing/packets/M2b*.md`,
`docs/staffing/packets/M4-*.md`, `tmp/staffing-m2/`, `tmp/staffing-m4/`.

### Prior Work Stream
`/supervise` (plan `plans/supervise-acceptance-2026-09-13.md`) ran its first
full acceptance case end-to-end: `render_evidence_report` in
`src/lee_llm_router/staffing/evidence_report.py` now splits routed groups
(printed first, under `Classes (N groups):`, N = routed count only) from
unrouted legacy groups (printed after, under a new
`Unrouted legacy groups (M groups, no router route recorded):` heading);
`build_evidence_report`'s JSON `classes` output is untouched. One same-route
repair (killed by its own ceiling) plus two ladder escalations were needed to
get both owned files Black-clean; the deterministic oracle (pytest + black +
ruff) and an independent review (0 findings, ACCEPT) both passed under direct
supervisor re-verification. Full details and every attempt id are in
`result-review.md` (2026-09-13 entry). The change is verified but left
**uncommitted** — committing is a separate Lee decision. Working tree also has
several unrelated untracked scratch/doc files from other in-flight sessions
(`docs/staffing/chief-answers-*.md`, `docs/staffing/logs/`, `tmp/`,
`.agent-orch-scratch/`, `.omp/`) that this run did not touch and left alone.

### Prior Work Stream
The staffing class-derivation slice for `.toml` and `.ini` is complete. Both
extensions now resolve to the existing `yaml-config` class, homogeneous config
sets remain `yaml-config`, and config-plus-code sets resolve to `mixed`. The
closed eight-value language taxonomy and independent domain-tag behavior remain
unchanged. Independent review returned **PASS** with zero findings at every
severity. No repair work remains for this slice.

The authoritative preserved checks all passed: test-module compilation; two
focused pytest validations; Black and Ruff on the implementation and tests; and
bytecode compilation of both files. These are Agent-Orch records and were not
rerun during closeout.

### Prior Work Stream (older)
Crew-aware worker resolver lane (D187). Sprint 5 is complete and reviewed: `crews page --out` projects the live crew roster, availability, and optional benchmark evidence into self-contained responsive HTML; missing benchmark and availability inputs degrade safely; present malformed inputs fail closed; and proposals remain advisory and empty until authoritative tier/vendor-independence metadata exists. Luna XHigh via Pi handled three implementation packets and four repair packets. Sonnet 5 High passed on round 4 after three reproduced High findings were repaired; Opus 5 High final gate passed with no findings. 601 tests pass. Publication/navigation/hourly regeneration remain Lee-gated in `docs/crew-resolver/needs-lee.md`. Do not begin Sprint 6 without a new instruction.

Prior stream:
Sprint 7 is complete. The pi coding harness path now has a repo-local reproduction fixture, stricter CLI harness contract handling, explicit `doctor` validation, regression coverage, and a user-style verification path. No downstream migration work is executed from this repo now; downstream projects are handled separately.

### Recently Completed
- Closed the `.toml` / `.ini` staffing class-derivation slice after an independent PASS with zero findings
- Preserved the existing `yaml-config` taxonomy while covering homogeneous config and mixed code/config inputs
- Swept the public docs and coder guide so the shipped Sprint 7 pi harness behavior is documented consistently
- Clarified that `default_role` must reference an existing role and that `model_flag` / `output_flag` can be set to `null` to disable default CLI flags
- Added a pi-style subprocess harness example plus updated `doctor` behavior notes in `docs/llm-coder-guide.md`
- Fixed the Sprint 7 review findings around pi harness flag handling and malformed JSON usage typing
- `codex_cli` now allows `model_flag: null` for wrappers that do not accept the default Codex CLI flags
- Invalid JSON `usage` fields from pi-style harnesses now raise typed `CONTRACT_VIOLATION` errors instead of falling through as `UNKNOWN`
- Added regression coverage for strict wrapper invocation without default flags and router-level malformed usage handling
- Added a repo-local simulated pi harness fixture at `tests/fixtures/pi_harness.py`
- Hardened `codex_cli` with fixed `args`, optional `response_format: json`, JSON text extraction, usage passthrough, and typed `CONTRACT_VIOLATION` failures for malformed harness output
- Improved non-zero exit diagnostics for CLI harness failures and preserved command metadata in raw responses
- Tightened config validation for unknown `default_role` and fallback providers
- Updated `doctor` to validate the configured provider and role wiring instead of a mock-only dry-run path
- Added focused pi harness tests for success, malformed JSON, missing text, timeout, non-zero exit, doctor validation, and router traceability
- Updated README, provider docs, config docs, and the example template with pi harness contract guidance
- Fixed `lee-llm-router export-source` so a pre-created empty destination directory now exports successfully
- Added a regression test covering export into an existing empty destination
- Validation complete:
  - `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_providers.py tests/test_router.py tests/test_doctor.py -q` -> `56 passed`
  - `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest tests/test_config.py tests/test_providers.py tests/test_router.py tests/test_doctor.py -q` -> `60 passed`
  - `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m pytest -q` -> `85 passed`
  - Test As Lee: `PYTHONPATH=src /Users/lee/projects/lee-llm-router/.venv/bin/python -m lee_llm_router.doctor doctor --config tests/fixtures/llm_test.yaml`
  - Test As Lee: temp pi harness config + `LLMRouter.complete("pi_local", ...)` -> `{"text":"pi json harness: ship sprint 7","provider":"codex_cli","model":"pi-harness-o3"}`

### Parallel Deferred Work
- **Crew Resolver Sprint 6 — ⏳ BLOCKED / EVIDENCE ACCUMULATING.** Engineering health: GREEN. Adoption conclusion: NOT YET MEASURABLE. Lee explicitly retained the genuine 14-day daily-use requirement; earliest meaningful resumption is approximately 2026-09-22. Normal use should generate the evidence naturally; do not manufacture `/crew` usage. Sparse natural use is itself adoption evidence. See `docs/crew-resolver/execution-log.md`.

---

## Decisions Locked

| Decision | Rationale | Date |
|----------|-----------|------|
| TinyClaw methodology | Build from scratch with small primitives; validate before scale | 2026-02-17 |
| httpx over requests | Native async support, modern HTTP client | 2026-02-18 |
| Add Codex subscription HTTP provider | Enable ChatGPT subscription routing without requiring API-key billing | 2026-03-02 |
| Downstream repos should treat `lee-llm-router` as an upstream improvement lane, not a required live runtime dependency | Preserves shared evolution while reducing install/auth/reproducibility friction in consumers | 2026-03-08 |
| Treat existing empty export destinations as valid `export-source` targets, and reserve `--force` for replacing non-empty destinations | Matches the Sprint 6 intended contract and avoids surprising failures for pre-created directories | 2026-03-29 |
| Pi coding harness reliability must be proven in this repo before downstream apps rely on it again | A downstream app already failed on this path, so reproduction, validation, and regression coverage are now first-class product work | 2026-03-29 |
| Pi-style subprocess harnesses should use a structured JSON envelope when reliability matters | Contract failures become deterministic `CONTRACT_VIOLATION`s instead of ambiguous free-form subprocess output errors | 2026-03-29 |

---

## Open Questions (keep short)

1. Should a follow-on sprint add an optional doctor smoke-execution mode for CLI harness roles?
2. Does broader harness-aware planning still belong in a follow-on sprint now that the pi path is stable?

---

## Next Actions Queue (ranked)

| Rank | Action | Owner | Done When |
|------|--------|-------|----------|
| 1 | Lee: publish `crews.html`, add the nav entry, and attach fail-closed hourly regeneration if desired | Lee | Public page is readable and regenerates only after a successful availability refresh |
| 2 | Crew Resolver Sprint 6: hardening/adoption evidence | Supervisor | Two-week resolver-use report and Auto-Orch adoption recommendation are complete |
| 3 | Decide the authoritative tier/vendor-independence metadata source before enabling proposals | Lee + Benchmark/Auto-Orch owners | Proposal predicates can be proven without local invention |

---

## Working Conventions

### Start of session
1. Read `AGENTS.md`
2. Read `context.md`
3. Read `result-review.md`
4. Read `product-definition.md`
5. Read `sprint-plan.md`
6. Execute the top-ranked item unless explicitly redirected by the user

### End of work unit
1. Move completed work into "Recently Completed"
2. Update "Next Actions Queue"
3. Add any new locked decisions
4. Keep "Open Questions" <= 5

---

## Environment Notes

- **Working Directory**: `C:\Users\leeba\projects\lee-llm-router`
- **Project Name**: Lee LLM Router
- **Profile**: Python package plus vendorable source export reference
- **Primary validation**: `PYTHONPATH=src python -m pytest -q`

---

## Crew Resolver Sprint 5 — governing contracts (supervisor working context)

These contracts are quoted verbatim in every Sprint 5 packet and review prompt that depends on them.

### S5-C1 — Page command and failure behavior

`lee-llm-router crews page --out <path> [--crews-file <path>] [--availability-file <path>] [--benchmark-file <path>] [--events-file <path>]` writes one self-contained HTML file with inline CSS and no external assets. The page supports light and dark color schemes through `prefers-color-scheme` and is readable without horizontal overflow at 390 CSS pixels. Success exits 0. Invalid crews, availability, benchmark, or event input exits 3 with one concise configuration error. A missing benchmark sidecar is not an error: generation succeeds and the page states `No benchmark evidence yet.` The command never edits `crews.yaml`, never writes the router event ledger, and never calls a provider CLI.

### S5-C2 — Required projection

The page projects all crews and stages from the selected crews file in declared order. Every crew card shows crew name, purpose, and each stage with its ordered worker roster. Every worker shows its channel headroom state (`healthy`, `degraded`, `likely_exhausted`, `exhausted`, or `unknown`), the availability observation time, and whether that observation is stale. When matching benchmark evidence exists, the worker shows best score, cost-to-accept, run count, task count, and the literal label `one task` when task count is exactly one; unavailable measurements are displayed as unknown, never as zero. A role-scoped worker placed on a coding stage is marked `planning/review only`. Human-facing prose outside the evidence appendix contains no source-system names, file paths, or run ids. Run ids may appear only in an appendix.

### S5-C3 — Benchmark matching and proposals

The optional benchmark input is schema `benchmark.staffing-evidence/2`. Evidence matches a crew worker only through an explicit, deterministic identity mapping from the crew worker's provider/model/effort/harness identity to a sidecar `worker_key`; display names are never matching keys. A proposal names a current assignment and a candidate only when both have evidence for the same resolver role and the same benchmark `task_key`, the candidate has at least one accepted run, and the candidate does not cross the current assignment's model tier or vendor-independence boundary. A candidate that is never automatic, or role-scoped on a coding stage, is never proposed. Proposal ordering is deterministic. Proposals are text only; generation never edits `crews.yaml`. If the evidence cannot prove every predicate, no proposal is emitted for that comparison.

### S5-C4 — Publication and refresh boundary

The repository implementation can generate an exact candidate for `~/projects/webroot/docs/pages/crews.html`, an exact navigation diff following the existing docs index convention, and an exact hourly-regeneration command that follows a successful availability refresh. Sprint 5 does not publish into webroot, edit webroot navigation, or install/change Lee's live cron without Lee's separate execution decision. A refresh integration must fail closed: a failed availability refresh cannot regenerate a page from a stale or partial newly-written snapshot, and page-generation failure must make the refresh command fail rather than silently preserve a misleading success status.

### S5-C5 — Performance and compatibility

The existing `resolve` behavior and output remain unchanged, and the median of five cold `resolve` runs against the live inputs stays below 50 ms. `crews page` has no latency gate, but its observed wall time is recorded. The full authoritative suite, Black on `src/`, Ruff on `src/`, and `doctor --crews --availability` must pass after every accepted packet.

## Staffing Migration Phase 0 — completed 2026-09-10

Catalog/data/schema/loader/explain, priced cheap routes, Pi crew dispatch, benchmark class/token evidence, and the attempt-record contract are implemented and committed across four repos. Final gates: router 814 passed + Black/Ruff clean; agent-orch 1872 passed / 9 skipped + 20 rate tests; auto-orch 1465 passed / 2 skipped + additive crew diff + preflights; benchmark 268 passed with only an authorized OpenCode 1.18.30 vs required 1.18.26 pin mismatch, staffing 21/63 and v5/v6 parity 86/4. Final Astra Low gate: PASS with no High or Medium findings.

Next action is Phase 1's first packet — display the effective channel tier in `catalog explain` — but do not begin it. Open follow-ups remain in `docs/staffing/needs-lee.md`; no Phase 0 blocker.

*This file is a living document - update it frequently.*
