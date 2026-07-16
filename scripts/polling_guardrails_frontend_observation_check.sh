#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${1:-}"
if [[ -z "${REPORT_PATH}" ]]; then
  if [[ -f /app/test_result.md ]]; then
    REPORT_PATH="/app/test_result.md"
  else
    echo "ERROR: frontend observation report path required (or /app/test_result.md must exist)"
    exit 2
  fi
fi

if [[ ! -f "${REPORT_PATH}" ]]; then
  echo "ERROR: report file not found: ${REPORT_PATH}"
  exit 2
fi

MAX_429_TOTAL="${POLLING_GUARDRAILS_FRONTEND_MAX_429_TOTAL:-120}"

python - <<'PY' "${REPORT_PATH}" "${MAX_429_TOTAL}"
import re
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
max_429 = int(sys.argv[2])
text = report_path.read_text(encoding='utf-8', errors='ignore')

norm = text.lower()

total_429 = None
patterns = [
    r'total_429_count\s*[:=]\s*(\d+)',
    r'total\s+429\s+count\s*[:=]\s*(\d+)',
    r'rate[- ]limited requests\s*[:=]\s*(\d+)',
    r'429\s+count\s*[:=]\s*(\d+)',
]
for pat in patterns:
    m = re.search(pat, norm)
    if m:
        total_429 = int(m.group(1))
        break

interactive = 'interactive' in norm and ('yes' in norm or 'pass' in norm or '✅' in text)
flood_present = None
if re.search(r'flood\s+present\s*[:=]\s*yes', norm):
    flood_present = True
elif re.search(r'flood\s+present\s*[:=]\s*no', norm):
    flood_present = False
elif re.search(r'flood_present\s*[:=]\s*yes', norm):
    flood_present = True
elif re.search(r'flood_present\s*[:=]\s*no', norm):
    flood_present = False
elif 'runaway flood' in norm and ('not present' in norm or 'resolved' in norm):
    flood_present = False
elif 'runaway flood' in norm and ('present' in norm or 'critical regression' in norm):
    flood_present = True

if total_429 is None:
    # Conservative behavior per locked protocol: if no machine-readable count, fail
    print(f'FRONTEND_OBSERVATION_STATUS=FAIL (no parseable total 429 count in {report_path})')
    sys.exit(2)

print(f'frontend_report={report_path}')
print(f'frontend_total_429={total_429}')
print(f'frontend_flood_present={flood_present}')
print(f'frontend_interactive_signal={interactive}')
print(f'frontend_max_429_allowed={max_429}')

if total_429 > max_429:
    print('FRONTEND_OBSERVATION_STATUS=FAIL (429 threshold exceeded)')
    sys.exit(2)

if flood_present is True:
    print('FRONTEND_OBSERVATION_STATUS=FAIL (flood marked present)')
    sys.exit(2)

print('FRONTEND_OBSERVATION_STATUS=PASS')
PY
