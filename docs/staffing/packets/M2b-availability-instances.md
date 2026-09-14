# Packet M2b — availability reader: per-instance headroom (channel instances, M2 continued)

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
("channel instances — many subscriptions per provider, universally"), milestone M2
("headroom per instance"). Supervised via `/supervise`. This is the `lee-llm-router`
half of M2; the `chief-of-staff` half (`scripts/ai-subs.sh`) is packet M2a, already
implemented, oracle-verified, and independently reviewed (ACCEPT) — this packet is
written against M2a's **actual, verified** output shape, not a guess.

## Confirmed upstream contract (from the verified M2a diff — do not re-derive)

`ai-subs.sh`'s `AFTER_REPORT_JSON` `subscriptions` entries now always carry an
`"instance"` key:
- For every non-OpenCode-Go provider (OpenAI, Anthropic, Gemini): always `null`.
- For OpenCode Go entries produced by the **live-fetch** path (today's only
  production path — unchanged, still single-account): always `null`.
- For OpenCode Go entries produced by the **TOML/snapshot** path with no
  `[opencode.instances]` sub-table (the old flat `[opencode]` shape): the
  literal string `"opencode-go"` (not `null`).
- For OpenCode Go entries produced by the TOML/snapshot path **with** an
  `[opencode.instances.<id>]` sub-table: the literal instance id string (e.g.
  `"a"`, `"b"`), one triplet of buckets (`Rolling — 5-hour`, `Weekly`,
  `Monthly`) per instance.

So today, in production, every live-fetched OpenCode Go bucket has
`"instance": null` and must be treated exactly like the literal `"opencode-go"`
case — both mean "the implicit single instance named after the channel."
`refresh_availability.sh` requires no code change for this (it validates
specific fields per entry and passes every entry through unmodified — verify
this yourself against the script before assuming otherwise; if you find it
genuinely needs a change, say so and make the minimal one, but do not make a
speculative change).

## Packet fields

Kind: impl
Declared size: 4 files (2 changed, 0 new — unless you find `refresh_availability.sh`
genuinely needs a change), approximately 250 changed/added lines
Owned paths: `src/lee_llm_router/availability.py`, `tests/test_availability.py`,
`scripts/refresh_availability.sh`, `tests/test_refresh_availability.py`
Oracle: `pytest tests/test_availability.py tests/test_refresh_availability.py -q`
Review: independent review required after the oracle passes

## Objective

`AvailabilitySnapshot`/`ChannelHeadroom`/`Bucket` currently aggregate every
bucket of a channel together (e.g. `opencode-go`'s worst-of-all-buckets
headroom), with no way to ask "how much headroom does *this specific account*
have left?" Add that without changing any existing channel-level behavior:
every current caller of `snapshot.headroom(channel)` must see byte-identical
results before and after this change (this is the single most important
regression to prove — see Tests below).

## Owned paths (exact)

- `src/lee_llm_router/availability.py`
- `tests/test_availability.py`
- `scripts/refresh_availability.sh`
- `tests/test_refresh_availability.py`

## Forbidden

Every other file, in particular:
- `chief-of-staff/scripts/ai-subs.sh` (M2a, already done — do not touch, do
  not re-verify it, treat its output shape above as given)
- `src/lee_llm_router/staffing/eligibility.py`, `src/lee_llm_router/staffing/catalog.py`
  (M3's owned paths — this packet does not wire the D216 reserve check or
  route selection to instances; it only exposes the per-instance headroom
  data those will read later). Do not import `lee_llm_router.staffing.catalog`
  from `availability.py` — that module is deliberately decoupled from the
  staffing catalog today and must stay that way.
- `context.md`, `sprint-plan.md`, `result-review.md` (the supervisor updates
  these after the packet is verified, not the worker)

## Required changes (in `src/lee_llm_router/availability.py`)

1. **`Bucket`** — add a new field `instance: str | None = None` at the end of
   the dataclass (after `raw_status`), so every existing keyword-constructed
   `Bucket(...)` call site keeps working unchanged. Add it to `to_dict()`'s
   output too (`"instance": self.instance`).

2. **`_buckets_from_entries`** — read `entry.get("instance")`; if it is a
   non-empty string, use it (after `.strip()`); otherwise (missing, `None`,
   empty string, or any non-string type) the bucket's `instance` is `None`.
   Do not raise on a malformed `instance` value — fail closed to `None`, the
   same way this function already fails closed on other malformed optional
   fields. Pass `instance=...` into every `Bucket(...)` construction in this
   function (there is exactly one call site inside the `for channel in
   targets:` loop).

