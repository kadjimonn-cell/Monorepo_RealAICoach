// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const tsParser = require('@typescript-eslint/parser');
const noHardcodedThemeColors = require('./eslint-rules/no-hardcoded-theme-colors');
const enforceGlobalTheme = require('./eslint-rules/enforce-global-theme');
const noBareEnglishLiterals = require('./eslint-rules/no-bare-english-literals');

module.exports = defineConfig([
  expoConfig,
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: './tsconfig.json',
        tsconfigRootDir: __dirname,
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
  },
  {
    ignores: ['dist/*', '.expo/*'],
    rules: {
      'react/no-unescaped-entities': 'off',
      // testID is a valid React Native / Expo prop (used throughout for Playwright tests)
      'react/no-unknown-property': ['warn', { ignore: ['testID'] }],
      // ── Hard block: deprecated theme helpers must never be re-introduced ──
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '../src/components/PublicPageLayout',
              importNames: ['getColors'],
              message: 'getColors() has been permanently removed. Use `const { colors: C } = useTheme()` from ThemeContext.',
            },
            {
              name: '../../src/components/PublicPageLayout',
              importNames: ['getColors'],
              message: 'getColors() has been permanently removed. Use `const { colors: C } = useTheme()` from ThemeContext.',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['app/**/*.tsx', 'src/components/**/*.tsx'],
    plugins: {
      'custom-theme': {
        rules: {
          'no-hardcoded-theme-colors': noHardcodedThemeColors,
          'enforce-global-theme': enforceGlobalTheme,
        },
      },
    },
    rules: {
      'custom-theme/no-hardcoded-theme-colors': 'error',
      'custom-theme/enforce-global-theme': 'error',
    },
  },
  {
    files: [
      'src/components/Footer.tsx',
      'src/components/GlobalNavBar.tsx',
      'src/components/home/**/*.tsx',
      'src/components/welcome/**/*.tsx',
    ],
    plugins: {
      'custom-i18n': {
        rules: {
          'no-bare-english-literals': noBareEnglishLiterals,
        },
      },
    },
    rules: {
      'custom-i18n/no-bare-english-literals': ['warn', {
        minWords: 2,
        enableAutoFixKnownKeys: true,
        localeFilePath: './src/i18n/locales/en.ts',
        ignorePatterns: [
          '^[A-Z]{1,4}$',
          '^v\\d+(?:\\.\\d+)*$',
          '^(PASS|FAIL|YES|NO|ACTIVE|INACTIVE|LOW|MEDIUM|HIGH|CRITICAL|MED|INFO|OK)$',
        ],
        ignoreFilePatterns: [
          '/node_modules/',
          '\\.(test|spec)\\.(tsx|jsx)$',
        ],
      }],
    },
  },
]);
