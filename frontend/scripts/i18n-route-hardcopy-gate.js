#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(PROJECT_ROOT, '..');
const APP_ROOT = path.join(PROJECT_ROOT, 'app');
const BASELINE_FILE = path.join(__dirname, 'i18n-route-hardcopy-baseline.json');
const REPORT_FILE = path.join(REPO_ROOT, 'test_reports', 'i18n_route_hardcopy_report.json');

const SOURCE_EXT = new Set(['.ts', '.tsx', '.js', '.jsx']);
const MIN_LITERAL_COUNT = 3;

function hasFlag(flag) {
  return process.argv.includes(flag);
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
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

function isHumanLiteral(text) {
  const s = String(text || '').trim();
  if (!s || s.length < 3) return false;
  if (s.includes('${')) return false;
  if (/^[0-9\s.,:%+-]+$/.test(s)) return false;
  if (/^[A-Za-z0-9_.-]+$/.test(s) && s.includes('.')) return false; // likely key-ish token
  return /[A-Za-z]{2,}/.test(s);
}

function extractRouteLiteralCandidates(source) {
  const found = [];

  const jsxTextRe = />\s*([^<>{\n][^<>{\n]{2,})\s*</g;
  const propLiteralRe = /\b(?:title|subtitle|placeholder|label|accessibilityLabel)\s*=\s*["'`]([^"'`]{3,})["'`]/g;

  let match;
  while ((match = jsxTextRe.exec(source)) !== null) {
    const text = (match[1] || '').trim();
    if (isHumanLiteral(text)) found.push(text);
  }

  while ((match = propLiteralRe.exec(source)) !== null) {
    const text = (match[1] || '').trim();
    if (isHumanLiteral(text)) found.push(text);
  }

  return Array.from(new Set(found));
}

function hasI18nUsage(source) {
  const i18nRe = /\b(useLanguage|useTranslation|useAutoTranslate)\b|\btx\(\s*['"`]|\bt\(\s*['"`]|\btt\(\s*['"`]/;
  return i18nRe.test(source);
}

function analyzeRoutes(files) {
  const violations = [];

  for (const filePath of files) {
    const relative = rel(filePath);
    if (!relative.startsWith('app/')) continue;
    if (!relative.endsWith('.tsx') && !relative.endsWith('.jsx')) continue;
    if (relative === 'app/+html.tsx') continue;
    if (relative.includes('/_layout.') || relative.includes('/+not-found.')) continue;

    let source = '';
    try {
      source = fs.readFileSync(filePath, 'utf8');
    } catch {
      continue;
    }

    if (source.includes('@i18n-route-hardcopy-ignore')) continue;

    const literals = extractRouteLiteralCandidates(source);
    const i18nUsed = hasI18nUsage(source);

    if (!i18nUsed && literals.length >= MIN_LITERAL_COUNT) {
      violations.push({
        file: relative,
        literal_count: literals.length,
        sample_literals: literals.slice(0, 8),
      });
    }
  }

  violations.sort((a, b) => (b.literal_count - a.literal_count) || a.file.localeCompare(b.file));
  return violations;
}

function readBaseline() {
  if (!fs.existsSync(BASELINE_FILE)) return { violations: [] };
  try {
    const parsed = JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8'));
    const rows = Array.isArray(parsed?.violations) ? parsed.violations : [];
    return {
      violations: rows
        .map((x) => ({ file: String(x.file || ''), literal_count: Number(x.literal_count || 0) }))
        .filter((x) => x.file),
    };
  } catch {
    return { violations: [] };
  }
}

function main() {
  const updateBaseline = hasFlag('--update-baseline');

  const files = walkFiles(APP_ROOT);
  const current = analyzeRoutes(files);

  if (updateBaseline) {
    writeJson(BASELINE_FILE, {
      generated_at: new Date().toISOString(),
      note: 'Baseline for route-level hardcoded-copy gate. CI fails only on newly introduced route violations.',
      violations: current.map((x) => ({ file: x.file, literal_count: x.literal_count })),
    });
    console.log(`[i18n-route-gate] Baseline updated: ${BASELINE_FILE} (${current.length} violations)`);
    process.exit(0);
  }

  const baseline = readBaseline();
  const baselineFiles = new Set(baseline.violations.map((x) => x.file));
  const zeroBaselineMode = baseline.violations.length === 0;
  const newlyIntroduced = current.filter((x) => !baselineFiles.has(x.file));
  const resolvedFromBaseline = baseline.violations.filter((x) => !current.some((v) => v.file === x.file));

  const report = {
    generated_at: new Date().toISOString(),
    scanned_files: files.length,
    baseline_violation_count: baseline.violations.length,
    current_violation_count: current.length,
    zero_baseline_mode: zeroBaselineMode,
    newly_introduced_count: newlyIntroduced.length,
    resolved_from_baseline_count: resolvedFromBaseline.length,
    newly_introduced: newlyIntroduced,
    resolved_from_baseline: resolvedFromBaseline,
  };
  writeJson(REPORT_FILE, report);

  console.log(`[i18n-route-gate] scanned route files: ${files.length}`);
  console.log(`[i18n-route-gate] baseline=${baseline.violations.length} current=${current.length} newly_introduced=${newlyIntroduced.length}`);

  if (zeroBaselineMode && current.length > 0) {
    console.error('[i18n-route-gate] FAIL: zero-baseline mode active, but route violations were found:');
    current.slice(0, 40).forEach((row) => console.error(` - ${row.file} (${row.literal_count})`));
    if (current.length > 40) {
      console.error(` - ...and ${current.length - 40} more`);
    }
    process.exit(1);
  }

  if (!zeroBaselineMode && newlyIntroduced.length > 0) {
    console.error('[i18n-route-gate] FAIL: newly introduced route hardcoded-copy violations detected:');
    newlyIntroduced.slice(0, 40).forEach((row) => console.error(` - ${row.file} (${row.literal_count})`));
    if (newlyIntroduced.length > 40) {
      console.error(` - ...and ${newlyIntroduced.length - 40} more`);
    }
    process.exit(1);
  }

  console.log('[i18n-route-gate] PASS: no newly introduced route hardcoded-copy violations.');
}

main();
