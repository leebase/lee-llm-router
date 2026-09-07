# Availability snapshots

`lee_llm_router.availability` answers one question for the resolver: **does this
funding channel have headroom left right now?** It answers it from a file on
disk, never by calling a provider CLI at decision time.

## Snapshot contract

Chief of Staff's `~/projects/chief-of-staff/scripts/ai-subs.sh` prints an
`AFTER_REPORT_JSON` block. A refresh script (run by cron, at most hourly) writes
that object — plus `host` and `written_at` — atomically to:

```
~/.local/state/lee-llm-router/availability/<host>.json
```

```json
{
  "observed_at": "2026-09-07T13:07:40.975124-05:00",
  "written_at": "2026-09-07T18:07:41+00:00",
  "host": "A8Max",
  "source": "live CLI integration",
  "subscriptions": [
    {
      "provider": "OpenAI/Codex",
      "bucket": "Weekly limit",
      "status": "HOT",
      "used_pct": 52.0,
      "remaining_pct": 48.0,
      "pace_ratio": 1.17,
      "pace_ratio_infinite": false,
      "resets_at": "2026-09-11T10:37:09-05:00",
      "resets_in_hours": 93.49
    },
    { "provider": "Gemini/agy", "status": "UNAVAILABLE", "error": "agy not found" }
  ]
}
```

`host` and `written_at` are optional; the reader tolerates their absence and
falls back to `observed_at`. Timestamps may carry any UTC offset (or none, in
which case they are read as UTC) and are normalised to aware UTC.

An entry with `status` `UNAVAILABLE` or `NO_DATA` carries no bucket numbers. It
still contributes one `unknown` bucket to its channel, so a provider that failed
to report never looks healthy.

### Well-formedness

Every *other* entry — a quota record — is scored only when it carries all three
of the fields health is derived from:

| Field | Requirement |
|---|---|
| `bucket` | a non-empty string |
| `status` | a string in `KNOWN_STATUSES` (see below) |
| `remaining_pct` | a finite number in `0`–`100` (a *number*, not `"90"`) |

