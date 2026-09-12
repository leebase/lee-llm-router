# Gate Review Packet — Phase 4 (Staffing Migration), D215 ruling 5

Independent, read-only gate review. Author routes across the phase: mixed (see
`docs/staffing/phase4-execution-log.md` for per-packet routes). This review is the
independent check before Chief seals D217.

## Scope: every commit in three repos

**`lee-llm-router`** (this repo), in order:
`0d8ca17` (price command), `20d5176` (crew reorder + ordering rule), `19ee902` (subscription
reserve D216), `a92d3a1` (docs), `fee397c` (D218 DeepSeek V4.1 Flash intake), `5459831` (.json
owned-path mapping), `c9e29f3` (docs), `7e1e249` (supervise dispatch pattern), `ed71aa7`
(persist worker output, parse judge verdicts), `026fd54` (docs), `1d9055e` (.toml/.ini
owned-path mapping — the P4-8 live-proof backlog item), `58333b1` (docs).

**`agent-orch`**, in order:
`af5dea5` (platform_timeout failure class + verification tier), `39a0457`
(cost_usd_marginal via price), `7751a07` (ESCALATE policy decision — gate item (a)), `870700f`
(D218 intake), `7296c38` (escalation: YAML parsing, found+fixed during P4-8).

**`auto-orch`**, in order:
`74d6fe3` (P4-6, auto crew via staff), `92d3800` (P4-7, task_type + performance rollup),
`d6fcb66` (auto crew's staff dispatch never reached the router — found+fixed during P4-8),
`68a2297` (resolve auto crew's route model via price — found+fixed during P4-8).

Read `docs/staffing/phase4-execution-log.md` in full first (all of "Group A", "Group A2",
"D218 DeepSeek V4.1 Flash intake", "Group B", and "Group C") — it is the narrative record of
every packet's attempts, defects found, and remediations, and tells you what to verify rather
than re-discover from a cold diff read alone.

## The gate you are checking (D215 ruling 5)

(a) a deterministic agent-orch test proves `ESCALATE` re-runs a step on the next rung from a
`capability_rejected` judgment;
(b) one live governed Auto-Orch cycle under an `auto` crew on a real small backlog item,
every attempt priced at list and marginal, the block in the playbook, all rows in the ledger;
an escalation in the live run is evidence if it occurs, not a requirement;
(c) `auto-orch`, `agent-orch`, and `router` suites green;
(d) this review, 0 blocking;
(e) closing report.

Supervisor's own claims to verify independently, not trust blindly:
- Gate (a): `agent-orch/tests/test_engine.py -k escalate` — 2 passed.
- Gate (b): live cycle `auto-orch/missions/staffing-proof/cycle-reports/20260912T102251Z.yaml`
  — mandate resolved via router (`routing_authority.mandate` in that report shows
  `source: router_auto`, real harness/model per role), governed run
  `lee-llm-router-agent-orch-runs/ba56e712bfe2` has 8 real attempts each with
  `route-selection.json`/`usage.json` (list cost populated; marginal `"unavailable"`, P4-4's
  documented fail-open for this harness/model — not a new gap). The backlog item's actual code
  diff (`1d9055e`) landed and passed independent review despite the cycle's own `evaluate`
  stage recording `cycle_outcome: failed` — the execution log explains why (a downstream
  user-simulation-gate environment mismatch, not a defect in the diff) and asks you to confirm
  that root-cause claim yourself, not accept it on faith.
- Gate (c) (verify these counts by re-running, don't trust them from prose):
  - `lee-llm-router`: `.venv/bin/python -m pytest -q` — 1717 passed, 1 skipped.
  - `agent-orch`: `.venv/bin/python -m pytest -q` — 1937 passed, 9 skipped, 3 failed
    (`tests/test_codex_usage.py`, all three) — confirm these three are genuinely pre-existing
    and unrelated to any Phase 4 change (the execution log claims this was independently
    confirmed against unmodified `HEAD` back in Group A's own P4-3 packet; you do not need to
    re-derive that, but do confirm the three failing test names and failure shape match what
    the log describes, and that nothing else fails).
  - `auto-orch`: `.venv/bin/python -m pytest -q` — 1513 passed, 2 skipped, 1 failed
    (`tests/test_auto_orch_end_to_end.py::test_end_to_end_failed_run_increments_and_third_fire_halts`)
    — the log attributes this to another lane's uncommitted, in-progress WIP still present in
    this repo's working tree (`cycle.py`/`scheduling_policy.py`/`missions/linux-utilities`,
    `missions/snowflake-accelerator-revival`, none of it staged or touched by any Phase 4
    commit). Confirm this repo's working tree really does still carry that unrelated WIP
    (`git status --short`) and that none of the four auto-orch Phase 4 commits above touch
    `scheduling_policy.py` or any `missions/` path.

## What to actually check (not just re-run numbers)

1. **Correctness of the three mid-flight defect fixes** (`7296c38`, `d6fcb66`, `68a2297`):
   read each diff, confirm the stated defect was real (reproduce at least one yourself against
   the real CLIs — e.g. try `lee-llm-router staff --from-packet` with owned path `` `.` `` vs
   `` `unspecified-scope.py` ``), and confirm the fix is sound, not just plausible-sounding.
2. **The two recorded needs-lee/chief items** (route dispatch metadata ownership; the
   trusted-template user-simulation gate's bare-`python3` invocation) — confirm these are
   real, are genuinely not blocking Phase 4's own gate, and are recorded rather than silently
   dropped.
3. **D216 (subscription reserve) and D215 ruling 1/3** (crew reorder, ordering rule) — spot
   check `19ee902`/`20d5176` still hold under the current live availability snapshot (a live
   `staff --mode auto` or `explain` call should show the reserve excluding a channel at or
   below 10% headroom with the `D216` reason string).
4. **Never-invent-usage discipline** — spot check a couple of `usage.json`/attempt records
   referenced in the execution log actually carry the basis they claim (`provider_reported`,
   `unavailable`, etc.), not a fabricated number.
5. **Rule/authority discipline** — confirm no OpenAI metered route was used for any Phase 4
   staffing dispatch (subscription-channel `codex_cli`/`openai-sub` use inside the live
   governed cycle's own native worker dispatch is a different thing — that is auto-orch's own
   crew mechanism, not a router `run` dispatch, and is fine); confirm every `run` dispatch this
   phase used only proven or explicitly-reasoned routes.

## Report

Classify every finding as Contract-blocking / Non-blocking hardening / Future concern (D209).
Blocking findings must cite the violated requirement and a reproducer. End with
`REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`.
