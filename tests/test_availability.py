"""Tests for the ``ai-subs`` availability snapshot reader."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lee_llm_router.availability import (
    AVAILABILITY_FILE_ENV_VAR,
    CHANNELS,
    GEMINI_CHANNELS,
    MAX_FUTURE_SKEW_MINUTES,
    AvailabilityError,
    Health,
    bucket_health,
    channels_for,
    is_routable_bucket,
    load_availability,
    parse_availability,
    resolve_availability_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "availability"
LIVE_SAMPLE = FIXTURES / "live-sample-2026-09-07.json"
LIVE_OBSERVED_AT = datetime(2026, 9, 7, 18, 7, 40, 975124, tzinfo=timezone.utc)
SYNTHETIC_OBSERVED_AT = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def fixture(name: str) -> Path:
    """Return the path to a synthetic availability fixture."""
    return FIXTURES / name


def load_fixture(name: str, *, minutes_old: float = 1.0, max_age: float = 90.0):
    """Load a synthetic fixture at a fixed age relative to its ``observed_at``."""
    return load_availability(
        fixture(name),
        now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=minutes_old),
        max_age_minutes=max_age,
    )


# --------------------------------------------------------------------------
# Live sample
# --------------------------------------------------------------------------


def test_live_sample_channel_healths() -> None:
    """The real 2026-09-07 snapshot normalises to the expected channel states."""
    snapshot = load_availability(
        LIVE_SAMPLE, now=LIVE_OBSERVED_AT + timedelta(minutes=2)
    )

    assert snapshot.problem is None
    assert snapshot.stale is False
    assert snapshot.observed_at == LIVE_OBSERVED_AT
    assert snapshot.age_minutes == pytest.approx(2.0)
    assert snapshot.ignored == ()

    # OpenAI: weekly is 48% remaining but the badge is HOT -> degraded.
    openai = snapshot.headroom("openai-sub")
    assert openai.health is Health.DEGRADED
    assert openai.limiting_bucket == "Weekly limit"
    assert openai.remaining_fraction == pytest.approx(0.48)

    # Anthropic: the current session is TOO FAST -> degraded.
    anthropic = snapshot.headroom("anthropic-sub")
    assert anthropic.health is Health.DEGRADED
    assert anthropic.limiting_bucket == "Current session"
    assert anthropic.remaining_fraction == pytest.approx(0.56)

    # Gemini's own models: weekly 44% ON TRACK, but the 5-hour bucket is HOT,
    # and a HOT badge is degraded regardless of the remaining percentage.
    gemini = snapshot.headroom("gemini-sub")
    assert gemini.health is Health.DEGRADED
    assert gemini.limiting_bucket == "Gemini models — 5-hour"
    assert gemini.remaining_fraction == pytest.approx(0.44)

    # Gemini's third-party passthrough: both buckets COLD with plenty left.
    thirdparty = snapshot.headroom("gemini-sub-thirdparty")
    assert thirdparty.health is Health.HEALTHY
    assert thirdparty.remaining_fraction == pytest.approx(0.85)

    # No source exists for these two today.
    for channel in ("openrouter", "opencode-go"):
        headroom = snapshot.headroom(channel)
        assert headroom.health is Health.UNKNOWN
        assert headroom.buckets == ()


def test_live_sample_bucket_routing() -> None:
    """Every live bucket lands on exactly one channel, in snapshot order."""
    snapshot = load_availability(
        LIVE_SAMPLE, now=LIVE_OBSERVED_AT + timedelta(minutes=2)
    )
    names = {
        channel: [bucket.name for bucket in snapshot.headroom(channel).buckets]
        for channel in CHANNELS
    }
    assert names["openai-sub"] == ["Weekly limit", "GPT-5.3-Codex-Spark (5h)"]
    assert names["anthropic-sub"] == [
        "Current session",
        "All models — weekly",
        "Claude Fable — weekly",
    ]
    assert names["gemini-sub"] == ["Gemini models — weekly", "Gemini models — 5-hour"]
    assert names["gemini-sub-thirdparty"] == [
        "Claude/GPT models — weekly",
        "Claude/GPT models — 5-hour",
    ]
    assert sum(len(v) for v in names.values()) == 9


def test_live_sample_resets_at_normalised_to_utc() -> None:
    """Offset timestamps inside buckets are normalised to aware UTC."""
    snapshot = load_availability(
        LIVE_SAMPLE, now=LIVE_OBSERVED_AT + timedelta(minutes=2)
    )
    weekly = snapshot.headroom("openai-sub").buckets[0]
    assert weekly.resets_at == datetime(2026, 9, 11, 15, 37, 9, tzinfo=timezone.utc)
    assert weekly.resets_in_hours == pytest.approx(93.49)
    assert weekly.pace_ratio == pytest.approx(1.17)
    assert weekly.raw_status == "HOT"


# --------------------------------------------------------------------------
# Per-health-state fixtures
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "channel", "expected"),
    [
        ("exhausted.json", "openai-sub", Health.EXHAUSTED),
        ("likely-exhausted.json", "openai-sub", Health.LIKELY_EXHAUSTED),
        ("degraded-by-pct.json", "openai-sub", Health.DEGRADED),
        ("degraded-by-status.json", "openai-sub", Health.DEGRADED),
        ("healthy.json", "openai-sub", Health.HEALTHY),
        ("unavailable.json", "openai-sub", Health.UNKNOWN),
        ("no-data.json", "anthropic-sub", Health.UNKNOWN),
    ],
)
def test_health_states(name: str, channel: str, expected: Health) -> None:
    """Each synthetic fixture yields exactly one health state."""
    snapshot = load_fixture(name)
    assert snapshot.stale is False
    assert snapshot.headroom(channel).health is expected


def test_failure_entry_keeps_a_bucket_without_numbers() -> None:
    """An UNAVAILABLE provider still contributes one unknown bucket."""
    snapshot = load_fixture("unavailable.json")
    (bucket,) = snapshot.headroom("openai-sub").buckets
    assert bucket.health is Health.UNKNOWN
    assert bucket.raw_status == "UNAVAILABLE"
    assert bucket.remaining_fraction is None
    assert snapshot.headroom("openai-sub").remaining_fraction is None


def test_worst_state_wins_and_names_the_limiting_bucket() -> None:
    """Channel health is the worst bucket, and it names that bucket."""
    snapshot = load_fixture("mixed-worst-wins.json")
    anthropic = snapshot.headroom("anthropic-sub")
    assert anthropic.health is Health.LIKELY_EXHAUSTED
    assert anthropic.limiting_bucket == "All models — weekly"
    assert anthropic.remaining_fraction == pytest.approx(0.04)


def test_unknown_bucket_clouds_an_otherwise_healthy_channel() -> None:
    """An unknown bucket outranks healthy ones but not a worse state."""
    payload = {
        "observed_at": SYNTHETIC_OBSERVED_AT.isoformat(),
        "subscriptions": [
            {
                "provider": "OpenAI/Codex",
                "bucket": "Weekly limit",
                "status": "COLD",
                "remaining_pct": 90.0,
            },
            {"provider": "OpenAI/Codex", "status": "NO_DATA"},
        ],
    }
    snapshot = parse_availability(
        payload, now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1)
    )
    openai = snapshot.headroom("openai-sub")
    assert openai.health is Health.UNKNOWN
    assert openai.limiting_bucket == "NO_DATA"
    assert openai.remaining_fraction == pytest.approx(0.90)


def test_unknown_providers_are_ignored_but_recorded() -> None:
    """An unrecognised *provider* is dropped into ``ignored``."""
    snapshot = load_fixture("unknown-provider.json")
    assert snapshot.headroom("openai-sub").health is Health.HEALTHY
    assert snapshot.ignored == ("Mystery/Vendor/Weekly limit",)
    # A recognised provider with an unrecognised bucket name is a different
    # thing entirely: it is malformed, not ignored (see Packet 14 below).
    assert len(snapshot.malformed) == 1
    assert "Gemini/agy" in snapshot.malformed[0]


@pytest.mark.parametrize(
    ("remaining", "status", "expected"),
    [
        (None, "COLD", Health.UNKNOWN),
        (0.0, "COLD", Health.EXHAUSTED),
        (-0.01, "COLD", Health.EXHAUSTED),
        (0.05, "COLD", Health.LIKELY_EXHAUSTED),
        (0.0999, "COLD", Health.LIKELY_EXHAUSTED),
        (0.10, "COLD", Health.DEGRADED),
        (0.2499, "COLD", Health.DEGRADED),
        (0.25, "COLD", Health.HEALTHY),
        (0.99, "HOT", Health.DEGRADED),
        (0.99, "TOO FAST", Health.DEGRADED),
        (0.99, "ON TRACK", Health.HEALTHY),
    ],
)
def test_bucket_health_thresholds(
    remaining: float | None, status: str, expected: Health
) -> None:
    """The documented thresholds hold at their boundaries."""
    assert bucket_health(remaining, status) is expected


# --------------------------------------------------------------------------
# Staleness
# --------------------------------------------------------------------------


def test_stale_snapshot_degrades_every_channel_to_unknown() -> None:
    """Past the age ceiling nothing is healthy, but buckets are kept."""
    snapshot = load_fixture("healthy.json", minutes_old=91.0)
    assert snapshot.stale is True
    assert snapshot.age_minutes == pytest.approx(91.0)
    for channel in CHANNELS:
        headroom = snapshot.headroom(channel)
        assert headroom.health is Health.UNKNOWN
        assert headroom.stale is True
    openai = snapshot.headroom("openai-sub")
    assert [bucket.name for bucket in openai.buckets] == ["Weekly limit"]
    assert openai.buckets[0].health is Health.HEALTHY
    assert openai.remaining_fraction == pytest.approx(0.90)
    assert openai.limiting_bucket is None


def test_boundary_age_is_not_stale() -> None:
    """Exactly at the ceiling the snapshot is still trusted."""
    snapshot = load_fixture("healthy.json", minutes_old=90.0)
    assert snapshot.stale is False
    assert snapshot.headroom("openai-sub").health is Health.HEALTHY


def test_a_fresh_write_cannot_launder_an_old_observation() -> None:
    """The older timestamp governs: a new ``written_at`` does not refresh age."""
    now = datetime(2026, 9, 7, 15, 30, tzinfo=timezone.utc)
    snapshot = load_availability(fixture("written-at-newer.json"), now=now)
    # written_at is 30 min old, but observed_at is 3.5 h old, so this is stale.
    assert snapshot.age_minutes == pytest.approx(210.0)
    assert snapshot.stale is True
    assert snapshot.stale_reason == "observed_at is older than 90 minutes"
    assert snapshot.host == "A8Max"
    assert snapshot.observed_at == SYNTHETIC_OBSERVED_AT
    assert snapshot.written_at == datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN


def test_naive_timestamps_are_treated_as_utc() -> None:
    """A timestamp without an offset is read as UTC rather than rejected."""
    payload = {
        "observed_at": "2026-09-07T12:00:00",
        "subscriptions": [
            {
                "provider": "OpenAI/Codex",
                "bucket": "Weekly limit",
                "status": "COLD",
                "remaining_pct": 90.0,
            }
        ],
    }
    snapshot = parse_availability(
        payload, now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=5)
    )
    assert snapshot.observed_at == SYNTHETIC_OBSERVED_AT
    assert snapshot.age_minutes == pytest.approx(5.0)


def test_missing_timestamp_is_stale_with_a_problem() -> None:
    """A snapshot with no timestamp cannot be trusted as current."""
    snapshot = parse_availability({"subscriptions": []})
    assert snapshot.stale is True
    assert snapshot.age_minutes is None
    assert snapshot.problem == "snapshot has no timestamp"
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN


# --------------------------------------------------------------------------
# Failure paths
# --------------------------------------------------------------------------


def test_missing_file_never_raises(tmp_path: Path) -> None:
    """A missing snapshot yields an all-unknown snapshot with a problem."""
    missing = tmp_path / "nope.json"
    snapshot = load_availability(missing)
    assert snapshot.stale is True
    assert snapshot.problem is not None
    assert "cannot read" in snapshot.problem
    assert snapshot.path == missing
    assert set(snapshot.channels) == set(CHANNELS)
    assert all(h.health is Health.UNKNOWN for h in snapshot.channels.values())


def test_malformed_json_never_raises() -> None:
    """Invalid JSON is reported, not raised."""
    snapshot = load_availability(fixture("malformed.json"))
    assert snapshot.stale is True
    assert snapshot.problem is not None
    assert "invalid JSON" in snapshot.problem


def test_missing_subscriptions_never_raises() -> None:
    """A snapshot without ``subscriptions`` is reported, not raised."""
    snapshot = load_availability(fixture("no-subscriptions.json"))
    assert snapshot.stale is True
    assert snapshot.problem == "snapshot missing a 'subscriptions' list"


def test_unparseable_timestamp_never_raises() -> None:
    """A bad ``observed_at`` is reported, not raised."""
    snapshot = load_availability(fixture("bad-timestamp.json"))
    assert snapshot.stale is True
    assert snapshot.problem is not None
    assert "observed_at is not an ISO timestamp" in snapshot.problem


def test_parse_availability_is_strict() -> None:
    """The strict parser raises where the loader reports."""
    with pytest.raises(AvailabilityError):
        parse_availability("{ this is not json")
    with pytest.raises(AvailabilityError):
        parse_availability({"observed_at": "2026-09-07T12:00:00Z"})
    with pytest.raises(AvailabilityError):
        parse_availability("[]")


# --------------------------------------------------------------------------
# Path resolution and serialisation
# --------------------------------------------------------------------------


def test_env_var_overrides_the_default_path(monkeypatch, tmp_path: Path) -> None:
    """``LEE_LLM_ROUTER_AVAILABILITY_FILE`` selects the snapshot file."""
    target = tmp_path / "custom.json"
    target.write_text(fixture("healthy.json").read_text(encoding="utf-8"), "utf-8")
    monkeypatch.setenv(AVAILABILITY_FILE_ENV_VAR, str(target))

    assert resolve_availability_path() == target
    snapshot = load_availability(now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1))
    assert snapshot.path == target
    assert snapshot.headroom("openai-sub").health is Health.HEALTHY


def test_explicit_path_beats_the_env_var(monkeypatch, tmp_path: Path) -> None:
    """An explicit argument wins over the environment variable."""
    monkeypatch.setenv(AVAILABILITY_FILE_ENV_VAR, str(tmp_path / "ignored.json"))
    assert resolve_availability_path(fixture("healthy.json")) == fixture("healthy.json")


def test_default_path_contains_the_hostname(monkeypatch) -> None:
    """Without an override the snapshot is the per-host state file."""
    monkeypatch.delenv(AVAILABILITY_FILE_ENV_VAR, raising=False)
    monkeypatch.setattr("socket.gethostname", lambda: "A8Max")
    resolved = resolve_availability_path()
    assert resolved.name == "A8Max.json"
    assert resolved.parent.as_posix().endswith(
        ".local/state/lee-llm-router/availability"
    )
    assert "~" not in resolved.as_posix()


def test_headroom_for_an_absent_channel_is_unknown() -> None:
    """Asking about a channel nobody reports never raises."""
    snapshot = load_fixture("healthy.json")
    for channel in ("openrouter", "opencode-go", "not-a-channel"):
        headroom = snapshot.headroom(channel)
        assert headroom.channel == channel
        assert headroom.health is Health.UNKNOWN
        assert headroom.remaining_fraction is None
        assert headroom.buckets == ()


def test_to_dict_round_trips_through_json() -> None:
    """``to_dict()`` is JSON-serialisable and keeps the channel keys."""
    snapshot = load_availability(
        LIVE_SAMPLE, now=LIVE_OBSERVED_AT + timedelta(minutes=2)
    )
    payload = json.loads(json.dumps(snapshot.to_dict()))
    assert set(payload["channels"]) == set(CHANNELS)
    assert payload["channels"]["openai-sub"]["health"] == "degraded"
    assert payload["channels"]["openai-sub"]["buckets"][0]["name"] == "Weekly limit"
    assert payload["stale"] is False
    assert payload["problem"] is None
    assert str(Health.HEALTHY) == "healthy"


# --------------------------------------------------------------------------
# Packet 7 — non-finite and out-of-range numbers (H1)
# --------------------------------------------------------------------------


def _one_bucket(remaining_pct: object) -> dict:
    """Build a one-entry payload whose OpenAI bucket carries ``remaining_pct``."""
    return {
        "observed_at": "2026-09-07T12:00:00+00:00",
        "subscriptions": [
            {
                "provider": "OpenAI/Codex",
                "bucket": "Weekly limit",
                "status": "COLD",
                "remaining_pct": remaining_pct,
            }
        ],
    }


@pytest.mark.parametrize(
    "remaining_pct",
    ["nan", "inf", "-inf", "NaN", "Infinity", float("nan"), float("inf")],
)
def test_non_finite_remaining_is_unknown_not_healthy(remaining_pct: object) -> None:
    """NaN and the infinities must never fall through to ``healthy``."""
    snapshot = parse_availability(
        _one_bucket(remaining_pct),
        now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1),
    )
    headroom = snapshot.headroom("openai-sub")
    assert headroom.buckets[0].remaining_fraction is None
    assert headroom.buckets[0].health is Health.UNKNOWN
    assert headroom.health is Health.UNKNOWN
    assert headroom.remaining_fraction is None


@pytest.mark.parametrize("remaining_pct", [150, -5, 100.001, -0.001, "150"])
def test_out_of_range_remaining_is_unknown_not_clamped(remaining_pct: object) -> None:
    """A percentage outside 0–100 is unknown; clamping would invent headroom."""
    snapshot = parse_availability(
        _one_bucket(remaining_pct),
        now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1),
    )
    headroom = snapshot.headroom("openai-sub")
    assert headroom.buckets[0].remaining_fraction is None
    assert headroom.buckets[0].health is Health.UNKNOWN
    assert headroom.health is Health.UNKNOWN


def test_in_range_boundaries_still_parse() -> None:
    """0% and 100% are legitimate and keep their documented health."""
    zero = parse_availability(
        _one_bucket(0), now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1)
    )
    assert zero.headroom("openai-sub").health is Health.EXHAUSTED
    full = parse_availability(
        _one_bucket(100), now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1)
    )
    assert full.headroom("openai-sub").health is Health.HEALTHY


def test_non_finite_side_numbers_are_dropped() -> None:
    """``pace_ratio`` and ``resets_in_hours`` also reject non-finite values."""
    snapshot = load_fixture("non-finite.json")
    bucket = snapshot.headroom("openai-sub").buckets[0]
    assert bucket.pace_ratio is None
    assert bucket.resets_in_hours is None
    assert bucket.health is Health.UNKNOWN
    assert json.dumps(snapshot.to_dict())  # no NaN/Infinity leaks into JSON


def test_bucket_health_rejects_non_finite_and_impossible_fractions() -> None:
    """The public helper is fail-closed on its own."""
    assert bucket_health(float("nan"), "COLD") is Health.UNKNOWN
    assert bucket_health(float("inf"), "COLD") is Health.UNKNOWN
    assert bucket_health(1.5, "COLD") is Health.UNKNOWN
    # A negative fraction is still the fail-closed reading, not unknown.
    assert bucket_health(-0.01, "COLD") is Health.EXHAUSTED


# --------------------------------------------------------------------------
# Packet 7 — future timestamps (H2)
# --------------------------------------------------------------------------


def test_slightly_future_timestamp_is_tolerated() -> None:
    """One minute of clock skew is normal and must not degrade the snapshot."""
    snapshot = load_fixture("future-timestamp.json", minutes_old=-1.0)
    assert snapshot.stale is False
    assert snapshot.stale_reason is None
    assert snapshot.problem is None
    assert snapshot.age_minutes == pytest.approx(-1.0)
    assert snapshot.headroom("openai-sub").health is Health.HEALTHY


def test_future_skew_boundary_is_not_stale() -> None:
    """Exactly at the tolerance the snapshot is still trusted."""
    snapshot = load_fixture(
        "future-timestamp.json", minutes_old=-MAX_FUTURE_SKEW_MINUTES
    )
    assert snapshot.stale is False
    assert snapshot.stale_reason is None
    assert snapshot.headroom("openai-sub").health is Health.HEALTHY


def test_far_future_timestamp_is_stale_and_all_unknown() -> None:
    """A snapshot from the future cannot be current; nothing reads healthy."""
    snapshot = load_fixture("future-timestamp.json", minutes_old=-10.0)
    assert snapshot.stale is True
    assert snapshot.stale_reason == "timestamp is in the future"
    assert snapshot.problem == "timestamp is in the future"
    # The negative age is kept for diagnostics rather than hidden.
    assert snapshot.age_minutes == pytest.approx(-10.0)
    for channel in CHANNELS:
        headroom = snapshot.headroom(channel)
        assert headroom.health is Health.UNKNOWN
        assert headroom.stale is True
        assert headroom.limiting_bucket is None
    assert snapshot.to_dict()["stale_reason"] == "timestamp is in the future"


def test_ordinary_staleness_reports_its_own_reason() -> None:
    """An old snapshot is stale for a different, named reason."""
    snapshot = load_fixture("healthy.json", minutes_old=91.0)
    assert snapshot.stale_reason == "observed_at is older than 90 minutes"
    assert snapshot.problem is None


def test_missing_timestamp_sets_a_stale_reason() -> None:
    """A snapshot with no timestamp names that as its staleness reason."""
    snapshot = parse_availability({"subscriptions": []})
    assert snapshot.stale_reason == "snapshot has no timestamp"


# --------------------------------------------------------------------------
# Packet 7 — naive datetimes are UTC, never host-local (M1)
# --------------------------------------------------------------------------


def test_naive_now_is_read_as_utc_not_host_local() -> None:
    """A naive ``now`` must age a snapshot identically to its aware twin."""
    naive = datetime(2026, 9, 7, 12, 30)
    aware = naive.replace(tzinfo=timezone.utc)
    from_naive = load_availability(fixture("healthy.json"), now=naive)
    from_aware = load_availability(fixture("healthy.json"), now=aware)
    assert from_naive.age_minutes == from_aware.age_minutes == pytest.approx(30.0)
    assert from_naive.stale is from_aware.stale is False


def test_naive_now_in_a_non_utc_host_zone_still_uses_utc(monkeypatch) -> None:
    """Setting TZ must not change how a naive ``now`` is interpreted."""
    import time

    monkeypatch.setenv("TZ", "Pacific/Kiritimati")  # UTC+14
    time.tzset()
    try:
        snapshot = load_availability(
            fixture("healthy.json"), now=datetime(2026, 9, 7, 12, 30)
        )
        assert snapshot.age_minutes == pytest.approx(30.0)
    finally:
        monkeypatch.undo()
        time.tzset()


def test_naive_snapshot_timestamp_parses_as_utc() -> None:
    """An offset-free ``written_at`` is UTC, matching the reader's own clock."""
    payload = {
        "observed_at": "2026-09-07T11:55:00",
        "written_at": "2026-09-07T12:00:00",
        "subscriptions": [],
    }
    snapshot = parse_availability(payload, now=datetime(2026, 9, 7, 12, 15))
    assert snapshot.written_at == datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    assert snapshot.observed_at == datetime(2026, 9, 7, 11, 55, tzinfo=timezone.utc)
    # The oldest timestamp governs, so the age is observed_at's, not written_at's.
    assert snapshot.age_minutes == pytest.approx(20.0)
    assert snapshot.stale is False


