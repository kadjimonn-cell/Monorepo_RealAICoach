#!/usr/bin/env bash
set -euo pipefail

cd /app
git config core.hooksPath .githooks
echo "✅ Git hooks path set to .githooks"
