#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const MANIFEST_PATH = path.join(__dirname, 'ui-contract-manifest.json');

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function hasTestIdRef(text, testId) {
  const escaped = testId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = [
    new RegExp(`data-testid\\s*=\\s*['"]${escaped}['"]`),
    new RegExp(`testID\\s*=\\s*['"]${escaped}['"]`),
    new RegExp(`${escaped}`),
  ];
  return patterns.some((p) => p.test(text));
}

function run() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    console.error('[ui-contract-gate] Missing manifest:', MANIFEST_PATH);
    process.exit(1);
  }

  const manifest = readJson(MANIFEST_PATH);
  const contracts = Array.isArray(manifest.contracts) ? manifest.contracts : [];
  const errors = [];

  for (const contract of contracts) {
    const rel = String(contract.file || '').replace(/\\/g, '/');
    const filePath = path.join(ROOT, rel);
    if (!fs.existsSync(filePath)) {
      errors.push(`[${contract.name}] file not found: ${rel}`);
      continue;
    }

    const text = fs.readFileSync(filePath, 'utf8');
    const required = Array.isArray(contract.required_testids) ? contract.required_testids : [];
    for (const id of required) {
      if (!hasTestIdRef(text, String(id))) {
        errors.push(`[${contract.name}] missing required test id '${id}' in ${rel}`);
      }
    }
  }

  const matrix = manifest.snapshot_matrix || {};
  const viewports = Array.isArray(matrix.viewports) ? matrix.viewports : [];
  const routes = Array.isArray(matrix.routes) ? matrix.routes : [];
  if (viewports.length < 3) {
    errors.push('[snapshot_matrix] must include at least 3 viewport targets');
  }
  if (routes.length < 4) {
    errors.push('[snapshot_matrix] must include at least 4 route targets');
  }

  if (errors.length) {
    console.error('\n[ui-contract-gate] FAILED');
    errors.forEach((e) => console.error(' -', e));
    process.exit(1);
  }

  console.log('[ui-contract-gate] PASS');
  console.log(` - Contracts checked: ${contracts.length}`);
  console.log(` - Snapshot matrix: ${viewports.length} viewports x ${routes.length} routes`);
}

run();
