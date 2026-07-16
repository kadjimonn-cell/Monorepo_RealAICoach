#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const MANIFEST_PATH = path.join(__dirname, 'brand-exclusion-manifest.json');
const REPORT_DIR = path.join(ROOT, '.quality');
const REPORT_PATH = path.join(REPORT_DIR, 'brand_exclusion_report.json');
const VIOLATIONS_PATH = path.join(REPORT_DIR, 'brand_exclusion_violations.json');

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function readText(rel) {
  const abs = path.join(ROOT, rel);
  return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
}

function collectSourceFilesFromRoot(relRoot) {
  const absRoot = path.join(ROOT, relRoot);
  if (!fs.existsSync(absRoot)) return [];
  const out = [];
  const stack = [absRoot];
  while (stack.length) {
    const dir = stack.pop();
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const ent of entries) {
      if (ent.name.startsWith('.')) continue;
      const abs = path.join(dir, ent.name);
      if (ent.isDirectory()) {
        stack.push(abs);
      } else if (ent.isFile() && /\.(ts|tsx)$/.test(ent.name)) {
        out.push(path.relative(ROOT, abs).replace(/\\/g, '/'));
      }
    }
  }
  return out;
}

function ensureDir() {
  if (!fs.existsSync(REPORT_DIR)) fs.mkdirSync(REPORT_DIR, { recursive: true });
}

function parseQuotedItems(source) {
  return Array.from(source.matchAll(/'([^']+)'/g)).map((m) => m[1]);
}

function extractListFromLine(text, marker) {
  const line = text.split('\n').find((l) => l.includes(marker));
  if (!line) return [];
  return parseQuotedItems(line);
}

function extractHtmlExactBrands(htmlText) {
  const match = htmlText.match(/var\s+EXACT_BRANDS\s*=\s*\{([^}]+)\};/);
  if (!match) return [];
  return parseQuotedItems(match[1]);
}

function extractHtmlParentPatterns(htmlText) {
  const match = htmlText.match(/var\s+PARENT_BRAND_PATTERNS\s*=\s*\[([^\]]+)\];/);
  if (!match) return [];
  return parseQuotedItems(match[1]);
}

