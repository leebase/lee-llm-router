"""Focused P2-5b ``staff`` CLI wiring tests.

Every test invokes the real argparse parser and ``main`` in-process against
scratch availability, attempt-ledger, and event files; only the external
state seams (the ``LEE_LLM_ROUTER_*_FILE`` environment variables) are
monkeypatched.  No provider is prompted and no real router state is touched.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lee_llm_router.doctor import main
from lee_llm_router.events import read_events
from lee_llm_router.staffing.staff import (
    render_staff_json,
    staff,
)

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
AT = "2026-10-01"
CLASS_KEY = "impl/deterministic/none/s/python"
NEVER_AUTOMATIC = "claude-claude-fable-5-1-high-anthropic-sub"
ORDINARY = "codex-gpt-5-6-sol-low-openai-sub"
CREWS = ("luna-sol", "sol-low-glm-pi")

SNAPSHOT = {
    "host": "staff-cli-test",
    "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    "subscriptions": [
        {
            "provider": "OpenAI/Codex",
            "bucket": "Weekly limit",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
        {
            "provider": "Anthropic/Claude",
            "bucket": "Current session",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
        {
            "provider": "Gemini/agy",
            "bucket": "Gemini models",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
        {
            "provider": "OpenCode/Go",
            "bucket": "Weekly",
            "status": "ON TRACK",
            "remaining_pct": 80,
        },
    ],
}


@pytest.fixture()
def scratch(tmp_path, monkeypatch):
    """Scratch availability snapshot, attempt ledger, and event file."""
    snapshot = tmp_path / "availability.json"
    snapshot.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
    events = tmp_path / "events.jsonl"
    events.touch()
    monkeypatch.setenv("LEE_LLM_ROUTER_EVENTS_FILE", str(events))
    monkeypatch.setenv("LEE_LLM_ROUTER_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    return {
        "snapshot": str(snapshot),
        "events": events,
        "catalog": str(REPO_CONFIG_DIR),
    }


def _invoke(argv, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    return excinfo.value.code, capsys.readouterr()


def _auto_argv(scratch, *extra, at=AT, class_key=CLASS_KEY):
    return [
        "staff",
        "--role",
        "impl",
        "--class",
        class_key,
        "--at",
        at,
        "--availability-file",
        scratch["snapshot"],
        "--catalog-dir",
        scratch["catalog"],
        *extra,
    ]


def test_staff_exact_auto_command_exits_0_with_compact_block(scratch, capsys):
    code, out = _invoke(_auto_argv(scratch), capsys)
    assert code == 0
    assert out.err == ""
    lines = out.out.splitlines()
    assert lines[0].startswith("staff auto impl ")
    assert lines[0].endswith("(authority: policy)")
    assert any("Workers:" in line for line in lines)
    assert any("Escalation:" in line for line in lines)


def test_staff_auto_at_is_forwarded_to_the_service(scratch, capsys):
    """The --at date reaches the service: the JSON payload is byte-for-byte
    the payload the service returns for the same at_date, and differs from
    the payload computed for another date (dated terms change the block)."""
    code, out = _invoke(_auto_argv(scratch, "--json"), capsys)
    assert code == 0
    payload = json.loads(out.out)
    from lee_llm_router.availability import load_availability
    from lee_llm_router.staffing.catalog import load_staffing_catalog

    def service_payload(at):
        return render_staff_json(
            staff(
                load_staffing_catalog(REPO_CONFIG_DIR),
                load_availability(scratch["snapshot"]),
                mode="auto",
                role="impl",
                class_key=CLASS_KEY,
                at_date=at,
                attempts_path=os.environ["LEE_LLM_ROUTER_ATTEMPTS_FILE"],
            )
        )

    assert payload == service_payload(AT)
    assert payload != service_payload("2026-01-01")


@pytest.mark.parametrize("crew_id", CREWS)
def test_staff_crew_both_spellings_exit_0_without_role_class_at(
    scratch, capsys, crew_id
):
    """Both saved catalog crews render with no --role/--class/--at supplied."""
    code, out = _invoke(
        ["staff", "--mode", "crew", crew_id, "--catalog-dir", scratch["catalog"]],
        capsys,
    )
    assert code == 0
    assert out.err == ""
    assert out.out.startswith(f"staff crew {crew_id} ")
    assert "authority:" in out.out


def test_staff_crew_json_payload_matches_text_block(scratch, capsys):
    argv = ["staff", "--mode", "crew", "luna-sol", "--catalog-dir", scratch["catalog"]]
    _code, text_out = _invoke(argv, capsys)
    code, json_out = _invoke([*argv, "--json"], capsys)
    assert code == 0
    payload = json.loads(json_out.out)
    assert payload["mode"] == "crew"
    assert payload["crew_id"] == "luna-sol"
    assert payload["authority"] in {"chief", "policy"}
    # Text and JSON carry the same facts: the text is the compact block.
    assert text_out.out.strip().splitlines()[0].startswith("staff crew luna-sol")


def test_staff_bind_never_automatic_refuses_without_lee(scratch, capsys):
    argv = [
        *_auto_argv(scratch),
        "--mode",
        "bind",
        NEVER_AUTOMATIC,
        "--authorized-by",
        "not-lee",
        "--reason",
        "human override",
    ]
    code, out = _invoke(argv, capsys)
    assert code == 3
    assert "never-automatic" in out.err
    assert "authorized" in out.err
    assert out.out == ""
    assert scratch["events"].read_text(encoding="utf-8") == ""


def test_staff_bind_unknown_route_refuses_and_appends_nothing(scratch, capsys):
    argv = [
        *_auto_argv(scratch),
        "--mode",
        "bind",
        "not-a-catalog-route",
        "--authorized-by",
        "lee",
        "--reason",
        "human override",
    ]
    code, out = _invoke(argv, capsys)
    assert code == 3
    assert "not-a-catalog-route" in out.err
    assert scratch["events"].read_text(encoding="utf-8") == ""


def test_staff_bind_missing_authorization_refuses(scratch, capsys):
    argv = [*_auto_argv(scratch), "--mode", "bind", ORDINARY]
    code, out = _invoke(argv, capsys)
    assert code == 3
    assert out.err.startswith("staff:")
    assert scratch["events"].read_text(encoding="utf-8") == ""


def test_staff_bind_acceptance_appends_exactly_one_event(scratch, capsys):
    argv = [
        *_auto_argv(scratch),
        "--mode",
        "bind",
        NEVER_AUTOMATIC,
        "--authorized-by",
        "lee",
        "--reason",
        "explicit human override",
    ]
    code, out = _invoke(argv, capsys)
    assert code == 0
    assert out.err == ""
    assert "staff bind " in out.out
    assert "authorized_by: lee" in out.out
    events = read_events(scratch["events"])
    assert len(events) == 1
    event = events[0]
    assert event["mode"] == "bind"
    assert event["worker_id"] == NEVER_AUTOMATIC
    assert event["authorized_by"] == "lee"
    assert event["reason"] == "explicit human override"
    assert event["role"] == "impl"


def test_staff_json_payload_matches_the_service(scratch, capsys):
    code, out = _invoke(_auto_argv(scratch, "--json"), capsys)
    assert code == 0
    payload = json.loads(out.out)
    from lee_llm_router.availability import load_availability
    from lee_llm_router.staffing.catalog import load_staffing_catalog

    expected = render_staff_json(
        staff(
            load_staffing_catalog(REPO_CONFIG_DIR),
            load_availability(scratch["snapshot"]),
            mode="auto",
            role="impl",
            class_key=CLASS_KEY,
            at_date=AT,
            attempts_path=os.environ["LEE_LLM_ROUTER_ATTEMPTS_FILE"],
        )
    )
    assert payload == expected


def test_staff_json_is_parseable_and_carry_the_block_facts(scratch, capsys):
    code, out = _invoke(_auto_argv(scratch, "--json"), capsys)
    assert code == 0
    payload = json.loads(out.out)  # parseable, strict compact JSON
    assert payload["mode"] == "auto"
    assert payload["authority"] == "policy"
    assert isinstance(payload["workers"], list) and payload["workers"]


def test_staff_invalid_mode_exits_3(scratch, capsys):
    code, out = _invoke(["staff", "--mode", "bogus"], capsys)
    assert code == 3
    assert "--mode" in out.err


def test_staff_crew_without_target_exits_3(scratch, capsys):
    code, out = _invoke(["staff", "--mode", "crew"], capsys)
    assert code == 3
    assert "--mode" in out.err


def test_staff_unknown_crew_target_exits_3(scratch, capsys):
    code, out = _invoke(
        ["staff", "--mode", "crew", "not-a-crew", "--catalog-dir", scratch["catalog"]],
        capsys,
    )
    assert code == 3
    assert "not-a-crew" in out.err


def test_staff_auto_without_required_args_exits_3(scratch, capsys):
    code, out = _invoke(["staff"], capsys)
    assert code == 3
    assert "auto" in out.err


def test_staff_auto_bad_at_exits_3(scratch, capsys):
    code, out = _invoke(_auto_argv(scratch, at="not-a-date"), capsys)
    assert code == 3
    assert "at_date" in out.err or "--at" in out.err


def test_staff_auto_bad_class_exits_3(scratch, capsys):
    code, out = _invoke(
        _auto_argv(scratch, class_key="impl/deterministic/s/python"),
        capsys,
    )
    assert code == 3
    assert out.err != ""


def test_old_commands_remain_accepted(scratch, capsys):
    code, out = _invoke(
        [
            "doctor",
            "--catalog",
            "--catalog-dir",
            scratch["catalog"],
        ],
        capsys,
    )
    assert code == 0
    assert "OK catalog" in out.out
    code, out = _invoke(
        [
            "catalog",
            "explain",
            "--role",
            "impl",
            "--class",
            CLASS_KEY,
            "--at",
            AT,
            "--catalog-dir",
            scratch["catalog"],
            "--json",
        ],
        capsys,
    )
    assert code == 0
    payload = json.loads(out.out)
    assert payload["role"] == "impl"
    assert payload["class_key"] == CLASS_KEY
