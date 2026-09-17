"""Tests for scripts/check_export_paths.py (packet P1-4).

The check is deterministic and import-free by design, so these tests exercise it
as a subprocess, exactly as a pre-flight would: nothing is imported from the
script, and the router package need not be installed.  No test writes anywhere
except pytest's ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_export_paths.py"
REPO_ROOT = SCRIPT.parents[1]

# All three provenance categories, plus a comment line, carrying the same path.
PROVENANCE_YAML = """
    # Provenance citation, never read: /home/someone/x/crews.yaml.
    crews:
      - crew_id: scratch
        evidence_ref: "/home/someone/x/crews.yaml scratch block"
"""

PROVENANCE_SCHEMA = """
    {
      "description": "embedded from /home/someone/x/performance.py",
      "properties": {
        "source_refs": ["/home/someone/x/crews.yaml"],
        "source_paths": ["/home/someone/x/run.json"]
      }
    }
"""

# The comment line is provenance; the dispatch template is a runtime value.
RUNTIME_YAML = """
    # Provenance citation, never read: /home/someone/x/worker.py.
    routes:
      - route_id: scratch
        dispatch_template: "python3 /home/someone/x/worker.py {stage}"
        status: active
"""

# The identical path in a comment, in evidence_ref, and in a worker route.
MIXED_YAML = """
    # Provenance citation, never read: /home/someone/x/crews.yaml.
    crews:
      - crew_id: scratch
        evidence_ref: "/home/someone/x/crews.yaml scratch block"
        worker_routes:
          envision: ["/home/someone/x/routes.yaml"]
"""

RUNTIME_SCHEMA = """
    {
      "properties": {
        "dispatch_template": { "const": "/home/someone/x/worker.py" }
      }
    }
"""

MACOS_RUNTIME_YAML = """
    routes:
      - route_id: scratch
        dispatch_template: "python3 /Users/someone/x/worker.py {stage}"
"""

# P1-4R defect 1: evidence_ref is provenance only inside crews.yaml.
EVIDENCE_REF_OUTSIDE_CREWS_YAML = """
    routes:
      - route_id: scratch
        evidence_ref: "/home/someone/x/actually/dispatched/worker.py"
"""

# P1-4R defect 2: a mapping under a provenance key holds runtime data.
NESTED_PROVENANCE_SCHEMA = """
{"description": {"dispatch_template": "/home/someone/actual/runtime/worker.py"}}
"""

# Regression: legitimate provenance forms keep their exemption.
REGRESSION_CREWS_YAML = """
    crews:
      - crew_id: scratch
        evidence_ref: "/home/someone/x/crews.yaml scratch block"
      - crew_id: scratch-block
        evidence_ref: |
          /home/someone/x/block/crews.yaml
          /home/someone/y/block/other.yaml
"""

REGRESSION_SCHEMA = """
    {
      "description": "embedded from /home/someone/x/performance.py",
      "properties": {
        "source_refs": ["/home/someone/x/crews.yaml"],
        "source_paths": ["/home/someone/x/run.json", "/home/someone/y/run.json"]
      }
    }
