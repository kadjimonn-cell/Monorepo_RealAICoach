#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const targetFile = path.resolve(__dirname, '..', 'app', 'subscription', 'plans.tsx');
const source = fs.readFileSync(targetFile, 'utf-8');

const failures = [];

if (!(source.includes('data-testid="payment-fedapay-btn"') || source.includes("'payment-fedapay-btn'"))) {
  failures.push('Missing FedaPay payment option test id (payment-fedapay-btn).');
}

if (!source.includes('data-testid="payment-picker-scroll"')) {
  failures.push('Payment picker is missing scroll container test id (payment-picker-scroll).');
}

const pickerIdx = source.indexOf('data-testid="payment-method-picker"');
const pickerSlice = pickerIdx >= 0 ? source.slice(pickerIdx, pickerIdx + 5000) : source;
const maxHeightMatch = pickerSlice.match(/maxHeight:\s*'([0-9]+)%'/);
if (!maxHeightMatch) {
  failures.push('Could not find payment picker maxHeight declaration.');
} else {
  const maxHeightValue = Number(maxHeightMatch[1]);
  if (!Number.isFinite(maxHeightValue) || maxHeightValue < 80) {
    failures.push(`Payment picker maxHeight too small (${maxHeightMatch[1]}%). Expected >= 80%.`);
  }
}

const fedapayIndex = source.indexOf('data-testid="payment-fedapay-btn"');
const scrollIndex = source.indexOf('data-testid="payment-picker-scroll"');
if (fedapayIndex >= 0 && scrollIndex >= 0 && fedapayIndex < scrollIndex) {
  failures.push('FedaPay button appears before scroll container declaration.');
}

if (failures.length > 0) {
  console.error('[payment-picker-viewport-guard] FAILED');
  failures.forEach((f) => console.error(` - ${f}`));
  process.exit(1);
}

console.log('[payment-picker-viewport-guard] PASS');
