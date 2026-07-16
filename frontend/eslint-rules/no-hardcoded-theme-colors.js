/**
 * ESLint rule: no-hardcoded-theme-colors
 *
 * Flags .tsx files that use common hardcoded dark/light hex colors
 * without importing a theme hook (useTheme, useAdminTheme, getAdminColors).
 * This enforces that all components adapt to the platform's light/dark mode.
 *
 * NOTE: getColors, getT, getRegisterColors, getPrivacyColors, useWelcomeTheme
 * have all been REMOVED from the codebase. Only useTheme / useAdminTheme /
 * getAdminColors are accepted as valid theme access patterns.
 */

const DARK_BG_COLORS = new Set([
  '#050a18', '#050a14', '#0b0f1a', '#0b1121', '#0b1120', '#0f172a',
  '#111b2e', '#131b2e', '#132036', '#161e35', '#18243c', '#1a2744',
  '#020617',
]);

const DARK_BORDER_COLORS = new Set([
  '#1e293b', '#162032', '#334155',
]);

const DARK_TEXT_COLORS = new Set([
  '#f1f5f9', '#f8fafc', '#f8fbff', '#e2e8f0', '#e1e9f3',
  '#cbd5e1', '#b7c7d9',
]);

const ALL_FLAGGED = new Set([...DARK_BG_COLORS, ...DARK_BORDER_COLORS, ...DARK_TEXT_COLORS]);

/** Only these theme access patterns are accepted. getColors / getT / etc. are BANNED. */
const THEME_IMPORTS = [
  'useTheme',
  'useAdminTheme',
  'getAdminColors',
];

module.exports = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow hardcoded dark theme colors without a theme hook import',
      category: 'Best Practices',
    },
    messages: {
      noHardcodedColor:
        "Hardcoded color '{{color}}' detected. Use useTheme(), useAdminTheme(), or getColors() instead. See THEME_GUIDE.md.",
    },
    schema: [],
  },

  create(context) {
    const filename = context.getFilename();
    if (!filename.endsWith('.tsx')) return {};

    let hasThemeImport = false;

    return {
      ImportDeclaration(node) {
        const specifiers = node.specifiers || [];
        for (const spec of specifiers) {
          const name = spec.local?.name || spec.imported?.name || '';
          if (THEME_IMPORTS.includes(name)) {
            hasThemeImport = true;
          }
        }
      },

      Literal(node) {
        if (hasThemeImport) return;
        if (typeof node.value !== 'string') return;

        const val = node.value.toLowerCase().trim();
        if (ALL_FLAGGED.has(val)) {
          context.report({
            node,
            messageId: 'noHardcodedColor',
            data: { color: node.value },
          });
        }
      },

      TemplateLiteral(node) {
        if (hasThemeImport) return;
        for (const quasi of node.quasis) {
          const raw = (quasi.value.raw || '').toLowerCase();
          for (const color of ALL_FLAGGED) {
            if (raw.includes(color)) {
              context.report({
                node,
                messageId: 'noHardcodedColor',
                data: { color },
              });
            }
          }
        }
      },
    };
  },
};
