#!/usr/bin/env node
/**
 * Theme Token Validity Gate
 * Fails the build when a component references a theme color token that does
 * not exist, which renders as `undefined` (black text/icons or transparent
 * backgrounds) and breaks V2 light/dark compliance.
 *
 * Checks:
 *  A) Local color mappers (mkColors/makeColors): every `C.<key>` used must be
 *     defined in the mapper, unless it has an inline `||` / `??` fallback.
 *  B) Direct theme usage: in files that destructure `colors` straight from
 *     useTheme() (and never shadow it), every `colors.<key>` must exist in
 *     the V2 palette, unless it has an inline fallback.
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
const V2 = path.join(SRC, 'theme', 'v2.ts');

const v2Text = fs.readFileSync(V2, 'utf8');
const validKeys = new Set();
for (const m of v2Text.matchAll(/^\s{2}(\w+):/gm)) validKeys.add(m[1]);

/* ───────────── Contrast Contract (WCAG) ─────────────
 * Palette-level contrast enforcement: every designed text-on-surface pair
 * must meet WCAG AA 4.5:1 (3.0:1 for the subdued textDim tier).
 * textDisabled / placeholder / skeleton are WCAG-exempt (disabled elements).
 */
const parsePalette = (blockName) => {
  const m = v2Text.match(new RegExp(`export const ${blockName} = \\{([\\s\\S]*?)\\} as const;`));
  const out = {};
  for (const mm of m[1].matchAll(/^\s{2}(\w+):\s*'([^']+)'/gm)) out[mm[1]] = mm[2];
  return out;
};
const hexToRgb = (h) => {
  h = h.replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
    a: h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1,
  };
};
const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
const luminance = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
const contrast = (a, b) => {
  const hi = Math.max(luminance(a), luminance(b));
  const lo = Math.min(luminance(a), luminance(b));
  return (hi + 0.05) / (lo + 0.05);
};
const blendOver = (top, base) => ({
  r: Math.round(top.r * top.a + base.r * (1 - top.a)),
  g: Math.round(top.g * top.a + base.g * (1 - top.a)),
  b: Math.round(top.b * top.a + base.b * (1 - top.a)),
  a: 1,
});
const resolveToken = (palette, key) => {
  const v = palette[key];
  if (!v || !v.startsWith('#')) return null; // rgba()/css-var tokens are out of contract scope
  const c = hexToRgb(v);
  return c.a < 1 ? blendOver(c, hexToRgb(palette.card)) : c;
};

const CONTRAST_SURFACES = ['bg', 'bgAlt', 'bgSoft', 'card', 'cardMuted', 'cardSoft', 'surface', 'surfaceHover', 'surfaceElevated', 'input'];
const CONTRAST_TEXT_ROLES = ['text', 'textSec', 'textSecondary', 'textMuted'];
const AA = 4.5;
const SUBDUED = 3.0;

function runContrastContract() {
  const failures = [];
  for (const blockName of ['V2_LIGHT', 'V2_DARK']) {
    const P = parsePalette(blockName);
    const pairs = [];
    for (const t of CONTRAST_TEXT_ROLES) for (const s of CONTRAST_SURFACES) pairs.push([t, s, AA]);
    for (const st of ['success', 'warning', 'error', 'info']) pairs.push([`${st}Text`, `${st}Soft`, AA]);
    pairs.push(['badgeText', 'badge', AA]);
    pairs.push(['primaryText', 'primary', AA]);
    for (const s of ['bg', 'card', 'surface', 'surfaceElevated']) pairs.push(['textDim', s, SUBDUED]);

    for (const [fgKey, bgKey, min] of pairs) {
      const fg = resolveToken(P, fgKey);
      const bg = resolveToken(P, bgKey);
      if (!fg || !bg) continue;
      const ratio = contrast(fg, bg);
      if (ratio < min) {
        failures.push(`${blockName}: ${fgKey} (${P[fgKey]}) on ${bgKey} (${P[bgKey]}) = ${ratio.toFixed(2)} < ${min}`);
      }
    }
  }
  return failures;
}

const NON_TOKEN = new Set(['length', 'map', 'filter', 'forEach', 'toString']);

const files = [];
(function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '__tests__') continue;
      walk(path.join(dir, e.name));
    } else if (/\.(tsx|ts)$/.test(e.name) && !/\.d\.ts$/.test(e.name)) {
      files.push(path.join(dir, e.name));
    }
  }
})(SRC);

