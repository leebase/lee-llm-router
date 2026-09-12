#!/usr/bin/env python3
"""Harvest failed production attempts into benchmark packet skeletons.

Phase 5, Packet P5-3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

# Ensure router src is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lee_llm_router.staffing.ledger import (  # noqa: E402
    AttemptLedgerError,
    read_attempts,
    resolve_attempts_path,
)

ROLE_INVERSE_MAP = {
    "impl": "implementation",
    "review": "reviewer",
    "plan": "planner",
}

DEFAULT_IMAGE = (
    "python:3.12-slim@sha256:"
    "97490e383c4cffb12825431fa24e3d2b70e39fd691a8e33c46bf4c18edca3998"
)

DEVIATION_MSG = (
    "skeleton: no repo archive, start_commit, or private evaluator yet; "
    "a human freezes the fixture before this packet is run"
)


def parse_now(now_str: str | None) -> datetime:
    """Parse --now argument as ISO datetime or date."""
    if now_str is None:
        return datetime.now(timezone.utc)
    cleaned = now_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            d = date.fromisoformat(now_str)
            dt = datetime(
                d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=timezone.utc
            )
        except ValueError as exc:
            raise ValueError(f"invalid ISO date/datetime for --now: {now_str}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if len(now_str) == 10 and now_str.count("-") == 2:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def parse_captured_at(captured_at_str: Any) -> datetime | None:
    if not isinstance(captured_at_str, str) or not captured_at_str:
        return None
    try:
        dt = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_production_failure(
    record: Mapping[str, Any], cutoff: datetime, now: datetime
) -> bool:
    """Check if record is a production attempt failure within the date window."""
    if record.get("record_kind") != "router_run":
        return False
    cap_dt = parse_captured_at(record.get("captured_at"))
    if cap_dt is None or not (cutoff <= cap_dt <= now):
        return False
    verdict = record.get("verdict")
    is_fail = (
        verdict == "fail"
        or (isinstance(verdict, dict) and verdict.get("status") == "fail")
        or record.get("failure_class") == "capability_rejected"
    )
    return is_fail


def index_packet_dirs(packet_dirs: list[str | Path]) -> dict[str, Path]:
    """Hash every *.md under packet_dirs and return sha256 -> Path mapping."""
    packet_map: dict[str, Path] = {}
    for pdir_raw in packet_dirs:
        pdir = Path(pdir_raw)
        if not pdir.exists():
            continue
        if pdir.is_file():
            if pdir.suffix.lower() == ".md":
                try:
                    digest = hashlib.sha256(pdir.read_bytes()).hexdigest()
                    packet_map[digest] = pdir
                except OSError:
                    pass
        else:
            for md_path in pdir.rglob("*.md"):
                try:
                    digest = hashlib.sha256(md_path.read_bytes()).hexdigest()
                    packet_map[digest] = md_path
                except OSError:
                    pass
    return packet_map


def extract_owned_paths_lines(text: str) -> list[str]:
    """Extract the verbatim lines of the Owned paths section from markdown."""
    lines = text.splitlines()
    res: list[str] = []
    in_owned = False
    for line in lines:
        if re.match(r"^\s*-\s*Owned paths", line):
            in_owned = True
            res.append(line.rstrip("\r\n"))
            continue
        if in_owned:
            if line.startswith("  ") or line.startswith("\t"):
                res.append(line.rstrip("\r\n"))
            else:
                break
    return res


def extract_oracle_line(text: str) -> str:
    """Extract the verbatim Oracle line from packet markdown."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- Oracle:") or stripped.startswith("Oracle:"):
            return stripped
        if stripped == "## Oracle":
            for j in range(i + 1, len(lines)):
                next_l = lines[j].strip()
                if next_l and not next_l.startswith("#"):
                    return next_l
    return ""