# --------------------------------------------------------------------------
# Packet 9 — the oldest timestamp governs staleness (H1)
# --------------------------------------------------------------------------

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def two_stamp_payload(observed_minutes: float, written_minutes: float) -> dict:
    """Build a healthy payload whose stamps are the given ages before ``NOW``."""
    return {
        "observed_at": (NOW - timedelta(minutes=observed_minutes)).isoformat(),
        "written_at": (NOW - timedelta(minutes=written_minutes)).isoformat(),
        "subscriptions": [
            {
                "provider": "OpenAI/Codex",
                "bucket": "Weekly limit",
                "status": "COLD",
                "remaining_pct": 90.0,
            }
        ],
    }


def test_old_observation_with_a_fresh_write_is_stale() -> None:
    """A rewrite does not re-observe quotas, so the old observation governs."""
    snapshot = parse_availability(two_stamp_payload(120.0, 1.0), now=NOW)

    assert snapshot.stale is True
    assert snapshot.age_minutes == pytest.approx(120.0)
    assert snapshot.stale_reason == "observed_at is older than 90 minutes"
    assert snapshot.problem is None
    for channel in CHANNELS:
        assert snapshot.headroom(channel).health is Health.UNKNOWN


def test_old_write_with_a_fresh_observation_is_stale() -> None:
    """The rule is symmetric: an old ``written_at`` governs just as well."""
    snapshot = parse_availability(two_stamp_payload(1.0, 120.0), now=NOW)

    assert snapshot.stale is True
    assert snapshot.age_minutes == pytest.approx(120.0)
    assert snapshot.stale_reason == "written_at is older than 90 minutes"
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN


