"""Explicit Lee authorization for a pinned router-run dispatch."""

from __future__ import annotations

import json

import pytest

from lee_llm_router.availability import load_availability
from lee_llm_router.staffing import load_staffing_catalog
from lee_llm_router.staffing.run import RunSelectionError, select_route
from tests.test_staffing_run import (
    CLAUDE_ROUTE,
    IMPL_CLASS,
    LaunchRecorder,
    _run_cli,
    _write_snapshot,
)

pytest_plugins = ("tests.test_staffing_run",)

OPUS_ROUTE = "claude-claude-opus-5-high-anthropic-sub"


@pytest.mark.parametrize(
    ("extra", "expected_mode", "expected_authorizer"),
    [
        ((), "strict", None),
        (("--authorized-by", "lee", "--reason", "Lee chose this route"), "bind", "lee"),
    ],
)
def test_eligible_explicit_route_preserves_selection_and_reason(
    monkeypatch,
    capsys,
    catalog_dir,
    snapshot,
    packet,
    scratch_state,
    extra,
    expected_mode,
    expected_authorizer,
):
    """An ordinary pin stays strict; an accepted declaration keeps its reason."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=CLAUDE_ROUTE,
        extra=extra,
        launcher=launcher,
    )
    assert code == 3
    assert len(launcher.processes) == 1
    payload = json.loads(captured.out)
    assert payload["selection"]["basis"] == "explicit"
    assert payload["router_event"]["mode"] == expected_mode
    assert payload["router_event"]["authorized_by"] == expected_authorizer
    assert ("Lee chose this route" in payload["selection"]["reason"]) == bool(extra)
    assert scratch_state["attempts"].exists()


def test_authorized_opus_cli_dispatch_records_authority_and_reason(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state
):
    """The CLI forwards the declaration and records the authorized exception."""
    launcher = LaunchRecorder(exit_code=0)
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=OPUS_ROUTE,
        extra=("--authorized-by", "lee", "--reason", "Lee requested Opus review"),
        launcher=launcher,
    )
    assert code == 3  # No verification oracle was supplied.
    assert len(launcher.processes) == 1
    payload = json.loads(captured.out)
    assert payload["selection"]["basis"] == "explicit"
    assert "never_automatic exception" in payload["selection"]["reason"]
    assert "Lee requested Opus review" in payload["selection"]["reason"]
    assert payload["router_event"]["authorized_by"] == "lee"
    assert payload["router_event"]["mode"] == "bind"
    assert payload["router_event"]["reason"] == payload["selection"]["reason"]
    excluded = payload["selection"]["excluded"]
    assert all(item["route_id"] != OPUS_ROUTE for item in excluded)
    assert excluded
    persisted = [
        json.loads(line)
        for line in scratch_state["attempts"].read_text(encoding="utf-8").splitlines()
    ]
    assert len(persisted) == 1
    assert persisted[0]["selection"] == payload["selection"]
    assert persisted[0]["router_event"] == payload["router_event"]

    outcome = select_route(
        load_staffing_catalog(catalog_dir),
        load_availability(snapshot),
        role="impl",
        oracle_type="deterministic",
        size_band="s",
        language="python",
        class_key=IMPL_CLASS,
        at_date="2026-09-15",
        route_id=OPUS_ROUTE,
        authorized_by="lee",
        authorization_reason="Lee requested Opus review",
    )
    assert outcome.authorized_by == "lee"
    assert outcome.authorization_reason == "Lee requested Opus review"
    assert outcome.reason == payload["selection"]["reason"]


@pytest.mark.parametrize(
    ("route", "extra"),
    [
        (OPUS_ROUTE, ()),
        (OPUS_ROUTE, ("--authorized-by", "lee")),
        (OPUS_ROUTE, ("--reason", "requested")),
        (OPUS_ROUTE, ("--authorized-by", "", "--reason", "requested")),
        (OPUS_ROUTE, ("--authorized-by", "lee", "--reason", "   ")),
        (OPUS_ROUTE, ("--authorized-by", "other", "--reason", "requested")),
        (None, ("--authorized-by", "lee", "--reason", "requested")),
    ],
)
def test_authorization_refusals_launch_nothing(
    monkeypatch, capsys, catalog_dir, snapshot, packet, scratch_state, route, extra
):
    """Incomplete, unknown, and unpinned declarations never dispatch."""
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=snapshot,
        packet_path=packet,
        route=route,
        extra=extra,
        launcher=launcher,
    )
    assert code == 3
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()
    if not extra:
        assert "never_automatic" in captured.err
    else:
        assert "authorization" in captured.err or "--route" in captured.err


def test_authorized_route_still_refuses_exhausted_channel(
    monkeypatch, capsys, tmp_path, catalog_dir, packet, scratch_state
):
    """A second exclusion is not removed with never_automatic."""
    exhausted = _write_snapshot(tmp_path / "exhausted.json", anthropic=("HOT", 0))
    launcher = LaunchRecorder()
    code, captured = _run_cli(
        monkeypatch,
        capsys,
        catalog_dir=catalog_dir,
        snapshot_path=exhausted,
        packet_path=packet,
        route=OPUS_ROUTE,
        extra=("--authorized-by", "lee", "--reason", "requested"),
        launcher=launcher,
    )
    assert code == 3
    assert "never_automatic" in captured.err
    assert "channel exhausted" in captured.err
    assert launcher.processes == []
    assert not scratch_state["attempts"].exists()


def test_direct_selection_rejects_unpinned_authority(catalog_dir, snapshot):
    """The selection API enforces the same pin requirement as the CLI."""
    with pytest.raises(RunSelectionError, match="require --route"):
        select_route(
            load_staffing_catalog(catalog_dir),
            load_availability(snapshot),
            role="impl",
            oracle_type="deterministic",
            size_band="s",
            language="python",
            class_key=IMPL_CLASS,
            at_date="2026-09-15",
            authorized_by="lee",
            authorization_reason="requested",
        )
