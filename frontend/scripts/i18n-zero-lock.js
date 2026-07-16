#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const BASELINE_PATH = path.join(__dirname, 'i18n-missing-keys-baseline.json');
const LOCALES_DIR = path.join(__dirname, '..', 'src', 'i18n', 'locales');
const TAG_PREFIX_RE = /(:\s*")\[[a-z]{2}\]\s+/gi;

function fail(message) {
  console.error(`[i18n-zero-lock] FAIL: ${message}`);
  process.exit(1);
}

function run() {
  if (!fs.existsSync(BASELINE_PATH)) {
    fail(`Baseline file missing: ${BASELINE_PATH}`);
  }

  let payload;
  try {
    payload = JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf8'));
  } catch (err) {
    fail(`Unable to parse baseline JSON: ${err?.message || err}`);
  }

  const keys = Array.isArray(payload?.missing_keys)
    ? payload.missing_keys.filter(Boolean)
    : [];

  if (keys.length > 0) {
    console.error('[i18n-zero-lock] Remaining keys:');
    keys.slice(0, 50).forEach((key) => console.error(`- ${key}`));
    if (keys.length > 50) {
      console.error(`... and ${keys.length - 50} more`);
    }
    fail(`Expected zero missing keys, found ${keys.length}.`);
  }

  const localeFiles = fs
    .readdirSync(LOCALES_DIR)
    .filter((name) => name.endsWith('.ts') && name !== 'en.ts');

  let taggedValues = 0;
  localeFiles.forEach((name) => {
    const raw = fs.readFileSync(path.join(LOCALES_DIR, name), 'utf8');
    taggedValues += (raw.match(TAG_PREFIX_RE) || []).length;
  });

  if (taggedValues > 0) {
    fail(`Detected ${taggedValues} locale values with leaked [xx] language tags.`);
  }

  console.log('[i18n-zero-lock] PASS: baseline is zero and no tagged locale values remain.');
}

run();