def test_both_timestamps_fresh_is_not_stale() -> None:
    """Only when both stamps are inside the ceiling is the snapshot trusted."""
    snapshot = parse_availability(two_stamp_payload(30.0, 1.0), now=NOW)

    assert snapshot.stale is False
    assert snapshot.stale_reason is None
    assert snapshot.age_minutes == pytest.approx(30.0)
    assert snapshot.headroom("openai-sub").health is Health.HEALTHY


def test_future_observed_at_is_stale_even_beside_a_fresh_write() -> None:
    """Future skew is checked per timestamp, not just on the governing one."""
    snapshot = parse_availability(two_stamp_payload(-60.0, 1.0), now=NOW)

    assert snapshot.stale is True
    assert snapshot.stale_reason == "timestamp is in the future"
    assert snapshot.problem == "timestamp is in the future"
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN


def test_future_written_at_is_stale_even_beside_a_fresh_observation() -> None:
    """A clock-skewed writer cannot stamp a snapshot into the future either."""
    snapshot = parse_availability(two_stamp_payload(1.0, -60.0), now=NOW)

    assert snapshot.stale is True
    assert snapshot.stale_reason == "timestamp is in the future"
    assert snapshot.problem == "timestamp is in the future"
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN


# --------------------------------------------------------------------------
# Packet 12 — malformed subscription records fail closed (H1)
# --------------------------------------------------------------------------


