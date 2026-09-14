# Packet M2b1 — availability reader: per-instance headroom (core, repair-split from M2b)

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
(milestone M2). This packet is **half of M2b** (packet
`docs/staffing/packets/M2b-availability-instances.md`), split after M2b's
first dispatch stalled (no output/file activity for 10 minutes, killed by the
router — attempt `router-run-5882ee6d56734a69bdae11e1eea47885`). This half is
the core `availability.py` change plus its tests; the `refresh_availability.sh`
regression test is the separate, smaller packet M2b2.

## Confirmed upstream contract (from the verified M2a diff — do not re-derive)

`ai-subs.sh`'s `AFTER_REPORT_JSON` `subscriptions` entries now always carry an
`"instance"` key:
- Every non-OpenCode-Go provider entry: always `null`.
- OpenCode Go entries from the live-fetch path (today's only production
  path): always `null`.
- OpenCode Go entries from the TOML/snapshot path with no
  `[opencode.instances]` sub-table: the literal string `"opencode-go"`.
- OpenCode Go entries from the TOML/snapshot path with an
  `[opencode.instances.<id>]` sub-table: the literal instance id (e.g.
  `"a"`, `"b"`), three buckets per instance.

So `null` and the literal string `"opencode-go"` both mean "the implicit
single instance named after the channel" and must normalize to the same
value.

## Packet fields

Kind: impl
Declared size: 2 files (both changed), approximately 170 changed/added lines
Owned paths: `src/lee_llm_router/availability.py`, `tests/test_availability.py`
Oracle: `pytest tests/test_availability.py -q`
Review: independent review required after the oracle passes

## Objective

Add per-instance headroom to the availability reader without changing any
existing channel-level behavior: every current caller of
`snapshot.headroom(channel)` must see byte-identical results before and after
this change (the single most important regression to prove).

## Owned paths (exact)

- `src/lee_llm_router/availability.py`
- `tests/test_availability.py`

## Forbidden

Every other file, in particular:
- `scripts/refresh_availability.sh`, `tests/test_refresh_availability.py`
  (packet M2b2 — a separate dispatch, not part of this packet)
- `chief-of-staff/scripts/ai-subs.sh` (M2a, already done)
- `src/lee_llm_router/staffing/eligibility.py`, `src/lee_llm_router/staffing/catalog.py`
  (M3's owned paths — this packet only exposes per-instance headroom data, it
  does not wire the D216 reserve check or route selection to instances). Do
  not import `lee_llm_router.staffing.catalog` from `availability.py` — that
  module is deliberately decoupled from the staffing catalog today and must
  stay that way.
- `context.md`, `sprint-plan.md`, `result-review.md`

## Required changes (in `src/lee_llm_router/availability.py`)

1. **`Bucket`** — add `instance: str | None = None` as the new last field
   (after `raw_status`), so existing keyword-constructed `Bucket(...)` call
   sites keep working unchanged. Add `"instance": self.instance` to
   `to_dict()`.

2. **`_buckets_from_entries`** — read `entry.get("instance")`; a non-empty
   string (after `.strip()`) is used as-is; anything else (missing, `None`,
   empty string, non-string) fails closed to `None`. Pass `instance=...` into
   the single `Bucket(...)` construction in this function.

3. **`ChannelHeadroom`** — add `instance: str | None = None` as the new last
   field (after `buckets`), included in `to_dict()` as `"instance":
   self.instance`. `instance is None` still means "the channel-wide
   aggregate across every instance" (today's meaning, unchanged); a set value
   means "the aggregate across only that one instance's buckets."

4. **New function `_effective_instance(bucket: Bucket, channel: str) -> str`**
   — returns `bucket.instance` if not `None`, else `channel` (the channel id
   itself is the implicit default instance name — the same convention `M1`
   used in `catalog.py`'s `Channel.effective_instances()`; do not invent a
   different default).

