#!/usr/bin/env node
/**
 * Theme Compliance Build Gate (STRICT, local, dependency-free)
 *
 * Runs a local static scan against app/ + src/components/ and blocks build
 * if any warn/fail issue exists.
 *
 * This guarantees pre-existing/current/future pages cannot ship with theme
 * drift and always inherit V2 light/dark behavior.
 */

const fs = require('fs');
const path = require('path');

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const EXCEPTION_ALLOWLIST_PATH = path.join(FRONTEND_ROOT, 'scripts', 'theme-exception-allowlist.json');
const QUALITY_DIR = path.join(FRONTEND_ROOT, '.quality');
const REPORT_PATH = path.join(QUALITY_DIR, 'theme_build_gate_report.json');

function loadApprovedExemptions() {
  try {
    const raw = fs.readFileSync(EXCEPTION_ALLOWLIST_PATH, 'utf-8');
    const parsed = JSON.parse(raw);
    const items = Array.isArray(parsed?.files) ? parsed.files : [];
    return new Set(items.map((x) => String(x || '').replace(/\\/g, '/')));
  } catch {
    return new Set();
  }
}

const APPROVED_EXEMPTIONS = loadApprovedExemptions();

const SCAN_ROOTS = [
  path.join(FRONTEND_ROOT, 'app'),
  path.join(FRONTEND_ROOT, 'src'),
];

const SKIP_PATH_MARKERS = [
  'src/components/ui/',
  'app/payment-history-export',
  'app/payment-document',
  'app/certificate',
  'src/components/admin/V7TemplateComplianceWidget.tsx',
  'src/components/admin/ThemeValidationDashboard.tsx',
];

const CRITICAL_ROUTE_FILES = new Set([
  'app/welcome.tsx',
  'app/pricing.tsx',
  'app/system-status.tsx',
  'app/careers.tsx',
  'src/components/welcome/WelcomePricing.tsx',
  'src/components/welcome/WelcomeFAQ.tsx',
  'src/components/welcome/WelcomeSocial.tsx',
  'src/components/PremiumGuard.tsx',
  'src/components/RenewalBanner.tsx',
  'src/components/SmartOnboarding.tsx',
  'src/components/admin/RealityValidationPanel.tsx',
  'app/admin/subscription-dashboard.tsx',
  'app/admin/mobile-money-dashboard.tsx',
]);

const DARK_HEX = '(?:050A18|080E24|0B0F1A|0F172A|0A0A0A|111827|1F2937|0D1B2A|1A2A45|1E293B|152232|0D2137|0D0F1A|0D0F1C|0A0F1E|060D1B)';
const LIGHT_HEX = '(?:F9FAFB|F8FAFC|FFFFFF|FFF|E2E8F0|CBD5E1|F1F5F9|FAFBFC|F5F7FA|FFFAEB|FFFFF0)';

