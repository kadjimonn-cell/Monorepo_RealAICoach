#!/usr/bin/env node

/**
 * i18n literal auto-fixer helper
 *
 * What it does:
 * 1) Scans TSX/JSX files for repeated bare literals
 * 2) Maps each repeated literal to an existing or new i18n key in en.ts
 * 3) Rewrites JSX literals to t('key') for files already using { t }
 * 4) Optionally writes updates (files + locale) when --write is provided
 *
 * Usage examples:
 *   node scripts/i18n-literal-autofix.js
 *   node scripts/i18n-literal-autofix.js --write
 *   node scripts/i18n-literal-autofix.js --write --min-repeats=3 --namespace=autofix
 */

const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');

const projectRoot = path.resolve(__dirname, '..');
const localeFile = path.join(projectRoot, 'src', 'i18n', 'locales', 'en.ts');

function parseArgs(argv) {
  const args = {
    write: false,
    minRepeats: 2,
    minWords: 2,
    allowSingleVisible: false,
    namespace: 'autofix',
    roots: ['src/components', 'app'],
    files: [],
    reportPath: path.resolve(projectRoot, '../memory/i18n_literal_autofix_report.json'),
  };

  for (const item of argv) {
    if (item === '--write') args.write = true;
    else if (item.startsWith('--min-repeats=')) args.minRepeats = Math.max(1, Number(item.split('=')[1]) || 2);
    else if (item.startsWith('--min-words=')) args.minWords = Math.max(1, Number(item.split('=')[1]) || 2);
    else if (item === '--allow-single-visible' || item === '--single-visible') args.allowSingleVisible = true;
    else if (item.startsWith('--namespace=')) args.namespace = String(item.split('=')[1] || 'autofix').trim() || 'autofix';
    else if (item.startsWith('--roots=')) args.roots = item.split('=')[1].split(',').map((v) => v.trim()).filter(Boolean);
    else if (item.startsWith('--files=')) args.files = item.split('=')[1].split(',').map((v) => v.trim()).filter(Boolean);
    else if (item.startsWith('--report=')) args.reportPath = path.resolve(projectRoot, item.split('=')[1]);
  }
  return args;
}

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function shouldIgnoreText(text, minWords) {
  if (!text) return true;
  if (text.length < 3) return true;
  if (!/[A-Za-z]/.test(text)) return true;
  if (/^[\d\s.,%:+\-_/|()[\]{}]+$/.test(text)) return true;
  if (/^[A-Z\d\s.,%:+\-_/|()[\]{}]+$/.test(text)) return true;
  if (/^(https?:\/\/|\/)/i.test(text)) return true;
  if (/^\S+@\S+\.\S+$/.test(text)) return true;
  if (/^[a-z0-9_-]+(?:\.[a-z0-9_-]+)+$/i.test(text)) return true;
  if (/^\{.+\}$/.test(text)) return true;
  const words = text.split(/\s+/).filter(Boolean);
  return words.length < minWords;
}

function isSafeSingleVisibleLiteral(text) {
  if (!text) return false;
  const s = normalizeText(text);
  if (s.length < 3 || s.length > 80) return false;
  if (!/[A-Za-z]/.test(s)) return false;
  if (/^(https?:\/\/|\/)/i.test(s)) return false;
  if (/^[a-z0-9_-]+(?:\.[a-z0-9_-]+)+$/i.test(s)) return false;
  if (/^\/?[a-z0-9/_\-\[\]]+$/i.test(s)) return false;
  if (/^[A-Z0-9_\-]{4,}$/.test(s)) return false;
  if (/\{.+\}|\$\{.+\}/.test(s)) return false;
  return true;
}

function listSourceFiles(args) {
  const out = [];
  const roots = args.files.length
    ? args.files.map((p) => path.resolve(projectRoot, p))
    : args.roots.map((p) => path.resolve(projectRoot, p));
  const skip = new Set(['node_modules', 'dist', '.expo', '.next', '.git']);
  const allowed = new Set(['.tsx', '.jsx']);

  const walk = (target) => {
    if (!fs.existsSync(target)) return;
    const stat = fs.statSync(target);
    if (stat.isFile()) {
      if (allowed.has(path.extname(target))) out.push(target);
      return;
    }
    const entries = fs.readdirSync(target, { withFileTypes: true });
    for (const ent of entries) {
      if (ent.name.startsWith('.')) continue;
      if (skip.has(ent.name)) continue;
      walk(path.join(target, ent.name));
    }
  };

  roots.forEach(walk);
  return [...new Set(out)].sort();
}

