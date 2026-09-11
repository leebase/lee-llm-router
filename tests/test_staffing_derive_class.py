"""Tests for conservative D213 packet class derivation."""

from __future__ import annotations

from pathlib import Path

import pytest

from lee_llm_router.staffing.derive_class import (
    PacketClassError,
    derive_class,
    parse_packet,
)

CLASSES = Path(__file__).resolve().parents[1] / "config" / "staffing" / "classes.yaml"


PACKETS = {
    "python_deterministic": """
# P3 packet
- Kind: `impl`
- Declared size: 2 files, at most 80 changed lines
- Owned paths: `src/database.py`, `tests/test_database.py`
- Requirement: Change the database helper.
- Oracle: `.venv/bin/pytest -q tests/test_database.py`
- Review: independent review required after the oracle passes.
- Commit: feat: database helper
""",
    "mixed_judge": """
- Kind: review
- Declared size: 4 files, approximately 220 changed lines
- Owned paths: `src/migration.ts`, `docs/migration.md`
- Requirement: Inspect the migration.
- Oracle: no automated oracle is available.
- Review: independent review by Sol Low.
""",
    "undeclared_conservative": """
- Kind: plan
- Owned paths: `docs/guide.md`
- Requirement: Update the guide.
""",
}


@pytest.fixture()
def packet(tmp_path: Path):
    def write(name: str) -> Path:
        path = tmp_path / f"{name}.md"
        path.write_text(PACKETS[name], encoding="utf-8")
        return path

    return write


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "python_deterministic",
            {
                "class_key": "impl/deterministic/persistence/s/python",
                "role": "impl",
                "oracle_type": "deterministic",
                "domain_tags": ("persistence",),
                "size_band": "s",
                "language": "python",
            },
        ),
        (
            "mixed_judge",
            {
                "class_key": "review/judge/persistence/m/mixed",
                "role": "review",
                "oracle_type": "judge",
                "domain_tags": ("persistence",),
                "size_band": "m",
                "language": "mixed",
            },
        ),
        (
            "undeclared_conservative",
            {
                "class_key": "plan/none/none/l/markdown",
                "role": "plan",
                "oracle_type": "none",
                "domain_tags": (),
                "size_band": "l",
                "language": "markdown",
            },
        ),
    ],
)
def test_packet_fixtures_derive_conservatively(packet, name, expected):
    derived = derive_class(packet(name), classes_path=CLASSES)

    assert derived.class_key == expected["class_key"]
    assert derived.role == expected["role"]
    assert derived.oracle_type == expected["oracle_type"]
    assert derived.domain_tags == expected["domain_tags"]
    assert derived.size_band == expected["size_band"]
    assert derived.language == expected["language"]


def test_domain_matches_are_literal_packet_text_evidence(packet):
    derived = derive_class(packet("python_deterministic"), classes_path=CLASSES)

    assert derived.domain_matches == ({"keyword": "database", "tag": "persistence"},)
    assert "database" not in derived.class_key.split("/")[2]


def test_keywords_match_packet_text_and_never_route_metadata(tmp_path: Path):
    packet = tmp_path / "packet.md"
    packet.write_text(
        """\
- Kind: impl
- Declared size: 1 file, at most 40 changed lines
- Owned paths: `src/plain.py`
- Requirement: Update database migration and browser route behavior.
""",
        encoding="utf-8",
    )

    payload = derive_class(packet, classes_path=CLASSES).as_dict()

    assert payload["domain_matches"] == [
        {"keyword": "migration", "tag": "persistence"},
        {"keyword": "database", "tag": "persistence"},
        {"keyword": "browser", "tag": "ui-browser"},
    ]
    assert payload["class"]["domain_tags"] == ["persistence", "ui-browser"]
    assert not ({"model", "provider", "route", "selected_route"} & payload.keys())


def test_oracle_requires_command_name_and_named_reviewer_is_judge(tmp_path: Path):
    packet = tmp_path / "packet.md"
    packet.write_text(
        """\
- Kind: review
- Declared size: 1 file, at most 20 changed lines
- Owned paths: `docs/report.md`
- Oracle: `echo check the report`
- Review: independent review required by Sol Low.
""",
        encoding="utf-8",
    )

    derived = derive_class(packet, classes_path=CLASSES)

    assert derived.oracle_command is None
    assert derived.reviewer == "Sol Low"
    assert derived.oracle_type == "judge"


def test_overrides_are_recorded_with_derived_and_replacement_values(packet):
    derived = derive_class(
        packet("python_deterministic"),
        classes_path=CLASSES,
        overrides={"size_band": "l", "language": "mixed"},
    )

    payload = derived.as_dict()
    assert payload["overrides"] == {"size_band": "l", "language": "mixed"}
    assert payload["override_records"] == [
        {"field": "size_band", "derived": "s", "value": "l"},
        {"field": "language", "derived": "python", "value": "mixed"},
    ]
    assert payload["class"]["class_key"] == "impl/deterministic/persistence/l/mixed"


@pytest.mark.parametrize(
    "content",
    [
        "- Owned paths: `src/a.py`\n",
        "- Kind: impl\n- Owned paths: `src/a.txt`\n",
        "- Kind: unknown\n- Owned paths: `src/a.py`\n",
        "- Kind: impl\n- Declared size: enormous\n- Owned paths: `src/a.py`\n",
        "- Kind: impl\n- Owned paths: `src/a.py`\n- Oracle: `pytest 'unterminated`\n",
    ],
)
def test_malformed_packets_fail_closed(tmp_path: Path, content: str):
    path = tmp_path / "bad.md"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(PacketClassError):
        if "a.txt" in content or "Oracle" in content:
            derive_class(path, classes_path=CLASSES)
        else:
            parse_packet(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"size_band": "huge"},
        {"domain_tags": "database"},
        {"class_key": "impl/deterministic/security+persistence/s/python"},
        {"route": "some-route"},
    ],
)
def test_malformed_overrides_fail_closed(packet, overrides):
    with pytest.raises(PacketClassError):
        derive_class(
            packet("python_deterministic"),
            classes_path=CLASSES,
            overrides=overrides,
        )