def _payload(*subscriptions: dict) -> dict:
    """Build a fresh snapshot payload carrying ``subscriptions``."""
    return {
        "observed_at": SYNTHETIC_OBSERVED_AT.isoformat(),
        "subscriptions": list(subscriptions),
    }


def _parse(*subscriptions: dict):
    """Parse a one-minute-old payload carrying ``subscriptions``."""
    return parse_availability(
        _payload(*subscriptions), now=SYNTHETIC_OBSERVED_AT + timedelta(minutes=1)
    )


NO_BUCKET_NO_STATUS = {"provider": "OpenAI/Codex", "remaining_pct": 90}
NO_STATUS = {
    "provider": "OpenAI/Codex",
    "bucket": "Weekly limit",
    "remaining_pct": 90,
}
UNKNOWN_STATUS = {
    "provider": "OpenAI/Codex",
    "bucket": "Weekly limit",
    "status": "BANANA",
    "remaining_pct": 90,
}


@pytest.mark.parametrize(
    "entry",
    [NO_BUCKET_NO_STATUS, NO_STATUS, UNKNOWN_STATUS],
    ids=["no-bucket-no-status", "no-status", "unknown-status"],
)
def test_malformed_records_are_unknown_not_healthy(entry: dict) -> None:
    """A record the reader cannot score must never read as ``healthy``."""
    snapshot = _parse(entry)
    headroom = snapshot.headroom("openai-sub")

    assert headroom.health is Health.UNKNOWN
    (bucket,) = headroom.buckets
    assert bucket.health is Health.UNKNOWN
    assert bucket.remaining_fraction is None
    assert headroom.remaining_fraction is None
    assert len(snapshot.malformed) == 1
    assert snapshot.to_dict()["malformed_count"] == 1