def build_group_data(
    group_key: tuple[str, str],
    members: list[dict[str, Any]],
    packet_map: dict[str, Path],
) -> dict[str, Any]:
    packet_id, class_key = group_key
    packet_sha = packet_id.split(":", 1)[-1] if ":" in packet_id else packet_id
    resolved_path = packet_map.get(packet_sha)

    routes = sorted(
        {
            str(r.get("router_event", {}).get("route_id"))
            for r in members
            if isinstance(r.get("router_event"), dict)
            and r.get("router_event", {}).get("route_id")
        }
    )
    failure_classes = sorted(
        {
            str(r.get("failure_class"))
            for r in members
            if r.get("failure_class") is not None
        }
    )
    captured_ats = [str(r.get("captured_at")) for r in members if r.get("captured_at")]
    first_captured_at = min(captured_ats) if captured_ats else ""
    last_captured_at = max(captured_ats) if captured_ats else ""

    oracle_cmds = [
        str(r.get("oracle_cmd")) for r in members if r.get("oracle_cmd") is not None
    ]
    oracle_cmd = oracle_cmds[0] if oracle_cmds else ""

    class_record = None
    for r in members:
        if isinstance(r.get("class_record"), dict):
            class_record = r["class_record"]
            break

    briefing_desc = (
        str(resolved_path)
        if resolved_path
        else "unresolved (no file under --packet-dirs hashes to this id)"
    )

    safe_class_key = class_key.replace("/", "-").replace("+", "-")
    harvest_id = f"h-{packet_sha[:12]}-{safe_class_key}"

    return {
        "packet_id": packet_id,
        "class_key": class_key,
        "attempt_count": len(members),
        "attempt_ids": [r.get("attempt_id") for r in members if r.get("attempt_id")],
        "routes": routes,
        "failure_classes": failure_classes,
        "first_captured_at": first_captured_at,
        "last_captured_at": last_captured_at,
        "oracle_cmd": oracle_cmd,
        "class_record": class_record,
        "briefing": briefing_desc,
        "resolved_path": resolved_path,
        "harvest_id": harvest_id,
        "members": members,
    }


