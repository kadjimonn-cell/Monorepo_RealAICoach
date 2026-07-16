#!/usr/bin/env node
/*
 * Runtime Crash Sentinel
 *
 * Blocks CI on common crash patterns that have caused global white/black screens:
 * - i18n route probe call before useTranslation() binding (TDZ/use-before-init)
 * - function-level `t(...)` usage without local binding
 * - function-level `colors.*` usage without local binding
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const args = process.argv.slice(2);
const scopeArg = args.find((arg) => arg.startsWith('--scope='));
const scope = (scopeArg ? scopeArg.split('=')[1] : 'critical').toLowerCase();

const FRONTEND_ROOT = path.resolve(__dirname, '..');

const CRITICAL_FILE_PATHS = [
  'app/_layout.tsx',
  'app/terms.tsx',
  'app/messages.tsx',
  'app/career.tsx',
  'app/certificate-compare.tsx',
  'app/certificate-gallery.tsx',
  'app/certificate-operations.tsx',
  'app/certificate-verify/[verificationId].tsx',
  'app/careers/offer/confirm.tsx',
  'app/mini-apps/job-platform.tsx',
  'app/(tabs)/profile.tsx',
  'app/admin/gdpr-requests.tsx',
  'app/admin/subscription-dashboard.tsx',
  'app/admin/mobile-money-dashboard.tsx',
  'app/settings/payment-cards.tsx',
  'app/subscription/kyc.tsx',
  'app/subscription/mobile-money.tsx',
  'app/contact.tsx',
  'app/employer-apply.tsx',
  'app/performance-observability.tsx',
  'src/components/SmartCarsView.tsx',
  'src/components/ErrorBoundary.tsx',
  'src/hooks/useGlobalPlatformState.ts',
];

const IGNORE_DIRS = new Set(['node_modules', '.expo', 'dist', 'dist-web', 'web-build']);

function toPosix(p) {
  return p.split(path.sep).join('/');
}

function walkTsFiles(rootDir) {
  const out = [];
  if (!fs.existsSync(rootDir)) return out;

  const walk = (dir) => {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const ent of entries) {
      if (ent.name.startsWith('.')) continue;
      if (ent.isDirectory()) {
        if (IGNORE_DIRS.has(ent.name)) continue;
        walk(path.join(dir, ent.name));
        continue;
      }
      if (!ent.isFile()) continue;
      if (!ent.name.endsWith('.tsx') && !ent.name.endsWith('.ts')) continue;
      out.push(path.join(dir, ent.name));
    }
  };

  walk(rootDir);
  return out;
}

function getLineNumber(source, idx) {
  return source.slice(0, idx).split('\n').length;
}

function isCommentedRouteProbe(source, idx) {
  const lineStart = source.lastIndexOf('\n', idx) + 1;
  const line = source.slice(lineStart, source.indexOf('\n', idx) === -1 ? source.length : source.indexOf('\n', idx));
  return line.trim().startsWith('//') || line.trim().startsWith('/*');
}

function extractFunctionBlocks(source) {
  const blocks = [];
  const fnRegex = /function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*\{/g;
  let match;

  while ((match = fnRegex.exec(source)) !== null) {
    const full = match[0];
    const name = match[1];
    const params = match[2] || '';
    const bodyStart = match.index + full.length - 1; // points at '{'

    let depth = 0;
    let end = -1;
    for (let i = bodyStart; i < source.length; i += 1) {
      const ch = source[i];
      if (ch === '{') depth += 1;
      else if (ch === '}') {
        depth -= 1;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }

    if (end === -1) continue;
    const body = source.slice(bodyStart + 1, end);
    blocks.push({ name, params, body, start: bodyStart + 1 });
  }

  return blocks;
}

function hasLocalTBinding(text, params = '') {
  if (/\bconst\s*\{[^}]*\bt\b[^}]*\}\s*=\s*useTranslation\s*\(/.test(text)) return true;
  if (/\bconst\s*\{[^}]*\bt\b[^}]*\}\s*=\s*useLanguage\s*\(/.test(text)) return true;
  if (/\bconst\s*\{[^}]*\bt\b[^}]*\}\s*=\s*[A-Za-z_$][\w$]*\s*;/.test(text)) return true;
  if (/\bconst\s+t\s*=/.test(text)) return true;
  if (/\b(let|var)\s+t\s*=/.test(text)) return true;
  if (/\bt\s*:\s*/.test(params) || /\{[^}]*\bt\b[^}]*\}/.test(params)) return true;
  if (/\bt\b/.test(params)) return true;
  return false;
}

