/**
 * ESLint rule: no-bare-english-literals
 *
 * Flags plain JSX text literals so UI copy is sourced from i18n keys
 * via `t('feature.key')` instead of hardcoded English.
 */

const fs = require('fs');
const path = require('path');

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

let LOCALE_CACHE = null;

function findObjectBounds(source, anchor = 'const locale') {
  const anchorIdx = source.indexOf(anchor);
  if (anchorIdx < 0) return null;
  const start = source.indexOf('{', anchorIdx);
  if (start < 0) return null;

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
  return null;
}

function loadLocaleValueToKeyMap(localeFilePath) {
  const abs = path.resolve(localeFilePath);
  if (LOCALE_CACHE && LOCALE_CACHE.path === abs) {
    return LOCALE_CACHE.valueToKey;
  }
  try {
    const src = fs.readFileSync(abs, 'utf-8');
    const bounds = findObjectBounds(src);
    if (!bounds) return {};
    const objectText = src.slice(bounds.start, bounds.end + 1).replace(/,\s*}/g, '}');
    const locale = JSON.parse(objectText);
    const valueToKey = {};
    for (const [key, value] of Object.entries(locale)) {
      if (!valueToKey[value]) valueToKey[value] = key;
    }
    LOCALE_CACHE = { path: abs, valueToKey };
    return valueToKey;
  } catch {
    return {};
  }
}

module.exports = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow bare English literals in JSX text nodes',
      category: 'i18n Enforcement',
      recommended: false,
    },
    schema: [
      {
        type: 'object',
        properties: {
          minWords: { type: 'number' },
          ignorePatterns: { type: 'array', items: { type: 'string' } },
          ignoreFilePatterns: { type: 'array', items: { type: 'string' } },
          enableAutoFixKnownKeys: { type: 'boolean' },
          localeFilePath: { type: 'string' },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      noBareLiteral:
        'Bare English literal "{{text}}" found in JSX. Use t("feature.key") instead.',
    },
  },

  create(context) {
    const filename = context.getFilename();
    if (!filename.endsWith('.tsx') && !filename.endsWith('.jsx')) return {};

    const options = context.options?.[0] || {};
    const minWords = Number.isFinite(options.minWords) ? Number(options.minWords) : 2;
    const enableAutoFixKnownKeys = Boolean(options.enableAutoFixKnownKeys);
    const cwd = context.cwd || process.cwd();
    const localeFilePath = options.localeFilePath || path.join(cwd, 'src', 'i18n', 'locales', 'en.ts');
    const knownValueToKey = enableAutoFixKnownKeys ? loadLocaleValueToKeyMap(localeFilePath) : {};
    const sourceText = context.sourceCode?.text || '';
    const hasTranslationHook = /const\s*\{[^}]*\bt\b[^}]*\}\s*=\s*use(?:Translation|Language)\s*\(/.test(sourceText);
    const ignorePatterns = (options.ignorePatterns || []).map((pattern) => {
      try { return new RegExp(pattern); } catch { return null; }
    }).filter(Boolean);
    const ignoreFilePatterns = (options.ignoreFilePatterns || []).map((pattern) => {
      try { return new RegExp(pattern); } catch { return null; }
    }).filter(Boolean);

    if (ignoreFilePatterns.some((re) => re.test(filename))) return {};

    function shouldIgnore(text) {
      if (!text) return true;
      if (text.length < 3) return true;
      if (!/[A-Za-z]/.test(text)) return true;
      if (/^[\d\s.,%:+\-_/|()[\]{}]+$/.test(text)) return true;
      if (/^[A-Z\d\s.,%:+\-_/|()[\]{}]+$/.test(text)) return true;
      if (/^(https?:\/\/|\/)/i.test(text)) return true;
      if (/^\S+@\S+\.\S+$/.test(text)) return true;
      if (/^[a-z0-9_-]+(?:\.[a-z0-9_-]+)+$/i.test(text)) return true;
      if (ignorePatterns.some((re) => re.test(text))) return true;

      const words = text.split(/\s+/).filter(Boolean);
      return words.length < minWords;
    }

    function maybeReport(node, rawText, kind) {
      const text = normalizeText(rawText);
      if (shouldIgnore(text)) return;
      const knownKey = knownValueToKey[text];
      const canFix = enableAutoFixKnownKeys && Boolean(knownKey) && hasTranslationHook;
      context.report({
        node,
        messageId: 'noBareLiteral',
        data: { text: text.slice(0, 60) },
        ...(canFix
          ? {
              fix(fixer) {
                if (kind === 'jsxText') {
                  return fixer.replaceText(node, `{t(${JSON.stringify(knownKey)})}`);
                }
                return fixer.replaceText(node, `t(${JSON.stringify(knownKey)})`);
              },
            }
          : {}),
      });
    }

    return {
      JSXText(node) {
        maybeReport(node, node.value, 'jsxText');
      },
      Literal(node) {
        if (typeof node.value !== 'string') return;
        const parent = node.parent;
        if (parent?.type === 'JSXExpressionContainer' && parent.parent?.type === 'JSXElement') {
          maybeReport(node, node.value, 'literal');
        }
      },
      TemplateLiteral(node) {
        if (node.expressions?.length) return;
        const parent = node.parent;
        if (parent?.type === 'JSXExpressionContainer' && parent.parent?.type === 'JSXElement') {
          const raw = node.quasis?.map((q) => q.value?.cooked || '').join('') || '';
          maybeReport(node, raw, 'template');
        }
      },
    };
  },
};
