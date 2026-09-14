# Packet M2a — `ai-subs.sh` per-instance OpenCode Go buckets (snapshot path only)

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
("channel instances — many subscriptions per provider, universally"), milestone M2
("headroom per instance"). Supervised via `/supervise`. This packet is the
`chief-of-staff` half of M2; the `lee-llm-router` half (`availability.py`,
`refresh_availability.sh` regression coverage) is packet M2b, dispatched after
this one lands and is verified, so M2b can be written against this packet's
*actual* emitted JSON shape rather than a guess.

## Scope decision (read before starting)

The plan's M2 status note says "everything else uses fake credentials and
touches no account" (only M4's live two-account smoke is held for Lee's
separate go-ahead). To honor that for M2 specifically, this packet touches
**only the TOML/snapshot rendering path** of `ai-subs.sh` (the `ai-subs.sh
<file.toml>` mode, which already exists precisely to test this script without
live credentials or network calls). The **live-fetch path** (`ai-subs.sh` with
no argument, which queries the real `opencode` CLI's `auth.json` and the real
zen usage API) is explicitly **out of scope and must not be touched**: leave
`fetch_opencode()` and its live-fetch call site exactly as they are today,
still single-instance. Wiring live per-instance discovery against the real
second account is deferred to a later milestone (M4, which is already gated on
Lee's confirmation). Do not read, glob, or reference any file under
`~/.local/state/lee-llm-router/credentials/` or `~/.local/share/opencode/` —
this packet has no reason to touch either path and must not.

## Packet fields

Kind: impl
Declared size: 2 files (1 changed, 1 new), approximately 120 changed/added lines
Owned paths: `scripts/ai-subs.sh`, `scripts/ai_subs_instance_check.sh` (new)
Oracle: `scripts/ai_subs_instance_check.sh` (a new deterministic, executable
check script you write — see below; no live credentials, no network)
Review: independent review required after the oracle passes

## Objective

`ai-subs.sh`'s TOML/snapshot rendering path currently emits exactly three
OpenCode Go buckets (`Rolling — 5-hour`, `Weekly`, `Monthly`) from one flat
`[opencode]` table, with no way to represent more than one account. Change it
so the TOML input can declare **one or more named instances**, and each
instance's three buckets are emitted with a new `"instance"` field in the
`AFTER_REPORT_JSON` payload, so a downstream reader can tell which account
each bucket belongs to. Every other provider's buckets (OpenAI, Anthropic,
Gemini) are unaffected functionally, but must still carry the new `"instance"`
key (as `null`) for a uniform JSON shape across all `subscriptions` entries.

## Owned paths (exact)

- `scripts/ai-subs.sh`
- `scripts/ai_subs_instance_check.sh` (new file you create)

## Forbidden

Every other file in the repository, in particular:
- `~/.local/state/lee-llm-router/credentials/` and `~/.local/share/opencode/`
  (any file under either — see Scope decision above)
- The live-fetch branch of `ai-subs.sh` (the `else:` branch under `if
  mode_toml:` — i.e. everything from `# ── Fetch live from CLIs concurrently
  ──` to the end of the script) and `fetch_opencode()` itself — read-only,
  not touched
- Any file in the `lee-llm-router` repository (that is M2b, a separate packet,
  dispatched after this one)
- `decisions.md`, `journal/`, or any other chief-of-staff authority file

## Required changes (in `scripts/ai-subs.sh`)

1. **`render_bucket()`** — add a new keyword parameter `instance=None` (after
   the existing `detail_note=None`). Add `"instance": instance,` as a new key
   in the dict appended to `AFTER_REPORT` (the `.append({...})` call inside
   `render_bucket`). Do not change the function's printed terminal output
   except as needed for step 3 below. Every existing call site for OpenAI,
   Anthropic, and Gemini stays exactly as it is today (so those entries get
   `"instance": null` in the JSON by virtue of the new default — no call-site
   change needed there).