def test_malformed_raw_status_is_preserved_or_marked() -> None:
    """The badge is kept as given; an absent one becomes ``MALFORMED``."""
    absent = _parse(NO_STATUS).headroom("openai-sub").buckets[0]
    assert absent.raw_status == "MALFORMED"

    unknown = _parse(UNKNOWN_STATUS).headroom("openai-sub").buckets[0]
    assert unknown.raw_status == "BANANA"


def test_malformed_record_clouds_an_otherwise_healthy_channel() -> None:
    """One malformed bucket outranks a healthy sibling on the same channel."""
    good = {
        "provider": "OpenAI/Codex",
        "bucket": "Weekly limit",
        "status": "COLD",
        "remaining_pct": 90.0,
    }
    snapshot = _parse(good, UNKNOWN_STATUS)
    headroom = snapshot.headroom("openai-sub")

    assert headroom.health is Health.UNKNOWN
    assert [b.health for b in headroom.buckets] == [Health.HEALTHY, Health.UNKNOWN]
    assert snapshot.ignored == ()
    assert len(snapshot.malformed) == 1


@pytest.mark.parametrize(
    "remaining_pct",
    ["90", None, True, "ninety", 150, float("nan")],
    ids=["numeric-string", "null", "bool", "text", "out-of-range", "nan"],
)
def test_remaining_pct_must_be_a_finite_in_range_number(remaining_pct: object) -> None:
    """Anything that is not a finite 0–100 number makes the bucket unknown."""
    snapshot = _parse(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "COLD",
            "remaining_pct": remaining_pct,
        }
    )
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN
    assert len(snapshot.malformed) == 1


