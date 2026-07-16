#!/usr/bin/env node
/* eslint-env node */

/**
 * V7 Platform Boundary Gate
 *
 * Prevents V7/template tokens from leaking into platform/public surfaces.
 * Global scope: scans all route files + shared components.
 */

const fs = require('fs');
const path = require('path');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/v7-platform-boundary-gate.js'));
const FRONTEND_ROOT = path.resolve(scriptDir, '..');
const REPORT_DIR = path.resolve(FRONTEND_ROOT, '.quality');
const REPORT_FILE = path.resolve(REPORT_DIR, 'v7_platform_boundary_report.json');

const TARGET_ROOTS = [
  path.resolve(FRONTEND_ROOT, 'app'),
  path.resolve(FRONTEND_ROOT, 'src/components'),
];

const TARGET_EXTENSIONS = new Set(['.ts', '.tsx']);

const BLOCKED_IMPORT_RE = /from\s+['"](?:\.\.\/|\.\/)*(?:src\/)?(?:theme\/v7|v7\/|\.\.\/src\/theme\/v7|\.\.\/src\/v7)[^'"]*['"]/g;
const BLOCKED_IDENT_RE = /\b(?:V7_LIGHT|V7_DARK|V7_SPACING|V7_TYPOGRAPHY|V7_RADII|useV7Theme|V7TemplateProvider|V7BoundaryEnforcer|THEME_V7_VERSION)\b/g;

function findLine(source, index) {
  return source.slice(0, index).split('\n').length;
}

function walkSourceFiles(rootDir) {
  const files = [];
  if (!fs.existsSync(rootDir)) return files;
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue;
      const abs = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === 'build') continue;
        stack.push(abs);
      } else if (TARGET_EXTENSIONS.has(path.extname(entry.name))) {
        files.push(abs);
      }
    }
  }
  return files;
}

function scanFile(absPath) {
  const rel = path.relative(FRONTEND_ROOT, absPath).replace(/\\/g, '/');
  let source = '';
  try {
    source = fs.readFileSync(absPath, 'utf-8');
  } catch {
    return { file: rel, violations: [] };
  }

  const violations = [];

  BLOCKED_IMPORT_RE.lastIndex = 0;
  let m;
  while ((m = BLOCKED_IMPORT_RE.exec(source)) !== null) {
    violations.push({
      file: rel,
      line: findLine(source, m.index),
      type: 'blocked_v7_import',
      code: String(m[0]).slice(0, 200),
    });
  }

  BLOCKED_IDENT_RE.lastIndex = 0;
  while ((m = BLOCKED_IDENT_RE.exec(source)) !== null) {
    violations.push({
      file: rel,
      line: findLine(source, m.index),
      type: 'blocked_v7_identifier',
      code: String(m[0]).slice(0, 200),
    });
  }

  return { file: rel, violations };
}

function run() {
  const targetFiles = TARGET_ROOTS.flatMap((root) => walkSourceFiles(root)).sort();
  const rows = targetFiles.map(scanFile);
  const violations = rows.flatMap((r) => r.violations);
  const payload = {
    generated_at: new Date().toISOString(),
    scanned_files_count: targetFiles.length,
    scanned_files: targetFiles.map((p) => path.relative(FRONTEND_ROOT, p).replace(/\\/g, '/')),
    violation_count: violations.length,
    violations,
  };

  fs.mkdirSync(REPORT_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, `${JSON.stringify(payload, null, 2)}\n`, 'utf-8');

  console.log(`[v7-platform-boundary-gate] violations=${violations.length}`);
  console.log(`[v7-platform-boundary-gate] scanned_files=${targetFiles.length}`);
  console.log(`[v7-platform-boundary-gate] report=${REPORT_FILE}`);

  if (violations.length > 0) {
    console.error('[v7-platform-boundary-gate] FAIL: V7/template references detected in platform route/component files.');
    violations.slice(0, 20).forEach((v) => console.error(` - ${v.file}:${v.line} ${v.type} ${v.code}`));
    process.exit(1);
  }

  console.log('[v7-platform-boundary-gate] PASS: no V7/template leakage found across app + components.');
}

run();
