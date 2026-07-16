#!/usr/bin/env node
/**
 * Theme Palette Prop Gate (cross-file)
 * Catches the blind spot of theme-token-validity-gate: components that
 * receive a palette via a `colors` prop and consume tokens the call-site
 * palette never defines (renders as undefined -> black-on-dark text).
 */
const fs = require('fs');
const path = require('path');

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const ROOTS = [path.join(FRONTEND_ROOT, 'src'), path.join(FRONTEND_ROOT, 'app')];
const ALLOWLIST_PATH = path.join(__dirname, 'theme-palette-prop-allowlist.json');

const files = [];
const walk = (d) => {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f);
    const s = fs.statSync(p);
    if (s.isDirectory()) walk(p);
    else if (/\.tsx?$/.test(f) && !f.endsWith('.bak')) files.push(p);
  }
};
ROOTS.forEach(walk);

const rel = (f) => path.relative(FRONTEND_ROOT, f).replace(/\\/g, '/');

let allowlist = new Set();
try {
  allowlist = new Set(JSON.parse(fs.readFileSync(ALLOWLIST_PATH, 'utf8')).pairs || []);
} catch {}

// v2 token keys
const v2Text = fs.readFileSync(path.join(FRONTEND_ROOT, 'src', 'theme', 'v2.ts'), 'utf8');
const v2Keys = new Set();
for (const m of v2Text.matchAll(/^\s{2}(\w+):/gm)) v2Keys.add(m[1]);

const contents = new Map();
const read = (f) => {
  if (!contents.has(f)) contents.set(f, fs.readFileSync(f, 'utf8'));
  return contents.get(f);
};

