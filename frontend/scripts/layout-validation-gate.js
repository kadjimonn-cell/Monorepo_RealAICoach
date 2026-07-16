#!/usr/bin/env node
/* eslint-env node */
/**
 * GLS Layout Validation Gate
 *
 * Modes:
 * - strict (default / --strict-zero): fail on any WARN/FAIL
 * - regression (--regression): fail only on FAIL or newly introduced WARN signatures
 * - baseline update (--update-baseline): refresh warning signature baseline
 */
'use strict';

const fs = require('fs');
const path = require('path');
const {
  summarize,
  signaturesToFiles,
  printOwnerSummary,
} = require('./regression-owner-map');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/layout-validation-gate.js'));
const FRONTEND_ROOT = path.resolve(scriptDir, '..');
const ALLOWED_MAX_WIDTHS = new Set([960, 1240, 1440]);
const SCAN_DIRS = [
  path.join(FRONTEND_ROOT, 'src', 'components'),
  path.join(FRONTEND_ROOT, 'app'),
];
const FILE_EXTENSIONS = ['.tsx', '.ts'];
const IGNORE_PATTERNS = [
  /node_modules/,
  /\.test\./,
  /\.spec\./,
  /__tests__/,
  /theme-build-gate/,
  /layout-validation-gate/,
  /scripts\//,
];

const BASELINE_FILE = path.join(scriptDir, 'layout-validation-baseline.json');
const REPORT_FILE = path.join(FRONTEND_ROOT, '.quality', 'layout_validation_report.json');
const OWNER_REPORT_FILE = path.join(FRONTEND_ROOT, '.quality', 'layout_regression_ownership_report.json');

const STRICT_ZERO_MODE = process.argv.includes('--strict-zero') || (!process.argv.includes('--regression') && !process.argv.includes('--update-baseline'));
const REGRESSION_MODE = process.argv.includes('--regression') || process.argv.includes('--update-baseline');
const UPDATE_BASELINE = process.argv.includes('--update-baseline');

const findings = { FAIL: [], WARN: [] };

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function signatureOfFinding(f) {
  return `${f.file}::${f.rule}::${String(f.raw || '').trim()}`;
}

function scanFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  const relPath = path.relative(FRONTEND_ROOT, filePath).replace(/\\/g, '/');

  if (content.includes('@gls-exempt') || content.includes('@layout-exempt')) return;

  lines.forEach((line, idx) => {
    const lineNum = idx + 1;
    const trimmed = line.trim();
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return;

    const fixedWidthMatch = trimmed.match(/width:\s*(\d{3,4})\s*[,}]/);
    if (fixedWidthMatch) {
      const val = parseInt(fixedWidthMatch[1], 10);
      if (val > 200 && !ALLOWED_MAX_WIDTHS.has(val)) {
        if (!trimmed.includes('maxWidth') && !trimmed.includes('height:') && !trimmed.includes('minWidth')) {
          findings.WARN.push({
            file: relPath,
            line: lineNum,
            rule: 'FIXED_WIDTH',
            detail: `Fixed width ${val}px detected. Use percentage, flex, or GLS container.`,
            raw: trimmed.substring(0, 120),
          });
        }
      }
    }

    const maxWidthMatch = trimmed.match(/maxWidth:\s*(\d+)/);
    if (maxWidthMatch) {
      const val = parseInt(maxWidthMatch[1], 10);
      if (val > 600 && !ALLOWED_MAX_WIDTHS.has(val)) {
        findings.WARN.push({
          file: relPath,
          line: lineNum,
          rule: 'NON_STANDARD_MAX_WIDTH',
          detail: `maxWidth: ${val} is not a GLS standard (960, 1240, 1440). Consider using GLSContainer.`,
          raw: trimmed.substring(0, 120),
        });
      }
    }

    if (trimmed.includes("margin: '0 auto'") || trimmed.includes('margin: "0 auto"')) {
      findings.WARN.push({
        file: relPath,
        line: lineNum,
        rule: 'INLINE_CENTERING',
        detail: 'Inline margin: 0 auto detected. Use GLSContainer for consistent centering.',
        raw: trimmed.substring(0, 120),
      });
    }
  });
}