def emit_skeleton(group_data: dict[str, Any], emit_dir: Path) -> Path:
    """Emit a single skeleton under emit_dir/<harvest-id>/v1/."""
    resolved_path = group_data["resolved_path"]
    if not resolved_path:
        raise ValueError("Cannot emit skeleton for unresolved packet")

    harvest_id = group_data["harvest_id"]
    target_v1 = emit_dir / harvest_id / "v1"
    target_v1.mkdir(parents=True, exist_ok=True)

    briefing_bytes = resolved_path.read_bytes()
    (target_v1 / "briefing.md").write_bytes(briefing_bytes)
    briefing_sha256 = hashlib.sha256(briefing_bytes).hexdigest()

    oracle_cmd = group_data["oracle_cmd"]
    oracle_content = (oracle_cmd.strip() + "\n") if oracle_cmd else ""
    (target_v1 / "oracle.txt").write_text(oracle_content, encoding="utf-8")

    class_record = group_data["class_record"]
    role_raw = class_record.get("role") if class_record else None
    if role_raw not in ROLE_INVERSE_MAP:
        pid = group_data["packet_id"]
        sys.stderr.write(
            f"harvest_failed_packets: unmapped role {role_raw!r} for packet {pid}\n"
        )
        sys.exit(1)
    role = ROLE_INVERSE_MAP[role_raw]

    briefing_text = briefing_bytes.decode("utf-8")
    observed_files = extract_owned_paths_lines(briefing_text)
    oracle_line = extract_oracle_line(briefing_text)

    fc_list = group_data["failure_classes"]
    failure_classes_str = ", ".join(fc_list) if fc_list else "none"
    r_list = group_data["routes"]
    routes_str = ", ".join(r_list) if r_list else "none"
    count = group_data["attempt_count"]
    evidence_summary = (
        f"{count} failed production attempts, "
        f"failure classes {failure_classes_str}, routes {routes_str}"
    )

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    manifest = {
        "schema_version": "pilot-packet/1",
        "task_id": harvest_id,
        "task_version": "v1",
        "role": role,
        "difficulty_intent": "production-failure",
        "design_target_minutes": None,
        "origin_kind": "harvested-production-failure",
        "origin_ref": f"lee-llm-router attempt ledger {group_data['packet_id']}",
        "origin": {
            "repository_label": "lee-llm-router",
            "commit": None,
            "parent_commit": None,
            "observed_files": observed_files,
            "source_lines": None,
            "evidence_summary": evidence_summary,
            "reconstruction_deviations": [DEVIATION_MSG],
        },
        "repo_path": None,
        "start_commit": None,
        "repo_archive_sha256": None,
        "visible_inputs": [{"path": "briefing.md", "sha256": briefing_sha256}],
        "environment": {
            "image": DEFAULT_IMAGE,
            "network": "disabled",
            "artifact_mount": "read-only",
            "private_evaluator_mount": "separate-read-only",
        },
        "protocol": {
            "fresh_session": True,
            "subagents": False,
            "candidate_visible_paths": ["repo", "briefing.md", "manifest.json"],
            "candidate_cannot_read": [],
            "clarification_policy": (
                "bounded fixture; no external clarification required"
            ),
        },
        "output_contract": {
            "required": oracle_line,
            "verification": oracle_cmd,
            "evaluation_schema": "pilot-evaluation/1",
            "acceptance_is_not_model_ranking": True,
        },
        "class": class_record,
        "harvest": {
            "packet_id": group_data["packet_id"],
            "attempt_ids": group_data["attempt_ids"],
            "routes": group_data["routes"],
            "failure_classes": group_data["failure_classes"],
            "first_captured_at": group_data["first_captured_at"],
            "last_captured_at": group_data["last_captured_at"],
            "harvested_at": now_iso,
        },
    }

    (target_v1 / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return target_v1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Harvest failed production attempts into benchmark skeletons."
    )
    parser.add_argument("--ledger", help="Override path to attempt ledger file")
    parser.add_argument(
        "--days", type=int, default=30, help="Lookback window in days (default: 30)"
    )
    parser.add_argument(
        "--now",
        help="ISO date/datetime for relative lookback window (default: today)",
    )
    parser.add_argument(
        "--packet-dirs",
        action="append",
        help="Directories containing packet .md files to hash",
    )
    parser.add_argument("--emit", help="Emit skeletons under this directory")
    parser.add_argument("--json", action="store_true", help="Emit output as JSON")

    args = parser.parse_args(argv)

    try:
        now = parse_now(args.now)
    except ValueError as exc:
        sys.stderr.write(f"harvest_failed_packets: {exc}\n")
        return 2

    cutoff = now - timedelta(days=args.days)

    ledger_path = Path(args.ledger) if args.ledger else resolve_attempts_path()
    try:
        records = read_attempts(ledger_path)
    except (AttemptLedgerError, OSError, FileNotFoundError) as exc:
        sys.stderr.write(
            f"harvest_failed_packets: cannot read ledger {ledger_path}: {exc}\n"
        )
        return 2

    packet_dirs = args.packet_dirs if args.packet_dirs else ["docs/staffing/packets"]
    packet_map = index_packet_dirs(packet_dirs)

    # Filter records
    failed_attempts = [
        r for r in records if is_production_failure(r, cutoff=cutoff, now=now)
    ]

    # Group by (packet_id, class_key)
    groups_map: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in failed_attempts:
        pid = r.get("packet_id")
        class_rec = r.get("class_record") or {}
        ckey = class_rec.get("class_key")
        if pid and ckey:
            groups_map[(pid, ckey)].append(r)

    # Build group data
    groups = [build_group_data(k, v, packet_map) for k, v in groups_map.items()]
    # Sort groups: attempt_count descending, first_captured_at ascending
    groups.sort(
        key=lambda g: (
            -g["attempt_count"],
            g["first_captured_at"],
            g["packet_id"],
            g["class_key"],
        )
    )

    # Emit if requested
    if args.emit:
        emit_dir = Path(args.emit)
        for g in groups:
            if g["resolved_path"]:
                emit_skeleton(g, emit_dir)

    # Output representation
    if args.json:
        json_out = [
            {
                "packet_id": g["packet_id"],
                "class_key": g["class_key"],
                "attempt_count": g["attempt_count"],
                "attempt_ids": g["attempt_ids"],
                "routes": g["routes"],
                "failure_classes": g["failure_classes"],
                "first_captured_at": g["first_captured_at"],
                "last_captured_at": g["last_captured_at"],
                "oracle_cmd": g["oracle_cmd"],
                "briefing": g["briefing"],
            }
            for g in groups
        ]
        print(json.dumps(json_out, indent=2))
    else:
        for i, g in enumerate(groups):
            if i > 0:
                print()
            routes_str = ", ".join(g["routes"]) if g["routes"] else "none"
            fclasses_str = (
                ", ".join(g["failure_classes"]) if g["failure_classes"] else "none"
            )
            print(f"packet_id: {g['packet_id']}")
            print(f"class_key: {g['class_key']}")
            print(f"attempt_count: {g['attempt_count']}")
            print(f"routes: {routes_str}")
            print(f"failure_classes: {fclasses_str}")
            print(f"first_captured_at: {g['first_captured_at']}")
            print(f"last_captured_at: {g['last_captured_at']}")
            print(f"oracle_cmd: {g['oracle_cmd']}")
            print(f"briefing: {g['briefing']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