/* 1) Consumers: files declaring a `colors` prop, tokens used WITHOUT fallback */
const consumers = new Map(); // exported component name -> { file, tokens:Set }
for (const f of files) {
  const t = read(f);
  if (!/colors\s*:\s*(any|Record|\{)/.test(t)) continue;
  if (/useTheme\s*\(/.test(t)) continue; // colors may be shadowed; local gate covers
  const strict = new Set();
  const withFallback = new Set();
  for (const m of t.matchAll(/colors\.(\w+)\b\s*(\|\||\?\?)/g)) withFallback.add(m[1]);
  for (const m of t.matchAll(/(\|\||\?\?)\s*colors\.(\w+)\b/g)) withFallback.add(m[2]);
  for (const m of t.matchAll(/\bcolors\.(\w+)\b/g)) {
    if (!withFallback.has(m[1])) strict.add(m[1]);
  }
  if (!strict.size && !/colors=\{colors\}/.test(t)) continue;
  for (const m of t.matchAll(/export\s+(?:const|function)\s+(\w+)/g)) {
    consumers.set(m[1], { file: f, tokens: strict });
  }
}

/* 1b) Transitive propagation: a consumer forwarding its `colors` prop to a
   child consumer inherits the child's token requirements. */
const consumerFiles = new Map(); // file -> Set of consumer names in that file
for (const [name, info] of consumers) {
  if (!consumerFiles.has(info.file)) consumerFiles.set(info.file, new Set());
  consumerFiles.get(info.file).add(name);
}
let changed = true;
while (changed) {
  changed = false;
  for (const [file] of consumerFiles) {
    const t = read(file);
    for (const m of t.matchAll(/<(\w+)\b/g)) {
      const child = consumers.get(m[1]);
      if (!child || child.file === file) continue;
      const tagEnd = t.indexOf('>', m.index);
      if (tagEnd === -1) continue;
      if (!/colors=\{colors\}/.test(t.slice(m.index, tagEnd + 1))) continue;
      for (const name of consumerFiles.get(file)) {
        const parent = consumers.get(name);
        for (const tok of child.tokens) {
          if (!parent.tokens.has(tok)) { parent.tokens.add(tok); changed = true; }
        }
      }
    }
  }
}

/* 2) Resolve a palette variable's keys within a producer file */
const resolvePalette = (t, varName, fileUsesTheme) => {
  if (varName === 'colors' && fileUsesTheme) return { keys: new Set(v2Keys), resolved: true };
  if (fileUsesTheme && new RegExp(`\\{[^}]*colors\\s*:\\s*${varName}\\b[^}]*\\}\\s*=\\s*useTheme\\(`).test(t)) {
    return { keys: new Set(v2Keys), resolved: true };
  }
  const defMatch = t.match(new RegExp(`const\\s+${varName}\\s*(?::[^=]+)?=\\s*(useMemo\\s*\\(\\s*\\(\\)\\s*=>\\s*\\()?\\(?\\{`));
  if (!defMatch) return { keys: null, resolved: false };
  // walk braces from the opening `{`
  const start = t.indexOf('{', defMatch.index + defMatch[0].length - 1);
  let depth = 0;
  let end = -1;
  for (let i = start; i < t.length; i++) {
    if (t[i] === '{') depth++;
    else if (t[i] === '}') { depth--; if (depth === 0) { end = i; break; } }
  }
  if (end === -1) return { keys: null, resolved: false };
  const body = t.slice(start + 1, end);
  const keys = new Set();
  let full = false;
  if (/\.\.\.\s*colors\b/.test(body) && fileUsesTheme) full = true;
  // unresolved foreign spreads make us permissive only for unknown keys
  const foreignSpreads = [...body.matchAll(/\.\.\.\s*(\w+)/g)].map((m) => m[1]).filter((n) => n !== 'colors');
  for (const sp of foreignSpreads) {
    const spDef = t.match(new RegExp(`const\\s+${sp}\\s*(?::[^=]+)?=\\s*\\{([\\s\\S]{0,4000}?)\\n\\};?`));
    if (spDef) for (const km of spDef[1].matchAll(/^\s*(\w+):/gm)) keys.add(km[1]);
    else return { keys: null, resolved: false }; // can't prove -> skip (avoid FPs)
  }
  for (const km of body.matchAll(/(?:^|[,{\n])\s*(\w+)\s*:/g)) keys.add(km[1]);
  if (full) for (const k of v2Keys) keys.add(k);
  return { keys, resolved: true };
};

/* 3) Producers: scan JSX call sites passing colors={VAR} */
const failures = [];
for (const f of files) {
  const t = read(f);
  const fileUsesTheme = /useTheme\s*\(/.test(t);
  for (const m of t.matchAll(/<(\w+)\b/g)) {
    const name = m[1];
    const consumer = consumers.get(name);
    if (!consumer || consumer.file === f) continue;
    const tagEnd = t.indexOf('>', m.index);
    if (tagEnd === -1) continue;
    const tag = t.slice(m.index, tagEnd + 1);
    const cv = tag.match(/colors=\{(\w+)\}/);
    if (!cv) continue;
    const { keys, resolved } = resolvePalette(t, cv[1], fileUsesTheme);
    if (!resolved || !keys) {
      if (process.env.PALETTE_GATE_DEBUG) console.log(`  ⚠ unresolved: ${rel(f)} -> <${name} colors={${cv[1]}}>`);
      continue;
    }
    const missing = [...consumer.tokens].filter((k) => !keys.has(k));
    if (missing.length) {
      const pairId = `${rel(f)}::${name}`;
      if (allowlist.has(pairId)) continue;
      failures.push({ producer: rel(f), consumer: name, consumerFile: rel(consumer.file), missing });
    }
  }
}

const unique = new Map();
for (const fl of failures) unique.set(`${fl.producer}::${fl.consumer}`, fl);

/* 4) Named theme objects: THEME = useExecTheme() usages must exist in getExecTheme */
const execSrc = read(path.join(FRONTEND_ROOT, 'src', 'components', 'admin', 'ExecDashboardPanels.tsx'));
const execBlock = execSrc.match(/export function getExecTheme[\s\S]*?\n\}/);
const execKeys = new Set();
if (execBlock) for (const m of execBlock[0].matchAll(/(\w+)\s*:/g)) execKeys.add(m[1]);
const namedThemeFailures = [];
for (const f of files) {
  const t = read(f);
  const decl = t.match(/const\s+(\w+)\s*=\s*useExecTheme\(\)/);
  if (!decl) continue;
  const varName = decl[1];
  const missing = new Set();
  for (const m of t.matchAll(new RegExp(`\\b${varName}\\.(\\w+)\\b(?!\\s*(\\|\\||\\?\\?))`, 'g'))) {
    if (!execKeys.has(m[1])) missing.add(m[1]);
  }
  if (missing.size) namedThemeFailures.push({ file: rel(f), missing: [...missing] });
}

/* 5) Canonical CSS-var mapping: surface/text keys must not point at mismatched vars */
const CANON = {
  bg: '--app-bg', bgAlt: '--app-bg', bgSoft: '--app-card-muted',
  card: '--app-card-bg', cardAlt: '--app-card-bg', cardBg: '--app-card-bg', surface: '--app-card-bg', surfaceAlt: '--app-card-bg',
  cardHover: '--app-surface-hover', surfaceHover: '--app-surface-hover',
  border: '--app-border', borderMd: '--app-border', divider: '--app-border', track: '--app-border',
  borderStrong: '--app-border-strong',
  text: '--app-text', textSec: '--app-text-sec', textSecondary: '--app-text-sec', textMuted: '--app-text-muted', muted: '--app-text-muted',
};
const BAD_VALUES = new Set(['--app-primary', '--app-primary-text', '--app-text', '--app-text-muted', '--app-text-sec']);
const canonPat = new RegExp(`\\b(${Object.keys(CANON).join('|')})\\s*:\\s*'var\\((--app-[a-z-]+)\\)'`, 'g');
const canonFailures = [];
for (const f of files) {
  const t = read(f);
  for (const m of t.matchAll(canonPat)) {
    if (BAD_VALUES.has(m[2]) && m[2] !== CANON[m[1]]) {
      canonFailures.push({ file: rel(f), key: m[1], got: m[2], want: CANON[m[1]] });
    }
  }
}

/* 5b) Module-level palettes: `const C = {...}` — every C.<key> used must be defined */
const modulePaletteFailures = [];
for (const f of files) {
  const t = read(f);
  const m = t.match(/^const C = \{([\s\S]*?)\n\};/m);
  if (!m) continue;
  const keys = new Set();
  for (const km of m[1].matchAll(/(\w+)\s*:/g)) keys.add(km[1]);
  const missing = new Set();
  for (const um of t.matchAll(/\bC\.(\w+)\b/g)) {
    if (!keys.has(um[1])) missing.add(um[1]);
  }
  if (missing.size) modulePaletteFailures.push({ file: rel(f), missing: [...missing] });
}

if (unique.size || namedThemeFailures.length || canonFailures.length || modulePaletteFailures.length) {
  console.log('\n❌ theme-palette-prop-gate FAILED:\n');
  for (const fl of modulePaletteFailures) {
    console.log(`  [module-palette] ${fl.file} uses undefined C keys: ${fl.missing.join(', ')}`);
  }
  for (const fl of unique.values()) {
    console.log(`  [palette-prop] ${fl.producer} -> <${fl.consumer}> (${fl.consumerFile})`);
    console.log(`     missing tokens: ${fl.missing.join(', ')}`);
  }
  for (const fl of namedThemeFailures) {
    console.log(`  [exec-theme] ${fl.file} uses unknown getExecTheme keys: ${fl.missing.join(', ')}`);
  }
  for (const fl of canonFailures) {
    console.log(`  [css-var-mismatch] ${fl.file}: ${fl.key}: 'var(${fl.got})' should be 'var(${fl.want})'`);
  }
  console.log(`\n  ${unique.size + namedThemeFailures.length + canonFailures.length + modulePaletteFailures.length} violation(s).`);
  process.exit(1);
}
console.log(`✅ theme-palette-prop-gate passed (${consumers.size} palette-prop consumers, exec-theme keys OK, css-var mappings canonical, ${files.length} files)`);
