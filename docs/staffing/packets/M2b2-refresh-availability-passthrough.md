# Packet M2b2 — `refresh_availability.sh` instance pass-through regression (repair-split from M2b)

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
(milestone M2). This packet is **half of M2b** (packet
`docs/staffing/packets/M2b-availability-instances.md`), split after M2b's
first dispatch stalled and was killed by the router (attempt
`router-run-5882ee6d56734a69bdae11e1eea47885`). This half is the
`refresh_availability.sh` regression coverage; the `availability.py` reader
change is the separate packet M2b1 (dispatch and verify independently — do
not wait for it or assume its outcome).

## Confirmed upstream contract

`ai-subs.sh`'s `AFTER_REPORT_JSON` `subscriptions` entries now always carry
an `"instance"` key (string id, the literal string `"opencode-go"`, or
`null`) — see `docs/staffing/packets/M2a-ai-subs-instances.md` for the full
verified shape. This packet does not need those details beyond knowing the
key can be a string or `null` on any entry.

## Packet fields

Kind: impl
Declared size: 2 files (0 or 1 changed, 1 changed), approximately 60 changed/added lines
Owned paths: `scripts/refresh_availability.sh`, `tests/test_refresh_availability.py`
Oracle: `pytest tests/test_refresh_availability.py -q`
Review: independent review required after the oracle passes

## Objective

Prove (and fix only if actually broken) that `refresh_availability.sh` passes
an `"instance"` key on a `subscriptions` entry through unmodified — it must
not strip, reject, or otherwise alter that key.

## Owned paths (exact)

- `scripts/refresh_availability.sh`
- `tests/test_refresh_availability.py`

## Forbidden

Every other file, in particular:
- `src/lee_llm_router/availability.py`, `tests/test_availability.py`
  (packet M2b1 — a separate dispatch, not part of this packet)
- `chief-of-staff/scripts/ai-subs.sh` (M2a, already done)
- `context.md`, `sprint-plan.md`, `result-review.md`

## Required work

1. Read `scripts/refresh_availability.sh` end to end. It validates specific
   named fields on each `subscriptions` entry (`provider`, and — unless the
   entry is a provider-level `UNAVAILABLE`/`NO_DATA` failure — `bucket`,
   `status`, `remaining_pct`) and writes back the whole parsed JSON object
   with `host`/`written_at` stamped on. Confirm for yourself whether it
   validates against a fixed field allowlist (which would silently drop an
   unrecognized `"instance"` key) or simply passes every field through.
2. If confirmed pass-through (the expected outcome): make **no** production
   change to this script. Add the regression test below only.
3. If you find a real gap — the script actually strips unknown keys, or
   validates with something like a JSON-schema `additionalProperties: false`
   — make the minimal fix so `"instance"` (and any other unrecognized key)
   survives the round-trip, and say exactly what you found and why in your
   evidence note. Do not broaden or narrow any of its *existing* required-
   field checks (`provider`/`bucket`/`status`/`remaining_pct`) while doing
   this.

## Test (required, in `tests/test_refresh_availability.py`)

Add one new test, following this file's existing `_capture_file`/`SAMPLE`/
`_run` pattern: build (or extend) a captured ai-subs stdout payload whose
`subscriptions` list includes at least one entry with `"instance": "a"` and
one entry with `"instance": null` (you can copy two entries from the existing
`SAMPLE` fixture and add the key, or write a small new fixture — your
choice, matching this file's existing conventions). Run the script via
`--input <file>` against a temp snapshot path (same as the existing
`test_writes_a_stamped_snapshot` test). Assert the written snapshot JSON's
matching entries still carry `"instance": "a"` and `"instance": null`
unchanged.

## Before you finish

Run `.venv/bin/black --check tests/test_refresh_availability.py` (and
`scripts/refresh_availability.sh` has no Python formatter — only the inline
`python3 -c` blocks matter for readability, not Black) before finishing;
re-run the Oracle commands below yourself and confirm each exits 0.

## Oracle (deterministic, required)

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_refresh_availability.py -q
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check tests/test_refresh_availability.py
.venv/bin/ruff check tests/test_refresh_availability.py
```

All four commands must exit 0; the full-suite run must show strictly more
passed tests than the pre-packet baseline (confirm the baseline yourself
before you start) and zero new failures.

## Runtime bound

15 minutes.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the two owned paths above (state
  explicitly whether `scripts/refresh_availability.sh` itself was touched,
  and why or why not).

## Stop / escalation condition

If `refresh_availability.sh` genuinely requires more than a minimal,
targeted fix to preserve unknown keys (e.g. it would need a structural
rewrite of its JSON validation), stop and report exactly what you found
rather than making a large change to a file mostly out of this packet's
declared scope.
