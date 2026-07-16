#!/usr/bin/env node
/* eslint-env node */

const fs = require('fs');
const path = require('path');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/i18n-baseline-burndown.js'));
const PROJECT_ROOT = path.resolve(scriptDir, '..');
const REPO_ROOT = path.resolve(PROJECT_ROOT, '..');

const LOCALE_FILE = path.join(PROJECT_ROOT, 'src', 'i18n', 'locales', 'en.ts');
const BASELINE_FILE = path.join(scriptDir, 'i18n-missing-keys-regression-baseline.json');
const REPORT_FILE = path.join(REPO_ROOT, 'test_reports', 'i18n_baseline_burndown_report.json');

const SCAN_ROOTS = [
  path.join(PROJECT_ROOT, 'app'),
  path.join(PROJECT_ROOT, 'src', 'components'),
  path.join(PROJECT_ROOT, 'src', 'hooks'),
];

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx']);

function argValue(flag, fallback) {
  const idx = process.argv.indexOf(flag);
  if (idx === -1 || idx + 1 >= process.argv.length) return fallback;
  return process.argv[idx + 1];
}

function hasFlag(flag) {
  return process.argv.includes(flag);
}

function walkFiles(rootDir) {
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
      } else if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
        out.push(fullPath);
      }
    }
  }
  return out;
}

function scanKeyUsage(files) {
  const usage = new Map();
  const fallbackMap = new Map();

  const txPattern = /\btx\(\s*['"`]([^'"`]+)['"`]\s*,\s*['"`]([^'"`]*)['"`]/g;
  const tPattern = /\bt\(\s*['"`]([^'"`]+)['"`]/g;
  const strictPattern = /\bstrictLabel\(\s*['"`]([^'"`]+)['"`]/g;

  const bump = (key) => usage.set(key, (usage.get(key) || 0) + 1);

  for (const filePath of files) {
    let text = '';
    try {
      text = fs.readFileSync(filePath, 'utf8');
    } catch {
      continue;
    }

    txPattern.lastIndex = 0;
    let match;
    while ((match = txPattern.exec(text)) !== null) {
      const key = (match[1] || '').trim();
      const fallback = (match[2] || '').trim();
      if (!key || key.includes('${')) continue;
      bump(key);
      if (fallback && !fallbackMap.has(key)) fallbackMap.set(key, fallback);
    }

    tPattern.lastIndex = 0;
    while ((match = tPattern.exec(text)) !== null) {
      const key = (match[1] || '').trim();
      if (!key || key.includes('${')) continue;
      bump(key);
    }

    strictPattern.lastIndex = 0;
    while ((match = strictPattern.exec(text)) !== null) {
      const key = (match[1] || '').trim();
      if (!key || key.includes('${')) continue;
      bump(key);
    }
  }

  return { usage, fallbackMap };
}

function parseLocaleKeys(localeText) {
  const keys = new Set();
  const re = /"([^"]+)"\s*:\s*"/g;
  let m;
  while ((m = re.exec(localeText)) !== null) {
    keys.add(m[1]);
  }
  return keys;
}

function humanizeKey(key) {
  const leaf = key.split('.').pop() || key;
  const text = leaf
    .replace(/[_-]+/g, ' ')
    .replace(/\b([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text) return key;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function escapeDoubleQuoted(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function main() {
  const apply = hasFlag('--apply');
  const batchSize = Number.parseInt(argValue('--batch-size', '200'), 10);
  const topN = Number.isFinite(batchSize) && batchSize > 0 ? batchSize : 200;

  if (!fs.existsSync(BASELINE_FILE)) {
    throw new Error(`Baseline missing: ${BASELINE_FILE}`);
  }

  const baseline = JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8'));
  const baselineKeys = Array.isArray(baseline?.missing_keys)
    ? Array.from(new Set(baseline.missing_keys.filter(Boolean)))
    : [];

  const files = SCAN_ROOTS.flatMap((root) => walkFiles(root));
  const { usage, fallbackMap } = scanKeyUsage(files);

  const localeText = fs.readFileSync(LOCALE_FILE, 'utf8');
  const localeKeys = parseLocaleKeys(localeText);

  const eligible = baselineKeys
    .filter((k) => usage.has(k) && !localeKeys.has(k))
    .map((k) => ({
      key: k,
      usage: usage.get(k) || 0,
      value: fallbackMap.get(k) || humanizeKey(k),
    }))
    .sort((a, b) => (b.usage - a.usage) || a.key.localeCompare(b.key));

  const selected = eligible.slice(0, topN);
  const selectedKeys = new Set(selected.map((x) => x.key));
  const remainingAfterSelection = eligible.filter((x) => !selectedKeys.has(x.key));

  let localeUpdated = false;
  let baselineUpdated = false;

  if (apply && selected.length > 0) {
    const insertionLines = selected.map((row) => `  "${escapeDoubleQuoted(row.key)}": "${escapeDoubleQuoted(row.value)}",`);

    const marker = '\n};\nexport default locale;';
    if (!localeText.includes(marker)) {
      throw new Error('Unable to locate locale object terminator in en.ts');
    }

    const nextLocaleText = localeText.replace(marker, `\n${insertionLines.join('\n')}\n};\nexport default locale;`);
    fs.writeFileSync(LOCALE_FILE, nextLocaleText, 'utf8');
    localeUpdated = true;

    const nextBaselineKeys = baselineKeys.filter((k) => !selectedKeys.has(k));
    const nextBaseline = {
      ...baseline,
      generated_at: new Date().toISOString(),
      note: 'Regression baseline for i18n missing-keys check. Gate fails only on newly introduced missing keys.',
      missing_keys: nextBaselineKeys,
    };
    writeJson(BASELINE_FILE, nextBaseline);
    baselineUpdated = true;
  }

  const report = {
    generated_at: new Date().toISOString(),
    mode: apply ? 'apply' : 'dry-run',
    batch_size: topN,
    baseline_before_count: baselineKeys.length,
    eligible_count: eligible.length,
    selected_count: selected.length,
    locale_updated: localeUpdated,
    baseline_updated: baselineUpdated,
    selected_keys: selected,
    unresolved_top_keys: (apply ? remainingAfterSelection : eligible).slice(0, 25),
    next_baseline_count: baselineKeys.length - selected.length,
  };
  writeJson(REPORT_FILE, report);

  console.log(`[i18n-burndown] mode=${report.mode} batch=${topN}`);
  console.log(`[i18n-burndown] baseline before=${report.baseline_before_count} eligible=${report.eligible_count} selected=${report.selected_count}`);
  console.log(`[i18n-burndown] baseline after (expected)=${report.next_baseline_count}`);
  console.log(`[i18n-burndown] report=${REPORT_FILE}`);
}

main();
