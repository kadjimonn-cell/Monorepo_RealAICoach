#!/usr/bin/env node
/* eslint-env node */

const fs = require('fs');
const path = require('path');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/pricing-policy-drift-gate.js'));
const FRONTEND_ROOT = path.resolve(scriptDir, '..');
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..');
const REPORT_DIR = path.resolve(FRONTEND_ROOT, '.quality');
const REPORT_FILE = path.resolve(REPORT_DIR, 'pricing_policy_drift_report.json');

const ROOTS = [
  path.resolve(FRONTEND_ROOT, 'app'),
  path.resolve(FRONTEND_ROOT, 'src'),
  path.resolve(REPO_ROOT, 'backend'),
];

const SOURCE_EXT = new Set(['.ts', '.tsx', '.js', '.jsx', '.py']);
const SKIP_MARKERS = ['/node_modules/', '/dist/', '/build/', '/.git/', '/__tests__/', '/tests/', '/src/i18n/locales/'];
const ALLOWLIST = new Set([
  'frontend/src/config/pricingPolicy.ts',
  'frontend/src/i18n/translationLoader.ts',
  'frontend/src/i18n/locales/en.ts',
  'backend/shared/pricing_policy.py',
]);

const PATTERNS = [
  { key: 'basic_monthly_label', regex: /\$5\.99\s*\/\s*mo|\$5\.99\s*\/month|\$5\.99\/mo|\$5\.99\/month|\$5\.99\s*month/i },
  { key: 'premium_monthly_label', regex: /\$15\.99\s*\/\s*mo|\$15\.99\s*\/month|\$15\.99\/mo|\$15\.99\/month|\$15\.99\s*month/i },
  { key: 'basic_yearly_literal', regex: /\$57\.50|57\.50/ },
  { key: 'premium_yearly_literal', regex: /\$153\.50|153\.50/ },
  { key: 'save_20_literal', regex: /SAVE\s*20%|20%\s+savings/i },
  { key: 'save_60_literal', regex: /SAVE\s*60%|60%\s+savings/i },
];

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const abs = path.join(dir, entry.name);
    const norm = abs.replace(/\\/g, '/');
    if (SKIP_MARKERS.some((marker) => norm.includes(marker))) continue;
    if (entry.isDirectory()) walk(abs, out);
    else if (entry.isFile() && SOURCE_EXT.has(path.extname(entry.name))) out.push(abs);
  }
  return out;
}

function rel(abs) {
  return path.relative(REPO_ROOT, abs).replace(/\\/g, '/');
}

function scanFile(absPath) {
  const relative = rel(absPath);
  if (ALLOWLIST.has(relative)) return [];
  const source = fs.readFileSync(absPath, 'utf8');
  const lines = source.split(/\r?\n/);
  const findings = [];
  lines.forEach((line, index) => {
    if (line.includes('@pricing-policy-ok')) return;
    for (const pattern of PATTERNS) {
      if (pattern.regex.test(line)) {
        findings.push({ file: relative, line: index + 1, pattern: pattern.key, code: line.trim().slice(0, 200) });
      }
    }
  });
  return findings;
}

function main() {
  const files = ROOTS.flatMap((root) => walk(root));
  const findings = files.flatMap((file) => scanFile(file));
  const payload = {
    generated_at: new Date().toISOString(),
    scanned_files: files.length,
    violation_count: findings.length,
    violations: findings.slice(0, 200),
  };
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  console.log(`[pricing-policy-drift-gate] scanned=${files.length} violations=${findings.length}`);
  console.log(`[pricing-policy-drift-gate] report=${REPORT_FILE}`);
  if (findings.length > 0) {
    console.error('[pricing-policy-drift-gate] FAIL: hardcoded platform pricing literals detected outside approved policy files.');
    findings.slice(0, 30).forEach((item) => console.error(` - ${item.file}:${item.line} ${item.pattern} => ${item.code}`));
    process.exit(1);
  }
  console.log('[pricing-policy-drift-gate] PASS: no hardcoded platform pricing literals detected outside approved policy files.');
}

main();