function hasTranslationHook(sourceCode) {
  return /const\s*\{[^}]*\bt\b[^}]*\}\s*=\s*use(?:Translation|Language)\s*\(/.test(sourceCode);
}

function parseTsx(code, filePath) {
  try {
    return parser.parse(code, {
      sourceType: 'module',
      plugins: ['jsx', 'typescript'],
      ranges: true,
      errorRecovery: true,
    });
  } catch (err) {
    console.warn(`[i18n-autofix] parse skip ${filePath}: ${err.message.split('\n')[0]}`);
    return null;
  }
}

function walkAst(node, parent, grandParent, visitor) {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return;
  visitor(node, parent, grandParent);
  for (const key of Object.keys(node)) {
    if (key === 'loc' || key === 'start' || key === 'end' || key === 'range') continue;
    const value = node[key];
    if (!value) continue;
    if (Array.isArray(value)) {
      for (const child of value) {
        if (child && typeof child.type === 'string') walkAst(child, node, parent, visitor);
      }
    } else if (value && typeof value.type === 'string') {
      walkAst(value, node, parent, visitor);
    }
  }
}

function findObjectBounds(source, anchor = 'const locale') {
  const anchorIdx = source.indexOf(anchor);
  if (anchorIdx < 0) throw new Error('Cannot find locale anchor');
  const start = source.indexOf('{', anchorIdx);
  if (start < 0) throw new Error('Cannot find locale object start');

  let depth = 0;
  let inString = false;
  let quote = '';
  let escaped = false;

  for (let i = start; i < source.length; i += 1) {
    const ch = source[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) {
        inString = false;
        quote = '';
      }
      continue;
    }

    if (ch === '"' || ch === '\'') {
      inString = true;
      quote = ch;
      continue;
    }

    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return { start, end: i };
    }
  }

  throw new Error('Cannot find locale object end');
}

function loadLocaleMap(localePath) {
  const src = fs.readFileSync(localePath, 'utf-8');
  const { start, end } = findObjectBounds(src);
  const objectLiteral = src.slice(start, end + 1);
  const jsonText = objectLiteral.replace(/,\s*}/g, '}');
  return { src, bounds: { start, end }, map: JSON.parse(jsonText) };
}

function writeLocaleMap(localePath, originalSrc, bounds, map) {
  const keys = Object.keys(map).sort((a, b) => a.localeCompare(b));
  const body = keys.map((key) => `  ${JSON.stringify(key)}: ${JSON.stringify(map[key])},`).join('\n');
  const updated = `${originalSrc.slice(0, bounds.start + 1)}\n${body}\n${originalSrc.slice(bounds.end)}`;
  fs.writeFileSync(localePath, updated, 'utf-8');
}

function slugify(text) {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '.')
    .replace(/^\.+|\.+$/g, '')
    .split('.')
    .filter(Boolean)
    .slice(0, 8)
    .join('.');
  return slug || 'text';
}

function ensureKey(namespace, text, localeMap) {
  const base = `${namespace}.${slugify(text)}`;
  let key = base;
  let idx = 2;
  while (Object.prototype.hasOwnProperty.call(localeMap, key) && localeMap[key] !== text) {
    key = `${base}.${idx}`;
    idx += 1;
  }
  return key;
}