"""


def _write(root: Path, relative: str, text: str) -> Path:
    """Write a dedented fixture file beneath ``root``."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def _run(
    root: Path,
    *,
    json_output: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the check against ``root`` and capture its output."""
    command = [sys.executable, str(SCRIPT)]
    if json_output:
        command.append("--json")
    command.append(str(root))
    return subprocess.run(
        command, capture_output=True, text=True, cwd=cwd, env=env, check=False
    )


def _findings(result: subprocess.CompletedProcess[str]) -> list[dict]:
    """Return the findings of a failing (exit 1) machine-readable report."""
    report = json.loads(result.stdout)
    assert report["ok"] is False
    return report["findings"]


def test_repo_config_is_clean() -> None:
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["findings"] == []
    scanned = report["files_scanned"]
    assert "config/staffing/routes.yaml" in scanned
    assert "config/staffing/schema/attempt-record.schema.json" in scanned


def test_config_directory_argument_is_accepted() -> None:
    result = _run(REPO_ROOT / "config")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_runtime_value_fails_with_file_line_key_path_and_value(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/routes.yaml", RUNTIME_YAML)
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["file"] == "config/staffing/routes.yaml"
    assert finding["line"] == 4
    assert finding["key_path"] == "routes[0].dispatch_template"
    assert finding["match"] == "/home/someone"
    assert "/home/someone/x/worker.py" in finding["value"]


def test_text_report_names_file_line_key_path_and_value(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/routes.yaml", RUNTIME_YAML)
    result = _run(tmp_path, json_output=False)
    assert result.returncode == 1
    assert "config/staffing/routes.yaml:4" in result.stdout
    assert "routes[0].dispatch_template" in result.stdout
    assert "/home/someone/x/worker.py" in result.stdout


def test_provenance_categories_are_allowed(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/crews.yaml", PROVENANCE_YAML)
    _write(tmp_path, "config/staffing/schema/scratch.schema.json", PROVENANCE_SCHEMA)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["findings"] == []


def test_identical_path_in_a_runtime_position_still_fails(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/crews.yaml", MIXED_YAML)
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    assert findings[0]["file"] == "config/staffing/crews.yaml"
    assert findings[0]["line"] == 6
    assert findings[0]["key_path"] == "crews[0].worker_routes.envision"
    assert findings[0]["value"].startswith("envision:")


def test_trailing_comment_is_allowed_but_the_value_is_not(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "config/staffing/routes.yaml",
        """
        routes:
          - route_id: scratch
            dispatch_template: "python3 /home/someone/x/worker.py"  # /home/someone/y
        """,
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    assert findings[0]["line"] == 3
    assert "worker.py" in findings[0]["value"]
    assert "/home/someone/y" not in findings[0]["value"]


def test_macos_style_home_path_is_caught(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/routes.yaml", MACOS_RUNTIME_YAML)
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    assert findings[0]["line"] == 3
    assert findings[0]["match"] == "/Users/someone"
    assert "/Users/someone/x/worker.py" in findings[0]["value"]


def test_json_string_outside_documentation_keys_fails(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/schema/scratch.schema.json", RUNTIME_SCHEMA)
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    assert findings[0]["file"] == "config/staffing/schema/scratch.schema.json"
    assert findings[0]["line"] == 3
    assert findings[0]["key_path"] == "properties.dispatch_template.const"


def test_evidence_ref_outside_crews_yaml_is_a_runtime_path(tmp_path: Path) -> None:
    _write(tmp_path, "config/staffing/routes.yaml", EVIDENCE_REF_OUTSIDE_CREWS_YAML)
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["file"] == "config/staffing/routes.yaml"
    assert finding["line"] == 3
    assert finding["key_path"] == "routes[0].evidence_ref"
    assert finding["match"] == "/home/someone"
    assert "/home/someone/x/actually/dispatched/worker.py" in finding["value"]


def test_json_provenance_key_must_be_the_direct_parent(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "config/staffing/schema/scratch.schema.json",
        NESTED_PROVENANCE_SCHEMA,
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    findings = _findings(result)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["file"] == "config/staffing/schema/scratch.schema.json"
    assert finding["line"] == 1
    assert finding["key_path"] == "description.dispatch_template"
    assert finding["match"] == "/home/someone"
    assert "/home/someone/actual/runtime/worker.py" in finding["value"]


def test_evidence_ref_in_crews_yaml_stays_provenance(tmp_path: Path) -> None:
    # Includes the multi-line block-scalar form, which must keep working.
    _write(tmp_path, "config/staffing/crews.yaml", REGRESSION_CREWS_YAML)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_json_provenance_values_and_list_elements_stay_allowed(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "config/staffing/schema/scratch.schema.json", REGRESSION_SCHEMA)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_check_is_import_free_and_runs_from_any_directory(tmp_path: Path) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:import|from)\s+lee_llm_router", source, re.M)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    result = _run(REPO_ROOT, json_output=False, cwd=tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_staffing_tree_is_a_usage_error(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert "config/staffing" in result.stderr
