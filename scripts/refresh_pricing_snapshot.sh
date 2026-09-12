#!/usr/bin/env bash
# Refresh OpenRouter catalog and OpenCode Zen pricing snapshot files.
#
# Fetches the latest OpenRouter models catalog and OpenCode Zen pricing
# documentation table at a pinned commit, validates both payloads, computes
# sha256 sidecars, and writes the snapshot files atomically.
#
# Repointing config/staffing/terms.yaml and config/staffing/channels.yaml is
# a reviewed commit (D121/D167). This script does NOT modify any existing
# snapshot, terms.yaml, channels.yaml, or any scheduler. It prints proposed
# changes and the proposed cron entry on stdout.
#
# Usage:
#   refresh_pricing_snapshot.sh [--date YYYY-MM-DD] [--out-dir DIR] [--dry-run] [--zen-commit SHA]
#
# Environment:
#   CURL_BIN      path to curl binary (default: curl)
#   TERMS_FILE    path to terms.yaml (default: $REPO_ROOT/config/staffing/terms.yaml)
#   CHANNELS_FILE path to channels.yaml (default: $REPO_ROOT/config/staffing/channels.yaml)
#
# Exit codes:
#   0  snapshots written (or dry-run printed)
#   1  network failure, validation failure, or invalid argument
#   4  snapshot file for <date> already exists under --out-dir (and not --dry-run)
#
# On failure, any existing snapshot is left untouched and no temporary file
# survives.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CURL="${CURL_BIN:-curl}"
TERMS_FILE="${TERMS_FILE:-$REPO_ROOT/config/staffing/terms.yaml}"
CHANNELS_FILE="${CHANNELS_FILE:-$REPO_ROOT/config/staffing/channels.yaml}"

dry_run=0
date_arg=""
out_dir=""
zen_commit=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --date)
      if [ $# -lt 2 ]; then
        echo "refresh_pricing_snapshot: --date requires an argument" >&2
        exit 1
      fi
      date_arg="$2"
      shift 2
      ;;
    --date=*)
      date_arg="${1#--date=}"
      shift
      ;;
    --out-dir)
      if [ $# -lt 2 ]; then
        echo "refresh_pricing_snapshot: --out-dir requires an argument" >&2
        exit 1
      fi
      out_dir="$2"
      shift 2
      ;;
    --out-dir=*)
      out_dir="${1#--out-dir=}"
      shift
      ;;
    --zen-commit)
      if [ $# -lt 2 ]; then
        echo "refresh_pricing_snapshot: --zen-commit requires an argument" >&2
        exit 1
      fi
      zen_commit="$2"
      shift 2
      ;;
    --zen-commit=*)
      zen_commit="${1#--zen-commit=}"
      shift
      ;;
    -h|--help)
      sed -n '2,27p' "$0"
      exit 0
      ;;
    *)
      echo "refresh_pricing_snapshot: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$out_dir" ]; then
  if [ "$PWD" = "$REPO_ROOT" ]; then
    out_dir="config/staffing/pricing"
  else
    out_dir="$REPO_ROOT/config/staffing/pricing"
  fi
fi

if [ -z "$date_arg" ]; then
  date_tag="$(date +%Y%m%d)"
else
  date_tag="${date_arg//-/}"
fi

if ! [[ "$date_tag" =~ ^[0-9]{8}$ ]]; then
  echo "refresh_pricing_snapshot: invalid date format (expected YYYY-MM-DD or YYYYMMDD): $date_arg" >&2
  exit 1
fi

target_files=(
  "$out_dir/openrouter-${date_tag}.json"
  "$out_dir/openrouter-${date_tag}.json.sha256"
  "$out_dir/opencode-zen-${date_tag}.mdx"
  "$out_dir/opencode-zen-${date_tag}.mdx.sha256"
  "$out_dir/opencode-zen-${date_tag}.mdx.source"
)

