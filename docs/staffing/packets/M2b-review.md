# Packet M2b-review — independent review of the uncommitted availability-instance diff

Kind: review
Declared size: 3 files, approximately 130 changed/added lines
Owned paths: src/lee_llm_router/availability.py, tests/test_availability.py, tests/test_refresh_availability.py
Oracle: none (judge review; verdict is the deliverable)
Review: n/a (this is the review)

The owned paths above are registered for conflict-freedom only — this is a
read-only review; write nothing.

Runtime bound: 20 minutes.

Scope: the **uncommitted** working-tree diff in `/home/lee/projects/lee-llm-router`
limited to `src/lee_llm_router/availability.py`, `tests/test_availability.py`,
and `tests/test_refresh_availability.py` (`git diff -- <those three>`).
`scripts/refresh_availability.sh` itself was deliberately left untouched
(confirmed pass-through of unknown JSON keys) — that is correct, not an
omission; do not flag it as missing work. Ignore every other file. Packets
under review: `docs/staffing/packets/M2b1-availability-instances-core.md` and
`docs/staffing/packets/M2b2-refresh-availability-passthrough.md` (both halves
of the original `docs/staffing/packets/M2b-availability-instances.md`, split
after a stall/ceiling repair chain — see those files for full context); plan:
`/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
(milestone M2).

## Judge (ACCEPT/REJECT each, with what you reproduced)

1. `Bucket` and `ChannelHeadroom` each gained an additive, defaulted
   `instance: str | None = None` trailing field (both dataclasses'
   `to_dict()` updated to include it). Confirm no existing call site broke —
   run the full suite.
2. `_buckets_from_entries` reads `entry.get("instance")`: a non-empty
   stripped string is kept, anything else (missing, `None`, empty string,
   non-string) fails closed to `None`.
3. New `_effective_instance(bucket, channel)` returns `bucket.instance` if
   set, else `channel` — the implicit default instance name equals the
   channel id, matching M1's `catalog.py` `effective_instances()` convention.
4. New `_instances_from_buckets` groups by `(channel, effective_instance)`
   and computes health/remaining_fraction the same way
   `_channels_from_buckets` already does per channel (worst severity, `min()`
   of numeric remaining fractions, `stale` forces `Health.UNKNOWN`). Confirm
   `_channels_from_buckets` itself is **byte-for-byte unchanged** in this
   diff — the channel-wide aggregate must not filter by instance.
5. `AvailabilitySnapshot.instance_headroom(channel, instance)` mirrors
   `headroom(channel)`'s existing missing-key fallback (returns an unknown
   `ChannelHeadroom` with `instance` set, never raises).
6. `to_dict()`'s new `"instances"` key is a sorted list, not a dict (tuple
   keys aren't valid JSON object keys) — confirm the sort key is `(channel,
   instance)`.
7. Backward-compatibility proof: the diff includes (or the test suite
   already proves) that `snapshot.headroom("opencode-go")` against the
   existing `LIVE_SAMPLE` fixture is unaffected by this change — reproduce
   this yourself by running the two test files' oracle command and reading
   the relevant assertions, not just trusting a green run.
8. `tests/test_refresh_availability.py`'s new test proves an `"instance"` key
   (both a string value and `null`) on a `subscriptions` entry survives
   `refresh_availability.sh --input ... ` unchanged, using the file's
   existing `_capture_payload`/`_run` helpers (not new ad hoc plumbing).
9. Run the oracle yourself: `python3 -m pytest tests/test_availability.py
   tests/test_refresh_availability.py -q` (from the repo root, with
   `PYTHONPATH=src` if needed) and confirm it passes; also run
   `python3 -m pytest -q` (full suite) and confirm no new failures.
10. `black --check` and `ruff check` on the three owned Python files pass.
11. Nothing outside the three owned files is touched by this diff — anything
    that changes `staff.py`, `eligibility.py`, `catalog.py`, or the D216
    reserve-check logic is contract-blocking and out of scope for this
    packet (that is M3).

End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not edit,
commit, stash, or write anything.