def test_use_it_status_is_healthy_by_percentage() -> None:
    """``USE IT`` means "spend it", not "something is wrong"."""
    snapshot = _parse(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "USE IT",
            "remaining_pct": 80.0,
        }
    )
    headroom = snapshot.headroom("openai-sub")
    assert headroom.health is Health.HEALTHY
    assert headroom.remaining_fraction == pytest.approx(0.80)
    assert snapshot.malformed == ()
    assert bucket_health(0.80, "USE IT") is Health.HEALTHY


def test_no_data_status_is_unknown_even_with_a_percentage() -> None:
    """``NO DATA`` means nothing was measured; the number is meaningless."""
    snapshot = _parse(
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "NO DATA",
            "remaining_pct": 90.0,
        }
    )
    headroom = snapshot.headroom("openai-sub")
    assert headroom.health is Health.UNKNOWN
    assert headroom.buckets[0].health is Health.UNKNOWN
    # The badge is recognised, so this is not a malformed record.
    assert snapshot.malformed == ()
    assert bucket_health(0.90, "NO DATA") is Health.UNKNOWN
    assert bucket_health(0.90, "NO_DATA") is Health.UNKNOWN


def test_gemini_record_without_a_bucket_clouds_both_gemini_channels() -> None:
    """An unnamed Gemini bucket could be either quota, so neither is trusted."""
    snapshot = _parse(
        {"provider": "Gemini/agy", "status": "COLD", "remaining_pct": 95.0}
    )
    for channel in ("gemini-sub", "gemini-sub-thirdparty"):
        headroom = snapshot.headroom(channel)
        assert headroom.health is Health.UNKNOWN
        assert [b.health for b in headroom.buckets] == [Health.UNKNOWN]
        assert headroom.remaining_fraction is None
    # One entry, recorded once, even though it lands on two channels.
    assert len(snapshot.malformed) == 1


