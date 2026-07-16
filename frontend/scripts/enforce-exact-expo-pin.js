#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const PKG_PATH = path.resolve(__dirname, '..', 'package.json');
const EXACT_EXPO_VERSION = '54.0.34';

function main() {
  if (!fs.existsSync(PKG_PATH)) {
    console.error('[enforce-exact-expo-pin] package.json not found:', PKG_PATH);
    process.exit(2);
  }

  const pkgRaw = fs.readFileSync(PKG_PATH, 'utf8');
  const pkg = JSON.parse(pkgRaw);
  const deps = pkg.dependencies || {};
  const currentExpo = String(deps.expo || '').trim();

  if (!currentExpo) {
    console.error('[enforce-exact-expo-pin] Missing dependencies.expo');
    process.exit(2);
  }

  if (currentExpo === EXACT_EXPO_VERSION) {
    console.log(`[enforce-exact-expo-pin] expo already exact pinned (${EXACT_EXPO_VERSION})`);
    return;
  }

  deps.expo = EXACT_EXPO_VERSION;
  pkg.dependencies = deps;
  fs.writeFileSync(PKG_PATH, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8');
  console.warn(`[enforce-exact-expo-pin] Rewrote expo pin ${currentExpo} -> ${EXACT_EXPO_VERSION}`);
}

main();
