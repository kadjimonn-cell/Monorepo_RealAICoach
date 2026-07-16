#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '..', 'src', 'i18n', 'locales');
const WRITE_MODE = process.argv.includes('--write');
const TAG_PREFIX_RE = /(:\s*")\[[a-z]{2}\]\s+/gi;

function sanitizeFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const matches = raw.match(TAG_PREFIX_RE) || [];
  const cleaned = raw.replace(TAG_PREFIX_RE, '$1');
  const changed = cleaned !== raw;
  if (WRITE_MODE && changed) {
    fs.writeFileSync(filePath, cleaned, 'utf8');
  }
  return { changed, matches: matches.length };
}

function run() {
  if (!fs.existsSync(LOCALES_DIR)) {
    console.error(`[i18n-strip-language-tags] FAIL: locales dir not found: ${LOCALES_DIR}`);
    process.exit(1);
  }

  const files = fs
    .readdirSync(LOCALES_DIR)
    .filter((name) => name.endsWith('.ts') && name !== 'en.ts')
    .map((name) => path.join(LOCALES_DIR, name));

  let totalMatches = 0;
  let changedFiles = 0;

  files.forEach((filePath) => {
    const result = sanitizeFile(filePath);
    totalMatches += result.matches;
    if (result.changed) changedFiles += 1;
  });

  if (!WRITE_MODE && totalMatches > 0) {
    console.error(`[i18n-strip-language-tags] FAIL: detected ${totalMatches} tagged locale values across ${changedFiles} files.`);
    console.error('[i18n-strip-language-tags] Run with --write to sanitize in-place.');
    process.exit(1);
  }

  if (WRITE_MODE) {
    // Verify zero remains after sanitize.
    let remaining = 0;
    files.forEach((filePath) => {
      const raw = fs.readFileSync(filePath, 'utf8');
      remaining += (raw.match(TAG_PREFIX_RE) || []).length;
    });
    if (remaining > 0) {
      console.error(`[i18n-strip-language-tags] FAIL: ${remaining} tagged values still remain after sanitize.`);
      process.exit(1);
    }
    console.log(`[i18n-strip-language-tags] PASS: sanitized ${totalMatches} tagged values across ${changedFiles} files.`);
    process.exit(0);
  }

  console.log('[i18n-strip-language-tags] PASS: no tagged locale values found.');
}

run();