def test_status_matching_is_case_sensitive() -> None:
    """``ai-subs`` emits upper-case badges; a lower-case one is not one of them."""
    from lee_llm_router.availability import is_known_status

    assert is_known_status("ON TRACK")
    assert is_known_status("  COLD  ")
    assert is_known_status("NO_DATA")
    assert not is_known_status("on track")
    assert not is_known_status("Cold")
    assert not is_known_status("BANANA")
    assert not is_known_status("")


def test_wellformed_records_are_not_flagged() -> None:
    """The live sample carries no malformed entries and keeps its healths."""
    snapshot = load_availability(
        LIVE_SAMPLE, now=LIVE_OBSERVED_AT + timedelta(minutes=2)
    )
    assert snapshot.malformed == ()
    assert snapshot.to_dict()["malformed_count"] == 0
    assert {c: snapshot.headroom(c).health for c in CHANNELS} == {
        "openai-sub": Health.DEGRADED,
        "anthropic-sub": Health.DEGRADED,
        "gemini-sub": Health.DEGRADED,
        "gemini-sub-thirdparty": Health.HEALTHY,
        "openrouter": Health.UNKNOWN,
        "opencode-go": Health.UNKNOWN,
    }


def test_provider_level_failure_entries_are_not_malformed() -> None:
    """``UNAVAILABLE``/``NO_DATA`` records legitimately carry no bucket."""
    snapshot = _parse(
        {"provider": "OpenAI/Codex", "status": "UNAVAILABLE", "error": "no codex"},
        {"provider": "Anthropic/Claude", "status": "NO_DATA"},
    )
    assert snapshot.malformed == ()
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN
    assert snapshot.headroom("anthropic-sub").health is Health.UNKNOWN


