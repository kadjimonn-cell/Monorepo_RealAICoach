#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const FEATURES_ROOT = path.join(PROJECT_ROOT, 'app', 'features');
const SOURCE_EXT = new Set(['.ts', '.tsx', '.js', '.jsx']);

function walkFiles(rootDir) {
  const out = [];
  if (!fs.existsSync(rootDir)) return out;
  const stack = [rootDir];
  while (stack.length) {
    const dir = stack.pop();
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === 'build') continue;
        stack.push(full);
        continue;
      }
      if (SOURCE_EXT.has(path.extname(entry.name))) out.push(full);
    }
  }
  return out;
}

function rel(filePath) {
  return path.relative(PROJECT_ROOT, filePath).replace(/\\/g, '/');
}

function hasRawFetch(source) {
  // Reject direct browser/global fetch calls.
  // Allow shadowed/local helper names by requiring no local declaration match.
  const hasFetchCall = /(^|[^\w$.])fetch\s*\(/m.test(source);
  if (!hasFetchCall) return false;

  const localFetchDeclaration = /\b(?:const|let|var)\s+fetch\s*=|\bfunction\s+fetch\s*\(/m.test(source);
  if (localFetchDeclaration) {
    // Still fail if explicit global fetch is used.
    return /\b(?:window|globalThis)\.fetch\s*\(/m.test(source);
  }

  return true;
}

function main() {
  const files = walkFiles(FEATURES_ROOT);
  const violations = [];

  for (const filePath of files) {
    let source = '';
    try {
      source = fs.readFileSync(filePath, 'utf8');
    } catch {
      continue;
    }

    if (source.includes('@raw-fetch-feature-gate-ignore')) continue;
    if (hasRawFetch(source)) violations.push(rel(filePath));
  }

  console.log(`[raw-fetch-gate] scanned files: ${files.length}`);
  if (violations.length > 0) {
    console.error('[raw-fetch-gate] FAIL: raw fetch() detected in feature routes:');
    violations.forEach((v) => console.error(` - ${v}`));
    process.exit(1);
  }

  console.log('[raw-fetch-gate] PASS: no raw fetch() usage in app/features.');
}

main();