Any failure makes the bucket `unknown`, which clouds its channel through the
ordinary worst-wins ordering. `raw_status` keeps whatever the record said; when
there was no `status` at all it reads `MALFORMED`. The entry's label is
recorded once in `snapshot.malformed`, and `to_dict()` reports both the list
and a `malformed_count`. A record that is well-formed but cannot be routed to a
single channel (see [Channels](#channels)) is counted there too.

This exists because the reader used to score partial records. For a recognised
provider, all three of these read as **healthy**:

```json
{"provider":"OpenAI/Codex","remaining_pct":90}
{"provider":"OpenAI/Codex","bucket":"Weekly limit","remaining_pct":90}
{"provider":"OpenAI/Codex","bucket":"Weekly limit","status":"BANANA","remaining_pct":90}
```

None of them says which quota window `90` belongs to or whether ai-subs even
believes it — a renamed field or a truncated record would have routed real work
to a channel nobody had measured. They now read `unknown`.

### `KNOWN_STATUSES`

`ai-subs.sh`'s `status_badge()` emits exactly `COLD`, `ON TRACK`, `HOT`,
`TOO FAST`, `USE IT` and `NO DATA`; provider-level failures use `UNAVAILABLE`
and `NO_DATA`. `KNOWN_STATUSES` is that vocabulary, and `NO_DATA` is accepted
as an alias of `NO DATA`. Matching is **case-sensitive** after `strip()`:
ai-subs emits upper-case badges, so `on track` is not one of them, and a badge
the reader does not recognise is a payload it does not understand rather than
something to guess at.

| Badge | Health |
|---|---|
| `COLD`, `ON TRACK`, `USE IT` | by remaining percentage |
| `HOT`, `TOO FAST` | `degraded` regardless of percentage |
| `NO DATA` / `NO_DATA` | `unknown` regardless of percentage |
| `UNAVAILABLE` | `unknown` (provider-level failure entry) |
| anything else | `unknown`, and the record is counted as malformed |

`USE IT` means "spend this window's quota before it resets" — it is a healthy
state, not a warning. `NO DATA` means nothing was measured, so any percentage
beside it is meaningless and the bucket stays `unknown`.

A `Gemini/agy` record whose `bucket` is empty, missing, or simply not one the
prefix table recognises cannot be routed to either Gemini quota, so it becomes an
`unknown` bucket in **both** `gemini-sub` and `gemini-sub-thirdparty` — the same
treatment a Gemini `UNAVAILABLE` entry already gets.

## Path resolution

1. an explicit `load_availability(path=...)` argument
2. the `LEE_LLM_ROUTER_AVAILABILITY_FILE` environment variable
3. `~/.local/state/lee-llm-router/availability/<socket.gethostname()>.json`

```bash
export LEE_LLM_ROUTER_AVAILABILITY_FILE=/path/to/snapshot.json
```

## Channels

A channel is a funding source, not a model. `CHANNELS`:

| Channel | Source in the snapshot |
|---|---|
| `openai-sub` | provider `OpenAI/Codex` |
| `anthropic-sub` | provider `Anthropic/Claude` |
| `gemini-sub` | provider `Gemini/agy`, bucket name starting `Gemini models` |
| `gemini-sub-thirdparty` | provider `Gemini/agy`, bucket name starting `Claude/GPT models` |
| `openrouter` | no source today — always `unknown` |
| `opencode-go` | no source today — always `unknown` |

The two Gemini channels are deliberately separate: Google's harness meters its
own models and its Claude/GPT passthrough against different quotas, and one can
be exhausted while the other is not.

An **unrecognised provider** is dropped, and its `provider/bucket` label is
listed in `snapshot.ignored` so nothing disappears silently.

A recognised provider with an **unroutable bucket name** is a different case and
is handled differently. A `Gemini/agy` record whose bucket name starts with
neither `Gemini models` nor `Claude/GPT models` — renamed upstream, garbled, or
empty — could be metered against either Gemini quota, and the reader cannot tell
which. It therefore contributes one `unknown` bucket to **both** `gemini-sub`
and `gemini-sub-thirdparty`, keeps its raw status, contributes no percentage to
either channel, and is listed once in `snapshot.malformed` — never in `ignored`.

Dropping it instead would be fail-open: a `Gemini flash — weekly` bucket sitting
at `0%` would vanish from the snapshot entirely and leave both Gemini channels
reading `healthy` off their remaining buckets, routing work to a quota that is
actually spent. `is_routable_bucket(provider, bucket)` is the rule: a pair that
resolves to exactly one channel is scored, and a pair that fans out to several is
ambiguous and cannot be.

`channels_for()` returns the empty tuple only for an unknown *provider*; for a
known provider it always names at least one channel.

## Health

Per bucket, from `remaining_pct / 100`:

| Remaining fraction | Health |
|---|---|
| `<= 0.00` | `exhausted` |
| `< 0.10` | `likely_exhausted` |
| `< 0.25` | `degraded` |
| any, with a `HOT` or `TOO FAST` badge | `degraded` |
| any, with a `NO DATA` badge | `unknown` |
| missing, non-numeric, non-finite, or outside 0–100% | `unknown` |
| any, on a record that is not well-formed (above) | `unknown` |
| any, on a record whose bucket name routes to no single channel | `unknown` |
| otherwise | `healthy` |

### Non-finite and out-of-range numbers

`NaN`, `Infinity`, `-Infinity` and their string spellings (`"nan"`, `"inf"`, …)
are rejected wherever a number is expected — `remaining_pct`, `pace_ratio`,
`resets_in_hours`. This is not pedantry: `NaN` loses *every* `<` and `<=`
comparison, so a `NaN` remaining fraction would fall past all three thresholds
and land on `healthy`. Rejecting it makes the bucket `unknown` instead.

A `remaining_pct` outside `0`–`100` (say `150` or `-5`) is likewise `unknown`.
It is deliberately **not** clamped: clamping `150` down to `100` would invent
headroom nobody observed, and clamping is the wrong answer to a number that
should not exist. `0` and `100` themselves are in range and behave normally.

`bucket_health()` is fail-closed on its own for direct callers: a non-finite
fraction, or one above `1.0`, returns `unknown`. A *negative* fraction still
returns `exhausted`, which is the safe reading of "less than none left".

A channel takes the **worst** health across its buckets, ordered:

```
exhausted > likely_exhausted > degraded > unknown > healthy
```

`unknown` ranking above `healthy` is intentional — an unreported bucket clouds a
channel rather than being ignored. `limiting_bucket` names the bucket that set
the state, and `remaining_fraction` is the smallest numeric fraction on the
channel.

## Staleness

Age is measured from the **oldest** timestamp the snapshot carries:
`age_minutes` is the larger of the `observed_at` and `written_at` ages, so
whichever is older governs. A refresh only rewrites the file — it does not
re-observe the provider quotas — so a fresh `written_at` must never make an old
`observed_at` read as current. Past `max_age_minutes` (default 90,
`DEFAULT_MAX_AGE_MINUTES`) the snapshot is **stale**: every channel's health
becomes `unknown` and `limiting_bucket` is cleared, and `stale_reason` names
the timestamp that tripped the ceiling (`observed_at is older than 90 minutes`).
With neither timestamp present the snapshot is stale with
`snapshot has no timestamp`. The raw buckets and remaining fractions are kept so a UI can still show
what was last seen, clearly labelled as old. Staleness never degrades a channel
to `healthy`.

### Timestamps from the future

A snapshot stamped *ahead* of `now` would otherwise compute a negative age and
sail through the ceiling as fresh. Up to `MAX_FUTURE_SKEW_MINUTES` (5) of skew
is tolerated as ordinary clock drift between hosts. The check runs on **each**
timestamp independently, not only on the governing one: if either `observed_at`
or `written_at` is beyond the tolerance the snapshot is stale, every channel is
`unknown`, and `stale_reason` (and `problem`) read `timestamp is in the future`.
`age_minutes` then reports the skew — the most negative of the two ages — so it
is visible for diagnosis rather than hidden.

`stale_reason` names *why* a snapshot is stale — `timestamp is in the future`,
`observed_at is older than 90 minutes` (or `written_at ...`, whichever is the
older stamp), or `snapshot has no timestamp` — and is `None` when the snapshot
is fresh.

### Naive datetimes are UTC

Neither the `now` argument nor an offset-free timestamp string in the snapshot
is ever read as host-local time. Both are treated as UTC. A router that ages a
snapshot differently depending on the machine's `TZ` would be a fail-open bug
on any host east of Greenwich, so the interpretation is fixed rather than
ambient. Pass an aware datetime if you mean a non-UTC wall clock.

A missing file, invalid JSON, a missing `subscriptions` list, a missing
timestamp, or an unparseable timestamp all produce the same shape: `stale=True`,
every channel `unknown`, and `problem` set to a human-readable reason.
`load_availability()` never raises; `parse_availability()` is the strict variant
and raises `AvailabilityError`.

## Usage

```python
from lee_llm_router.availability import Health, load_availability

snapshot = load_availability()
headroom = snapshot.headroom("anthropic-sub")   # never raises, even if absent

if snapshot.stale:
    print(f"headroom unknown: {snapshot.stale_reason}")
elif headroom.health in (Health.EXHAUSTED, Health.LIKELY_EXHAUSTED):
    print(f"vetoed: {headroom.limiting_bucket} at {headroom.remaining_fraction:.0%}")

snapshot.to_dict()   # JSON-ready, for the CLI and the crew page
```
