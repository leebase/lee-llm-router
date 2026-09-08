"""Tests for the append-only resolution event ledger."""

from __future__ import annotations

import ast
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lee_llm_router import events as events_module
from lee_llm_router.events import (
    EVENT_FIELDS,
    EVENTS_FILE_ENV_VAR,
    MAX_EVENT_BYTES,
    EventTooLarge,
    append_event,
    build_event,
    encode_event,
    read_events,
    resolve_events_path,
)

BASE_FIELDS = {
    "crew": "gemini-flash-tiered",
    "role": "coder",
    "mode": "strict",
    "worker_id": "flash-high",
    "provider": "gemini",
    "model": "gemini-3.7-flash",
    "channel": "gemini-sub",
    "headroom": "healthy",
    "reason": "top eligible worker for coder",
    "route_id": "gemini/gemini-3.7-flash/high",
    "snapshot_stale": False,
}


def make_event(**overrides):
    """Build a valid event with optional field overrides."""
    fields = dict(BASE_FIELDS)
    fields.update(overrides)
    return build_event(**fields)


def test_build_event_has_exactly_the_contract_keys_in_order():
    event = make_event()
    assert tuple(event) == EVENT_FIELDS


def test_build_event_defaults():
    event = make_event()
    assert event["harness"] == "cli"
    assert event["host"] == socket.gethostname()
    assert event["effort"] is None
    assert event["authorized_by"] is None
    assert event["snapshot_observed_at"] is None
    parsed = datetime.fromisoformat(event["ts"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)
    assert parsed.microsecond == 0


def test_build_event_normalises_timestamps_to_utc_seconds():
    observed = datetime(2026, 9, 7, 18, 7, 40, 975124, tzinfo=timezone.utc)
    event = make_event(ts=observed, snapshot_observed_at=observed)
    assert event["ts"] == "2026-09-07T18:07:40+00:00"
    assert event["snapshot_observed_at"] == "2026-09-07T18:07:40+00:00"


def test_build_event_rejects_unknown_key():
    with pytest.raises(ValueError, match="unknown event field"):
        make_event(cost_usd=0.01)


def test_build_event_rejects_missing_key():
    fields = dict(BASE_FIELDS)
    del fields["route_id"]
    with pytest.raises(ValueError, match="missing event field"):
        build_event(**fields)


def test_build_event_rejects_authorized_by_outside_bind():
    with pytest.raises(ValueError, match="only allowed when mode"):
        make_event(authorized_by="lee")


def test_build_event_allows_authorized_by_in_bind_mode():
    event = make_event(mode="bind", authorized_by="lee")
    assert event["authorized_by"] == "lee"


def test_build_event_requires_bool_snapshot_stale():
    with pytest.raises(ValueError, match="snapshot_stale must be a bool"):
        make_event(snapshot_stale="yes")


def test_two_appends_produce_two_ordered_parseable_lines(tmp_path):
    ledger = tmp_path / "events.jsonl"
    append_event(make_event(reason="first"), ledger)
    append_event(make_event(reason="second"), ledger)

    raw_lines = ledger.read_bytes().decode("utf-8").split("\n")
    assert raw_lines[-1] == ""
    assert len(raw_lines) == 3
    decoded = [json.loads(line) for line in raw_lines[:2]]
    assert [item["reason"] for item in decoded] == ["first", "second"]


def test_newline_in_reason_stays_one_physical_line(tmp_path):
    ledger = tmp_path / "events.jsonl"
    append_event(make_event(reason="line one\nline two"), ledger)

    text = ledger.read_text(encoding="utf-8")
    assert text.count("\n") == 1
    assert json.loads(text)["reason"] == "line one\nline two"


def test_size_limit_is_bytes_not_characters(tmp_path):
    reason = "€" * 1400  # 1400 characters, 4200 UTF-8 bytes
    assert len(reason) < MAX_EVENT_BYTES
    event = make_event(reason=reason)
    with pytest.raises(EventTooLarge):
        encode_event(event)
    ledger = tmp_path / "events.jsonl"
    with pytest.raises(EventTooLarge):
        append_event(event, ledger)
    assert not ledger.exists()


def test_line_at_the_limit_is_accepted(tmp_path):
    event = make_event(reason="x")
    padding = MAX_EVENT_BYTES - len(encode_event(event))
    event = make_event(reason="x" * (1 + padding))
    assert len(encode_event(event)) == MAX_EVENT_BYTES
    ledger = tmp_path / "events.jsonl"
    append_event(event, ledger)
    assert len(ledger.read_bytes()) == MAX_EVENT_BYTES


def test_path_precedence_explicit_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv(EVENTS_FILE_ENV_VAR, str(tmp_path / "from-env.jsonl"))
    explicit = tmp_path / "explicit.jsonl"
    assert resolve_events_path(explicit) == explicit


def test_path_precedence_env_beats_default(tmp_path, monkeypatch):
    from_env = tmp_path / "from-env.jsonl"
    monkeypatch.setenv(EVENTS_FILE_ENV_VAR, str(from_env))
    assert resolve_events_path() == from_env


def test_default_path_is_per_host_jsonl(monkeypatch):
    monkeypatch.delenv(EVENTS_FILE_ENV_VAR, raising=False)
    resolved = resolve_events_path()
    assert resolved.name == f"{socket.gethostname()}.jsonl"
    assert resolved.parent == events_module.DEFAULT_EVENTS_DIR.expanduser()
    assert "~" not in str(resolved)


def test_append_creates_private_file_and_directory(tmp_path):
    ledger = tmp_path / "state" / "events" / "host.jsonl"
    written = append_event(make_event(), ledger)
    assert written == ledger
    assert os.stat(ledger).st_mode & 0o777 == 0o600
    assert os.stat(ledger.parent).st_mode & 0o777 == 0o700


def test_append_uses_env_path_when_none_given(tmp_path, monkeypatch):
    ledger = tmp_path / "env" / "events.jsonl"
    monkeypatch.setenv(EVENTS_FILE_ENV_VAR, str(ledger))
    assert append_event(make_event()) == ledger
    assert len(read_events(ledger)) == 1


def test_short_write_raises_and_does_not_loop(tmp_path, monkeypatch):
    ledger = tmp_path / "events.jsonl"
    calls = []
    real_write = os.write

    def short_write(fd, data):
        calls.append(len(data))
        return real_write(fd, data[:5])

    monkeypatch.setattr(events_module.os, "write", short_write)
    with pytest.raises(events_module.ShortWriteError):
        append_event(make_event(), ledger)
    assert len(calls) == 1


def test_read_events_round_trips_and_skips_blank_lines(tmp_path):
    ledger = tmp_path / "events.jsonl"
    first = make_event(reason="first")
    second = make_event(reason="second")
    append_event(first, ledger)
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write("\n   \n")
    append_event(second, ledger)

    assert read_events(ledger) == [first, second]


def test_read_events_surfaces_malformed_lines_without_hiding_good_ones(tmp_path):
    ledger = tmp_path / "events.jsonl"
    append_event(make_event(reason="good one"), ledger)
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write('{"broken": \n')
        handle.write("42\n")
    append_event(make_event(reason="good two"), ledger)

    records = read_events(ledger)
    assert [record.get("reason") for record in records] == [
        "good one",
        None,
        None,
        "good two",
    ]
    assert records[1] == {"_malformed": '{"broken": '}
    assert records[2] == {"_malformed": "42"}


def test_module_has_no_network_subprocess_or_provider_imports():
    tree = ast.parse(Path(events_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    roots = {name.split(".")[0] for name in imported}
    assert roots == {
        "__future__",
        "json",
        "os",
        "socket",
        "datetime",
        "pathlib",
        "typing",
    }
    forbidden = {"subprocess", "requests", "httpx", "urllib", "http", "lee_llm_router"}
    assert not roots & forbidden
