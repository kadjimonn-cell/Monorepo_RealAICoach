#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/test_reports}"
mkdir -p "$REPORT_DIR"

WINDOW_LINES="${POLLING_GUARDRAILS_WINDOW_LINES:-3000}"
MAX_429_TOTAL="${POLLING_GUARDRAILS_MAX_429_TOTAL:-120}"
MAX_429_GPS="${POLLING_GUARDRAILS_MAX_429_GPS:-60}"
MAX_429_NON_GPS="${POLLING_GUARDRAILS_MAX_429_NON_GPS:-60}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="$REPORT_DIR/polling_guardrails_${TS}.txt"

echo "[Polling Guardrails Locked Protocol Check]" | tee "$REPORT_PATH"
echo "timestamp_utc=${TS}" | tee -a "$REPORT_PATH"
echo "window_lines=${WINDOW_LINES}" | tee -a "$REPORT_PATH"
echo "max_429_total=${MAX_429_TOTAL}" | tee -a "$REPORT_PATH"
echo "max_429_gps=${MAX_429_GPS}" | tee -a "$REPORT_PATH"
echo "max_429_non_gps=${MAX_429_NON_GPS}" | tee -a "$REPORT_PATH"

echo "\n[1/3] Running locked-protocol contracts..." | tee -a "$REPORT_PATH"
pytest -q \
  "$ROOT_DIR/backend/tests/test_polling_guardrails_locked_protocol_contract.py" \
  "$ROOT_DIR/backend/tests/test_i18n_language_switch_deadlock_contract.py" \
  | tee -a "$REPORT_PATH"

echo "\n[2/4] Recent backend endpoint counters and threshold gate..." | tee -a "$REPORT_PATH"
python - <<'PY' | tee -a "$REPORT_PATH"
import re
from collections import Counter
from pathlib import Path
import os
import sys

log_path = Path(os.environ.get('BACKEND_LOG_PATH', '/var/log/supervisor/backend.out.log'))
if not log_path.exists():
    print('backend log not found')
    raise SystemExit(0)

window_lines = int(os.environ.get('POLLING_GUARDRAILS_WINDOW_LINES', '3000'))
max_429_total = int(os.environ.get('POLLING_GUARDRAILS_MAX_429_TOTAL', '120'))
max_429_gps = int(os.environ.get('POLLING_GUARDRAILS_MAX_429_GPS', '60'))
max_429_non_gps = int(os.environ.get('POLLING_GUARDRAILS_MAX_429_NON_GPS', '60'))

lines = log_path.read_text(encoding='utf-8', errors='ignore').splitlines()[-window_lines:]
targets = {
    '/api/gps/state',
    '/api/onboarding-ab/assign',
    '/api/subscriptions/renewal-banner',
    '/api/subscriptions/plans',
}

counter = Counter()
status_429_counter = Counter()
for ln in lines:
    m = re.search(r'"(GET|POST) (/api/[^ ]+) HTTP/1.1" (\d+)', ln)
    if not m:
        continue
    method, url, status = m.groups()
    url_base = url.split('?')[0]
    if url_base in targets or url_base.startswith('/api/notifications/'):
        counter[f'{method} {url_base} {status}'] += 1
        if status == '429':
            status_429_counter[url_base] += 1

for key, value in counter.most_common(20):
    print(f'{value:>6}  {key}')

total_429 = sum(status_429_counter.values())
gps_429 = status_429_counter.get('/api/gps/state', 0)
non_gps_429 = total_429 - gps_429

print('\n[Threshold Evaluation]')
print(f'total_429={total_429} (max={max_429_total})')
print(f'gps_429={gps_429} (max={max_429_gps})')
print(f'non_gps_429={non_gps_429} (max={max_429_non_gps})')

if total_429 > max_429_total or gps_429 > max_429_gps or non_gps_429 > max_429_non_gps:
    print('GATE_STATUS=FAIL')
    sys.exit(2)

print('GATE_STATUS=PASS')
PY

echo "\n[3/4] Guardrail source anchors" | tee -a "$REPORT_PATH"
rg -n "HARD_429_COOLDOWN_RULES|enableHeavyBackgroundPollers|getHybridPollingInterval|fallbackIntervalMs|GPS_MAX_POLL_INTERVAL_MS|GPS_MIN_POLL_INTERVAL_MS|onboarding:ab:assigned|renewal:banner:fetched" \
  "$ROOT_DIR/frontend/src/utils/hybridPolling.ts" \
  "$ROOT_DIR/frontend/src/context/RealtimeContext.tsx" \
  "$ROOT_DIR/frontend/src/services/api.ts" \
  "$ROOT_DIR/frontend/src/components/AppShell.tsx" \
  "$ROOT_DIR/frontend/src/hooks/useGlobalPlatformState.ts" \
  "$ROOT_DIR/frontend/src/components/admin/PerformanceGuardianPanel.tsx" \
  "$ROOT_DIR/frontend/src/components/admin/WebVitalsPanel.tsx" \
  "$ROOT_DIR/frontend/src/components/SmartOnboarding.tsx" \
  "$ROOT_DIR/frontend/src/components/RenewalBanner.tsx" \
  | tee -a "$REPORT_PATH"

echo "\n[4/4] Writing latest report pointer" | tee -a "$REPORT_PATH"
printf "%s\n" "$REPORT_PATH" > "$REPORT_DIR/polling_guardrails_latest_report.txt"

echo "\nDONE. report=${REPORT_PATH}" | tee -a "$REPORT_PATH"
