#!/usr/bin/env bash
# Refresh the lee-llm-router availability snapshot from ai-subs.
#
# Runs the Chief of Staff `ai-subs.sh` dashboard, extracts the single JSON line
# that follows its AFTER_REPORT_JSON marker, stamps it with `host` and
# `written_at`, and writes it atomically to the snapshot path the router's
# availability reader consumes.
#
# The only provider usage this touches is through ai-subs itself; this script
# never calls a provider CLI directly.
#
# Usage:
#   refresh_availability.sh [--dry-run] [--input <captured-ai-subs-stdout>]
#
# Environment:
#   AI_SUBS                            path to ai-subs.sh
#   LEE_LLM_ROUTER_AVAILABILITY_FILE   snapshot path to write
#
# Exit codes: 0 written (or dry-run printed); 1 ai-subs failed, marker missing,
# or the captured payload is not a JSON object carrying a `subscriptions` list
# and an `observed_at` string that parses as an ISO 8601 timestamp. Every
# `subscriptions` element must be an object with a `provider` string; unless it
# is a provider-level UNAVAILABLE/NO_DATA failure entry it must also carry a
# non-empty `bucket` string, a `status` that is one of the ai-subs badges, and a
# finite numeric `remaining_pct` between 0 and 100.
# On failure any existing snapshot is left untouched and no temporary file
# survives.

set -euo pipefail

MARKER="AFTER_REPORT_JSON"
AI_SUBS="${AI_SUBS:-$HOME/projects/chief-of-staff/scripts/ai-subs.sh}"
OUT_FILE="${LEE_LLM_ROUTER_AVAILABILITY_FILE:-$HOME/.local/state/lee-llm-router/availability/$(hostname).json}"

dry_run=0
input_file=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --input)
      if [ $# -lt 2 ]; then
        echo "refresh_availability: --input requires a file argument" >&2
        exit 1
      fi
      input_file="$2"
      shift 2
      ;;
    --input=*)
      input_file="${1#--input=}"
      shift
      ;;
    -h|--help)
      sed -n '2,26p' "$0"
      exit 0
      ;;
    *)
      echo "refresh_availability: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# 1. Capture ai-subs stdout (or read a previously captured file, for tests).
if [ -n "$input_file" ]; then
  if [ ! -f "$input_file" ]; then
    echo "refresh_availability: --input file not found: $input_file" >&2
    exit 1
  fi
  captured="$(cat -- "$input_file")"
else
  if [ ! -x "$AI_SUBS" ]; then
    echo "refresh_availability: ai-subs not executable: $AI_SUBS" >&2
    exit 1
  fi
  if ! captured="$("$AI_SUBS" 2>/dev/null)"; then
    echo "refresh_availability: ai-subs failed: $AI_SUBS" >&2
    exit 1
  fi
fi

# 2. Extract the single JSON line immediately after the marker.
payload="$(printf '%s\n' "$captured" | awk -v marker="$MARKER" '
  found { print; exit }
  index($0, marker) { found = 1 }
')"

if [ -z "${payload//[[:space:]]/}" ]; then
  echo "refresh_availability: no JSON line after $MARKER marker" >&2
  exit 1
fi

# 3. Validate, stamp host/written_at, and serialise.
if ! stamped="$(
  printf '%s' "$payload" | AVAIL_HOST="$(hostname)" python3 -c '
import json
import math
import os
import sys
from datetime import datetime, timezone

try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError as exc:
    sys.stderr.write(f"refresh_availability: AFTER_REPORT_JSON is not valid JSON: {exc}\n")
    raise SystemExit(1)
if not isinstance(data, dict):
    sys.stderr.write("refresh_availability: AFTER_REPORT_JSON is not a JSON object\n")
    raise SystemExit(1)
if not isinstance(data.get("subscriptions"), list):
    sys.stderr.write(
        "refresh_availability: AFTER_REPORT_JSON has no 'subscriptions' list\n"
    )
    raise SystemExit(1)
observed_at = data.get("observed_at")
if not isinstance(observed_at, str):
    sys.stderr.write(
        "refresh_availability: AFTER_REPORT_JSON has no '\''observed_at'\'' string\n"
    )
    raise SystemExit(1)
try:
    datetime.fromisoformat(observed_at.strip().replace("Z", "+00:00"))
except ValueError:
    sys.stderr.write(
        "refresh_availability: AFTER_REPORT_JSON '\''observed_at'\'' is not an ISO 8601 "
        f"timestamp: {observed_at!r}\n"
    )
    raise SystemExit(1)

FAILURE_STATUSES = {"UNAVAILABLE", "NO_DATA"}
# Kept byte-identical with availability.py::KNOWN_STATUSES (plus its NO_DATA
# alias of NO DATA). Hardcoded on purpose: this script must run from cron
# without the package importable.
KNOWN_STATUSES = {
    "COLD",
    "ON TRACK",
    "HOT",
    "TOO FAST",
    "USE IT",
    "NO DATA",
    "NO_DATA",
    "UNAVAILABLE",
}
for index, entry in enumerate(data["subscriptions"]):
    if not isinstance(entry, dict):
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] is not a JSON object\n"
        )
        raise SystemExit(1)
    if not isinstance(entry.get("provider"), str):
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] has no '\''provider'\'' string\n"
        )
        raise SystemExit(1)
    status = entry.get("status")
    if isinstance(status, str) and status.strip() in FAILURE_STATUSES:
        continue
    bucket = entry.get("bucket")
    if not isinstance(bucket, str) or not bucket.strip():
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] has no non-empty "
            "'\''bucket'\'' string\n"
        )
        raise SystemExit(1)
    if not isinstance(status, str):
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] has no '\''status'\'' string\n"
        )
        raise SystemExit(1)
    if status.strip() not in KNOWN_STATUSES:
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] '\''status'\'' is not a "
            f"known ai-subs badge: {status!r}\n"
        )
        raise SystemExit(1)
    remaining = entry.get("remaining_pct")
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] has no numeric "
            "'\''remaining_pct'\''\n"
        )
        raise SystemExit(1)
    if not math.isfinite(remaining):
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] '\''remaining_pct'\'' is "
            f"not finite: {remaining!r}\n"
        )
        raise SystemExit(1)
    if not 0 <= remaining <= 100:
        sys.stderr.write(
            f"refresh_availability: subscriptions[{index}] '\''remaining_pct'\'' is "
            f"outside 0-100: {remaining!r}\n"
        )
        raise SystemExit(1)

data["host"] = os.environ["AVAIL_HOST"]
data["written_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sys.stdout.write(json.dumps(data, separators=(",", ":")))
'
)"; then
  exit 1
fi

# 4. Emit or write atomically.
if [ "$dry_run" -eq 1 ]; then
  printf '%s\n' "$stamped"
  exit 0
fi

out_dir="$(dirname -- "$OUT_FILE")"
mkdir -p -- "$out_dir"
tmp_file="${OUT_FILE}.tmp.$$"
# Any exit between here and the rename must leave no partial *.tmp.* behind.
trap 'rm -f -- "$tmp_file"' EXIT
printf '%s\n' "$stamped" > "$tmp_file"
mv -f -- "$tmp_file" "$OUT_FILE"
trap - EXIT
