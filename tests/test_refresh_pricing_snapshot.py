"""Tests for scripts/refresh_pricing_snapshot.sh."""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "refresh_pricing_snapshot.sh"
TERMS_FILE = REPO_ROOT / "config" / "staffing" / "terms.yaml"


@pytest.fixture
def fake_curl(tmp_path: Path) -> Path:
    """Create a fake curl shim that serves mock HTTP responses."""
    shim = tmp_path / "fake_curl.sh"
    shim_content = """#!/usr/bin/env bash
set -euo pipefail

url=""
for arg in "$@"; do
  case "$arg" in
    http*|https*)
      url="$arg"
      ;;
  esac
done

if [ -n "${FAKE_CURL_FAIL_ALL:-}" ]; then
  echo "fake_curl: network error" >&2
  exit 1
fi

if [[ "$url" == *"openrouter.ai/api/v1/models"* ]]; then
  if [ -n "${FAKE_CURL_OPENROUTER_FAIL:-}" ]; then
    echo "fake_curl: OpenRouter fetch error" >&2
    exit 1
  fi
  if [ -n "${FAKE_CURL_OPENROUTER_PAYLOAD:-}" ]; then
    printf '%s' "$FAKE_CURL_OPENROUTER_PAYLOAD"
  else
    printf '{"data":[{"id":"test/fake-model-1"}]}'
  fi
  exit 0
fi

if [[ "$url" == *"api.github.com/repos/sst/opencode/commits"* ]]; then
  if [ -n "${FAKE_CURL_COMMITS_FAIL:-}" ]; then
    echo "fake_curl: GitHub commits error" >&2
    exit 1
  fi
  if [ -n "${FAKE_CURL_COMMITS_PAYLOAD:-}" ]; then
    printf '%s' "$FAKE_CURL_COMMITS_PAYLOAD"
  else
    printf '[{"sha":"1111222233334444555566667777888899990000"}]'
  fi
  exit 0
fi

if [[ "$url" == *"raw.githubusercontent.com/sst/opencode/"* ]]; then
  if [ -n "${FAKE_CURL_ZEN_FAIL:-}" ]; then
    echo "fake_curl: Zen mdx fetch error" >&2
    exit 1
  fi
  if [ -n "${FAKE_CURL_ZEN_PAYLOAD:-}" ]; then
    printf '%s' "$FAKE_CURL_ZEN_PAYLOAD"
  else
    printf '# OpenCode Zen\\n\\n| Model | Input | Output |\\n'
  fi
  exit 0
fi

echo "fake_curl: unknown url: $url" >&2
exit 1
"""
    shim.write_text(shim_content, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def run_script(
    args: list[str],
    fake_curl: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run refresh_pricing_snapshot.sh with fake curl in CURL_BIN and PATH."""
    env = os.environ.copy()
    env["CURL_BIN"] = str(fake_curl)
    env["PATH"] = f"{fake_curl.parent}:{env.get('PATH', '')}"
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        [str(SCRIPT_PATH)] + args,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_success_writes_exactly_five_files_and_sidecars(
    fake_curl: Path, tmp_path: Path
) -> None:
    """Verify success writes five files with correct sha256 and .source."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-01"
    date_tag = "20261001"

    proc = run_script(["--date", date_str, "--out-dir", str(out_dir)], fake_curl)
    assert proc.returncode == 0, f"stdout: {proc.stdout}\nstderr: {proc.stderr}"

    written_files = sorted(p.name for p in out_dir.iterdir())
    expected_files = sorted(
        [
            f"openrouter-{date_tag}.json",
            f"openrouter-{date_tag}.json.sha256",
            f"opencode-zen-{date_tag}.mdx",
            f"opencode-zen-{date_tag}.mdx.sha256",
            f"opencode-zen-{date_tag}.mdx.source",
        ]
    )
    assert written_files == expected_files

    # Check sha256 sidecars using sha256sum -c inside out_dir
    check_or = subprocess.run(
        ["sha256sum", "-c", f"openrouter-{date_tag}.json.sha256"],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    assert check_or.returncode == 0, f"sha256 check failed: {check_or.stderr}"

    check_zen = subprocess.run(
        ["sha256sum", "-c", f"opencode-zen-{date_tag}.mdx.sha256"],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    assert check_zen.returncode == 0, f"sha256 check failed: {check_zen.stderr}"

    # Check .source content
    source_content = (out_dir / f"opencode-zen-{date_tag}.mdx.source").read_text(
        encoding="utf-8"
    )
    expected_sha = "1111222233334444555566667777888899990000"
    raw_prefix = "https://raw.githubusercontent.com/sst/opencode"
    expected_url = f"{raw_prefix}/{expected_sha}/packages/web/src/content/docs/zen.mdx"
    assert source_content == f"commit={expected_sha}\nurl={expected_url}\n"

    # Check stdout contains each path with its sha256
    for name in expected_files:
        path_str = str(out_dir / name)
        assert path_str in proc.stdout


def test_existing_date_refusal(fake_curl: Path, tmp_path: Path) -> None:
    """Verify refusal with exit 4 if target files exist (unless --dry-run)."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-02"

    first = run_script(["--date", date_str, "--out-dir", str(out_dir)], fake_curl)
    assert first.returncode == 0

    # Running again without --dry-run must exit 4
    second = run_script(["--date", date_str, "--out-dir", str(out_dir)], fake_curl)
    assert second.returncode == 4
    assert "already exists" in second.stderr

    # Running with --dry-run on an existing date must succeed
    dry = run_script(
        ["--date", date_str, "--out-dir", str(out_dir), "--dry-run"], fake_curl
    )
    assert dry.returncode == 0


def test_invalid_openrouter_json_exits_1_and_no_files(
    fake_curl: Path, tmp_path: Path
) -> None:
    """Verify invalid OpenRouter JSON exits 1 and leaves no partial files."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-03"

    # Non-JSON response
    proc = run_script(
        ["--date", date_str, "--out-dir", str(out_dir)],
        fake_curl,
        env_overrides={"FAKE_CURL_OPENROUTER_PAYLOAD": "<html>502 Bad Gateway</html>"},
    )
    assert proc.returncode == 1
    assert "invalid OpenRouter JSON" in proc.stderr
    assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0

    # JSON without data list
    proc_empty = run_script(
        ["--date", date_str, "--out-dir", str(out_dir)],
        fake_curl,
        env_overrides={"FAKE_CURL_OPENROUTER_PAYLOAD": '{"data": []}'},
    )
    assert proc_empty.returncode == 1
    assert "data" in proc_empty.stderr
    assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0


def test_dry_run_writes_nothing(fake_curl: Path, tmp_path: Path) -> None:
    """Verify --dry-run writes nothing under --out-dir while printing output."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-04"

    proc = run_script(
        ["--dry-run", "--date", date_str, "--out-dir", str(out_dir)], fake_curl
    )
    assert proc.returncode == 0
    assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0
    assert "PROPOSED (not applied) — apply through a reviewed commit:" in proc.stdout
    assert "PROPOSED CRON (not installed):" in proc.stdout


def test_proposed_terms_block_names_current_snapshot(
    fake_curl: Path, tmp_path: Path
) -> None:
    """Verify PROPOSED terms block names real current snapshot from terms.yaml."""
    terms_text = TERMS_FILE.read_text(encoding="utf-8")
    m_openrouter = re.search(r"openrouter-\d{8}\.json", terms_text)
    m_zen = re.search(r"opencode-zen-\d{8}\.mdx", terms_text)
    assert m_openrouter is not None
    assert m_zen is not None
    current_openrouter = m_openrouter.group(0)
    current_zen = m_zen.group(0)

    out_dir = tmp_path / "pricing"
    date_str = "2026-10-05"
    date_tag = "20261005"

    proc = run_script(
        ["--dry-run", "--date", date_str, "--out-dir", str(out_dir)], fake_curl
    )
    assert proc.returncode == 0

    assert current_openrouter in proc.stdout
    assert current_zen in proc.stdout
    assert f"openrouter-{date_tag}.json" in proc.stdout
    assert f"opencode-zen-{date_tag}.mdx" in proc.stdout


def test_cron_line_present_and_script_never_invokes_crontab(
    fake_curl: Path, tmp_path: Path
) -> None:
    """Verify PROPOSED CRON line is present and the script never invokes crontab."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-06"

    proc = run_script(
        ["--dry-run", "--date", date_str, "--out-dir", str(out_dir)], fake_curl
    )
    assert proc.returncode == 0

    cron_log = "$HOME/.local/state/lee-llm-router/pricing-refresh.log"
    # The literal line in the script uses '~' which is:
    expected_cron = (
        "15 06 * * 1 cd /home/lee/projects/lee-llm-router && "
        f"scripts/refresh_pricing_snapshot.sh >> {cron_log.replace('$HOME', '~')} 2>&1"
    )
    assert "PROPOSED CRON (not installed):" in proc.stdout
    assert expected_cron in proc.stdout

    script_source = SCRIPT_PATH.read_text(encoding="utf-8")
    # Assert script never invokes crontab (no mention of crontab anywhere in source)
    assert "crontab" not in script_source.lower()


def test_zen_commit_flag_override(fake_curl: Path, tmp_path: Path) -> None:
    """Verify --zen-commit bypasses GitHub commit lookup and uses provided SHA."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-07"
    date_tag = "20261007"
    custom_sha = "aabbccddeeff00112233445566778899aabbccdd"

    # FAKE_CURL_COMMITS_FAIL=1 ensures script would fail if it called GitHub API
    proc = run_script(
        [
            "--date",
            date_str,
            "--out-dir",
            str(out_dir),
            "--zen-commit",
            custom_sha,
        ],
        fake_curl,
        env_overrides={"FAKE_CURL_COMMITS_FAIL": "1"},
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"

    source_content = (out_dir / f"opencode-zen-{date_tag}.mdx.source").read_text(
        encoding="utf-8"
    )
    assert f"commit={custom_sha}" in source_content


def test_invalid_zen_mdx_fails_and_no_partial_files(
    fake_curl: Path, tmp_path: Path
) -> None:
    """Verify missing OpenCode Zen marker in fetched mdx fails cleanly with exit 1."""
    out_dir = tmp_path / "pricing"
    date_str = "2026-10-08"

    proc = run_script(
        ["--date", date_str, "--out-dir", str(out_dir)],
        fake_curl,
        env_overrides={"FAKE_CURL_ZEN_PAYLOAD": "No matching marker text"},
    )
    assert proc.returncode == 1
    assert "OpenCode Zen" in proc.stderr
    assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0