function walkDir(dir) {
  if (!fs.existsSync(dir)) return;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (IGNORE_PATTERNS.some((p) => p.test(fullPath))) continue;
    if (entry.isDirectory()) {
      walkDir(fullPath);
    } else if (FILE_EXTENSIONS.some((ext) => entry.name.endsWith(ext))) {
      scanFile(fullPath);
    }
  }
}

console.log('[gls-layout-gate] Scanning for layout compliance...\n');
for (const dir of SCAN_DIRS) walkDir(dir);

const failCount = findings.FAIL.length;
const warnCount = findings.WARN.length;

if (failCount > 0) {
  console.log(`\n  FAIL (${failCount} blocking):\n`);
  findings.FAIL.forEach((f) => {
    console.log(`    ${f.file}:${f.line} [${f.rule}] ${f.detail}`);
  });
}

if (warnCount > 0) {
  console.log(`\n  WARN (${warnCount} advisory):\n`);
  findings.WARN.slice(0, 20).forEach((f) => {
    console.log(`    ${f.file}:${f.line} [${f.rule}] ${f.detail}`);
  });
  if (warnCount > 20) {
    console.log(`    ... and ${warnCount - 20} more warnings`);
  }
}

console.log(`\n[gls-layout-gate] Results: ${failCount} FAIL, ${warnCount} WARN\n`);

const warnSignatures = Array.from(new Set(findings.WARN.map(signatureOfFinding))).sort();
writeJson(REPORT_FILE, {
  generated_at: new Date().toISOString(),
  mode: UPDATE_BASELINE ? 'update-baseline' : (REGRESSION_MODE ? 'regression' : 'strict'),
  fail_count: failCount,
  warn_count: warnCount,
  warn_signature_count: warnSignatures.length,
  warn_signatures: warnSignatures,
});

if (UPDATE_BASELINE) {
  writeJson(BASELINE_FILE, {
    generated_at: new Date().toISOString(),
    note: 'Regression baseline for GLS layout validation. Gate fails only on newly introduced WARN signatures in regression mode.',
    warn_signatures: warnSignatures,
  });
  console.log(`[gls-layout-gate] Baseline updated: ${BASELINE_FILE} (${warnSignatures.length} signatures)`);
  process.exit(0);
}

if (REGRESSION_MODE) {
  if (!fs.existsSync(BASELINE_FILE)) {
    console.error(`[gls-layout-gate] FAIL: baseline missing for regression mode: ${BASELINE_FILE}`);
    console.error('[gls-layout-gate] Run with --update-baseline to establish baseline.');
    process.exit(1);
  }

  let baseline = { warn_signatures: [] };
  try {
    baseline = JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8'));
  } catch (e) {
    console.error(`[gls-layout-gate] FAIL: unable to parse baseline file: ${e?.message || e}`);
    process.exit(1);
  }

  const baselineSet = new Set(Array.isArray(baseline?.warn_signatures) ? baseline.warn_signatures : []);
  const newlyIntroduced = warnSignatures.filter((sig) => !baselineSet.has(sig));
  const ownerSummary = summarize(signaturesToFiles(newlyIntroduced));

  writeJson(OWNER_REPORT_FILE, {
    generated_at: new Date().toISOString(),
    newly_introduced_warn_count: newlyIntroduced.length,
    owner_summary: ownerSummary,
  });

  if (failCount > 0 || newlyIntroduced.length > 0) {
    console.error('[gls-layout-gate] BUILD BLOCKED — regression detected (new FAIL or new WARN signatures).');
    if (newlyIntroduced.length > 0) {
      console.error(`[gls-layout-gate] New WARN signatures: ${newlyIntroduced.length}`);
      newlyIntroduced.slice(0, 30).forEach((sig) => console.error(` - ${sig}`));
      if (newlyIntroduced.length > 30) {
        console.error(` - ...and ${newlyIntroduced.length - 30} more`);
      }
      printOwnerSummary('gls-layout-gate', ownerSummary);
    }
    process.exit(1);
  }

  console.log('[gls-layout-gate] PASS — no new layout regressions against baseline.');
  process.exit(0);
}

if (STRICT_ZERO_MODE) {
  if (failCount > 0 || warnCount > 0) {
    console.error('[gls-layout-gate] BUILD BLOCKED — strict mode requires zero FAIL and zero WARN findings.');
    process.exit(1);
  }
  console.log('[gls-layout-gate] PASS — no blocking layout violations.');
  process.exit(0);
}
