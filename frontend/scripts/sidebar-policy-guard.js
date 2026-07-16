const fs = require('fs');
const path = require('path');

const FORBIDDEN_SIDEBAR_KEYS = [
  'sports-source-health',
  'matchday-reminders',
  'content-integrity',
];

function extractQuotedList(source) {
  const values = [];
  const re = /['"]([^'"]+)['"]/g;
  let match = re.exec(source);
  while (match) {
    values.push(String(match[1] || '').trim());
    match = re.exec(source);
  }
  return values;
}

function findForbidden(values) {
  const set = new Set(values);
  return FORBIDDEN_SIDEBAR_KEYS.filter((key) => set.has(key));
}

function runSidebarPolicyGuard() {
  const appShellPath = path.join(__dirname, '..', 'src', 'components', 'AppShell.tsx');
  if (!fs.existsSync(appShellPath)) {
    throw new Error(`[sidebar-policy-guard] AppShell not found at ${appShellPath}`);
  }

  const source = fs.readFileSync(appShellPath, 'utf8');

  const adminRawMatch = source.match(/const\s+adminNavDefinitions[\s\S]*?const\s+raw\s*=\s*\[([\s\S]*?)\]\s*\.filter/);
  if (!adminRawMatch) {
    throw new Error('[sidebar-policy-guard] Could not locate adminNavDefinitions raw array block.');
  }

  const adminRaw = adminRawMatch[1] || '';
  const forbiddenKeyPattern = new RegExp(`key\\s*:\\s*['\"](${FORBIDDEN_SIDEBAR_KEYS.join('|')})['\"]`, 'g');
  const rawViolations = new Set();
  let rawMatch = forbiddenKeyPattern.exec(adminRaw);
  while (rawMatch) {
    rawViolations.add(rawMatch[1]);
    rawMatch = forbiddenKeyPattern.exec(adminRaw);
  }

  const lockedSetMatch = source.match(/const\s+LOCKED_ADMIN_NAV_KEYS\s*=\s*new\s+Set\s*\(\s*\[([\s\S]*?)\]\s*\)/);
  if (!lockedSetMatch) {
    throw new Error('[sidebar-policy-guard] Could not locate LOCKED_ADMIN_NAV_KEYS declaration.');
  }
  const lockedSetValues = extractQuotedList(lockedSetMatch[1] || '');
  const lockedSetViolations = findForbidden(lockedSetValues);

  const lockedOrderMatch = source.match(/const\s+LOCKED_ADMIN_NAV_ORDER\s*=\s*Object\.freeze\(\s*\[([\s\S]*?)\]\s*\)/);
  if (!lockedOrderMatch) {
    throw new Error('[sidebar-policy-guard] Could not locate LOCKED_ADMIN_NAV_ORDER declaration.');
  }
  const lockedOrderValues = extractQuotedList(lockedOrderMatch[1] || '');
  const lockedOrderViolations = findForbidden(lockedOrderValues);

  const violations = [
    ...Array.from(rawViolations),
    ...lockedSetViolations,
    ...lockedOrderViolations,
  ];

  if (violations.length > 0) {
    const unique = Array.from(new Set(violations));
    throw new Error(
      `[sidebar-policy-guard] Forbidden sidebar keys detected: ${unique.join(', ')}. `
      + 'These pages must remain inside Operations Console only.'
    );
  }

  console.log('[sidebar-policy-guard] ✓ Locked sidebar policy verified (no forbidden admin sidebar keys).');
}

if (require.main === module) {
  try {
    runSidebarPolicyGuard();
  } catch (error) {
    console.error(String(error && error.message ? error.message : error));
    process.exit(1);
  }
}

module.exports = {
  runSidebarPolicyGuard,
};
