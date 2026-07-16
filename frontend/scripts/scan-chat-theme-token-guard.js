#!/usr/bin/env node
/**
 * Scan/Chat Shared Theme Token Guard
 *
 * Purpose:
 * - Block hardcoded color literals in shared Scan/Chat infrastructure files.
 * - Enforce structural theme inheritance via FeatureLayout -> shared panels.
 *
 * This is intentionally strict for:
 *  - src/components/AIScanner.tsx
 *  - src/components/AIChatPanel.tsx
 *  - src/components/FeatureLayout.tsx
 */

const fs = require('fs');
const path = require('path');

const FRONTEND_ROOT = path.resolve(__dirname, '..');

const TARGETS = [
  'src/components/AIScanner.tsx',
  'src/components/AIChatPanel.tsx',
  'src/components/FeatureLayout.tsx',
];

const HEX_COLOR_RE = /#[0-9A-Fa-f]{3,8}\b/g;
const RAW_COLOR_FN_RE = /['"`](?:rgb|rgba|hsl|hsla)\([^'"`]+\)['"`]/g;

function readFile(relPath) {
  const absPath = path.join(FRONTEND_ROOT, relPath);
  if (!fs.existsSync(absPath)) {
    throw new Error(`Missing required file: ${relPath}`);
  }
  return fs.readFileSync(absPath, 'utf-8');
}

function collectLiteralColorViolations(relPath, text) {
  const violations = [];
  const lines = text.split(/\r?\n/);

  for (let i = 0; i < lines.length; i += 1) {
    const lineNo = i + 1;
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith('//') || trimmed.startsWith('/*') || trimmed.startsWith('*')) {
      continue;
    }

    const hexMatches = line.match(HEX_COLOR_RE) || [];
    const fnMatches = line.match(RAW_COLOR_FN_RE) || [];

    if (hexMatches.length > 0 || fnMatches.length > 0) {
      violations.push({
        file: relPath,
        line: lineNo,
        code: trimmed.slice(0, 200),
      });
    }
  }

  return violations;
}

function runStructuralChecks(fileMap) {
  const issues = [];

  const featureLayout = fileMap['src/components/FeatureLayout.tsx'] || '';
  if (!/AIScanner\s+feature=\{feature\}\s+themeColors=\{colors\}/.test(featureLayout)) {
    issues.push('FeatureLayout must pass themeColors={colors} to AIScanner.');
  }
  if (!/AIChatPanel\s+feature=\{feature\}\s+themeColors=\{colors\}/.test(featureLayout)) {
    issues.push('FeatureLayout must pass themeColors={colors} to AIChatPanel.');
  }

  const scanner = fileMap['src/components/AIScanner.tsx'] || '';
  if (!/themeColors\?:\s*any/.test(scanner) || !/const\s+activeColors\s*=\s*themeColors\s*\|\|\s*colors/.test(scanner)) {
    issues.push('AIScanner must expose themeColors prop and derive activeColors = themeColors || colors.');
  }

  const chat = fileMap['src/components/AIChatPanel.tsx'] || '';
  if (!/themeColors\?:\s*any/.test(chat) || !/const\s+activeColors\s*=\s*themeColors\s*\|\|\s*colors/.test(chat)) {
    issues.push('AIChatPanel must expose themeColors prop and derive activeColors = themeColors || colors.');
  }

  return issues;
}

function main() {
  const fileMap = {};
  const allViolations = [];

  for (const relPath of TARGETS) {
    const text = readFile(relPath);
    fileMap[relPath] = text;
    allViolations.push(...collectLiteralColorViolations(relPath, text));
  }

  const structuralIssues = runStructuralChecks(fileMap);

  if (allViolations.length > 0 || structuralIssues.length > 0) {
    console.error('❌ Scan/Chat theme token guard failed.');

    if (allViolations.length > 0) {
      console.error('\nHardcoded/raw color literals detected:');
      for (const v of allViolations) {
        console.error(`- ${v.file}:${v.line} -> ${v.code}`);
      }
    }

    if (structuralIssues.length > 0) {
      console.error('\nStructural guard failures:');
      for (const issue of structuralIssues) {
        console.error(`- ${issue}`);
      }
    }

    process.exit(1);
  }

  console.log('✅ Scan/Chat theme token guard passed.');
}

main();
