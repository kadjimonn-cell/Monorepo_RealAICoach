/**
 * i18n v2 regression — every footer link and section in `siteConfig.ts`
 * MUST carry an `i18nKey`, AND every key MUST exist in `en.ts` and `fr.ts`.
 *
 * Triggered by Apr 25, 2026 user-reported mixed-language footer where the
 * French preview rendered "COMPANY", "Help Center", "Privacy Policy",
 * "Cookie Policy" et al. in English because the static dictionary had
 * zero coverage and the runtime DOM `__txEngine` raced against React.
 */
import { FOOTER_LINKS, NAV_LINKS } from '../config/siteConfig';
import enLocale from '../i18n/locales/en';
import frLocale from '../i18n/locales/fr';

describe('i18n v2 — siteConfig coverage guard', () => {
  it('every NAV_LINK has an i18nKey', () => {
    for (const link of NAV_LINKS) {
      expect(link.i18nKey).toBeTruthy();
      expect(typeof link.i18nKey).toBe('string');
    }
  });

  it('every FOOTER section has an i18nKey AND every link has an i18nKey', () => {
    for (const section of Object.values(FOOTER_LINKS)) {
      expect(section.i18nKey).toBeTruthy();
      for (const link of section.links) {
        expect(link.i18nKey).toBeTruthy();
      }
    }
  });

  it('every i18nKey resolves to a non-empty value in en.ts', () => {
    const missing: string[] = [];
    for (const link of NAV_LINKS) {
      if (link.i18nKey && !enLocale[link.i18nKey]) missing.push(link.i18nKey);
    }
    for (const section of Object.values(FOOTER_LINKS)) {
      if (section.i18nKey && !enLocale[section.i18nKey]) missing.push(section.i18nKey);
      for (const link of section.links) {
        if (link.i18nKey && !enLocale[link.i18nKey]) missing.push(link.i18nKey);
      }
    }
    expect(missing).toEqual([]);
  });

  it('every i18nKey resolves to a non-empty value in fr.ts (no mixed-language render)', () => {
    const missing: string[] = [];
    for (const link of NAV_LINKS) {
      if (link.i18nKey && !frLocale[link.i18nKey]) missing.push(link.i18nKey);
    }
    for (const section of Object.values(FOOTER_LINKS)) {
      if (section.i18nKey && !frLocale[section.i18nKey]) missing.push(section.i18nKey);
      for (const link of section.links) {
        if (link.i18nKey && !frLocale[link.i18nKey]) missing.push(link.i18nKey);
      }
    }
    expect(missing).toEqual([]);
  });

  it('previously-broken footer strings are now translated to French', () => {
    // Spot-check the exact strings from the user's screenshot
    expect(frLocale['footer.section.company']).not.toBe('Company');
    expect(frLocale['footer.link.helpCenter']).not.toBe('Help Center');
    expect(frLocale['footer.link.privacyPolicy']).not.toBe('Privacy Policy');
    expect(frLocale['footer.link.termsOfService']).not.toBe('Terms of Service');
    expect(frLocale['footer.link.cookiePolicy']).not.toBe('Cookie Policy');
    expect(frLocale['footer.link.contentLibrary']).not.toBe('Content Library');
    expect(frLocale['footer.link.dailyBriefing']).not.toBe('Daily Briefing');
    expect(frLocale['footer.link.leaderboard']).not.toBe('Leaderboard');
  });
});
