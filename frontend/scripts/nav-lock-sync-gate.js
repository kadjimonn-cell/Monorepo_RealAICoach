#!/usr/bin/env node
// Fails the build when BASE_NAV_ITEMS, LOCKED_USER_NAV_KEYS, LOCKED_USER_NAV_ORDER and NAV_TKEY drift apart.

const fs = require('fs');
const path = require('path');

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const APP_SHELL_PATH = path.join(FRONTEND_ROOT, 'src', 'components', 'AppShell.tsx');
const QUALITY_DIR = path.join(FRONTEND_ROOT, '.quality');
const REPORT_PATH = path.join(QUALITY_DIR, 'nav_lock_sync_report.json');

function extractBlock(text, startMarker, endMarker) {
  const start = text.indexOf(startMarker);
  if (start === -1) return null;
  const end = text.indexOf(endMarker, start + startMarker.length);
  if (end === -1) return null;
  return text.slice(start + startMarker.length, end);
}

function extractQuotedStrings(block) {
  return (block.match(/'([^']+)'/g) || []).map((s) => s.slice(1, -1));
}

function run() {
  const appShell = fs.readFileSync(APP_SHELL_PATH, 'utf8');

  const baseBlock = extractBlock(appShell, 'export const BASE_NAV_ITEMS = [', '];');
  const lockedKeysBlock = extractBlock(appShell, 'const LOCKED_USER_NAV_KEYS = new Set([', ']);');
  const lockedOrderBlock = extractBlock(appShell, 'const LOCKED_USER_NAV_ORDER = Object.freeze([', ']);');
  const adminKeysBlock = extractBlock(appShell, 'const LOCKED_ADMIN_NAV_KEYS = new Set([', ']);');
  const tkeyBlock = extractBlock(appShell, 'export const NAV_TKEY: Record<string, string> = {', '\n};');

  const problems = [];
  if (!baseBlock) problems.push('Could not parse BASE_NAV_ITEMS');
  if (!lockedKeysBlock) problems.push('Could not parse LOCKED_USER_NAV_KEYS');
  if (!lockedOrderBlock) problems.push('Could not parse LOCKED_USER_NAV_ORDER');
  if (!tkeyBlock) problems.push('Could not parse NAV_TKEY');
  if (problems.length) {
    console.error('[nav-lock-sync-gate] FAILED (parse):', problems.join('; '));
    process.exit(1);
  }

  const baseKeys = (baseBlock.match(/key:\s*'([^']+)'/g) || []).map((m) => m.match(/'([^']+)'/)[1]);
  const lockedKeys = extractQuotedStrings(lockedKeysBlock);
  const lockedOrder = extractQuotedStrings(lockedOrderBlock);
  const adminKeys = adminKeysBlock ? extractQuotedStrings(adminKeysBlock) : [];

  const tkeyKeys = [];
  const tkeyRx = /(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_-]*))\s*:\s*'/g;
  let m;
  while ((m = tkeyRx.exec(tkeyBlock)) !== null) tkeyKeys.push(m[1] || m[2]);

  const baseSet = new Set(baseKeys);
  const lockedSet = new Set(lockedKeys);
  const orderSet = new Set(lockedOrder);
  const tkeySet = new Set(tkeyKeys);
  const allowedExtraTkeys = new Set([...adminKeys, '_section_admin']);

  const missingFromLockedKeys = baseKeys.filter((k) => !lockedSet.has(k));
  const missingFromLockedOrder = baseKeys.filter((k) => !orderSet.has(k));
  const missingFromTkey = baseKeys.filter((k) => !tkeySet.has(k));
  const staleLockedKeys = lockedKeys.filter((k) => !baseSet.has(k));
  const staleLockedOrder = lockedOrder.filter((k) => !baseSet.has(k));
  const unknownTkeys = tkeyKeys.filter((k) => !baseSet.has(k) && !allowedExtraTkeys.has(k));

  const report = {
    generated_at: new Date().toISOString(),
    base_nav_item_count: baseKeys.length,
    missing_from_locked_keys: missingFromLockedKeys,
    missing_from_locked_order: missingFromLockedOrder,
    missing_from_nav_tkey: missingFromTkey,
    stale_locked_keys: staleLockedKeys,
    stale_locked_order: staleLockedOrder,
    unknown_nav_tkeys: unknownTkeys,
    pass:
      missingFromLockedKeys.length === 0 &&
      missingFromLockedOrder.length === 0 &&
      missingFromTkey.length === 0 &&
      staleLockedKeys.length === 0 &&
      staleLockedOrder.length === 0 &&
      unknownTkeys.length === 0,
  };

  if (!fs.existsSync(QUALITY_DIR)) fs.mkdirSync(QUALITY_DIR, { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));

  if (!report.pass) {
    console.error('[nav-lock-sync-gate] FAILED — nav lock lists are out of sync');
    for (const [field, items] of Object.entries(report)) {
      if (Array.isArray(items) && items.length) console.error(` - ${field}: ${items.join(', ')}`);
    }
    console.error(` - Report: ${REPORT_PATH}`);
    process.exit(1);
  }

  console.log(`[nav-lock-sync-gate] PASS — ${baseKeys.length} nav items in sync across all locked lists`);
}

run();
