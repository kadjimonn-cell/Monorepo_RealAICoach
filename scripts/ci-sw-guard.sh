#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# ci-sw-guard.sh
# Pre-deploy invariant check. Runs every test that locks in the
# outage-proof SW contract. Exit 0 = safe to ship. Non-zero = DO NOT SHIP.
#
# Intended to be invoked from:
#   • GitHub Actions (.github/workflows/sw-guard.yml)
#   • Local pre-push hook (scripts/install-git-hooks.sh)
#   • Any CI runner (exit-code driven)
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
export PYTHONPATH="${REPO_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

echo "┌────────────────────────────────────────────────────────────┐"
echo "│  SW Invariant Guard — enforcing outage-proof contract       │"
echo "└────────────────────────────────────────────────────────────┘"

# 1) The auto-bumper script + package.json wiring + self-heal listeners
# must all pass static + sandbox-integration guards.
python3 -m pytest \
  backend/tests/test_sw_bump_script.py \
  backend/tests/test_sw_self_healing.py \
  -v --tb=short --color=yes

# 2) Node must be available so `yarn export:web` can actually run bump-sw.js.
if ! command -v node >/dev/null 2>&1; then
  echo "❌ node is not installed — bump-sw.js cannot run in this CI image."
  exit 2
fi

# 3) Lightweight invocation of the bumper in --check mode (idempotency).
if [[ -d "frontend/dist/client/_expo/static/js/web" ]]; then
  # Snapshot current SW contents
  before_sw="$(sha256sum frontend/dist/sw.js | cut -d' ' -f1 || true)"
  node frontend/scripts/bump-sw.js >/dev/null
  after_sw="$(sha256sum frontend/dist/sw.js | cut -d' ' -f1 || true)"
  if [[ "$before_sw" != "$after_sw" ]]; then
    echo "❌ dist/sw.js was OUT OF SYNC with the current bundle."
    echo "   Run \`yarn export:web\` (or \`yarn bump-sw\`) and commit the result."
    exit 3
  fi
  echo "✔ dist/sw.js is in sync with bundle hash."
else
  echo "ℹ No dist/ present — skipping live-dist drift check."
fi

echo
echo "✅  SW Invariant Guard PASSED — safe to deploy."