if [ "$dry_run" -eq 0 ]; then
  for target_path in "${target_files[@]}"; do
    if [ -e "$target_path" ]; then
      echo "refresh_pricing_snapshot: target snapshot file already exists: $target_path" >&2
      exit 4
    fi
  done
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT

# 1. Fetch and validate OpenRouter models catalog.
openrouter_raw="$tmp_dir/openrouter.raw"
if ! "$CURL" -fsSL "https://openrouter.ai/api/v1/models" > "$openrouter_raw"; then
  echo "refresh_pricing_snapshot: failed to fetch OpenRouter models catalog" >&2
  exit 1
fi

openrouter_json="$tmp_dir/openrouter-${date_tag}.json"
if ! python3 -c '
import json
import sys

path = sys.argv[1]
try:
    with open(path, "rb") as f:
        data = json.load(f)
except Exception as exc:
    sys.stderr.write(f"refresh_pricing_snapshot: invalid OpenRouter JSON: {exc}\n")
    sys.exit(1)

if not isinstance(data, dict):
    sys.stderr.write("refresh_pricing_snapshot: OpenRouter payload is not a JSON object\n")
    sys.exit(1)

models = data.get("data")
if not isinstance(models, list) or len(models) == 0:
    sys.stderr.write("refresh_pricing_snapshot: OpenRouter payload missing non-empty '\''data'\'' list\n")
    sys.exit(1)
' "$openrouter_raw"; then
  exit 1
fi

mv "$openrouter_raw" "$openrouter_json"
(cd "$tmp_dir" && sha256sum "openrouter-${date_tag}.json" > "openrouter-${date_tag}.json.sha256")

# 2. Resolve OpenCode Zen pinned commit and fetch docs mdx.
if [ -z "$zen_commit" ]; then
  commits_raw="$tmp_dir/commits.raw"
  if ! "$CURL" -fsSL "https://api.github.com/repos/sst/opencode/commits?path=packages/web/src/content/docs/zen.mdx&per_page=1" > "$commits_raw"; then
    echo "refresh_pricing_snapshot: failed to fetch OpenCode Zen commit history from GitHub" >&2
    exit 1
  fi

  if ! zen_commit="$(python3 -c '
import json
import sys

path = sys.argv[1]
try:
    with open(path, "rb") as f:
        data = json.load(f)
except Exception as exc:
    sys.stderr.write(f"refresh_pricing_snapshot: failed to parse GitHub commits response: {exc}\n")
    sys.exit(1)

if isinstance(data, dict) and "message" in data:
    msg = data.get("message", "")
    sys.stderr.write(f"refresh_pricing_snapshot: GitHub API error: {msg}\n")
    sys.exit(1)

if not isinstance(data, list) or len(data) == 0:
    sys.stderr.write("refresh_pricing_snapshot: GitHub commits response is empty or not a list\n")
    sys.exit(1)

first_commit = data[0]
if not isinstance(first_commit, dict) or "sha" not in first_commit:
    sys.stderr.write("refresh_pricing_snapshot: GitHub commit missing '\''sha'\'' field\n")
    sys.exit(1)

sha = first_commit["sha"]
if not isinstance(sha, str) or not sha.strip():
    sys.stderr.write("refresh_pricing_snapshot: invalid commit sha in GitHub response\n")
    sys.exit(1)

print(sha.strip())
' "$commits_raw")"; then
    exit 1
  fi
fi

zen_raw_url="https://raw.githubusercontent.com/sst/opencode/${zen_commit}/packages/web/src/content/docs/zen.mdx"
zen_mdx="$tmp_dir/opencode-zen-${date_tag}.mdx"

if ! "$CURL" -fsSL "$zen_raw_url" > "$zen_mdx"; then
  echo "refresh_pricing_snapshot: failed to fetch OpenCode Zen docs mdx from $zen_raw_url" >&2
  exit 1
fi

if [ ! -s "$zen_mdx" ]; then
  echo "refresh_pricing_snapshot: OpenCode Zen docs mdx is empty" >&2
  exit 1
