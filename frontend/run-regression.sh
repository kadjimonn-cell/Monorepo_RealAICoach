#!/bin/bash
# run-regression.sh — Run the full Playwright regression suite
# Usage: bash run-regression.sh [optional: specific test file]
#
# Prerequisites:
#   - Frontend built: cd /app/frontend && bash build-and-serve.sh
#   - Backend running: sudo supervisorctl status backend
#
# Examples:
#   bash run-regression.sh                          # Run strict CI smoke sequence (default)
#   bash run-regression.sh regression-suite         # Run only regression suite
#   bash run-regression.sh --grep "WhatsNew"        # Run WhatsNew tests only
#   bash run-regression.sh --all                    # Run all e2e specs

set -euo pipefail
cd /app/frontend

# Resolve base URL
BASE_URL=$(grep REACT_APP_BACKEND_URL .env | cut -d '=' -f2)
if [ -z "$BASE_URL" ]; then
  echo "ERROR: REACT_APP_BACKEND_URL not found in .env"
  exit 1
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║  Playwright Regression Suite                     ║"
echo "║  Base URL: $BASE_URL                             "
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Check services
echo "[1/4] Checking services..."
curl -sf "$BASE_URL/api/health" > /dev/null 2>&1 || { echo "ERROR: Backend not responding"; exit 1; }
curl -sf "$BASE_URL" > /dev/null 2>&1 || { echo "ERROR: Frontend not responding"; exit 1; }
echo "  Backend: OK"
echo "  Frontend: OK"
echo ""

# Ensure Playwright browsers are installed
echo "[2/4] Ensuring Playwright browsers..."
if ! npx playwright install --with-deps chromium 2>/dev/null; then
  echo "  WARNING: Could not install Playwright browsers (may already be installed)"
fi
echo "  Chromium: OK"
echo ""

# Export E2E_BASE_URL for Playwright config
export E2E_BASE_URL="$BASE_URL"

# Run tests
echo "[3/4] Running tests..."
SPEC_FILE="${1:-}"
EXTRA_ARGS="${@:2}"
STRICT_SMOKE_SPECS=(
  e2e/header-actions-snapshots.spec.ts
  e2e/auth-journey-gate.spec.ts
  e2e/wake-admin-smoke.spec.ts
  e2e/auth-blank-storage-guard.spec.ts
  e2e/subscription-payments-visual-regression.spec.ts
  e2e/welcome-first-paint-regression.spec.ts
)

if [ -n "$SPEC_FILE" ] && [[ "$SPEC_FILE" != --* ]]; then
  node node_modules/@playwright/test/cli.js test "e2e/${SPEC_FILE}.spec.ts" \
    --project=desktop-chromium \
    --reporter=list \
    $EXTRA_ARGS
elif [ "$SPEC_FILE" = "--all" ]; then
  node node_modules/@playwright/test/cli.js test e2e/*.spec.ts \
    --project=desktop-chromium \
    --reporter=list
elif [ -n "$SPEC_FILE" ]; then
  node node_modules/@playwright/test/cli.js test e2e/regression-suite.spec.ts \
    --project=desktop-chromium \
    --reporter=list \
    "$SPEC_FILE" $EXTRA_ARGS
else
  node node_modules/@playwright/test/cli.js test "${STRICT_SMOKE_SPECS[@]}" \
    --project=desktop-chromium \
    --reporter=list
fi

echo ""
echo "[4/4] Done!"
echo "  HTML report: npx playwright show-report playwright-report"
