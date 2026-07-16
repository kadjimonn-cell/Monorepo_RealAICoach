#!/usr/bin/env node
/* eslint-env node */

/**
 * Footer Route Contract Gate (STRICT)
 *
 * Prevents regressions where critical footer links silently drift away from
 * canonical public routes.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(process.cwd());
const SITE_CONFIG_PATH = path.join(ROOT, 'src', 'config', 'siteConfig.ts');
const FOOTER_COMPONENT_PATH = path.join(ROOT, 'src', 'components', 'Footer.tsx');

const CRITICAL_CONTRACTS = [
  { key: 'footer.link.pricing', href: '/pricing', requirePublic: true },
  { key: 'footer.link.aboutUs', href: '/about-us', requirePublic: true },
  { key: 'footer.link.contact', href: '/contact', requirePublic: true },
  { key: 'footer.link.careers', href: '/careers', requirePublic: true },
  { key: 'footer.link.blog', href: '/blog', requirePublic: true },
];

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function readFile(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`file not found: ${filePath}`);
  }
  return fs.readFileSync(filePath, 'utf8');
}

function run() {
  const errors = [];
  const siteConfig = readFile(SITE_CONFIG_PATH);
  const footerComponent = readFile(FOOTER_COMPONENT_PATH);

  for (const contract of CRITICAL_CONTRACTS) {
    const key = escapeRegex(contract.key);
    const href = escapeRegex(contract.href);

    const entryRegex = new RegExp(
      `i18nKey\\s*:\\s*['\"]${key}['\"][\\s\\S]{0,220}?href\\s*:\\s*['\"]${href}['\"]`,
      'm',
    );
    if (!entryRegex.test(siteConfig)) {
      errors.push(`siteConfig contract missing/mismatched: ${contract.key} -> ${contract.href}`);
      continue;
    }

    if (contract.requirePublic) {
      const publicRegex = new RegExp(
        `i18nKey\\s*:\\s*['\"]${key}['\"][\\s\\S]{0,260}?public\\s*:\\s*true`,
        'm',
      );
      if (!publicRegex.test(siteConfig)) {
        errors.push(`siteConfig contract requires public:true: ${contract.key}`);
      }
    }
  }

  if (/router\.(push|replace)\(\s*['\"]\/welcome\?section=pricing['\"]\s*\)/m.test(footerComponent)) {
    errors.push('Footer must not hard-route Pricing to /welcome?section=pricing');
  }

  if (!/resolveVisitorCtaPath\(\s*['\"]\/pricing['\"]\s*,/m.test(footerComponent)) {
    errors.push('Footer Pricing branch must resolve canonical /pricing target through visitor CTA policy');
  }

  if (!/fallbackPath\s*:\s*['\"]\/pricing['\"]/m.test(footerComponent)) {
    errors.push('Footer Pricing branch must keep fallbackPath set to /pricing');
  }

  if (errors.length > 0) {
    console.error('\n[footer-route-contract-gate] FAILED');
    errors.forEach((e) => console.error(` - ${e}`));
    process.exit(1);
  }

  console.log('[footer-route-contract-gate] PASS');
  console.log(` - Critical contracts checked: ${CRITICAL_CONTRACTS.length}`);
}

run();