const PATTERNS = [
  {
    key: 'inverted_dark_text',
    severity: 'fail',
    regex: new RegExp(String.raw`(?<![a-z])color:\s*darkMode\s*\?\s*'#${DARK_HEX}'`, 'i'),
    onlyWhenTernary: true,
  },
  {
    key: 'same_dark_both_modes',
    severity: 'fail',
    regex: new RegExp(String.raw`darkMode\s*\?\s*'#${DARK_HEX}'\s*:\s*'#${DARK_HEX}'`, 'i'),
    onlyWhenTernary: true,
  },
  {
    key: 'css_dark_bg_always',
    severity: 'warn',
    regex: new RegExp(String.raw`background(?:Color)?:\s*'#${DARK_HEX}'`, 'i'),
  },
  {
    key: 'hardcoded_dark_text_no_branch',
    severity: 'warn',
    regex: new RegExp(String.raw`(?<![a-z])color:\s*'#${DARK_HEX}'`, 'i'),
    skipIfTernary: true,
  },
  {
    key: 'hardcoded_light_text_no_branch',
    severity: 'warn',
    regex: new RegExp(String.raw`(?<![a-z])color:\s*'#${LIGHT_HEX}'`, 'i'),
    skipIfTernary: true,
  },
  {
    key: 'hardcoded_light_bg_no_branch',
    severity: 'warn',
    regex: new RegExp(String.raw`backgroundColor:\s*'#${LIGHT_HEX}'`, 'i'),
    skipIfTernary: true,
  },
  {
    key: 't_object_hardcoded_dark',
    severity: 'info',
    regex: new RegExp(String.raw`(?:text|bg|bgAlt|bgCard|bgSoft):\s*'#${DARK_HEX}'`, 'i'),
  },
  {
    key: 'hardcoded_bg_any_hex',
    severity: 'warn',
    regex: /backgroundColor:\s*['"]#[0-9A-Fa-f]{3,8}['"]/,
    skipIfColorsToken: true,
  },
  {
    key: 'hardcoded_css_bg_any_hex',
    severity: 'warn',
    regex: /(?<!Image)background:\s*['"][^'"]*#[0-9A-Fa-f]{3,8}/,
    skipIfColorsToken: true,
  },
  {
    key: 'hardcoded_text_color_any_hex',
    severity: 'warn',
    regex: /(?<![a-z])color:\s*['"]#[0-9A-Fa-f]{3,8}['"]/,
    skipIfColorsToken: true,
  },
  {
    key: 'hardcoded_border_any_hex',
    severity: 'warn',
    regex: /borderColor:\s*['"]#[0-9A-Fa-f]{3,8}['"]/,
    skipIfColorsToken: true,
  },
  {
    key: 'css_var_hex_fallback',
    severity: 'warn',
    regex: /var\(\s*--app-[a-z0-9\-]+\s*,\s*#[0-9A-Fa-f]{3,8}\s*\)/i,
  },
  {
    key: 'direct_usecolorscheme',
    severity: 'warn',
    regex: /\buseColorScheme\s*\(/,
  },
];

function walkTsxFiles(rootDir) {
  const out = [];
  if (!fs.existsSync(rootDir)) return out;
  const stack = [rootDir];
  while (stack.length) {
    const curr = stack.pop();
    const entries = fs.readdirSync(curr, { withFileTypes: true });
    for (const ent of entries) {
      const abs = path.join(curr, ent.name);
      if (ent.isDirectory()) {
        stack.push(abs);
      } else if (ent.isFile() && ent.name.endsWith('.tsx')) {
        out.push(abs);
      }
    }
  }
  return out.sort();
}

function scanFile(absPath) {
  const rel = path.relative(FRONTEND_ROOT, absPath).replace(/\\/g, '/');

  let text = '';
  try {
    text = fs.readFileSync(absPath, 'utf-8');
  } catch {
    return { file: rel, skipped: true, failCount: 0, warnCount: 0, infoCount: 0, totalIssues: 0, issues: [] };
  }

  const lines = text.split(/\r?\n/);
  const header = lines.slice(0, 20).join('\n');
  const hasFileExemptMarker = header.includes('@theme-audit-file-ok');
  const approvedFileExemption = hasFileExemptMarker && APPROVED_EXEMPTIONS.has(rel);
  const isCriticalRoute = CRITICAL_ROUTE_FILES.has(rel);

  if (SKIP_PATH_MARKERS.some((marker) => rel.includes(marker)) && !hasFileExemptMarker) {
    return { file: rel, skipped: true, failCount: 0, warnCount: 0, infoCount: 0, totalIssues: 0, issues: [] };
  }

  const rank = { fail: 3, warn: 2, info: 1 };
  const bestByLine = new Map();

  // Runtime-crash guard: usage of `colors.*` without a declaration/import
  // caused a production `/settings` crash (`ReferenceError: colors is not defined`).
  // Block this class of regressions at build-gate time.
  const COLORS_REF_REGEX = /(^|[^\w.])colors\.[A-Za-z_][A-Za-z0-9_]*/;
  const hasColorsRef = COLORS_REF_REGEX.test(text);
  if (hasColorsRef) {
    const hasColorsDeclaration = (
      /\b(?:const|let|var)\s+colors\b/.test(text) ||
      /\bimport\s+\{[^}]*\bcolors\b[^}]*\}\s+from\b/.test(text) ||
      /\bimport\s+colors\b/.test(text) ||
      /\{[^}]*\bcolors\b[^}]*\}\s*=/.test(text) ||
      /\bfunction\s+\w+\s*\([^)]*\bcolors\b[^)]*\)/.test(text) ||
      /\([^)]*\bcolors\b[^)]*\)\s*=>/.test(text)
    );

    if (!hasColorsDeclaration) {
      let lineNo = 1;
      for (let i = 0; i < lines.length; i += 1) {
        const raw = lines[i];
        const stripped = raw.trim();
        if (stripped.startsWith('//') || stripped.startsWith('*') || stripped.startsWith('/*')) continue;
        if (COLORS_REF_REGEX.test(raw)) {
          lineNo = i + 1;
          break;
        }
      }
      bestByLine.set(lineNo, {
        line: lineNo,
        pattern: 'undefined_colors_reference',
        severity: 'fail',
        code: 'Detected `colors.*` usage without a local/imported `colors` declaration.',
      });
    }
  }

  if (hasFileExemptMarker && !approvedFileExemption) {
    bestByLine.set(1, {
      line: 1,
      pattern: 'unapproved_file_exemption',
      severity: 'fail',
      code: '@theme-audit-file-ok present but not in scripts/theme-exception-allowlist.json',
    });
  }

  const normalizeExpr = (value) => String(value || '').replace(/\/\*.*?\*\//g, '').replace(/\s+/g, '').trim();

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i];
    const stripped = raw.trim();
    if (stripped.startsWith('//') || stripped.startsWith('*') || stripped.startsWith('/*')) continue;
    if (raw.includes('@theme-ok') && !isCriticalRoute) continue;

    const hasDarkTernary = /darkMode\s*\?/.test(raw);
    const hasColorsToken = /colors\.\w+/.test(raw);

    for (const p of PATTERNS) {
      if (p.onlyWhenTernary && !hasDarkTernary) continue;
      if (p.skipIfTernary && hasDarkTernary) continue;
      if (p.skipIfColorsToken && hasColorsToken) continue;
      if (!p.regex.test(raw)) continue;

      const issue = {
        line: i + 1,
        pattern: p.key,
        severity: p.severity,
        code: stripped.slice(0, 160),
      };
      const prev = bestByLine.get(issue.line);
      if (!prev || rank[issue.severity] > rank[prev.severity]) {
        bestByLine.set(issue.line, issue);
      }
    }

    const sameLinePair = raw.match(/backgroundColor\s*:\s*([^,}]+),\s*color\s*:\s*([^,}]+)/);
    if (sameLinePair) {
      const bgExpr = normalizeExpr(sameLinePair[1]);
      const fgExpr = normalizeExpr(sameLinePair[2]);
      if (bgExpr && fgExpr && bgExpr === fgExpr) {
        const issue = {
          line: i + 1,
          pattern: 'same_fg_bg_expression',
          severity: 'fail',
          code: `backgroundColor and color share same value (${bgExpr})`,
        };
        const prev = bestByLine.get(issue.line);
        if (!prev || rank[issue.severity] > rank[prev.severity]) {
          bestByLine.set(issue.line, issue);
        }
      }
    }
  }

  const modulePalette = text.match(/(?:^|\n)(?:export\s+)?const\s+[A-Z_][A-Z0-9_]*\s*=\s*\{[\s\S]{0,900}#[0-9A-Fa-f]{3,8}/m);
  if (modulePalette) {
    const line = text.slice(0, modulePalette.index || 0).split('\n').length;
    const issue = {
      line,
      pattern: 'module_scope_palette_with_hex',
      severity: 'info',
      code: String(modulePalette[0]).split('\n')[0].trim().slice(0, 160),
    };
    const prev = bestByLine.get(issue.line);
    if (!prev || rank[issue.severity] > rank[prev.severity]) {
      bestByLine.set(issue.line, issue);
    }
  }

  let issues = Array.from(bestByLine.values()).sort((a, b) => a.line - b.line);

  if (approvedFileExemption && !isCriticalRoute) {
    issues = [
      {
        line: 1,
        pattern: 'approved_file_exemption',
        severity: 'info',
        code: '@theme-audit-file-ok approved via theme-exception-allowlist.json',
      },
      ...issues.map((it) => ({ ...it, severity: 'info' })),
    ];
  }

  if (isCriticalRoute) {
    issues = issues.map((it) => {
      if (it.severity === 'warn') {
        return { ...it, severity: 'fail', pattern: `critical_${it.pattern}` };
      }
      return it;
    });
  }

  const failCount = issues.filter((x) => x.severity === 'fail').length;
  const warnCount = issues.filter((x) => x.severity === 'warn').length;
  const infoCount = issues.filter((x) => x.severity === 'info').length;

  return {
    file: rel,
    issues,
    failCount,
    warnCount,
    infoCount,
    totalIssues: issues.length,
  };
}

function runAudit() {
  const allFiles = SCAN_ROOTS.flatMap((root) => walkTsxFiles(root));
  const results = allFiles.map(scanFile).filter((r) => !r.skipped);

  const totalWarn = results.reduce((acc, r) => acc + (r.warnCount || 0), 0);
  const totalFail = results.reduce((acc, r) => acc + (r.failCount || 0), 0);
  const totalInfo = results.reduce((acc, r) => acc + (r.infoCount || 0), 0);
  const filesWarning = results.filter((r) => r.warnCount > 0).length;
  const filesFailing = results.filter((r) => r.failCount > 0).length;

  const offenders = results
    .filter((r) => r.totalIssues > 0)
    .sort((a, b) => ((b.failCount * 1000 + b.warnCount) - (a.failCount * 1000 + a.warnCount)));

  // Compliance is blocker/fail-driven. Warnings are advisory and surfaced separately.
  const grade = totalFail > 0 ? 'B' : 'A';

  return {
    overallGrade: grade,
    warns: totalWarn,
    fails: totalFail,
    infos: totalInfo,
    filesScanned: results.length,
    filesWarning,
    filesFailing,
    offenders,
  };
}

function run() {
  console.log('\n🔒 Theme Compliance Build Gate (strict)\n');
  console.log('   Running local V2 theme audit scanner...');

  const payload = runAudit();
  try {
    fs.mkdirSync(QUALITY_DIR, { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify({ generatedAt: new Date().toISOString(), ...payload }, null, 2));
  } catch {
    // no-op report write best effort
  }
  const grade = payload.overallGrade || '?';
  const warns = Number(payload.warns || 0);
  const fails = Number(payload.fails || 0);
  const infos = Number(payload.infos || 0);
  const scanned = Number(payload.filesScanned || 0);

  console.log(`   Grade: ${grade} | Warns: ${warns} | Fails: ${fails} | Infos: ${infos} | Files: ${scanned}`);
  console.log(`   Report: ${REPORT_PATH}`);

  if (fails === 0 && warns === 0) {
    console.log('   ✅ GATE PASSED (strict) — zero warn/fail issues\n');
    process.exit(0);
  }

  console.error('   ❌ BUILD BLOCKED — theme audit is not clean (warns/fails > 0).');
  for (const row of payload.offenders.slice(0, 12)) {
    console.error(`      - ${row.file} (fail=${row.failCount}, warn=${row.warnCount})`);
    const sample = row.issues?.[0];
    if (sample) {
      console.error(`        line ${sample.line} ${sample.pattern}: ${sample.code}`);
    }
  }
  console.error('      Fix theme issues first, then re-run export.\n');
  process.exit(1);
}

run();
