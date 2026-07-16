#!/usr/bin/env node
/* eslint-env node */

/**
 * Theme Warning Ratchet Gate
 *
 * Enforces non-regression for theme WARN signatures while theme-build-gate
 * continues to hard-block FAIL severity.
 */

const fs = require('fs');
const path = require('path');
const {
  summarize,
  signaturesToFiles,
  printOwnerSummary,
} = require('./regression-owner-map');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/theme-warning-ratchet-gate.js'));
const FRONTEND_ROOT = path.resolve(scriptDir, '..');
const REPORT_FILE = path.resolve(FRONTEND_ROOT, '.quality', 'theme_build_gate_report.json');
const BASELINE_FILE = path.resolve(scriptDir, 'theme-warning-ratchet-baseline.json');
const OWNER_REPORT_FILE = path.resolve(FRONTEND_ROOT, '.quality', 'theme_regression_ownership_report.json');

const UPDATE_BASELINE = process.argv.includes('--update-baseline');

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function collectWarnSignatures(themeReport) {
  const out = [];
  const offenders = Array.isArray(themeReport?.offenders) ? themeReport.offenders : [];
  for (const row of offenders) {
    const file = String(row?.file || '').trim();
    const issues = Array.isArray(row?.issues) ? row.issues : [];
    for (const issue of issues) {
      if (String(issue?.severity || '') !== 'warn') continue;
      const line = Number(issue?.line || 0);
      const pattern = String(issue?.pattern || '').trim();
      const code = String(issue?.code || '').trim();
      if (!file || !pattern) continue;
      out.push(`${file}::L${line}::${pattern}::${code}`);
    }
  }
  return Array.from(new Set(out)).sort();
}

function main() {
  if (!fs.existsSync(REPORT_FILE)) {
    console.error(`[theme-warning-ratchet] FAIL: missing theme report: ${REPORT_FILE}`);
    process.exit(1);
  }

  const themeReport = readJson(REPORT_FILE);
  const warnSignatures = collectWarnSignatures(themeReport);

  if (UPDATE_BASELINE) {
    writeJson(BASELINE_FILE, {
      generated_at: new Date().toISOString(),
      note: 'Regression baseline for theme WARN signatures. CI fails only on newly introduced WARN signatures.',
      warn_signatures: warnSignatures,
    });
    console.log(`[theme-warning-ratchet] baseline updated: ${BASELINE_FILE} (${warnSignatures.length} signatures)`);
    process.exit(0);
  }

  if (!fs.existsSync(BASELINE_FILE)) {
    console.error(`[theme-warning-ratchet] FAIL: missing baseline file: ${BASELINE_FILE}`);
    console.error('[theme-warning-ratchet] Run with --update-baseline once after approved audit.');
    process.exit(1);
  }

  let baseline = { warn_signatures: [] };
  try {
    baseline = readJson(BASELINE_FILE);
  } catch (e) {
    console.error(`[theme-warning-ratchet] FAIL: unable to parse baseline: ${e?.message || e}`);
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

  console.log(`[theme-warning-ratchet] current_warn_signatures=${warnSignatures.length} baseline=${baselineSet.size} new=${newlyIntroduced.length}`);

  if (newlyIntroduced.length > 0) {
    console.error('[theme-warning-ratchet] FAIL: newly introduced theme WARN signatures detected.');
    newlyIntroduced.slice(0, 30).forEach((sig) => console.error(` - ${sig}`));
    if (newlyIntroduced.length > 30) {
      console.error(` - ...and ${newlyIntroduced.length - 30} more`);
    }
    printOwnerSummary('theme-warning-ratchet', ownerSummary);
    process.exit(1);
  }

  console.log('[theme-warning-ratchet] PASS: no new theme WARN regressions.');
}

main();