3. **`ChannelHeadroom`** — add a new field `instance: str | None = None` at
   the end (after `buckets`), included in `to_dict()` as `"instance":
   self.instance`. When `instance is None`, a `ChannelHeadroom` means what it
   means today: the channel-wide aggregate across every instance. When set,
   it means the aggregate across only that one instance's buckets.

4. **New function `_effective_instance(bucket: Bucket, channel: str) -> str`**
   — returns `bucket.instance` if it is not `None`, else `channel` (the
   channel id itself is the implicit default instance name, matching
   `catalog.py`'s `Channel.effective_instances()` convention from M1 — do not
   invent a different default).

5. **New function `_instances_from_buckets(buckets: list[Bucket], observed_at,
   stale) -> dict[tuple[str, str], ChannelHeadroom]`** — group buckets by
   `(bucket.channel, _effective_instance(bucket, bucket.channel))`; for each
   group compute health/remaining_fraction/limiting_bucket exactly the way
   `_channels_from_buckets` already does for one channel (worst severity via
   `_SEVERITY`, `min()` of numeric remaining fractions, `stale` forces
   `Health.UNKNOWN`), and build a `ChannelHeadroom` with `channel=<channel>,
   instance=<instance_id>` plus that group's own buckets. Only emit an entry
   for `(channel, instance)` pairs that actually have at least one bucket —
   unlike `_channels_from_buckets`, do not synthesize placeholder "unknown"
   entries for instances that never appeared (this module has no way to know
   what instances *should* exist; that is the catalog's job, deliberately out
   of this module's scope).

6. **`AvailabilitySnapshot`** — add a new field `instances: dict[tuple[str,
   str], ChannelHeadroom] = field(default_factory=dict)` (needs no change to
   existing callers, since it is populated by the constructor call sites
   inside this module, not by external code). Wire `_instances_from_buckets`
   into both `parse_availability` (success path) — every other path
   (`_problem_snapshot`, the stale/malformed branches) already returns an
   empty-buckets result, so `instances` there is simply `{}` via the
   dataclass default; do not add special-casing.

7. **`AvailabilitySnapshot.instance_headroom(self, channel: str, instance:
   str) -> ChannelHeadroom`** — new method, same shape and fallback contract
   as the existing `headroom()` method: look up `self.instances.get((channel,
   instance))`; if missing, return an unknown/absent `ChannelHeadroom` (reuse
   or lightly adapt `_unknown_channel`, but it must carry `instance=instance`
   this time, not leave it `None` — a missing instance is "this specific
   account is unknown," not "the whole channel is unknown").

8. **`AvailabilitySnapshot.to_dict()`** — add a new top-level key
   `"instances"`, a list (not a dict-by-tuple-key, since tuple keys are not
   valid JSON object keys) of every value in `self.instances`, each rendered
   via `ChannelHeadroom.to_dict()` (which now includes `channel` and the new
   `instance` field, so no extra wrapping is needed) — order by `(channel,
   instance)` for determinism (`sorted(self.instances.items())` before
   mapping to dicts, or equivalent).

9. Existing `headroom(channel)` and `_channels_from_buckets` must **not**
   change behavior: they keep aggregating across every bucket of a channel
   regardless of `instance`, exactly as today. Do not filter buckets by
   instance anywhere inside the existing channel-aggregate path.

## `scripts/refresh_availability.sh`

Read the script and confirm for yourself whether an `"instance"` key on a
`subscriptions` entry already passes through its validation and JSON
round-trip unmodified (it validates specific named fields per entry — look at
exactly which ones — and writes back the whole parsed `data` object, so an
extra key that isn't checked should survive). If confirmed, make **no**
production-code change to this file; add the regression test described below
only. If you find a real gap (e.g. the script actually strips unknown keys
somewhere, or validates `additionalProperties`), make the minimal fix and
say exactly what you found and why in your evidence note.

## Tests (required, in the owned test files)

In `tests/test_availability.py`:
- **Backward-compatibility regression (most important):** for every existing
  test in this file that calls `snapshot.headroom(...)`, the result must be
  unaffected by this change — you are not required to duplicate every
  existing assertion, but add at least one test that loads the existing
  `LIVE_SAMPLE` fixture (which carries no `"instance"` field on any entry —
  confirm this) and asserts `snapshot.headroom("opencode-go")` returns
  identical `health`/`remaining_fraction`/`limiting_bucket` values to what
  the existing `test_live_sample_channel_healths` test already asserts, i.e.
  nothing regressed for the channel-level aggregate.
- A new synthetic fixture (JSON file under `tests/fixtures/availability/`, or
  an inline dict passed to `parse_availability`, your choice, following this
  file's existing fixture conventions) with two OpenCode Go instances: `"a"`
  with all three buckets healthy (e.g. 80% remaining, `COLD`/`ON TRACK`
  status) and `"b"` with all three buckets exhausted (e.g. 0% remaining).
  Assert:
  - `snapshot.instance_headroom("opencode-go", "a").health is Health.HEALTHY`
  - `snapshot.instance_headroom("opencode-go", "b").health is Health.EXHAUSTED`
  - `snapshot.headroom("opencode-go").health is Health.EXHAUSTED` (the
    channel-wide aggregate is still worst-of-all, unaffected by instance
    separation — this is the proof the two are not conflated in either
    direction).
  - Each returned `ChannelHeadroom.instance` equals the instance id you asked
    for; the channel-wide `snapshot.headroom("opencode-go").instance is None`.
- A fixture with an OpenCode Go bucket that has no `"instance"` key at all
  (today's live-fetch shape): `snapshot.instance_headroom("opencode-go",
  "opencode-go")` returns the same health/remaining_fraction as
  `snapshot.headroom("opencode-go")` (implicit-default backward compat).
- `snapshot.instance_headroom("opencode-go", "does-not-exist")` returns an
  unknown `ChannelHeadroom` (not a `KeyError`), with `instance ==
  "does-not-exist"`.
- A malformed `"instance"` value (e.g. `"instance": 7` or `"instance": ""`)
  on an entry is read as `Bucket.instance is None`, not raised or coerced.
- `to_dict()` on a snapshot with at least one multi-instance channel includes
  an `"instances"` list; assert its shape directly (each element has
  `channel`, `instance`, `health` keys at minimum) and that it is sorted by
  `(channel, instance)`.

In `tests/test_refresh_availability.py`:
- One new test: build a captured ai-subs stdout payload (following this
  file's existing `_capture_file`/`SAMPLE` pattern, or a small new fixture)
  whose `subscriptions` list includes at least one entry with `"instance":
  "a"` and one with `"instance": null`; run the script via `--input
  ... --dry-run` (or write to a snapshot path, matching this file's existing
  patterns); assert the written/printed JSON's matching entries still carry
  `"instance": "a"` and `"instance": null` unchanged. This is the pass-through
  proof for the claim in "Confirmed upstream contract" above.

## Before you finish

Run `.venv/bin/black src/lee_llm_router/availability.py tests/test_availability.py
tests/test_refresh_availability.py` (no `--check`, so it actually rewrites the
files) as your own last edit before finishing, then re-run every command in
the Oracle section below yourself and confirm each exits 0.

## Oracle (deterministic, required)

Run, in order, from the repo root with the project's `.venv`:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_availability.py tests/test_refresh_availability.py -q
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/availability.py tests/test_availability.py tests/test_refresh_availability.py
.venv/bin/ruff check src/lee_llm_router/availability.py tests/test_availability.py tests/test_refresh_availability.py
```

All four commands must exit 0. The full-suite `pytest -q` run must show
strictly more passed tests than the pre-packet baseline (confirm the current
baseline yourself before you start) and zero new failures.

## Runtime bound

35 minutes.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the owned paths above (call out
  explicitly whether `scripts/refresh_availability.sh` itself was touched,
  and why or why not).
- A one-paragraph confirmation that `snapshot.headroom(channel)` is
  byte-identical to pre-change behavior for every existing test in
  `tests/test_availability.py`.

## Stop / escalation condition

If `ChannelHeadroom` or `Bucket` cannot take a new optional trailing field
without breaking an existing positional-construction call site somewhere in
this module or its tests, stop and report exactly which call site conflicts
rather than reordering existing fields. If `refresh_availability.sh` turns
out to actively strip or reject unknown per-entry keys (contradicting the
"Confirmed upstream contract" section's assumption that it passes them
through), stop and report the exact validation branch responsible rather than
loosening it in a way that weakens its existing required-field checks.
