#!/usr/bin/env bash
set -euo pipefail

# Contract compatibility anchor:
# email_subject_overrides.(update_one|insert_one|update_many|replace_one)

ROOT_DIR="${ROOT_DIR:-/app}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/test_reports}"
mkdir -p "$REPORT_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="$REPORT_DIR/feature32_override_write_gate_${TS}.txt"

echo "[Feature32 Override Write Gate]" | tee "$REPORT_PATH"
echo "timestamp_utc=${TS}" | tee -a "$REPORT_PATH"

ALLOWLIST=(
  "$ROOT_DIR/backend/services/email_override_service.py"
  "$ROOT_DIR/backend/scripts/remediate_protected_subject_overrides.py"
)

echo "\n[1/3] Scanning for direct email_subject_overrides writes..." | tee -a "$REPORT_PATH"
MATCHES=$(rg -n "email_subject_overrides\.(update_one|insert_one|update_many|replace_one)" "$ROOT_DIR/backend" -g '!backend/tests/**' || true)
echo "$MATCHES" | tee -a "$REPORT_PATH"

if [[ -z "${MATCHES// }" ]]; then
  echo "FEATURE32_OVERRIDE_WRITE_GATE=PASS (no direct writes found)" | tee -a "$REPORT_PATH"
  printf "%s\n" "$REPORT_PATH" > "$REPORT_DIR/feature32_override_write_gate_latest.txt"
  exit 0
fi

echo "\n[2/3] Enforcing allowlist..." | tee -a "$REPORT_PATH"
violations=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  file_path=$(echo "$line" | cut -d: -f1)
  allowed=false
  for wl in "${ALLOWLIST[@]}"; do
    if [[ "$file_path" == "$wl" ]]; then
      allowed=true
      break
    fi
  done
  if [[ "$allowed" == false ]]; then
    echo "VIOLATION: $line" | tee -a "$REPORT_PATH"
    violations=$((violations + 1))
  fi
done <<< "$MATCHES"

echo "\n[3/3] Final gate verdict" | tee -a "$REPORT_PATH"
if [[ "$violations" -gt 0 ]]; then
  echo "FEATURE32_OVERRIDE_WRITE_GATE=FAIL (violations=${violations})" | tee -a "$REPORT_PATH"
  printf "%s\n" "$REPORT_PATH" > "$REPORT_DIR/feature32_override_write_gate_latest.txt"
  exit 2
fi

echo "FEATURE32_OVERRIDE_WRITE_GATE=PASS" | tee -a "$REPORT_PATH"
printf "%s\n" "$REPORT_PATH" > "$REPORT_DIR/feature32_override_write_gate_latest.txt"