function run() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    console.error('[brand-exclusion-gate] Missing manifest:', MANIFEST_PATH);
    process.exit(1);
  }

  const manifest = readJson(MANIFEST_PATH);
  const withNegativeFixture = process.argv.includes('--with-negative-fixture');
  const violations = [];

  const brandProtectionRel = 'src/utils/brandProtection.ts';
  const welcomeRel = 'app/welcome.tsx';
  const htmlRel = 'app/+html.tsx';

  const bp = readText(brandProtectionRel);
  const welcome = readText(welcomeRel);
  const html = readText(htmlRel);

  if (!bp) violations.push(`${brandProtectionRel} missing`);
  if (!welcome) violations.push(`${welcomeRel} missing`);
  if (!html) violations.push(`${htmlRel} missing`);

  const platformBrand = String(manifest.platform_brand || '').trim();

  if (bp && !bp.includes(`export const PLATFORM_BRAND = '${platformBrand}'`)) {
    violations.push(`PLATFORM_BRAND constant mismatch in ${brandProtectionRel}`);
  }

  const brandSurfaceFiles = Array.isArray(manifest.brand_surface_files) && manifest.brand_surface_files.length
    ? manifest.brand_surface_files
    : [welcomeRel];
  const rootFiles = (manifest.brand_surface_roots || []).flatMap((root) => collectSourceFilesFromRoot(root));
  const scanFiles = Array.from(new Set([...brandSurfaceFiles, ...rootFiles]));

  if (withNegativeFixture && manifest.negative_fixture_file) {
    scanFiles.push(String(manifest.negative_fixture_file));
  }

  if (welcome) {
    for (const selector of manifest.required_selectors || []) {
      let found = false;
      for (const file of scanFiles) {
        const content = readText(file);
        if (content && content.includes(selector)) {
          found = true;
          break;
        }
      }
      if (!found) {
        violations.push(`Missing required selector '${selector}' across configured brand surfaces`);
      }
    }
    if (!welcome.includes('PLATFORM_BRAND')) {
      violations.push(`${welcomeRel} does not use PLATFORM_BRAND`);
    }

    for (const file of scanFiles) {
      const content = readText(file);
      if (!content) {
        violations.push(`Brand surface file missing: ${file}`);
        continue;
      }
      for (const key of manifest.forbidden_i18n_keys_on_brand_surfaces || []) {
        const rx = new RegExp(`t\\(\\s*['\"]${key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}['\"]\\s*\\)`);
        if (rx.test(content)) {
          violations.push(`Forbidden brand-surface i18n key usage detected in ${file}: ${key}`);
        }
      }
      for (const rawPattern of manifest.forbidden_source_patterns || []) {
        const re = new RegExp(rawPattern, 'm');
        if (re.test(content)) {
          violations.push(`Forbidden brand composition pattern matched in ${file}: ${rawPattern}`);
        }
      }
    }
  }

  const htmlExact = html ? extractHtmlExactBrands(html) : [];
  const htmlParents = html ? extractHtmlParentPatterns(html) : [];

  if (html) {
    for (const term of manifest.required_html_guards?.exact_brands || []) {
      if (!htmlExact.includes(term)) {
        violations.push(`EXACT_BRANDS missing '${term}' in ${htmlRel}`);
      }
    }
    for (const term of manifest.required_html_guards?.parent_patterns || []) {
      if (!htmlParents.includes(term)) {
        violations.push(`PARENT_BRAND_PATTERNS missing '${term}' in ${htmlRel}`);
      }
    }
    for (const fragment of manifest.required_html_guards?.regex_fragments || []) {
      if (!html.includes(fragment)) {
        violations.push(`BRAND_RE missing fragment '${fragment}' in ${htmlRel}`);
      }
    }
  }

  const bpMulti = bp ? extractListFromLine(bp, 'PROTECTED_BRANDS_MULTI') : [];
  const bpSingle = bp ? extractListFromLine(bp, 'PROTECTED_BRANDS_SINGLE') : [];
  const exclusionUnion = Array.from(new Set([...bpMulti, ...bpSingle, ...htmlExact, ...htmlParents])).sort((a, b) => a.localeCompare(b));

  for (const required of manifest.required_terms || []) {
    if (!exclusionUnion.includes(required)) {
      violations.push(`Required brand term '${required}' missing from effective exclusion union`);
    }
  }

  ensureDir();
  const report = {
    generated_at: new Date().toISOString(),
    platform_brand: platformBrand,
    mode: withNegativeFixture ? 'negative-fixture' : 'standard',
    scanned_file_count: scanFiles.length,
    scanned_files: scanFiles,
    exclusion_union_count: exclusionUnion.length,
    exclusion_union: exclusionUnion,
    checks: {
      manifest_loaded: true,
      platform_brand_constant_ok: bp ? bp.includes(`export const PLATFORM_BRAND = '${platformBrand}'`) : false,
      welcome_uses_platform_brand: welcome ? welcome.includes('PLATFORM_BRAND') : false,
      html_exact_brands_count: htmlExact.length,
      html_parent_patterns_count: htmlParents.length,
      violations_count: violations.length,
    },
  };

  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  fs.writeFileSync(VIOLATIONS_PATH, JSON.stringify({ generated_at: report.generated_at, violations }, null, 2));

  if (violations.length) {
    console.error('\n[brand-exclusion-gate] FAILED');
    violations.forEach((v) => console.error(' -', v));
    console.error(`\nReport: ${REPORT_PATH}`);
    console.error(`Violations: ${VIOLATIONS_PATH}`);
    process.exit(1);
  }

  console.log('[brand-exclusion-gate] PASS');
  console.log(` - Platform brand: ${platformBrand}`);
  console.log(` - Exclusion terms: ${exclusionUnion.length}`);
  console.log(` - Report: ${REPORT_PATH}`);
}

run();