def test_malformed_fixture_snapshot_fails_closed() -> None:
    """The synthetic malformed-records fixture reads as unknown end to end."""
    snapshot = load_fixture("malformed-records.json")
    assert snapshot.stale is False
    assert snapshot.headroom("openai-sub").health is Health.UNKNOWN
    assert snapshot.headroom("anthropic-sub").health is Health.UNKNOWN
    assert len(snapshot.malformed) == 2
    assert json.dumps(snapshot.to_dict())


# --------------------------------------------------------------------------
# Packet 14 — an unroutable Gemini bucket name must not vanish (H1)
# --------------------------------------------------------------------------


def test_renamed_gemini_bucket_clouds_both_gemini_channels() -> None:
    """An exhausted bucket under an unrecognised name must not read healthy."""
    snapshot = _parse(
        {
            "provider": "Gemini/agy",
            "bucket": "Gemini models — weekly",
            "status": "COLD",
            "remaining_pct": 90.0,
        },
        {
            "provider": "Gemini/agy",
            "bucket": "Gemini flash — weekly",
            "status": "COLD",
            "remaining_pct": 0,
        },
    )

    for channel in GEMINI_CHANNELS:
        headroom = snapshot.headroom(channel)
        assert headroom.health is Health.UNKNOWN, channel

    # The renamed bucket lands on both Gemini channels, alongside the healthy
    # one it cannot be distinguished from.
    own = snapshot.headroom("gemini-sub")
    assert [bucket.name for bucket in own.buckets] == [
        "Gemini models — weekly",
        "Gemini flash — weekly",
    ]
    assert [bucket.health for bucket in own.buckets] == [
        Health.HEALTHY,
        Health.UNKNOWN,
    ]
    thirdparty = snapshot.headroom("gemini-sub-thirdparty")
    assert [bucket.name for bucket in thirdparty.buckets] == ["Gemini flash — weekly"]
    assert thirdparty.buckets[0].health is Health.UNKNOWN


def test_unroutable_gemini_record_is_malformed_never_ignored() -> None:
    """It is recorded once, in ``malformed``, with its raw status preserved."""
    snapshot = _parse(
        {
            "provider": "Gemini/agy",
            "bucket": "Gemini flash — weekly",
            "status": "TOO FAST",
            "remaining_pct": 0,
        }
    )

    assert snapshot.ignored == ()
    assert len(snapshot.malformed) == 1
    assert "Gemini flash — weekly" in snapshot.malformed[0]
    assert snapshot.to_dict()["malformed_count"] == 1
    bucket = snapshot.headroom("gemini-sub").buckets[0]
    assert bucket.raw_status == "TOO FAST"
    assert bucket.remaining_fraction is None


def test_unroutable_gemini_bucket_does_not_invent_a_percentage() -> None:
    """Its numbers describe no channel, so no channel may report them."""
    snapshot = _parse(
        {
            "provider": "Gemini/agy",
            "bucket": "Gemini flash — weekly",
            "status": "COLD",
            "remaining_pct": 100.0,
        }
    )
    for channel in GEMINI_CHANNELS:
        assert snapshot.headroom(channel).remaining_fraction is None


def test_channel_routing_helpers_agree_on_ambiguity() -> None:
    """``channels_for`` fans out exactly where ``is_routable_bucket`` says no."""
    assert channels_for("Gemini/agy", "Gemini models — weekly") == ("gemini-sub",)
    assert channels_for("Gemini/agy", "Claude/GPT models — 5-hour") == (
        "gemini-sub-thirdparty",
    )
    assert channels_for("Gemini/agy", "Gemini flash — weekly") == GEMINI_CHANNELS
    assert channels_for("Gemini/agy", "") == GEMINI_CHANNELS
    # An unknown provider still routes nowhere at all.
    assert channels_for("Mystery/Vendor", "Weekly limit") == ()

    assert is_routable_bucket("Gemini/agy", "Gemini models — weekly")
    assert is_routable_bucket("OpenAI/Codex", "anything at all")
    assert not is_routable_bucket("Gemini/agy", "Gemini flash — weekly")
    assert not is_routable_bucket("Gemini/agy", "")
    assert not is_routable_bucket("Mystery/Vendor", "Weekly limit")


def test_live_sample_routing_is_unaffected_by_the_fan_out() -> None:
    """Every live Gemini bucket still pins to exactly one channel."""
    snapshot = load_availability(
        LIVE_SAMPLE, now=LIVE_OBSERVED_AT + timedelta(minutes=2)
    )
    assert snapshot.malformed == ()
    assert snapshot.ignored == ()
    assert len(snapshot.headroom("gemini-sub").buckets) == 2
    assert len(snapshot.headroom("gemini-sub-thirdparty").buckets) == 2
    assert snapshot.headroom("gemini-sub").health is Health.DEGRADED
    assert snapshot.headroom("gemini-sub-thirdparty").health is Health.HEALTHY
