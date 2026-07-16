#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const checks = [
  {
    label: 'EmployerPortalPanel responsive grid',
    file: path.resolve(__dirname, '..', 'src', 'components', 'admin', 'EmployerPortalPanel.tsx'),
    requiredSnippets: [
      'ResponsiveDataGrid',
      'compactBreakpoint={980}',
      'desktopTestId="employer-applications-desktop-table"',
      'compactTestId="employer-applications-compact-list"',
    ],
  },
  {
    label: 'PaymentBillingPanel responsive transactions grid',
    file: path.resolve(__dirname, '..', 'src', 'components', 'admin', 'PaymentBillingPanel.tsx'),
    requiredSnippets: [
      'ResponsiveDataGrid',
      'compactBreakpoint={980}',
      'desktopTestId="payment-billing-transactions-desktop-table"',
      'compactTestId="payment-billing-transactions-compact-list"',
    ],
  },
  {
    label: 'PlatformHealthPanel responsive history grid',
    file: path.resolve(__dirname, '..', 'src', 'components', 'admin', 'PlatformHealthPanel.tsx'),
    requiredSnippets: [
      'ResponsiveDataGrid',
      'compactBreakpoint={980}',
      'desktopTestId="scan-history-desktop-table"',
      'compactTestId="scan-history-compact-list"',
    ],
  },
];

const failures = [];

for (const check of checks) {
  if (!fs.existsSync(check.file)) {
    failures.push(`${check.label}: missing file ${check.file}`);
    continue;
  }
  const source = fs.readFileSync(check.file, 'utf8');
  for (const snippet of check.requiredSnippets) {
    if (!source.includes(snippet)) {
      failures.push(`${check.label}: missing snippet -> ${snippet}`);
    }
  }
}

if (failures.length > 0) {
  console.error('[admin-dashboard-viewport-guard] FAILED');
  failures.forEach((f) => console.error(` - ${f}`));
  process.exit(1);
}

console.log('[admin-dashboard-viewport-guard] PASS');
