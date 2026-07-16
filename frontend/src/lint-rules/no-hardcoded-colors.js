/**
 * ESLint Plugin: no-hardcoded-colors
 *
 * Blocks hardcoded hex colors (#RRGGBB, #RRGGBBAA) in .tsx files.
 * Forces all colors to come from the v1 theme system (useTheme().colors).
 *
 * Usage: npx eslint --rulesdir src/lint-rules src/components/
 * Or integrate into CI: eslint --rulesdir src/lint-rules --rule '{"no-hardcoded-colors": "error"}'
 */

module.exports = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Disallow hardcoded hex color values. Use theme tokens from useTheme().colors instead.',
      category: 'Theme Enforcement',
      recommended: true,
    },
    messages: {
      noHardcodedColor:
        'Hardcoded color "{{color}}" detected. Use a theme token from useTheme().colors (e.g., colors.primary, colors.text, colors.bg). See theme/v1.ts for available tokens.',
    },
    schema: [],
  },

  create(context) {
    // Only apply to .tsx files (component files)
    const filename = context.getFilename();
    if (!filename.endsWith('.tsx')) return {};

    // Exempt files that DEFINE theme tokens
    const EXEMPT_FILES = [
      'theme/v1.ts',
      'ThemeContext.tsx',
      'ThemeEnforcer.tsx',
      'useAdminTheme.ts',
      'design_guidelines',
    ];
    if (EXEMPT_FILES.some((f) => filename.includes(f))) return {};

    // Hex color pattern: #RGB, #RRGGBB, #RRGGBBAA (in quotes)
    const _HEX_PATTERN = /(['"`])#(?:[0-9A-Fa-f]{3}){1,2}(?:[0-9A-Fa-f]{2})?\1/g;

    // Allowed patterns (CSS custom properties, opacity modifiers used with theme tokens)
    const _ALLOWED_PATTERNS = [
      /rgba?\(/,     // rgba() is OK (used for opacity on theme colors)
      /transparent/,
      /var\(--/,     // CSS custom properties
      /\/\//,        // Comments
    ];

    return {
      Literal(node) {
        if (typeof node.value !== 'string') return;
        const val = node.value;

        // Check for hex color pattern
        if (/^#(?:[0-9A-Fa-f]{3}){1,2}(?:[0-9A-Fa-f]{2})?$/.test(val)) {
          // Allow pure white/black with alpha (often used for shadows/overlays)
          if (/^#(?:000|fff|000000|ffffff)$/i.test(val)) return;

          context.report({
            node,
            messageId: 'noHardcodedColor',
            data: { color: val },
          });
        }
      },

      TemplateLiteral(node) {
        for (const quasi of node.quasis) {
          const raw = quasi.value.raw;
          const matches = raw.match(/#(?:[0-9A-Fa-f]{3}){1,2}(?:[0-9A-Fa-f]{2})?/g);
          if (matches) {
            for (const color of matches) {
              if (/^#(?:000|fff|000000|ffffff)$/i.test(color)) continue;
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