fi

if ! grep -Fq "OpenCode Zen" "$zen_mdx"; then
  echo "refresh_pricing_snapshot: OpenCode Zen docs mdx missing required string '\''OpenCode Zen'\''" >&2
  exit 1
fi

(cd "$tmp_dir" && sha256sum "opencode-zen-${date_tag}.mdx" > "opencode-zen-${date_tag}.mdx.sha256")

cat <<EOF > "$tmp_dir/opencode-zen-${date_tag}.mdx.source"
commit=${zen_commit}
url=${zen_raw_url}
EOF

# 3. Write atomically or dry-run.
if [ "$dry_run" -eq 0 ]; then
  mkdir -p "$out_dir"
  for target_path in "${target_files[@]}"; do
    if [ -e "$target_path" ]; then
      echo "refresh_pricing_snapshot: target snapshot file already exists: $target_path" >&2
      exit 4
    fi
  done

  for f in "openrouter-${date_tag}.json" \
           "openrouter-${date_tag}.json.sha256" \
           "opencode-zen-${date_tag}.mdx" \
           "opencode-zen-${date_tag}.mdx.sha256" \
           "opencode-zen-${date_tag}.mdx.source"; do
    mv -f "$tmp_dir/$f" "$out_dir/$f"
  done
fi

# 4. Print written paths with sha256.
for f in "openrouter-${date_tag}.json" \
         "openrouter-${date_tag}.json.sha256" \
         "opencode-zen-${date_tag}.mdx" \
         "opencode-zen-${date_tag}.mdx.sha256" \
         "opencode-zen-${date_tag}.mdx.source"; do
  dest="$out_dir/$f"
  if [ "$dry_run" -eq 1 ]; then
    sha="$(sha256sum "$tmp_dir/$f" | awk '{print $1}')"
  else
    sha="$(sha256sum "$dest" | awk '{print $1}')"
  fi
  printf '%s  %s\n' "$sha" "$dest"
done

# 5. Print proposed terms repoint block.
echo
echo "PROPOSED (not applied) — apply through a reviewed commit:"

cur_openrouter=""
cur_zen=""
if [ -f "$TERMS_FILE" ]; then
  cur_openrouter="$(grep -oE 'openrouter-[0-9]{8}\.json' "$TERMS_FILE" | head -n 1 || true)"
  cur_zen="$(grep -oE 'opencode-zen-[0-9]{8}\.mdx' "$TERMS_FILE" | head -n 1 || true)"
fi

new_openrouter="openrouter-${date_tag}.json"
new_zen="opencode-zen-${date_tag}.mdx"

for yaml_file in "$CHANNELS_FILE" "$TERMS_FILE"; do
  if [ -f "$yaml_file" ]; then
    rel_path="${yaml_file#$REPO_ROOT/}"
    echo "$rel_path:"
    python3 -c '
import sys

path = sys.argv[1]
cur_open = sys.argv[2]
cur_zen = sys.argv[3]
new_open = sys.argv[4]
new_zen = sys.argv[5]

with open(path, "r", encoding="utf-8") as f:
    for line in f:
        matched = False
        if cur_open and cur_open in line:
            matched = True
        if cur_zen and cur_zen in line:
            matched = True
        if matched:
            stripped = line.rstrip("\n")
            new_line = stripped
            if cur_open:
                new_line = new_line.replace(cur_open, new_open)
            if cur_zen:
                new_line = new_line.replace(cur_zen, new_zen)
            print(f"- {stripped}")
            print(f"+ {new_line}")
' "$yaml_file" "$cur_openrouter" "$cur_zen" "$new_openrouter" "$new_zen"
  fi
done

# 6. Print proposed cron line.
echo
echo "PROPOSED CRON (not installed):"
echo "15 06 * * 1 cd /home/lee/projects/lee-llm-router && scripts/refresh_pricing_snapshot.sh >> ~/.local/state/lee-llm-router/pricing-refresh.log 2>&1"
