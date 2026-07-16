#!/bin/bash
# Pre-push Git hook — Deployment Gate Check
# Blocks git push if critical code issues (F821, F811, F601) are found
#
# Installation:
#   cp scripts/pre-push-gate.sh .git/hooks/pre-push
#   chmod +x .git/hooks/pre-push

set -e

RUFF_BIN="${RUFF_BIN:-ruff}"
BACKEND_DIR="$(cd "$(dirname "$0")/../.." && pwd)/backend"
GATE_RULES="F821,F811,F601"

echo "========================================"
echo "  Deploy Gate — Pre-Push Check"
echo "  Rules: $GATE_RULES"
echo "========================================"

if ! command -v "$RUFF_BIN" &> /dev/null; then
    echo "[WARN] ruff not found, skipping gate check"
    exit 0
fi

cd "$BACKEND_DIR"
OUTPUT=$("$RUFF_BIN" check . --select "$GATE_RULES" 2>&1) || true
FOUND=$(echo "$OUTPUT" | grep -oP 'Found \K\d+' || echo "0")

if [ "$FOUND" -gt 0 ]; then
    echo ""
    echo "[BLOCKED] $FOUND critical issue(s) detected!"
    echo ""
    echo "$OUTPUT"
    echo ""
    echo "Fix these issues before pushing:"
    echo "  F821 = Undefined name (runtime crash)"
    echo "  F811 = Redefined while unused (logic error)"
    echo "  F601 = Duplicate dict key (data loss)"
    echo ""
    echo "To bypass (emergency only): git push --no-verify"
    echo "========================================"
    exit 1
fi

echo "[PASSED] No critical issues found. Push allowed."

echo "Running Architecture Mode hard gate..."
if ! python "$BACKEND_DIR/scripts/architecture_mode_gate.py" > /tmp/architecture_mode_gate.log 2>&1; then
    echo ""
    echo "[BLOCKED] Architecture Mode hard gate failed!"
    cat /tmp/architecture_mode_gate.log
    echo ""
    echo "Fix architecture contract/deployment/test issues before pushing."
    echo "========================================"
    exit 1
fi

echo "[PASSED] Architecture Mode hard gate passed."
echo "========================================"
exit 0