2. **TOML `[opencode]` rendering block** (inside `if mode_toml:`, the section
   currently reading:
   ```python
   REPORT_PROVIDER = "OpenCode/Go"
   og = toml_cfg.get("opencode", {})
   og_reset = parse_reset(og.get("resets", ""))
   section("OpenCode Go", "🟣", "via snapshot")
   render_bucket("Rolling — 5-hour", pct(og.get("rolling_limit_left", 100)), og_reset, 5)
   render_bucket("Weekly",           pct(og.get("weekly_limit_left", 100)),  og_reset, 7 * 24)
   render_bucket("Monthly",          pct(og.get("monthly_limit_left", 100)), og_reset, 30 * 24)
   ```
   ) — replace with instance-aware rendering:
   - `og = toml_cfg.get("opencode", {})`
   - `instances = og.get("instances")`
   - If `instances` is a non-empty dict: iterate `sorted(instances.items())`
     (sort by instance id, for deterministic output order) — each value is a
     table with the same four fields the flat table has today
     (`rolling_limit_left`, `weekly_limit_left`, `monthly_limit_left`,
     `resets`).
   - Else (no `instances` sub-table — the old flat shape): treat `og` itself
     as a single implicit instance whose id is the literal string
     `"opencode-go"` (same "implicit instance named the channel id"
     convention M1 used in `catalog.py`'s `effective_instances()` — do not
     invent a different default name).
   - For each `(instance_id, table)` pair, in order: call `section("OpenCode
     Go", "🟣", f"via snapshot · instance {instance_id}")`, then the three
     `render_bucket(...)` calls exactly as today but reading from `table`
     instead of `og`, each passing `instance=instance_id`.
   - `REPORT_PROVIDER = "OpenCode/Go"` is set once before the loop, as today
     (it does not vary per instance).

3. Leave the human-readable printed dashboard (the `print(...)` lines inside
   `render_bucket`/`section`) as close to today's format as the above change
   naturally allows; the `section` subtitle change in step 2 is sufficient —
   no other cosmetic work is required or wanted.

## New file: `scripts/ai_subs_instance_check.sh`

Write a deterministic, self-contained bash script, starting with a
`#!/usr/bin/env bash` shebang and made executable (`chmod +x
scripts/ai_subs_instance_check.sh`) so it can be run directly as
`scripts/ai_subs_instance_check.sh` (no network, no real credentials) that:

1. Creates a temp directory (cleaned up on exit via `trap`).
2. Writes two TOML fixtures into it:
   - `multi.toml` with two instances, `a` and `b`, under
     `[opencode.instances.a]` / `[opencode.instances.b]`, each declaring
     distinct `rolling_limit_left` / `weekly_limit_left` /
     `monthly_limit_left` / `resets` values (so the test can tell them
     apart — e.g. instance `a` at 20/40/60 remaining, instance `b` at
     100/100/100 remaining).
   - `single.toml` with the old flat `[opencode]` table (no `instances`
     key), any remaining values.
3. Runs `scripts/ai-subs.sh multi.toml` and `scripts/ai-subs.sh single.toml`,
   captures stdout, and extracts the JSON line immediately after the
   `AFTER_REPORT_JSON` marker for each (the same `awk` pattern
   `scripts/refresh_availability.sh` already uses is a fine model — or write
   your own equivalent extraction).
4. Feeds both JSON payloads to a `python3 -c`/heredoc block that asserts, and
   exits non-zero with a clear message if any assertion fails:
   - `multi.toml`'s output has exactly 6 `provider == "OpenCode/Go"` entries.
   - Grouping those by `"instance"`, the set of instance ids is exactly
     `{"a", "b"}`, three entries each.
   - Instance `a`'s `"Rolling — 5-hour"` entry's `remaining_pct` equals the
     value implied by your fixture's `rolling_limit_left` for `a`; likewise
     for instance `b`; the two must differ (proving they are not conflated).
   - Every non-`OpenCode/Go` entry in `multi.toml`'s output has `"instance":
     null` (or the key absent — treat both as pass, since JSON `null` and a
     missing key are equivalent here).
   - `single.toml`'s output has exactly 3 `provider == "OpenCode/Go"`
     entries, and every one has `"instance": "opencode-go"`.
5. Prints a one-line success message and exits 0 only if every assertion
   passed.

## Required evidence

- Full stdout of `scripts/ai_subs_instance_check.sh` showing the success
  message and exit 0. Run it once before your `ai-subs.sh` change (it will
  fail, since `ai-subs.sh` does not yet emit `"instance"` — confirm the
  failure mode makes sense) and once after.
- `git status --short` and `git diff --stat` limited to exactly the two owned
  paths above (no other file touched, no file under
  `~/.local/state/lee-llm-router/` or `~/.local/share/opencode/` read or
  written — say so explicitly in your evidence note).
- A one-paragraph confirmation that you did not touch the live-fetch branch
  or `fetch_opencode()`.

## Runtime bound

30 minutes.

## Stop / escalation condition

If TOML's dotted-table syntax (`[opencode.instances.a]`) does not parse the
way this packet assumes with the `tomllib`/`tomli` version actually installed
in this environment, stop and report the exact parse error and the resulting
`toml_cfg` structure rather than inventing a different TOML shape. If
`render_bucket`'s existing call sites cannot take the new `instance=` kwarg
without touching a call site this packet marks forbidden, stop and report
exactly which call site conflicts.
