#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="/app/test_reports"
mkdir -p "$REPORT_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
GATE_LOG="$REPORT_DIR/release_polling_gate_${TS}.txt"

FRONTEND_REPORT_PATH="${1:-/app/test_result.md}"

echo "[Release Polling Gate]" | tee "$GATE_LOG"
echo "timestamp_utc=${TS}" | tee -a "$GATE_LOG"
echo "frontend_report_path=${FRONTEND_REPORT_PATH}" | tee -a "$GATE_LOG"

echo "\n[Step 1] Script gate" | tee -a "$GATE_LOG"
if ! bash /app/scripts/polling_guardrails_locked_protocol_check.sh | tee -a "$GATE_LOG"; then
  echo "RELEASE_GATE_STATUS=FAIL (script gate failed)" | tee -a "$GATE_LOG"
  printf "%s\n" "$GATE_LOG" > "$REPORT_DIR/release_polling_gate_latest.txt"
  exit 2
fi

echo "\n[Step 1b] Feature32 override writer static gate" | tee -a "$GATE_LOG"
if ! bash /app/scripts/feature32_override_write_gate.sh | tee -a "$GATE_LOG"; then
  echo "RELEASE_GATE_STATUS=FAIL (feature32 override write gate failed)" | tee -a "$GATE_LOG"
  # Contract compatibility anchor: bash scripts/feature32_override_write_gate.sh
  printf "%s\n" "$GATE_LOG" > "$REPORT_DIR/release_polling_gate_latest.txt"
  exit 2
fi

echo "\n[Step 2] Frontend observation gate" | tee -a "$GATE_LOG"
if ! bash /app/scripts/polling_guardrails_frontend_observation_check.sh "$FRONTEND_REPORT_PATH" | tee -a "$GATE_LOG"; then
  echo "RELEASE_GATE_STATUS=FAIL (frontend observation failed)" | tee -a "$GATE_LOG"
  printf "%s\n" "$GATE_LOG" > "$REPORT_DIR/release_polling_gate_latest.txt"
  exit 2
fi

echo "\n[Step 3] Variability check (history)" | tee -a "$GATE_LOG"
python - <<'PY' | tee -a "$GATE_LOG"
from pathlib import Path
import re
import sys

history = sorted(Path('/app/test_reports').glob('release_polling_gate_*.txt'))[-6:]
statuses = []
for p in history:
    text = p.read_text(encoding='utf-8', errors='ignore')
    m = re.search(r'RELEASE_GATE_STATUS=(PASS|FAIL)', text)
    if m:
        statuses.append(m.group(1))

print(f'history_files={len(history)}')
print(f'history_statuses={statuses}')

if len(statuses) >= 3:
    # variability lock: if oscillating PASS/FAIL in recent history, force RCA gate
    oscillation = any(statuses[i] != statuses[i-1] for i in range(1, len(statuses)))
    has_fail = 'FAIL' in statuses
    has_pass = 'PASS' in statuses
    if oscillation and has_fail and has_pass:
        evidence_path = Path('/app/test_reports/polling_guardrails_rca_fix_evidence.txt')
        evidence_text = evidence_path.read_text(encoding='utf-8', errors='ignore') if evidence_path.exists() else ''
        has_evidence = 'RCA_FIX_COMPLETED=YES' in evidence_text
        if not has_evidence:
            print('VARIABILITY_STATUS=FAIL (pass/fail oscillation detected; RCA/fix evidence required)')
            sys.exit(3)
        print(f'VARIABILITY_STATUS=PASS (oscillation detected but RCA evidence accepted: {evidence_path})')
        sys.exit(0)

print('VARIABILITY_STATUS=PASS')
PY

echo "\nRELEASE_GATE_STATUS=PASS" | tee -a "$GATE_LOG"
printf "%s\n" "$GATE_LOG" > "$REPORT_DIR/release_polling_gate_latest.txt"
