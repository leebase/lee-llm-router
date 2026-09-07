# Availability refresh

The resolver never calls a provider CLI at decision time. It reads a *snapshot*
of subscription headroom that a small shell script refreshes on a schedule.
This page covers the script, the snapshot it writes, and the cron line that
drives it.

The reader side — how a snapshot is normalized into per-channel health — is
documented in [`availability.md`](availability.md).

## What the script does

`scripts/refresh_availability.sh` runs the Chief of Staff `ai-subs.sh`
dashboard, takes the single JSON line that follows its `AFTER_REPORT_JSON`
marker, stamps it, and writes it atomically:

1. Run `ai-subs.sh` (path from `AI_SUBS`, default
   `~/projects/chief-of-staff/scripts/ai-subs.sh`) and capture stdout.
2. Extract the one JSON line immediately after the `AFTER_REPORT_JSON` marker.
3. Validate the payload (see [Payload validation](#payload-validation)).
4. Add `host` (from `hostname`) and `written_at` (ISO 8601 UTC, `Z`-suffixed).
5. Write to `<file>.tmp.$$` and `mv -f` it into place, creating the parent
   directory if needed. An `EXIT` trap is armed the moment the temp path is
   chosen and cleared only after a successful rename.

## Payload validation

Parsing as JSON is not enough — an object the reader cannot use must never
replace a good snapshot. The payload is accepted only when all of these hold:

| Requirement | Rejected example |
|---|---|
| top level is a JSON object | `[]`, `"a string"`, `42` |
| `subscriptions` is present and is a list | `{"observed_at":"..."}` |
| `observed_at` is present and is a string | `{"subscriptions":[]}` |
| `observed_at` parses as ISO 8601 (a trailing `Z` is accepted) | `"yesterday-ish"`, `"1757260000"`, `""` |
| every `subscriptions` element is a JSON object | `["OpenAI/Codex"]` |
| every element has a `provider` string | `{"bucket":"Weekly limit",...}` |
| a non-failure element has a non-empty `bucket` string | `{"provider":"OpenAI/Codex","status":"COLD","remaining_pct":90}` |
| a non-failure element has a `status` string | `{"provider":"OpenAI/Codex","bucket":"Weekly limit","remaining_pct":90}` |
| a non-failure element has a numeric `remaining_pct` | `{"...","remaining_pct":"90"}` |
| a non-failure `status` is one of the ai-subs badges | `{"...","status":"BANANA"}` |
| `remaining_pct` is a real number, not a bool | `{"...","remaining_pct":true}` |
| `remaining_pct` is finite | `{"...","remaining_pct":NaN}`, `Infinity` |
| `remaining_pct` is within `0`–`100` | `{"...","remaining_pct":150}`, `-5` |

The status vocabulary is `COLD`, `ON TRACK`, `HOT`, `TOO FAST`, `USE IT`,
`NO DATA` and `UNAVAILABLE`, with `NO_DATA` accepted as an alias of `NO DATA`.
Comparison is case-sensitive after `strip()`. The script hardcodes that set —
it runs from cron and must not need the package on `sys.path` — with a comment
pointing at `availability.py::KNOWN_STATUSES`, which is the authority; the two
are kept in step by hand.

These last four rules bring the writer to parity with the reader: they are
exactly `availability.is_wellformed_quota()`'s conditions. A record the reader
would fail closed to `unknown` is now refused at the writer instead, so it
never displaces a snapshot that could still be scored. `NaN` and `Infinity` in
particular parse happily as JSON floats through Python's decoder, and a
percentage of `150` or `-5` is a parsing bug upstream rather than a headroom
reading.

A *failure* element is one whose `status` is `UNAVAILABLE` or `NO_DATA`: that
is how ai-subs reports a provider it could not query at all, and such a record
legitimately carries no bucket and no numbers, so it short-circuits before the
badge and percentage rules. Everything else is a quota record, and a quota
record missing or mangling any of the three fields the reader scores is
rejected here rather than written to disk — the reader also fails such a record
closed to `unknown` (see [`availability.md`](availability.md#well-formedness)),
but a snapshot that cannot be scored should never displace one that could.

The `observed_at` check matters because the reader ages a snapshot from its
*oldest* timestamp: a payload whose observation time cannot be parsed would
otherwise be aged only by the `written_at` this script stamps on, which is
always fresh. Rejecting it here keeps stale data from reading as healthy.

An **empty** `subscriptions` list is accepted: "ai-subs saw nothing" is a real
observation, and the reader turns it into all-`unknown` channels on its own.

Anything else prints one stderr line, exits 1, and leaves the existing snapshot
byte-for-byte untouched.

`ai-subs` is the only thing it executes. No provider CLI is ever invoked
directly, and the crews file is never read or written.

## Snapshot path

```
${LEE_LLM_ROUTER_AVAILABILITY_FILE:-$HOME/.local/state/lee-llm-router/availability/$(hostname).json}
```

One file per host. The `<host>.json` naming keeps two machines' snapshots from
colliding in a synced state directory, and `host` inside the payload lets a
reader confirm which machine observed it.

## Snapshot contents

The `AFTER_REPORT_JSON` object, verbatim, plus two added keys:

| Key | Source | Meaning |
|---|---|---|
| `observed_at` | ai-subs | When ai-subs queried the subscriptions |
| `source` | ai-subs | How ai-subs obtained the numbers |
| `subscriptions` | ai-subs | One entry per provider/bucket pair |
| `host` | this script | `hostname` of the machine that wrote it |
| `written_at` | this script | ISO 8601 UTC write time, e.g. `2026-09-07T18:10:33Z` |

## Failure behaviour

If ai-subs fails, the marker is absent, or the captured payload fails
validation, the script prints **one line** to stderr, exits non-zero, and
leaves any existing snapshot untouched. A stale snapshot is strictly better
than a truncated one: the reader ages snapshots out to `unknown` on its own,
so a failed refresh degrades safely.

**No temp file survives a failure.** `trap 'rm -f -- "$tmp_file"' EXIT` is set
as soon as the temp path is defined and cleared only after `mv` succeeds, so a
failure anywhere in between — a full disk, an unwritable destination, a signal
— leaves the snapshot directory with no `*.tmp.*` residue. Without it, a
failing rename strands a partial file next to the snapshot, where the next
listing or sync picks it up.

## Options

| Option | Effect |
|---|---|
| `--dry-run` | Print the stamped JSON to stdout and write nothing. Safe to run any time; useful for confirming ai-subs still emits the marker. |
| `--input <file>` | Read a previously captured ai-subs stdout file instead of running ai-subs. Used by the tests so the suite never touches a live subscription. |
| `-h`, `--help` | Print usage. |

```bash
# Confirm the live plumbing without writing a snapshot
scripts/refresh_availability.sh --dry-run

# Replay a captured dashboard into a scratch snapshot
LEE_LLM_ROUTER_AVAILABILITY_FILE=/tmp/snap.json \
  scripts/refresh_availability.sh --input /tmp/ai-subs-stdout.txt
```

## Cron line (documented, not installed)

```cron
7 * * * * PATH=/home/lee/.local/bin:/usr/local/bin:/usr/bin:/bin /home/lee/projects/lee-llm-router/scripts/refresh_availability.sh >> /home/lee/.local/state/lee-llm-router/availability/refresh.log 2>&1
```

Hourly at seven past, which keeps it clear of the top-of-hour crowd and well
inside the reader's 90-minute staleness window.

**This repository does not install it.** Linux (A8Max) owns the schedule per
Chief of Staff decisions D121 (Linux-owned operational changes execute and
verify on the Linux host) and D167 (Linux owns weekday schedules). Lee or the
Chief of Staff installs the entry; a worker session never does.

Create the log directory first, since cron will not:

```bash
mkdir -p ~/.local/state/lee-llm-router/availability
```

## Checking it

```bash
lee-llm-router doctor --availability
```

Reports the snapshot path, its age in minutes, and how many subscription
buckets it carries. A missing or stale snapshot is a warning with exit 0 —
absence is a valid state before cron has ever run. Only a file that exists but
is not valid JSON with a `subscriptions` list is an error (exit 1).