const hasFallback = (line, endIdx) => /^\s*(\|\||\?\?)/.test(line.slice(endIdx, endIdx + 24));

const violations = [];

for (const file of files) {
  const txt = fs.readFileSync(file, 'utf8');
  const rel = path.relative(path.join(__dirname, '..'), file);
  const lines = txt.split('\n');

  // A) local mapper check
  const mapper = txt.match(/(?:mkColors|makeColors)\s*=\s*\([^)]*\)\s*=>\s*\(\{([\s\S]*?)\}\)/);
  if (mapper) {
    const defined = new Set();
    for (const m of mapper[1].matchAll(/(?:^|\n)\s*(\w+):/g)) defined.add(m[1]);
    lines.forEach((line, i) => {
      for (const m of line.matchAll(/\bC\.(\w+)\b/g)) {
        const k = m[1];
        if (defined.has(k) || NON_TOKEN.has(k)) continue;
        if (hasFallback(line, m.index + m[0].length)) continue;
        violations.push(`${rel}:${i + 1}  C.${k} is not defined in the local color mapper`);
      }
    });
  }

  // B) direct theme usage check
  const directTheme = /const\s*\{\s*colors\s*[,}][^\n]*useTheme\(\)/.test(txt);
  const shadowed = /const\s+colors\s*=/.test(txt) || /\bcolors\s*:\s*(any|SummaryColors|\w*Colors)\b/.test(txt);
  if (directTheme && !shadowed) {
    lines.forEach((line, i) => {
      for (const m of line.matchAll(/\bcolors\.(\w+)\b/g)) {
        const k = m[1];
        if (validKeys.has(k) || NON_TOKEN.has(k)) continue;
        if (hasFallback(line, m.index + m[0].length)) continue;
        violations.push(`${rel}:${i + 1}  colors.${k} does not exist in the V2 theme palette`);
      }
    });
  }

  // C) hardcoded hex on interactive elements (TouchableOpacity/Pressable)
  if (file.endsWith('.tsx')) {
    const hexProp = /(?:(?:color|backgroundColor)\s*:\s*['"]#[0-9a-fA-F]{3,8}['"])|(?:color=["']#[0-9a-fA-F]{3,8}["'])/g;
    for (const open of txt.matchAll(/<(TouchableOpacity|Pressable)\b/g)) {
      const tag = open[1];
      const closeIdx = txt.indexOf(`</${tag}>`, open.index);
      const selfCloseIdx = txt.indexOf('/>', open.index);
      const end = closeIdx !== -1 && (selfCloseIdx === -1 || closeIdx < selfCloseIdx)
        ? closeIdx
        : (selfCloseIdx !== -1 ? selfCloseIdx : open.index + 500);
      const span = txt.slice(open.index, end);
      for (const hit of span.matchAll(hexProp)) {
        const absPos = open.index + hit.index;
        const lineNo = txt.slice(0, absPos).split('\n').length;
        const line = lines[lineNo - 1] || '';
        if (line.includes('@theme-ok')) continue;
        violations.push(`${rel}:${lineNo}  hardcoded hex on interactive <${tag}> — use a theme token (or add an inline @theme-ok marker for fixed-canvas visuals): ${hit[0]}`);
      }
    }
  }
}

if (violations.length) {
  console.error('\n❌ theme-token-validity-gate FAILED — theme violations found:\n');
  for (const v of violations) console.error('  • ' + v);
  console.error(
    '\nUndefined tokens render as black text/icons or transparent backgrounds and break V2 light/dark themes.' +
    '\nFix: use a valid token from src/theme/v2.ts, add the key to the local mapper, or add an explicit `||` fallback.\n'
  );
  process.exit(1);
}

const contrastFailures = runContrastContract();
if (contrastFailures.length) {
  console.error('\n❌ theme-token-validity-gate FAILED — WCAG contrast contract violations:\n');
  for (const v of contrastFailures) console.error('  • ' + v);
  console.error(
    '\nText tokens must meet WCAG AA 4.5:1 against their designed surfaces (3.0:1 for textDim).' +
    '\nFix: adjust the offending token value in src/theme/v2.ts. Remember to sync the FOUC vars in app/+html.tsx.\n'
  );
  process.exit(1);
}

console.log(`✅ theme-token-validity-gate passed (${files.length} files scanned, ${validKeys.size} valid tokens, contrast contract OK)`);
