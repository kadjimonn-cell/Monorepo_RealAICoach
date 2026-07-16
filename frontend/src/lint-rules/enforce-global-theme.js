/**
 * ESLint Plugin: enforce-global-theme
 *
 * Blocks custom per-page color palette functions.
 * Enforces that all pages use the global theme system:
 *   - getT() from login/designTokens.ts (for auth/public pages)
 *   - useTheme().colors from ThemeContext (for dashboard/admin pages)
 *
 * Detects and reports:
 *   1. Custom color palette function declarations (getXxxColors, makeXxxColors)
 *   2. Inline dark/light color objects that bypass the theme system
 *
 * Usage: npx eslint --rulesdir src/lint-rules --rule '{"enforce-global-theme": "error"}' src/
 */

module.exports = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Enforce global theme token system. Block custom per-page color palettes.',
      category: 'Theme Enforcement',
      recommended: true,
    },
    messages: {
      noCustomPalette:
        'Custom color palette function "{{name}}" detected. Use getT() from login/designTokens.ts or useTheme().colors from ThemeContext instead. Per-page palettes cause visual inconsistency.',
      noInlinePalette:
        'Inline color palette object detected in "{{name}}". Use getT() from login/designTokens.ts or useTheme().colors instead of defining per-page color maps.',
    },
    schema: [],
  },

  create(context) {
    const filename = context.getFilename();

    // Only apply to .tsx and .ts files
    if (!filename.endsWith('.tsx') && !filename.endsWith('.ts')) return {};

    // Exempt files that DEFINE the global theme tokens
    const EXEMPT_FILES = [
      'theme/v1.ts',
      'ThemeContext.tsx',
      'ThemeEnforcer.tsx',
      'useAdminTheme.ts',
      'designTokens.ts',       // The single source of truth
      'design_guidelines',
      'lint-rules/',
      'no-hardcoded-colors.js',
      'enforce-global-theme.js',
      'PublicPageLayout.tsx',   // Wrapper that derives from getT() — not a custom palette
      'ExecDashboardPanels.tsx', // Derives from getAdminColors (V1 tokens)
    ];
    if (EXEMPT_FILES.some((f) => filename.includes(f))) return {};

    // Pattern: function declarations named get*Colors or make*Colors
    const PALETTE_FUNC_PATTERN = /^(?:get|make)[A-Z]\w*(?:Colors|Palette|Theme|Tokens)$/;

    return {
      // Catch: function getXxxColors(dark) { ... }
      FunctionDeclaration(node) {
        if (node.id && PALETTE_FUNC_PATTERN.test(node.id.name)) {
          context.report({
            node,
            messageId: 'noCustomPalette',
            data: { name: node.id.name },
          });
        }
      },

      // Catch: const getXxxColors = (dark) => { ... }
      VariableDeclarator(node) {
        if (
          node.id &&
          node.id.type === 'Identifier' &&
          PALETTE_FUNC_PATTERN.test(node.id.name) &&
          node.init &&
          (node.init.type === 'ArrowFunctionExpression' || node.init.type === 'FunctionExpression')
        ) {
          context.report({
            node,
            messageId: 'noCustomPalette',
            data: { name: node.id.name },
          });
        }
      },
    };
  },
};
