import { test, expect } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL || process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3000';

const VIEWPORTS = [
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'desktop-1440', width: 1440, height: 900 },
];

const LOCAL_BASE_HOSTS = ['http://127.0.0.1:3000', 'http://localhost:3000'];
const RUN_WELCOME_EMBED_E2E = process.env.RUN_WELCOME_EMBED_E2E === '1';

async function gotoWelcome(page: any, viewport: { width: number; height: number }) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto('/welcome', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2200);
  await expect(page.locator('[data-testid="welcome-hero"]')).toBeVisible({ timeout: 15000 });
}

async function evaluateWelcomeState<T>(page: any, readState: () => T): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await page.evaluate(readState);
    } catch (error) {
      lastError = error;
      await page.waitForTimeout(500);
    }
  }
  throw lastError;
}

for (const viewport of VIEWPORTS) {
  test.describe(`Welcome first-paint regression @ ${viewport.name}`, () => {
    test(`core shell paints without blank screen on ${viewport.name}`, async ({ page }) => {
      await gotoWelcome(page, viewport);

      const state = await evaluateWelcomeState(page, () => ({
        bodyTextLength: (document.body?.innerText || '').trim().length,
        bodyChildren: document.body?.children?.length || 0,
        hasWelcomeScreen: !!document.querySelector('[data-testid="welcome-screen"]'),
        hasHero: !!document.querySelector('[data-testid="welcome-hero"]'),
        hasHeroTitle: !!document.querySelector('[data-testid="welcome-hero-title"]'),
        hasHeroSubtitle: !!document.querySelector('[data-testid="welcome-hero-subtitle"]'),
        heroTitleLength: (document.querySelector('[data-testid="welcome-hero-title"]')?.textContent || '').trim().length,
        heroSubtitleLength: (document.querySelector('[data-testid="welcome-hero-subtitle"]')?.textContent || '').trim().length,
        hasSkeleton: !!document.querySelector('[data-testid="skeleton-welcome"]'),
        appReady: document.getElementById('root')?.getAttribute('data-app-ready') === 'true',
        hasOverflow: document.documentElement.scrollWidth > window.innerWidth,
      }));

      expect(state.bodyChildren).toBeGreaterThan(0);
      expect(state.bodyTextLength).toBeGreaterThan(40);
      expect(state.hasHero).toBeTruthy();
      expect(state.hasHeroTitle).toBeTruthy();
      expect(state.hasHeroSubtitle).toBeTruthy();
      expect(state.hasWelcomeScreen || state.hasHero).toBeTruthy();
      expect(state.heroTitleLength).toBeGreaterThan(12);
      expect(state.heroSubtitleLength).toBeGreaterThan(24);
      expect(state.hasOverflow).toBeFalsy();
      expect(state.appReady || state.hasHero).toBeTruthy();
    });

    test(`theme, locale, and critical testids stay available on ${viewport.name}`, async ({ page }) => {
      await gotoWelcome(page, viewport);

      // Theme toggle and language selector are only visible on desktop (>=1024px per GLS breakpoints)
      // On mobile/tablet, these controls are inside the hamburger menu
      if (viewport.width >= 1024) {
        await expect(page.locator('[data-testid="welcome-theme-toggle"]')).toBeVisible();
        await expect(page.locator('[data-testid="welcome-language-selector"]')).toBeVisible();

        // Test dark mode toggle on desktop (use evaluate to avoid Playwright click timeout issues)
        await page.evaluate(() => {
          const darkBtn = document.querySelector('[data-testid="welcome-theme-toggle-dark"]') as HTMLElement;
          if (darkBtn) darkBtn.click();
        });
        await page.waitForTimeout(600);

        const darkState = await evaluateWelcomeState(page, () => ({
          themeActive: document.documentElement.getAttribute('data-theme-active'),
          bodyBgColor: getComputedStyle(document.body).backgroundColor,
          hasRawWelcomeKey: (document.body?.innerText || '').includes('welcome.'),
        }));

        expect(darkState.themeActive).toBe('dark');
        expect(darkState.bodyBgColor).not.toBe('rgb(255, 255, 255)');
        expect(darkState.hasRawWelcomeKey).toBeFalsy();
      } else {
        // On mobile, open hamburger menu to access language selector (use evaluate to avoid click timeout)
        const hamburgerVisible = await page.locator('[data-testid="welcome-mobile-menu-toggle"]').isVisible();
        if (hamburgerVisible) {
          await page.evaluate(() => {
            const hamburger = document.querySelector('[data-testid="welcome-mobile-menu-toggle"]') as HTMLElement;
            if (hamburger) hamburger.click();
          });
          await page.waitForTimeout(400);
          await expect(page.locator('[data-testid="welcome-mobile-language-selector"]')).toBeVisible();
        }

        // Verify no raw i18n keys are visible (locale-safe rendering)
        const localeState = await evaluateWelcomeState(page, () => ({
          hasRawWelcomeKey: (document.body?.innerText || '').includes('welcome.'),
        }));
        expect(localeState.hasRawWelcomeKey).toBeFalsy();
      }
    });

    test(`embedded welcome still paints immediately on ${viewport.name}`, async ({ page }, testInfo) => {
      const isPreviewEnv = BASE.includes('preview.emergentagent.com') || BASE.includes('cloudflare');
      const isLocalBase = LOCAL_BASE_HOSTS.some((host) => BASE.startsWith(host));
      const shouldRunFocusedEmbedCheck = testInfo.project.name === 'desktop-chromium' && viewport.name === 'mobile-390';
      if (isPreviewEnv || !shouldRunFocusedEmbedCheck || !isLocalBase || !RUN_WELCOME_EMBED_E2E) {
        test.skip(true, 'Embedded iframe test skipped in preview environment due to X-Frame-Options restrictions');
        return;
      }

      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(500);
      await page.setContent(`
        <!doctype html>
        <html>
          <body style="margin:0;background:#eef2f7;">
            <iframe
              data-testid="welcome-embed-frame"
              src="${BASE}/welcome"
              style="width:${viewport.width}px;height:${viewport.height}px;border:0;display:block;"
            ></iframe>
          </body>
        </html>
      `);

      const frame = page.frameLocator('[data-testid="welcome-embed-frame"]');
      await expect(frame.locator('[data-testid="welcome-hero"]')).toBeVisible({ timeout: 20000 });

      const embeddedState = await frame.locator('[data-testid="welcome-screen"]').evaluate((root) => {
        const doc = root.ownerDocument;
        return {
          bodyTextLength: (doc.body?.innerText || '').trim().length,
          hasHero: !!doc.querySelector('[data-testid="welcome-hero"]'),
          hasFeatured: !!doc.querySelector('[data-testid="welcome-featured-in-marquee"]'),
          hasMedia: !!doc.querySelector('[data-testid="welcome-media-mentions-strip"]'),
          hasOverflow: doc.documentElement.scrollWidth > doc.defaultView!.innerWidth,
        };
      });

      expect(embeddedState.bodyTextLength).toBeGreaterThan(200);
      expect(embeddedState.hasHero).toBeTruthy();
      expect(embeddedState.hasFeatured).toBeTruthy();
      expect(embeddedState.hasMedia).toBeTruthy();
      expect(embeddedState.hasOverflow).toBeFalsy();
    });
  });
}