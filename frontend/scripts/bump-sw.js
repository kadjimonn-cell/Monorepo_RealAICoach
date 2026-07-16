#!/usr/bin/env node
/**
 * bump-sw.js
 * ----------
 * Build-time Service Worker version auto-bumper.
 *
 * Why: `expo export` regenerates content-hashed bundle filenames every run.
 * If the service worker's cache names stay identical across deploys, the
 * `activate` handler does not evict the stale chunk cache and clients
 * explode with "ChunkLoadError → Something Went Wrong". This script makes
 * that impossible by tying the SW cache names to the fresh bundle hash.
 *
 * What it does:
 *   1. Walks `dist/client/_expo/static/js/web/` for the main `index-*.js`
 *      bundle.
 *   2. Extracts the first 8 hex chars of the bundle hash.
 *   3. Rewrites the three `CACHE_NAME` / `STATIC_CACHE` / `API_CACHE`
 *      constants in:
 *        - dist/sw.js         (served to clients)
 *        - dist/client/sw.js  (served under /client prefix)
 *        - public/sw.js       (source template; intentionally NOT modified at
 *                              runtime to avoid build-fingerprint loops)
 *   4. Prints a summary and exits 0 on success, non-zero on failure.
 *
 * Invoked automatically by the `export:web` npm script. Safe to re-run —
 * idempotent when the bundle hash is unchanged.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const FRONTEND = path.resolve(__dirname, '..');
const BUNDLE_DIR = path.join(FRONTEND, 'dist', 'client', '_expo', 'static', 'js', 'web');
const SW_PATHS = [
  path.join(FRONTEND, 'dist', 'sw.js'),
  path.join(FRONTEND, 'dist', 'client', 'sw.js'),
];

function fail(msg, code = 1) {
  console.error(`[bump-sw] ERROR: ${msg}`);
  process.exit(code);
}

function extractBundleHash() {
  if (!fs.existsSync(BUNDLE_DIR)) {
    fail(`bundle dir missing: ${BUNDLE_DIR} — run \`expo export --platform web\` first.`);
  }
  const candidates = fs.readdirSync(BUNDLE_DIR).filter(
    (f) => /^index-[a-f0-9]+\.js$/.test(f)
  );
  if (candidates.length === 0) {
    fail('no index-<hash>.js bundle found');
  }
  // Use the newest index-*.js (export always produces exactly one).
  const picked = candidates
    .map((f) => ({ f, mtime: fs.statSync(path.join(BUNDLE_DIR, f)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime)[0].f;
  const m = picked.match(/^index-([a-f0-9]+)\.js$/);
  if (!m) fail(`could not parse hash from ${picked}`);
  return { bundle: picked, hash: m[1] };
}

function buildVersions(hashShort) {
  return {
    CACHE_NAME: `realaicoach-v-${hashShort}`,
    STATIC_CACHE: `realaicoach-static-${hashShort}`,
    API_CACHE: `realaicoach-api-${hashShort}`,
  };
}

function rewrite(filePath, versions) {
  if (!fs.existsSync(filePath)) {
    console.warn(`[bump-sw] skip (missing): ${filePath}`);
    return { changed: false };
  }
  let src = fs.readFileSync(filePath, 'utf8');
  let changed = false;
  for (const key of ['CACHE_NAME', 'STATIC_CACHE', 'API_CACHE']) {
    const re = new RegExp(`const ${key}\\s*=\\s*'[^']+'`);
    if (!re.test(src)) {
      fail(`${filePath}: could not find \`const ${key} = '...'\` declaration`);
    }
    const replacement = `const ${key} = '${versions[key]}'`;
    const next = src.replace(re, replacement);
    if (next !== src) {
      changed = true;
      src = next;
    }
  }
  if (changed) {
    fs.writeFileSync(filePath, src);
    console.log(`[bump-sw] patched ${path.relative(FRONTEND, filePath)}`);
  } else {
    console.log(`[bump-sw] in-sync    ${path.relative(FRONTEND, filePath)}`);
  }
  return { changed };
}

function main() {
  const { bundle, hash } = extractBundleHash();
  const hashShort = hash.slice(0, 8);
  const versions = buildVersions(hashShort);
  console.log(`[bump-sw] bundle: ${bundle}`);
  console.log(`[bump-sw] hashShort: ${hashShort}`);
  console.log(`[bump-sw] versions:`, versions);

  let totalChanged = 0;
  for (const p of SW_PATHS) {
    const { changed } = rewrite(p, versions);
    if (changed) totalChanged += 1;
  }
  console.log(`[bump-sw] ${totalChanged} SW file(s) updated.`);
  console.log('[bump-sw] done.');
}

main();
