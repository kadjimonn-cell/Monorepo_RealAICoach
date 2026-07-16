#!/bin/bash
# build-and-serve.sh — Permanent production build script for RealAICoach
# This script rebuilds the production bundle and restarts the production server.
# Run after any frontend code change to ensure the latest optimized build is served.
#
# Usage: bash /app/frontend/build-and-serve.sh

set -e

FRONTEND_DIR="/app/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

echo "[1/4] Cleaning old build..."
rm -rf "$DIST_DIR"

echo "[2/4] Building production bundle..."
cd "$FRONTEND_DIR"
npx expo export --platform web --output-dir dist 2>&1 | tail -5

echo "[3/4] Verifying build..."
if [ ! -f "$DIST_DIR/server/index.html" ]; then
  echo "ERROR: Production build failed — no index.html found"
  exit 1
fi

MAIN_JS=$(find "$DIST_DIR/client/_expo/static/js/web/" -name "index-*.js" 2>/dev/null | head -1)
if [ -z "$MAIN_JS" ]; then
  echo "ERROR: No main JS bundle found"
  exit 1
fi

RAW_SIZE=$(stat -c%s "$MAIN_JS")
GZIP_SIZE=$(gzip -c "$MAIN_JS" | wc -c)
echo "Main bundle: $(( RAW_SIZE / 1024 ))KB raw, $(( GZIP_SIZE / 1024 ))KB gzipped"

echo "[4/4] Restarting production server..."
sudo supervisorctl restart expo_manual

sleep 3

# Verify server is running
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
if [ "$HTTP_CODE" = "200" ]; then
  echo "Production server is running (HTTP $HTTP_CODE)"
  echo "Build complete!"
else
  echo "WARNING: Server returned HTTP $HTTP_CODE"
fi
