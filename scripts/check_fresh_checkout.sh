#!/usr/bin/env bash
# Fresh-checkout reproducibility check.
#
# A long-lived working tree certifies "tracked repository + accumulated local
# state", not "exported repository". Untracked-but-present fixtures, generated
# inputs and ignored files all pass there and vanish on a clone. This script
# exports exactly what git tracks into a scratch directory and runs the suite
# against it, so the acceptance path tests what someone else would actually get.
#
# Usage: scripts/check_fresh_checkout.sh [pytest-args...]
# Exit 0 when the exported tree passes; nonzero otherwise.

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

echo "fresh-checkout: exporting tracked content from $repo_root"
git -C "$repo_root" archive --format=tar HEAD | tar -C "$scratch" -xf -

# Uncommitted-but-staged content is part of what a push would deliver; include
# it so the check reflects the tree about to be shared, not only the last commit.
if ! git -C "$repo_root" diff --cached --quiet; then
  echo "fresh-checkout: applying staged changes not yet committed"
  git -C "$repo_root" diff --cached --binary | (cd "$scratch" && git apply --whitespace=nowarn - || true)
fi

echo "fresh-checkout: running the suite against the exported tree"
cd "$scratch"
PYTHONPATH="$scratch/src" python3 -m pytest -q "$@"
