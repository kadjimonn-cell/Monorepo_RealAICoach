#!/usr/bin/env node
/* eslint-env node */

/**
 * Critical Surface i18n Gate (strict)
 *
 * Scans only the high-risk public UX surfaces where copy drift is most visible:
 * - app/welcome.tsx
 * - src/components/Footer.tsx
 *
 * Build policy:
 * - FAIL on any newly discovered hardcoded user-facing string not present in
 *   the approved exemption baseline.
 */

const fs = require('fs');
const path = require('path');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/critical-surface-i18n-gate.js'));
const FRONTEND_ROOT = path.resolve(scriptDir, '..');
const REPORT_DIR = path.resolve(FRONTEND_ROOT, '.quality');
const REPORT_FILE = path.resolve(REPORT_DIR, 'critical_surface_i18n_report.json');
const EXEMPTIONS_FILE = path.resolve(scriptDir, 'critical-surface-i18n-exemptions.json');

const TARGET_FILES = [
  'app/welcome.tsx',
  'src/components/Footer.tsx',
].map((p) => path.resolve(FRONTEND_ROOT, p));

const PROP_KEY_RE = /\b(?:accessibilityLabel|placeholder|title|subtitle|label)\s*=\s*(["'`])([^"'`]{2,})\1/g;
const JSX_TEXT_RE = />\s*([^<{\n][^<{\n]{2,})\s*</g;
const ARRAY_TEXT_RE = /\btext\s*:\s*(["'`])([^"'`]{2,})\1/g;
const RETURN_TEXT_RE = /\breturn\s+(["'`])([^"'`]{2,})\1/g;

function loadExemptions() {
  try {
    const raw = fs.readFileSync(EXEMPTIONS_FILE, 'utf-8');
    const parsed = JSON.parse(raw);
    const rows = Array.isArray(parsed?.exemptions) ? parsed.exemptions : [];
    return new Set(rows.map((x) => String(x || '').trim()).filter(Boolean));
  } catch {
    return new Set();
  }
}

function isLikelyUserFacing(str) {
  const s = String(str || '').trim();
  if (!s) return false;
  if (s.length < 3) return false;
  if (s.includes('${')) return false;
  if (/^[0-9\s.,:+\-/%]+$/.test(s)) return false;
  if (/^(https?:\/\/|\/?[\w-]+(?:\/[\w-]*)*)$/i.test(s)) return false;
  if (/^[A-Za-z0-9_.-]+$/.test(s) && s.includes('.')) return false;
  return /[A-Za-z]{2,}|[\u00C0-\uFFFF]{2,}/.test(s);
}

function buildKey(fileRel, _line, text) {
  return `${fileRel}::${String(text).trim()}`;
}

function findLine(content, index) {
  return content.slice(0, index).split('\n').length;
}

function scanFile(absPath) {
  const rel = path.relative(FRONTEND_ROOT, absPath).replace(/\\/g, '/');
  let source = '';
  try {
    source = fs.readFileSync(absPath, 'utf-8');
  } catch {
    return { file: rel, findings: [] };
  }

  const findings = [];
  const scanners = [
    { re: PROP_KEY_RE, kind: 'prop_literal' },
    { re: JSX_TEXT_RE, kind: 'jsx_text' },
    { re: ARRAY_TEXT_RE, kind: 'object_text' },
    { re: RETURN_TEXT_RE, kind: 'return_text' },
  ];

  for (const scanner of scanners) {
    scanner.re.lastIndex = 0;
    let m;
    while ((m = scanner.re.exec(source)) !== null) {
      const text = String(m[2] || '').trim();
      if (!isLikelyUserFacing(text)) continue;
      const line = findLine(source, m.index);
      findings.push({
        file: rel,
        line,
        kind: scanner.kind,
        text,
        key: buildKey(rel, line, text),
      });
    }
  }

  const dedup = new Map();
  for (const row of findings) {
    if (!dedup.has(row.key)) dedup.set(row.key, row);
  }
  return { file: rel, findings: Array.from(dedup.values()).sort((a, b) => a.line - b.line) };
}

function run() {
  const exemptions = loadExemptions();
  const results = TARGET_FILES.map(scanFile);
  const all = results.flatMap((r) => r.findings);
  const violations = all.filter((f) => !exemptions.has(f.key));

  const payload = {
    generated_at: new Date().toISOString(),
    target_files: TARGET_FILES.map((p) => path.relative(FRONTEND_ROOT, p).replace(/\\/g, '/')),
    scanned_literals: all.length,
    exemption_count: exemptions.size,
    violation_count: violations.length,
    violations: violations.slice(0, 200),
  };

  fs.mkdirSync(REPORT_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, `${JSON.stringify(payload, null, 2)}\n`, 'utf-8');

  console.log(`[critical-surface-i18n-gate] scanned=${all.length} exemptions=${exemptions.size} violations=${violations.length}`);
  console.log(`[critical-surface-i18n-gate] report=${REPORT_FILE}`);

  if (violations.length > 0) {
    console.error('[critical-surface-i18n-gate] FAIL: non-exempt hardcoded literals found on critical surfaces.');
    violations.slice(0, 25).forEach((v) => {
      console.error(` - ${v.file}:${v.line} ${v.kind} => "${String(v.text).slice(0, 120)}"`);
    });
    process.exit(1);
  }

  console.log('[critical-surface-i18n-gate] PASS: no non-exempt literals found.');
}

run();
