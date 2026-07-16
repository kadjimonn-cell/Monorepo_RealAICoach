#!/usr/bin/env node
/* eslint-env node */

const fs = require('fs');
const path = require('path');
const {
  summarize,
  ownerFromI18nKey,
  printOwnerSummary,
} = require('./regression-owner-map');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/i18n-new-missing-keys-check.js'));
const PROJECT_ROOT = path.resolve(scriptDir, '..');
const REPO_ROOT = path.resolve(PROJECT_ROOT, '..');
const LOCALE_FILE = path.join(PROJECT_ROOT, 'src', 'i18n', 'locales', 'en.ts');
const BASELINE_FILE = path.join(scriptDir, 'i18n-missing-keys-regression-baseline.json');
const REPORT_FILE = path.join(REPO_ROOT, 'test_reports', 'i18n_new_missing_keys_report.json');
const OWNER_REPORT_FILE = path.join(PROJECT_ROOT, '.quality', 'i18n_regression_ownership_report.json');

const SCAN_ROOTS = [
  path.join(PROJECT_ROOT, 'app'),
  path.join(PROJECT_ROOT, 'src', 'components'),
  path.join(PROJECT_ROOT, 'src', 'hooks'),
];

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx']);
const KEY_PATTERNS = [
  /\btx\(\s*['"`]([^'"`]+)['"`]/g,
  /\bt\(\s*['"`]([^'"`]+)['"`]/g,
  /\bstrictLabel\(\s*['"`]([^'"`]+)['"`]/g,
];

function listSourceFiles(rootDir) {
  const out = [];
  if (!fs.existsSync(rootDir)) return out;
  const stack = [rootDir];
  while (stack.length) {
    const dir = stack.pop();
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue;
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === 'build') continue;
        stack.push(fullPath);
        continue;
      }
      if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
        out.push(fullPath);
      }
    }
  }
  return out;
}

function extractUsedKeys(files) {
  const keys = new Set();
  for (const filePath of files) {
    let text = '';
    try {
      text = fs.readFileSync(filePath, 'utf8');
    } catch {
      continue;
    }
    for (const pattern of KEY_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) {
        const key = (match[1] || '').trim();
        if (!key || key.includes('${')) continue;
        keys.add(key);
      }
    }
  }
  return keys;
}

function extractLocaleKeys(localeText) {
  const keys = new Set();
  const re = /"([^"]+)"\s*:\s*"/g;
  let match;
  while ((match = re.exec(localeText)) !== null) {
    keys.add((match[1] || '').trim());
  }
  return keys;
}

function readBaseline() {
  if (!fs.existsSync(BASELINE_FILE)) {
    return { missing_keys: [] };
  }
  try {
    const parsed = JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8'));
    const keys = Array.isArray(parsed?.missing_keys) ? parsed.missing_keys.filter(Boolean) : [];
    return { missing_keys: Array.from(new Set(keys)).sort() };
  } catch {
    return { missing_keys: [] };
  }
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function main() {
  const updateBaseline = process.argv.includes('--update-baseline');

  const allFiles = SCAN_ROOTS.flatMap((root) => listSourceFiles(root));
  const usedKeys = extractUsedKeys(allFiles);
  const localeText = fs.readFileSync(LOCALE_FILE, 'utf8');
  const localeKeys = extractLocaleKeys(localeText);

  const missingNow = Array.from(usedKeys).filter((k) => !localeKeys.has(k)).sort();
  const missingNowSet = new Set(missingNow);

  if (updateBaseline) {
    writeJson(BASELINE_FILE, {
      generated_at: new Date().toISOString(),
      note: 'Regression baseline for i18n missing-keys check. Gate fails only on newly introduced missing keys.',
      missing_keys: missingNow,
    });
    console.log(`[i18n-nightly] Baseline updated: ${BASELINE_FILE} (${missingNow.length} keys)`);
    process.exit(0);
  }

  const baseline = readBaseline();
  const baselineSet = new Set(baseline.missing_keys);

  const newlyMissing = missingNow.filter((k) => !baselineSet.has(k));
  const resolvedFromBaseline = baseline.missing_keys.filter((k) => !missingNowSet.has(k));

  const report = {
    generated_at: new Date().toISOString(),
    scanned_files: allFiles.length,
    used_key_count: usedKeys.size,
    locale_key_count: localeKeys.size,
    missing_now_count: missingNow.length,
    baseline_missing_count: baseline.missing_keys.length,
    newly_missing_count: newlyMissing.length,
    resolved_from_baseline_count: resolvedFromBaseline.length,
    newly_missing_keys: newlyMissing,
    resolved_from_baseline_keys: resolvedFromBaseline,
  };

  const ownerSummary = summarize(newlyMissing, ownerFromI18nKey);
  const ownerReport = {
    generated_at: new Date().toISOString(),
    newly_missing_count: newlyMissing.length,
    owner_summary: ownerSummary,
  };

  writeJson(REPORT_FILE, report);
  writeJson(OWNER_REPORT_FILE, ownerReport);

  console.log(`[i18n-nightly] scanned files: ${allFiles.length}`);
  console.log(`[i18n-nightly] used keys: ${usedKeys.size}, locale keys: ${localeKeys.size}`);
  console.log(`[i18n-nightly] missing now: ${missingNow.length}, baseline: ${baseline.missing_keys.length}`);

  if (newlyMissing.length > 0) {
    console.error(`[i18n-nightly] FAIL: ${newlyMissing.length} newly introduced missing i18n keys detected.`);
    for (const key of newlyMissing.slice(0, 50)) {
      console.error(` - ${key}`);
    }
    if (newlyMissing.length > 50) {
      console.error(` - ...and ${newlyMissing.length - 50} more`);
    }
    printOwnerSummary('i18n-nightly', ownerSummary);
    process.exit(1);
  }

  console.log('[i18n-nightly] PASS: No newly introduced missing i18n keys.');
}

main();
