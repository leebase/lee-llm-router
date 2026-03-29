"""Repo-local simulated pi harness for Sprint 7 regression coverage."""

from __future__ import annotations

import json
import sys
import time


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "success_text"
    prompt = sys.argv[-1] if len(sys.argv) > 2 else ""

    if mode == "success_text":
        print(f"pi text harness: {prompt}")
        return 0

    if mode == "success_json":
        print(
            json.dumps(
                {
                    "output_text": f"pi json harness: {prompt}",
                    "model": "pi-harness-o3",
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total_tokens": 20,
                    },
                }
            )
        )
        return 0

    if mode == "missing_text":
        print(json.dumps({"model": "pi-harness-o3"}))
        return 0

    if mode == "malformed_json":
        print("{not valid json")
        return 0

    if mode == "stderr_exit":
        print("pi harness exploded", file=sys.stderr)
        return 7

    if mode == "timeout":
        time.sleep(2.0)
        print("too late")
        return 0

    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
