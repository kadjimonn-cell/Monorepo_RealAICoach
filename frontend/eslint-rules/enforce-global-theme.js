/**
 * ESLint Plugin: enforce-global-theme
 *
 * Blocks custom per-page color palette functions and deprecated theme helpers.
 * Enforces that ALL pages/components use:
 *   - useTheme().colors from ThemeContext  (public pages, dashboard components)
 *   - useAdminTheme() / getAdminColors()   (admin-only pages)
 *
 * BANNED (removed from codebase — do NOT re-introduce):
 *   - getColors()         (was in PublicPageLayout.tsx — DELETED)
 *   - getT()              (was in designTokens.ts — DELETED)
 *   - getRegisterColors() (was in register.tsx — DELETED)
 *   - getPrivacyColors()  (was in privacy-policy.tsx — DELETED)
 *   - useWelcomeTheme()   (was in welcome.tsx — DELETED)
 *
 * Detects and reports:
 *   1. Custom color palette function declarations (getXxxColors, makeXxxColors)
 *      that are NOT getAdminColors from useAdminTheme
 *   2. Calls to explicitly banned helpers
 *
 * Usage: npx eslint --rulesdir eslint-rules --rule '{"enforce-global-theme": "error"}' app/
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
        'Custom color palette function "{{name}}" is not allowed. ' +
        'Use `const { colors: C } = useTheme()` from ThemeContext (public/dashboard pages) ' +
        'or `useAdminTheme()` / `getAdminColors()` (admin-only pages). ' +
        'Per-page palettes cause visual inconsistency.',
      noInlinePalette:
        'Inline color palette object in "{{name}}" is not allowed. ' +
        'Use `const { colors: C } = useTheme()` from ThemeContext instead.',
      bannedHelper:
        '"{{name}}" has been permanently removed from the codebase. ' +
        'Use `const { colors: C } = useTheme()` from ThemeContext instead.',
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
      'designTokens.ts',
      'design_guidelines',
      'lint-rules/',
      'no-hardcoded-colors.js',
      'enforce-global-theme.js',
      'ExecDashboardPanels.tsx', // uses getAdminColors (V1 admin tokens — allowed)
    ];
    if (EXEMPT_FILES.some((f) => filename.includes(f))) return {};

    // Pattern: function declarations named get*Colors or make*Colors
    // EXEMPT: getAdminColors (legitimate admin theme helper from useAdminTheme)
    const PALETTE_FUNC_PATTERN = /^(?:get|make)[A-Z]\w*(?:Colors|Palette|Theme|Tokens)$/;
    const ALLOWED_PALETTE_FUNCS = new Set(['getAdminColors']);

    // Deprecated helpers that must never be re-introduced
    const BANNED_CALL_NAMES = new Set(['getColors', 'getT', 'getRegisterColors', 'getPrivacyColors']);

    return {
      // Catch: function getXxxColors(dark) { ... }
      FunctionDeclaration(node) {
        if (node.id && PALETTE_FUNC_PATTERN.test(node.id.name) && !ALLOWED_PALETTE_FUNCS.has(node.id.name)) {
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
          !ALLOWED_PALETTE_FUNCS.has(node.id.name) &&
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

      // Catch: getColors(...), getT(...), etc. — banned call sites
      CallExpression(node) {
        const callee = node.callee;
        if (callee.type === 'Identifier' && BANNED_CALL_NAMES.has(callee.name)) {
          context.report({
            node,
            messageId: 'bannedHelper',
            data: { name: callee.name },
          });
        }
      },
    };
  },
};
