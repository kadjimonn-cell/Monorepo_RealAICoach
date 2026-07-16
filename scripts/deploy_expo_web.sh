#!/usr/bin/env bash
# Safe re-export + deploy of the Expo Web production bundle.
# Replaces /app/frontend/dist atomically to avoid partial-merge bugs
# (cp -r into an existing folder silently merges and can leave stale _expo bundles → white screens).
set -euo pipefail

cd /app/frontend

# ── Pre-deploy env guard ──────────────────────────────────────────────
# Fails loud BEFORE building if REACT_APP_BACKEND_URL / EXPO_PUBLIC_BACKEND_URL
# point to a hostname that doesn't match the current EXPO_TUNNEL_SUBDOMAIN.
# Without this, a stale preview URL baked into the bundle would silently
# break every component that reads process.env.REACT_APP_BACKEND_URL
# (CSV exports, WebSockets, direct API calls that bypass window.location.host).
echo "▶ Running pre-deploy env guard …"
if [ ! -f /app/frontend/.env ]; then
  echo "✗ /app/frontend/.env missing — cannot verify backend URL alignment." >&2
  exit 1
fi

env_get() {
  # Reads a KEY=value pair from /app/frontend/.env (first match, last wins).
  grep -E "^${1}=" /app/frontend/.env | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'"
}

SUBDOMAIN=$(env_get EXPO_TUNNEL_SUBDOMAIN)
REACT_URL=$(env_get REACT_APP_BACKEND_URL)
EXPO_URL=$(env_get EXPO_PUBLIC_BACKEND_URL)

if [ -z "$SUBDOMAIN" ]; then
  echo "✗ EXPO_TUNNEL_SUBDOMAIN is empty in /app/frontend/.env" >&2
  exit 1
fi
if [ -z "$REACT_URL" ]; then
  echo "✗ REACT_APP_BACKEND_URL is empty in /app/frontend/.env" >&2
  exit 1
fi
if [ -z "$EXPO_URL" ]; then
  echo "✗ EXPO_PUBLIC_BACKEND_URL is empty in /app/frontend/.env" >&2
  exit 1
fi

# Strip protocol + path to extract hostname
react_host=$(echo "$REACT_URL" | sed -E 's|^https?://||; s|/.*$||')
expo_host=$(echo "$EXPO_URL" | sed -E 's|^https?://||; s|/.*$||')

# Both URLs must point to the same host so window.location.host fallbacks
# and process.env fallbacks don't diverge in the compiled bundle.
if [ "$react_host" != "$expo_host" ]; then
  echo "✗ REACT_APP_BACKEND_URL host ($react_host) does not match EXPO_PUBLIC_BACKEND_URL host ($expo_host)" >&2
  echo "  Aborting build — fix /app/frontend/.env so both point to the same hostname." >&2
  exit 1
fi

# Expected preview hostname pattern: ${SUBDOMAIN}.preview.emergentagent.com
expected_prefix="${SUBDOMAIN}."
if [[ "$react_host" != ${expected_prefix}* ]]; then
  echo "✗ Backend URL host ($react_host) does not start with EXPO_TUNNEL_SUBDOMAIN ($SUBDOMAIN)" >&2
  echo "  The deployed bundle would reference a stale preview URL." >&2
  echo "  Fix: update REACT_APP_BACKEND_URL + EXPO_PUBLIC_BACKEND_URL in /app/frontend/.env so their host starts with '${expected_prefix}'" >&2
  exit 1
fi

echo "✓ Env guard passed — subdomain=$SUBDOMAIN, backend_host=$react_host"

# ── Global guard-test gate (current-codebase, fail-closed) ────────────
# Locked protocol: deploy is blocked if any required guard contract is
# missing or fails. This list must reference files that exist in the current
# codebase (no stale legacy paths).
echo "▶ Running global guard tests …"
GUARD_TESTS=(
  tests/test_env_guard.py
  tests/test_stale_url_ci_guard.py
  tests/test_issue11_theme_consistency_contract.py
  tests/test_polling_guardrails_locked_protocol_contract.py
  tests/test_polling_guardrails_release_gate_contract.py
  tests/test_i18n_language_switch_deadlock_contract.py
)

for test_file in "${GUARD_TESTS[@]}"; do
  if [ ! -f "/app/backend/${test_file}" ]; then
    echo "✗ Required guard test missing: /app/backend/${test_file}" >&2
    echo "  Deploy blocked (fail-closed). Update guard list to current codebase contracts." >&2
    exit 1
  fi
done

if ! (cd /app/backend && python -m pytest "${GUARD_TESTS[@]}" -q --tb=short --disable-warnings); then
  echo "✗ Global guard tests failed — deploy blocked." >&2
  echo "  Fix the failing guard(s) before shipping." >&2
  exit 1
fi
echo "✓ Global guard tests passed."

TMP_DIR=$(mktemp -d -t expo-export.XXXXXX)

echo "▶ Exporting expo web to $TMP_DIR …"
CI=1 npx expo export -p web --output-dir "$TMP_DIR"

# ── Post-build stale-URL sentinel ─────────────────────────────────────
# Scan the generated bundle for any hostname that does NOT match the
# current subdomain (except localhost). Catches cases where a .env change
# was applied AFTER the metro cache was primed against the old value.
echo "▶ Scanning bundle for stale preview URLs …"
stale_matches=$(grep -rhoE 'https://[a-z0-9-]+\.preview\.emergentagent\.com' "$TMP_DIR" 2>/dev/null \
  | sort -u \
  | grep -v "https://${SUBDOMAIN}\.preview\.emergentagent\.com" || true)

if [ -n "$stale_matches" ]; then
  echo "✗ Stale preview URL(s) detected in bundle:" >&2
  echo "$stale_matches" | sed 's/^/    /' >&2
  echo "  Expected only: https://coach-web-preview.preview.emergentagent.com" >&2
  echo "  Run: cd /app/frontend && rm -rf .metro-cache && $(basename "$0")" >&2
  rm -rf "$TMP_DIR"
  exit 1
fi
echo "✓ Bundle scan clean — only https://coach-web-preview.preview.emergentagent.com referenced."

echo "▶ Replacing /app/frontend/dist atomically …"
rm -rf /app/frontend/dist
mv "$TMP_DIR" /app/frontend/dist

echo "▶ Restarting expo_manual …"
sudo supervisorctl restart expo_manual >/dev/null
sleep 3

HOME_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/)
echo "✓ Home responded with $HOME_CODE"
if [ "$HOME_CODE" != "200" ]; then
  echo "✗ Deploy failed — home returned $HOME_CODE" >&2
  exit 1
fi
echo "✅ Deploy complete."
