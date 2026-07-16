#!/usr/bin/env node
// Fails the build when a CSS/querySelector attribute selector contains a second attribute,
// e.g. [data-testid="app-shell" testID="app-shell"] — invalid CSS that silently drops the
// entire rule list (root cause of the 2026-07-11 global responsiveness outage).

const fs = require('fs');
const path = require('path');

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const QUALITY_DIR = path.join(FRONTEND_ROOT, '.quality');
const REPORT_PATH = path.join(QUALITY_DIR, 'selector_validity_report.json');

const SCAN_ROOTS = [path.join(FRONTEND_ROOT, 'app'), path.join(FRONTEND_ROOT, 'src')];
const SCAN_EXTS = new Set(['.ts', '.tsx', '.css']);

// Matches [data-testid="..."] (or *=, ^=, $=, |=, ~=) followed by a second attribute inside the same brackets.
const MALFORMED_SELECTOR_RX = /\[\s*data-testid\s*[*^$|~]?=\s*(?:"[^"\]]*"|'[^'\]]*')\s+[A-Za-z_][A-Za-z0-9_-]*\s*=/g;

function collectFiles(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) collectFiles(full, out);
    else if (SCAN_EXTS.has(path.extname(entry.name))) out.push(full);
  }
}

function run() {
  const files = [];
  for (const root of SCAN_ROOTS) {
    if (fs.existsSync(root)) collectFiles(root, files);
  }

  const violations = [];
  for (const file of files) {
    const text = fs.readFileSync(file, 'utf8');
    if (!text.includes('[data-testid')) continue;
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i += 1) {
      MALFORMED_SELECTOR_RX.lastIndex = 0;
      const match = MALFORMED_SELECTOR_RX.exec(lines[i]);
      if (match) {
        violations.push({
          file: path.relative(FRONTEND_ROOT, file),
          line: i + 1,
          snippet: lines[i].trim().slice(0, 160),
        });
      }
    }
  }

  fs.mkdirSync(QUALITY_DIR, { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify({
    generatedAt: new Date().toISOString(),
    scannedFiles: files.length,
    violationCount: violations.length,
    violations,
  }, null, 2));

  if (violations.length > 0) {
    console.error(`[selector-validity-gate] FAILED — ${violations.length} malformed attribute selector(s) found:`);
    for (const v of violations) {
      console.error(`  ${v.file}:${v.line}  ${v.snippet}`);
    }
    console.error('[selector-validity-gate] A second attribute inside [data-testid="..."] is invalid CSS and drops the ENTIRE rule. Remove the extra attribute.');
    console.error(`[selector-validity-gate] Report: ${REPORT_PATH}`);
    process.exit(1);
  }

  console.log(`[selector-validity-gate] PASS — ${files.length} files scanned, 0 malformed selectors.`);
  console.log(`[selector-validity-gate] Report: ${REPORT_PATH}`);
}

run();