5. **New function `_instances_from_buckets(buckets: list[Bucket],
   observed_at, stale) -> dict[tuple[str, str], ChannelHeadroom]`** — group
   buckets by `(bucket.channel, _effective_instance(bucket, bucket.channel))`;
   for each group compute health/remaining_fraction/limiting_bucket exactly
   the way `_channels_from_buckets` already does for one channel (worst
   severity via `_SEVERITY`, `min()` of numeric remaining fractions, `stale`
   forces `Health.UNKNOWN`); build a `ChannelHeadroom` with
   `channel=<channel>, instance=<instance_id>` plus that group's own buckets.
   Only emit an entry for `(channel, instance)` pairs that actually have at
   least one bucket — do not synthesize placeholder "unknown" entries for
   instances that never appeared (this module has no way to know what
   instances *should* exist; that is the catalog's job, out of scope here).

6. **`AvailabilitySnapshot`** — add `instances: dict[tuple[str, str],
   ChannelHeadroom] = field(default_factory=dict)`. Wire
   `_instances_from_buckets` into `parse_availability`'s success path; every
   other path (`_problem_snapshot`, stale/malformed branches) already returns
   an empty-buckets result, so `instances` there is `{}` via the dataclass
   default — no special-casing needed.

7. **`AvailabilitySnapshot.instance_headroom(self, channel: str, instance:
   str) -> ChannelHeadroom`** — new method, same shape/fallback contract as
   the existing `headroom()`: look up `self.instances.get((channel,
   instance))`; if missing, return an unknown `ChannelHeadroom` (adapt
   `_unknown_channel`, but set `instance=instance` this time — a missing
   instance is "this specific account is unknown," not "the whole channel is
   unknown").

8. **`AvailabilitySnapshot.to_dict()`** — add a new top-level key
   `"instances"`: a list (tuple keys are not valid JSON object keys) of every
   value in `self.instances`, each via `ChannelHeadroom.to_dict()`, ordered
   by `sorted(self.instances.items())` for determinism.

9. Existing `headroom(channel)` / `_channels_from_buckets` must **not**
   change behavior: they keep aggregating across every bucket of a channel
   regardless of `instance`, exactly as today. Do not filter by instance
   anywhere in the existing channel-aggregate path.

## Tests (required, in `tests/test_availability.py`)

- **Backward-compatibility regression (most important):** load the existing
  `LIVE_SAMPLE` fixture (confirm it carries no `"instance"` field on any
  entry) and assert `snapshot.headroom("opencode-go")` returns the same
  `health`/`remaining_fraction`/`limiting_bucket` the existing
  `test_live_sample_channel_healths` test already asserts — proof nothing
  regressed for the channel-level aggregate.
- A new synthetic fixture with two OpenCode Go instances: `"a"` with all
  three buckets healthy (e.g. 80% remaining, `COLD`/`ON TRACK`) and `"b"`
  with all three buckets exhausted (0% remaining). Assert:
  - `snapshot.instance_headroom("opencode-go", "a").health is Health.HEALTHY`
  - `snapshot.instance_headroom("opencode-go", "b").health is Health.EXHAUSTED`
  - `snapshot.headroom("opencode-go").health is Health.EXHAUSTED` (channel
    aggregate still worst-of-all — proof the two are not conflated).
  - Each returned `ChannelHeadroom.instance` equals the instance id asked
    for; `snapshot.headroom("opencode-go").instance is None`.
- A fixture with an OpenCode Go bucket carrying no `"instance"` key at all
  (today's live-fetch shape): `snapshot.instance_headroom("opencode-go",
  "opencode-go")` returns the same health/remaining_fraction as
  `snapshot.headroom("opencode-go")`.
- `snapshot.instance_headroom("opencode-go", "does-not-exist")` returns an
  unknown `ChannelHeadroom` (not `KeyError`), with `instance ==
  "does-not-exist"`.
- A malformed `"instance"` value (`"instance": 7` or `"instance": ""`) on an
  entry is read as `Bucket.instance is None`.
- `to_dict()` on a snapshot with a multi-instance channel includes an
  `"instances"` list; assert its shape (each element has `channel`,
  `instance`, `health` keys at minimum) and that it is sorted by `(channel,
  instance)`.

## Before you finish

Run `.venv/bin/black src/lee_llm_router/availability.py tests/test_availability.py`
(no `--check`) as your own last edit, then re-run the Oracle commands below
yourself and confirm each exits 0.

## Oracle (deterministic, required)

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_availability.py -q
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/availability.py tests/test_availability.py
.venv/bin/ruff check src/lee_llm_router/availability.py tests/test_availability.py
```

All four commands must exit 0; the full-suite run must show strictly more
passed tests than the pre-packet baseline (confirm the baseline yourself
before you start) and zero new failures.

## Runtime bound

20 minutes.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the two owned paths above.
- A one-paragraph confirmation that `snapshot.headroom(channel)` is
  byte-identical to pre-change behavior for every existing test in
  `tests/test_availability.py`.

## Stop / escalation condition

If `ChannelHeadroom` or `Bucket` cannot take a new optional trailing field
without breaking an existing positional-construction call site somewhere in
this module or its tests, stop and report exactly which call site conflicts
rather than reordering existing fields.