function applyReplacements(source, replacements) {
  if (!replacements.length) return source;
  let out = source;
  const sorted = [...replacements].sort((a, b) => b.start - a.start);
  for (const rep of sorted) {
    out = `${out.slice(0, rep.start)}${rep.value}${out.slice(rep.end)}`;
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const files = listSourceFiles(args);

  if (!files.length) {
    console.log('[i18n-autofix] no files matched scan roots.');
    process.exit(0);
  }

  const locale = loadLocaleMap(localeFile);
  const localeMap = { ...locale.map };
  const reverseLocale = {};
  for (const [key, value] of Object.entries(localeMap)) {
    if (!reverseLocale[value]) reverseLocale[value] = key;
  }

  const occurrences = [];
  const byTextCount = new Map();
  const fileMeta = new Map();

  for (const filePath of files) {
    const source = fs.readFileSync(filePath, 'utf-8');
    const ast = parseTsx(source, filePath);
    if (!ast) continue;

    const canRewrite = hasTranslationHook(source);
    fileMeta.set(filePath, { source, canRewrite });

    const register = (node, kind, raw) => {
      const text = normalizeText(raw);
      if (shouldIgnoreText(text, args.minWords)) return;
      if (typeof node.start !== 'number' || typeof node.end !== 'number') return;
      occurrences.push({ filePath, start: node.start, end: node.end, kind, text });
      byTextCount.set(text, (byTextCount.get(text) || 0) + 1);
    };

    walkAst(ast, null, null, (node, parent, grandParent) => {
      if (node.type === 'JSXText') {
        register(node, 'jsxText', node.value);
        return;
      }
      if (node.type === 'StringLiteral' && parent?.type === 'JSXExpressionContainer' && grandParent?.type === 'JSXElement') {
        register(node, 'stringLiteral', node.value);
        return;
      }
      if (node.type === 'TemplateLiteral' && node.expressions?.length === 0 && parent?.type === 'JSXExpressionContainer' && grandParent?.type === 'JSXElement') {
        const raw = (node.quasis || []).map((q) => q.value?.cooked || '').join('');
        register(node, 'templateLiteral', raw);
      }
    });
  }

  const repeatedTexts = [...byTextCount.entries()]
    .filter(([text, count]) => (
      count >= args.minRepeats
      || (args.allowSingleVisible && count === 1 && isSafeSingleVisibleLiteral(text))
    ))
    .map(([text]) => text);

  const textToKey = new Map();
  const newLocaleEntries = {};
  for (const text of repeatedTexts) {
    if (reverseLocale[text]) {
      textToKey.set(text, reverseLocale[text]);
      continue;
    }
    const key = ensureKey(args.namespace, text, localeMap);
    localeMap[key] = text;
    reverseLocale[text] = key;
    textToKey.set(text, key);
    newLocaleEntries[key] = text;
  }

  let changedFiles = 0;
  let replacementCount = 0;
  const changedFilePaths = [];

  const byFile = new Map();
  for (const occ of occurrences) {
    if (!textToKey.has(occ.text)) continue;
    if (!byFile.has(occ.filePath)) byFile.set(occ.filePath, []);
    byFile.get(occ.filePath).push(occ);
  }

  for (const [filePath, entries] of byFile.entries()) {
    const meta = fileMeta.get(filePath);
    if (!meta?.canRewrite) continue;
    const replacements = [];

    for (const occ of entries) {
      const key = textToKey.get(occ.text);
      if (!key) continue;
      if (occ.kind === 'jsxText') {
        replacements.push({ start: occ.start, end: occ.end, value: `{t(${JSON.stringify(key)})}` });
      } else {
        replacements.push({ start: occ.start, end: occ.end, value: `t(${JSON.stringify(key)})` });
      }
    }

    const updated = applyReplacements(meta.source, replacements);
    if (updated !== meta.source) {
      changedFiles += 1;
      replacementCount += replacements.length;
      changedFilePaths.push(path.relative(projectRoot, filePath));
      if (args.write) fs.writeFileSync(filePath, updated, 'utf-8');
    }
  }

  if (args.write && changedFiles > 0 && Object.keys(newLocaleEntries).length > 0) {
    writeLocaleMap(localeFile, locale.src, locale.bounds, localeMap);
  }

  const report = {
    timestamp: new Date().toISOString(),
    writeMode: args.write,
    scanRoots: args.files.length ? args.files : args.roots,
    minRepeats: args.minRepeats,
    minWords: args.minWords,
    allowSingleVisible: args.allowSingleVisible,
    namespace: args.namespace,
    filesScanned: files.length,
    repeatedLiteralCount: repeatedTexts.length,
    changedFiles,
    replacementsApplied: replacementCount,
    newLocaleKeyCount: Object.keys(newLocaleEntries).length,
    newLocaleEntries,
    changedFilePaths,
  };

  fs.mkdirSync(path.dirname(args.reportPath), { recursive: true });
  fs.writeFileSync(args.reportPath, JSON.stringify(report, null, 2), 'utf-8');

  console.log('[i18n-autofix] report:', args.reportPath);
  console.log('[i18n-autofix] files scanned:', files.length);
  console.log('[i18n-autofix] repeated literals:', repeatedTexts.length);
  console.log('[i18n-autofix] changed files:', changedFiles);
  console.log('[i18n-autofix] replacements:', replacementCount);
  console.log('[i18n-autofix] new locale keys:', Object.keys(newLocaleEntries).length);
}

main();
