#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const MANIFEST_PATH = path.join(__dirname, 'brand-exclusion-manifest.json');
const REPORT_DIR = path.join(ROOT, '.quality');
const CANARY_REPORT_PATH = path.join(REPORT_DIR, 'brand_exclusion_canary.json');

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function run() {
  const manifest = readJson(MANIFEST_PATH);
  const welcomePath = path.join(ROOT, 'app', 'welcome.tsx');
  const footerPath = path.join(ROOT, 'src', 'components', 'Footer.tsx');
  const termsPath = path.join(ROOT, 'app', 'terms.tsx');
  const privacyPath = path.join(ROOT, 'app', 'privacy-policy.tsx');
  const emailTemplatesPath = path.join(ROOT, 'src', 'components', 'admin', 'email-templates', 'TemplatesView.tsx');
  const htmlPath = path.join(ROOT, 'app', '+html.tsx');
  const welcomeText = fs.readFileSync(welcomePath, 'utf8');
  const footerText = fs.readFileSync(footerPath, 'utf8');
  const termsText = fs.readFileSync(termsPath, 'utf8');
  const privacyText = fs.readFileSync(privacyPath, 'utf8');
  const emailTemplatesText = fs.readFileSync(emailTemplatesPath, 'utf8');
  const htmlText = fs.readFileSync(htmlPath, 'utf8');

  const languages = Array.isArray(manifest.canary_languages) ? manifest.canary_languages : ['en'];
  const checks = languages.map((lang) => {
    const hasBrandSelector = welcomeText.includes('welcome-brand-name');
    const usesPlatformBrand = welcomeText.includes('PLATFORM_BRAND');
    const highRiskSurfacesHaveCanonicalBrand = footerText.includes('RealAICoach')
      && termsText.includes('RealAICoach')
      && privacyText.includes('RealAICoach');
    const highRiskSurfacesAvoidForbiddenFragmentComposition = !/autofix\.precision12\.real/.test(
      `${footerText}\n${termsText}\n${privacyText}\n${emailTemplatesText}`,
    ) && !/autofix\.precision12\.coach/.test(
      `${footerText}\n${termsText}\n${privacyText}\n${emailTemplatesText}`,
    );
    const hasRegexGuard = htmlText.includes('\\\\bRealAICoach\\\\b')
      && htmlText.includes('\\\\bReal\\\\s*AI\\\\s*Coach\\\\b')
      && htmlText.includes('\\\\bReal-?AI-?Coach\\\\b');
    const pass = hasBrandSelector
      && usesPlatformBrand
      && hasRegexGuard
      && highRiskSurfacesHaveCanonicalBrand
      && highRiskSurfacesAvoidForbiddenFragmentComposition;
    return {
      language: lang,
      pass,
      checks: {
        has_brand_selector: hasBrandSelector,
        uses_platform_brand_constant: usesPlatformBrand,
        has_html_brand_regex_guards: hasRegexGuard,
        high_risk_surfaces_have_canonical_brand: highRiskSurfacesHaveCanonicalBrand,
        high_risk_surfaces_avoid_forbidden_fragment_composition: highRiskSurfacesAvoidForbiddenFragmentComposition,
      },
    };
  });

  if (!fs.existsSync(REPORT_DIR)) fs.mkdirSync(REPORT_DIR, { recursive: true });
  const payload = {
    generated_at: new Date().toISOString(),
    route: '/welcome',
    platform_brand: manifest.platform_brand,
    languages,
    checks,
    pass: checks.every((c) => c.pass),
  };
  fs.writeFileSync(CANARY_REPORT_PATH, JSON.stringify(payload, null, 2));

  if (!payload.pass) {
    console.error('[brand-exclusion-canary] FAILED');
    console.error(` - Report: ${CANARY_REPORT_PATH}`);
    process.exit(1);
  }

  console.log('[brand-exclusion-canary] PASS');
  console.log(` - Report: ${CANARY_REPORT_PATH}`);
}

run();