function hasLocalColorsBinding(text, params = '') {
  if (/\bconst\s*\{[^}]*\bcolors\b[^}]*\}\s*=/.test(text)) return true;
  if (/\bconst\s*\{[^}]*\bcolors\b[^}]*\}\s*=\s*[A-Za-z_$][\w$]*\s*;/.test(text)) return true;
  if (/\bconst\s+colors\s*=/.test(text)) return true;
  if (/\b(let|var)\s+colors\s*=/.test(text)) return true;
  if (/\b(let|var|const)\s+colors\b\s*:\s*/.test(text)) return true;
  if (/\b(let|var|const)\s+colors\b\s*;/.test(text)) return true;
  if (/\bcolors\s*:\s*/.test(params) || /\{[^}]*\bcolors\b[^}]*\}/.test(params)) return true;
  if (/\bcolors\b/.test(params)) return true;
  return false;
}

function getFilesToScan() {
  if (scope === 'full') {
    return [
      ...walkTsFiles(path.join(FRONTEND_ROOT, 'app')),
      ...walkTsFiles(path.join(FRONTEND_ROOT, 'src')),
    ];
  }

  return CRITICAL_FILE_PATHS
    .map((p) => path.join(FRONTEND_ROOT, p))
    .filter((abs) => fs.existsSync(abs));
}

function runFooterRouteContractGate() {
  const gateScript = path.join(FRONTEND_ROOT, 'scripts', 'footer-route-contract-gate.js');
  const res = spawnSync('node', [gateScript], {
    cwd: FRONTEND_ROOT,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((res.stdout || '').trim()) process.stdout.write(res.stdout);
  if ((res.stderr || '').trim()) process.stderr.write(res.stderr);

  if (res.status !== 0 || res.error) {
    const err = (res.stderr || '').trim() || res.error?.message || `exit=${res.status}`;
    console.error('[runtime-crash-sentinel] FAIL: footer route contract gate failed:', err);
    process.exit(1);
  }
}

function run() {
  runFooterRouteContractGate();

  const files = getFilesToScan();
  const violations = [];

  for (const filePath of files) {
    const source = fs.readFileSync(filePath, 'utf8');
    const relPath = toPosix(path.relative(FRONTEND_ROOT, filePath));

    // Rule 1: route probe before translation binding
    const probeRegex = /\bt\(\s*['"]i18n\.route\./g;
    let probeMatch;
    while ((probeMatch = probeRegex.exec(source)) !== null) {
      const idx = probeMatch.index;
      if (isCommentedRouteProbe(source, idx)) continue;
      const before = source.slice(0, idx);
      if (!/const\s*\{[^}]*\bt\b[^}]*\}\s*=\s*useTranslation\s*\(/.test(before)) {
        violations.push({
          file: relPath,
          line: getLineNumber(source, idx),
          rule: 'route-probe-before-useTranslation',
          detail: 'Found route probe call before `const { t } = useTranslation()` binding.',
        });
      }
    }

    // Rule 2/3: function blocks with unbound t/colors
    const blocks = extractFunctionBlocks(source);
    for (const block of blocks) {
      if (/\bt\(\s*['"]/m.test(block.body) && !hasLocalTBinding(block.body, block.params)) {
        const localIdx = block.body.search(/\bt\(\s*['"]/m);
        violations.push({
          file: relPath,
          line: getLineNumber(source, block.start + Math.max(localIdx, 0)),
          rule: 'unbound-t-usage',
          detail: `Function \`${block.name}\` uses t(...) without local translation binding.`,
        });
      }

      if (/(?<![\w$.])colors\./m.test(block.body) && !hasLocalColorsBinding(block.body, block.params)) {
        const localIdx = block.body.search(/(?<![\w$.])colors\./m);
        violations.push({
          file: relPath,
          line: getLineNumber(source, block.start + Math.max(localIdx, 0)),
          rule: 'unbound-colors-usage',
          detail: `Function \`${block.name}\` references colors.* without local binding.`,
        });
      }
    }
  }

  if (violations.length === 0) {
    console.log(`[runtime-crash-sentinel] PASS (${scope}) — scanned ${files.length} files, no crash signatures found.`);
    process.exit(0);
  }

  console.error(`[runtime-crash-sentinel] FAIL (${scope}) — found ${violations.length} potential crash signature(s):`);
  for (const v of violations) {
    console.error(`- ${v.file}:${v.line} [${v.rule}] ${v.detail}`);
  }
  process.exit(1);
}

run();
