"""Tests for ``scripts/refresh_availability.sh``.

The script is exercised through ``--input``, which replaces the live ai-subs
run with a captured stdout file, so no provider CLI is ever invoked here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "refresh_availability.sh"
SAMPLE = (
    Path(__file__).parent / "fixtures" / "availability" / "live-sample-2026-09-07.json"
)

DASHBOARD_NOISE = """
AI Subscriptions
================
OpenAI/Codex     Weekly limit          52% used
Anthropic/Claude Current session       27% used

Legend: COLD / ON TRACK / HOT / TOO FAST
"""


def _capture_file(tmp_path: Path, *, marker: bool = True) -> Path:
    """Write a fake ai-subs stdout capture into ``tmp_path``."""
    payload = SAMPLE.read_text(encoding="utf-8").strip()
    parts = [DASHBOARD_NOISE]
    if marker:
        parts.append("AFTER_REPORT_JSON")
        parts.append(payload)
    parts.append("")
    path = tmp_path / "ai-subs-stdout.txt"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def _run(args: list[str], snapshot: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["LEE_LLM_ROUTER_AVAILABILITY_FILE"] = str(snapshot)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture(autouse=True)
def _require_script() -> None:
    if not SCRIPT.is_file():
        pytest.skip("refresh_availability.sh not present")


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)


def test_writes_a_stamped_snapshot(tmp_path: Path) -> None:
    capture = _capture_file(tmp_path)
    snapshot = tmp_path / "state" / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    assert snapshot.is_file()
    written = json.loads(snapshot.read_text(encoding="utf-8"))
    expected = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert written["subscriptions"] == expected["subscriptions"]
    assert written["observed_at"] == expected["observed_at"]
    assert written["host"]
    assert written["written_at"]
    assert written["written_at"].endswith("Z") or "+00:00" in written["written_at"]


def test_written_at_parses_as_utc(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    capture = _capture_file(tmp_path)
    snapshot = tmp_path / "A8Max.json"

    assert _run(["--input", str(capture)], snapshot).returncode == 0

    stamp = json.loads(snapshot.read_text(encoding="utf-8"))["written_at"]
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_dry_run_prints_json_and_writes_nothing(tmp_path: Path) -> None:
    capture = _capture_file(tmp_path)
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--dry-run", "--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    assert not snapshot.exists()
    printed = json.loads(result.stdout)
    assert printed["host"]
    assert printed["written_at"]
    assert len(printed["subscriptions"]) == 9


def test_missing_marker_fails_and_leaves_snapshot_untouched(tmp_path: Path) -> None:
    capture = _capture_file(tmp_path, marker=False)
    snapshot = tmp_path / "A8Max.json"
    snapshot.write_text('{"subscriptions": [], "sentinel": true}', encoding="utf-8")

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode != 0
    assert "AFTER_REPORT_JSON" in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert json.loads(snapshot.read_text(encoding="utf-8"))["sentinel"] is True


def test_missing_input_file_fails(tmp_path: Path) -> None:
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(tmp_path / "nope.txt")], snapshot)

    assert result.returncode != 0
    assert "not found" in result.stderr


def test_invalid_json_after_marker_fails(tmp_path: Path) -> None:
    capture = tmp_path / "ai-subs-stdout.txt"
    capture.write_text("AFTER_REPORT_JSON\n{not json at all}\n", encoding="utf-8")
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode != 0
    assert not snapshot.exists()


def test_leaves_no_temporary_files(tmp_path: Path) -> None:
    capture = _capture_file(tmp_path)
    snapshot = tmp_path / "state" / "A8Max.json"

    assert _run(["--input", str(capture)], snapshot).returncode == 0

    assert not list(snapshot.parent.glob("*.tmp.*"))
    assert [p.name for p in snapshot.parent.iterdir()] == ["A8Max.json"]


# --------------------------------------------------------------------------
# Packet 7 — payload validation (M2)
# --------------------------------------------------------------------------


def _capture_payload(tmp_path: Path, payload: str) -> Path:
    """Write a capture whose post-marker line is exactly ``payload``."""
    path = tmp_path / "ai-subs-stdout.txt"
    path.write_text(f"{DASHBOARD_NOISE}\nAFTER_REPORT_JSON\n{payload}\n", "utf-8")
    return path


@pytest.mark.parametrize(
    "payload",
    [
        '{"foo":1}',
        '{"observed_at":"2026-09-07T12:00:00Z"}',
        '{"subscriptions":[]}',
        '{"observed_at":"2026-09-07T12:00:00Z","subscriptions":{}}',
        '{"observed_at":123,"subscriptions":[]}',
        "[]",
        '"a string"',
    ],
)
def test_payload_without_the_required_shape_is_rejected(
    tmp_path: Path, payload: str
) -> None:
    """Only a JSON object with a subscriptions list and observed_at string wins."""
    capture = _capture_payload(tmp_path, payload)
    snapshot = tmp_path / "A8Max.json"
    prior = '{"subscriptions": [], "observed_at": "x", "sentinel": true}'
    snapshot.write_text(prior, encoding="utf-8")

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 1
    assert len(result.stderr.strip().splitlines()) == 1
    assert result.stderr.startswith("refresh_availability:")
    assert snapshot.read_text(encoding="utf-8") == prior
    assert not list(snapshot.parent.glob("*.tmp.*"))


def test_empty_subscriptions_list_is_accepted(tmp_path: Path) -> None:
    """An empty list is a legitimate observation, not a malformed payload."""
    capture = _capture_payload(
        tmp_path, '{"observed_at":"2026-09-07T12:00:00Z","subscriptions":[]}'
    )
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    assert json.loads(snapshot.read_text(encoding="utf-8"))["subscriptions"] == []


# --------------------------------------------------------------------------
# Packet 7 — temp-file cleanup (M3)
# --------------------------------------------------------------------------


def test_failure_after_temp_creation_leaves_no_temp_file(tmp_path: Path) -> None:
    """A rename that cannot land must not strand a ``*.tmp.*`` beside it."""
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")

    capture = _capture_file(tmp_path)
    out_dir = tmp_path / "state"
    out_dir.mkdir()
    # The destination path is a read-only directory, so the temp file is
    # written successfully and only the `mv` fails.
    blocker = out_dir / "A8Max.json"
    blocker.mkdir()
    blocker.chmod(0o500)
    try:
        result = _run(["--input", str(capture)], blocker)

        assert result.returncode != 0
        assert not list(out_dir.glob("*.tmp.*"))
        assert list(blocker.iterdir()) == []
    finally:
        blocker.chmod(0o700)


# --------------------------------------------------------------------------
# Packet 9 — observed_at must parse as ISO 8601 (M1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "observed_at",
    ["yesterday-ish", "", "2026-13-45T99:99:99Z", "1757260000"],
)
def test_unparseable_observed_at_is_rejected(tmp_path: Path, observed_at: str) -> None:
    """A string that is not an ISO timestamp must not replace a good snapshot."""
    payload = json.dumps({"observed_at": observed_at, "subscriptions": []})
    capture = _capture_payload(tmp_path, payload)
    snapshot = tmp_path / "A8Max.json"
    prior = '{"subscriptions": [], "observed_at": "2026-09-07T12:00:00Z"}'
    snapshot.write_text(prior, encoding="utf-8")

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 1
    assert len(result.stderr.strip().splitlines()) == 1
    assert result.stderr.startswith("refresh_availability:")
    assert snapshot.read_text(encoding="utf-8") == prior
    assert not list(snapshot.parent.glob("*.tmp.*"))


def test_iso_observed_at_variants_are_accepted(tmp_path: Path) -> None:
    """``Z``-suffixed, offset, and offset-free ISO timestamps all pass."""
    for observed_at in (
        "2026-09-07T12:00:00Z",
        "2026-09-07T07:00:00-05:00",
        "2026-09-07T12:00:00",
    ):
        capture = _capture_payload(
            tmp_path, json.dumps({"observed_at": observed_at, "subscriptions": []})
        )
        snapshot = tmp_path / "A8Max.json"

        result = _run(["--input", str(capture)], snapshot)

        assert result.returncode == 0, result.stderr
        written = json.loads(snapshot.read_text(encoding="utf-8"))
        assert written["observed_at"] == observed_at


# --------------------------------------------------------------------------
# Packet 12 — subscription records must be well-formed (H1)
# --------------------------------------------------------------------------

GOOD_ENTRY = {
    "provider": "OpenAI/Codex",
    "bucket": "Weekly limit",
    "status": "COLD",
    "remaining_pct": 90.0,
}
PRIOR_SNAPSHOT = '{"subscriptions": [], "observed_at": "2026-09-07T12:00:00Z"}'


def _subscriptions_payload(*entries: object) -> str:
    """Serialise a valid-envelope payload carrying ``entries``."""
    return json.dumps(
        {"observed_at": "2026-09-07T12:00:00Z", "subscriptions": list(entries)}
    )


def _reject(tmp_path: Path, payload: str) -> subprocess.CompletedProcess[str]:
    """Run the script on ``payload`` over an existing snapshot and assert it fails."""
    capture = _capture_payload(tmp_path, payload)
    snapshot = tmp_path / "A8Max.json"
    snapshot.write_text(PRIOR_SNAPSHOT, encoding="utf-8")

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 1
    assert len(result.stderr.strip().splitlines()) == 1
    assert result.stderr.startswith("refresh_availability:")
    assert snapshot.read_text(encoding="utf-8") == PRIOR_SNAPSHOT
    assert not list(snapshot.parent.glob("*.tmp.*"))
    return result


def test_entry_missing_bucket_is_rejected(tmp_path: Path) -> None:
    """A quota record with no bucket name must not replace a good snapshot."""
    entry = {k: v for k, v in GOOD_ENTRY.items() if k != "bucket"}
    result = _reject(tmp_path, _subscriptions_payload(entry))
    assert "bucket" in result.stderr


def test_entry_with_empty_bucket_is_rejected(tmp_path: Path) -> None:
    """A blank bucket name is as unusable as a missing one."""
    result = _reject(tmp_path, _subscriptions_payload({**GOOD_ENTRY, "bucket": "  "}))
    assert "bucket" in result.stderr


def test_entry_with_non_numeric_remaining_pct_is_rejected(tmp_path: Path) -> None:
    """``remaining_pct`` must be a number, not a numeric-looking string."""
    result = _reject(
        tmp_path, _subscriptions_payload({**GOOD_ENTRY, "remaining_pct": "90"})
    )
    assert "remaining_pct" in result.stderr


def test_entry_missing_remaining_pct_is_rejected(tmp_path: Path) -> None:
    """An absent percentage is rejected at the writer, not scored at the reader."""
    entry = {k: v for k, v in GOOD_ENTRY.items() if k != "remaining_pct"}
    result = _reject(tmp_path, _subscriptions_payload(entry))
    assert "remaining_pct" in result.stderr


def test_entry_missing_status_is_rejected(tmp_path: Path) -> None:
    """A quota record with no status badge is rejected."""
    entry = {k: v for k, v in GOOD_ENTRY.items() if k != "status"}
    result = _reject(tmp_path, _subscriptions_payload(entry))
    assert "status" in result.stderr


def test_entry_missing_provider_is_rejected(tmp_path: Path) -> None:
    """Every element needs a provider string, failure entries included."""
    entry = {k: v for k, v in GOOD_ENTRY.items() if k != "provider"}
    result = _reject(tmp_path, _subscriptions_payload(entry))
    assert "provider" in result.stderr


def test_non_object_subscription_element_is_rejected(tmp_path: Path) -> None:
    """A list of strings is not a list of subscription records."""
    result = _reject(tmp_path, _subscriptions_payload("OpenAI/Codex"))
    assert "not a JSON object" in result.stderr


def test_failure_entries_need_no_bucket_or_percentage(tmp_path: Path) -> None:
    """``UNAVAILABLE``/``NO_DATA`` records pass exactly as ai-subs emits them."""
    payload = _subscriptions_payload(
        {"provider": "OpenAI/Codex", "status": "UNAVAILABLE", "error": "no codex"},
        {"provider": "Anthropic/Claude", "status": "NO_DATA"},
        GOOD_ENTRY,
    )
    capture = _capture_payload(tmp_path, payload)
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    assert len(json.loads(snapshot.read_text(encoding="utf-8"))["subscriptions"]) == 3


def test_the_live_sample_still_passes_validation(tmp_path: Path) -> None:
    """The real snapshot must not be rejected by the stricter rule."""
    capture = _capture_file(tmp_path)
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    assert len(json.loads(snapshot.read_text(encoding="utf-8"))["subscriptions"]) == 9


# --------------------------------------------------------------------------
# Packet 13 — writer validation matches the reader's contract (H1)
# --------------------------------------------------------------------------


def test_unknown_status_badge_is_rejected(tmp_path: Path) -> None:
    """A badge outside ``availability.KNOWN_STATUSES`` is not a scorable record."""
    result = _reject(
        tmp_path, _subscriptions_payload({**GOOD_ENTRY, "status": "BANANA"})
    )
    assert "status" in result.stderr


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_remaining_pct_is_rejected(tmp_path: Path, token: str) -> None:
    """``NaN``/``Infinity`` parse as floats but cannot be scored as a percentage."""
    payload = (
        '{"observed_at":"2026-09-07T12:00:00Z","subscriptions":['
        '{"provider":"OpenAI/Codex","bucket":"Weekly limit","status":"COLD",'
        f'"remaining_pct":{token}'
        "}]}"
    )
    result = _reject(tmp_path, payload)
    assert "remaining_pct" in result.stderr


@pytest.mark.parametrize("remaining", [150, -5, 100.001])
def test_out_of_range_remaining_pct_is_rejected(
    tmp_path: Path, remaining: float
) -> None:
    """A percentage outside 0-100 is a parsing bug, not a headroom reading."""
    result = _reject(
        tmp_path, _subscriptions_payload({**GOOD_ENTRY, "remaining_pct": remaining})
    )
    assert "remaining_pct" in result.stderr


def test_boolean_remaining_pct_is_rejected(tmp_path: Path) -> None:
    """``true`` is an int in Python and must not slip through as 1 percent."""
    result = _reject(
        tmp_path, _subscriptions_payload({**GOOD_ENTRY, "remaining_pct": True})
    )
    assert "remaining_pct" in result.stderr


def test_no_data_failure_entry_without_bucket_is_accepted(tmp_path: Path) -> None:
    """``NO_DATA`` short-circuits before the badge and percentage rules."""
    capture = _capture_payload(
        tmp_path,
        _subscriptions_payload({"provider": "Google/Gemini", "status": "NO_DATA"}),
    )
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    written = json.loads(snapshot.read_text(encoding="utf-8"))
    assert written["subscriptions"][0]["status"] == "NO_DATA"


@pytest.mark.parametrize(
    ("status", "remaining"),
    [("USE IT", 80), ("COLD", 100), ("TOO FAST", 0), ("ON TRACK", 55.5), ("HOT", 12)],
)
def test_every_known_badge_and_boundary_percentage_is_accepted(
    tmp_path: Path, status: str, remaining: float
) -> None:
    """The whole ai-subs vocabulary, and both range endpoints, still pass."""
    capture = _capture_payload(
        tmp_path,
        _subscriptions_payload(
            {**GOOD_ENTRY, "status": status, "remaining_pct": remaining}
        ),
    )
    snapshot = tmp_path / "A8Max.json"

    result = _run(["--input", str(capture)], snapshot)

    assert result.returncode == 0, result.stderr
    written = json.loads(snapshot.read_text(encoding="utf-8"))
    assert written["subscriptions"][0]["status"] == status


def test_script_status_set_matches_the_reader() -> None:
    """The hardcoded badge set must not drift from ``availability.KNOWN_STATUSES``.

    The script cannot import the package — it runs from cron — so the set is
    duplicated by hand. This reads the literal back out of the file text
    (never executing it) so a one-sided edit fails here instead of silently
    rejecting a badge the reader accepts.
    """
    from lee_llm_router.availability import KNOWN_STATUSES

    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^KNOWN_STATUSES = \{(.*?)^\}", source, re.MULTILINE | re.DOTALL)
    assert match is not None, "KNOWN_STATUSES literal not found in the script"
    in_script = set(re.findall(r'"([^"]+)"', match.group(1)))

    assert in_script == set(KNOWN_STATUSES) | {"NO_DATA"}
