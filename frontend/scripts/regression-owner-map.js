#!/usr/bin/env node
/* eslint-env node */

const OWNER_RULES = [
  { match: (file) => file.startsWith('app/careers/'), owner: '@careers-frontend' },
  { match: (file) => file.startsWith('src/components/travel-visa/'), owner: '@travel-visa-frontend' },
  { match: (file) => file.startsWith('app/executive-dashboard'), owner: '@executive-frontend' },
  { match: (file) => file.startsWith('app/features/'), owner: '@feature-experiences' },
  { match: (file) => file.startsWith('src/components/'), owner: '@frontend-components' },
];

function ownerFromFile(filePath = '') {
  const file = String(filePath || '').trim();
  const hit = OWNER_RULES.find((rule) => rule.match(file));
  return hit ? hit.owner : '@frontend-platform';
}

function ownerFromI18nKey(key = '') {
  const k = String(key || '').trim().toLowerCase();
  if (k.startsWith('careertracker.') || k.includes('careers')) return '@careers-frontend';
  if (k.includes('travelvisa') || k.startsWith('tv.')) return '@travel-visa-frontend';
  if (k.includes('executive')) return '@executive-frontend';
  if (k.startsWith('i18n.route.features.') || k.includes('feature')) return '@feature-experiences';
  return '@frontend-platform';
}

function summarize(entries = [], resolver = ownerFromFile) {
  const summaryMap = new Map();
  for (const entry of entries) {
    const owner = resolver(entry);
    if (!summaryMap.has(owner)) {
      summaryMap.set(owner, { owner, count: 0, samples: [] });
    }
    const row = summaryMap.get(owner);
    row.count += 1;
    if (row.samples.length < 5) row.samples.push(String(entry));
  }
  return Array.from(summaryMap.values()).sort((a, b) => b.count - a.count);
}

function signaturesToFiles(signatures = []) {
  return signatures
    .map((sig) => String(sig || '').split('::')[0])
    .filter(Boolean);
}

function printOwnerSummary(tag, summary = []) {
  if (!summary.length) return;
  console.error(`[${tag}] Owner mapping for regressions:`);
  for (const row of summary) {
    console.error(` - ${row.owner}: ${row.count}`);
    row.samples.forEach((sample) => console.error(`    • ${sample}`));
  }
}

module.exports = {
  ownerFromFile,
  ownerFromI18nKey,
  summarize,
  signaturesToFiles,
  printOwnerSummary,
};
