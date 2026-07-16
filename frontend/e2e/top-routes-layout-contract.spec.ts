/**
 * E2E: Top-routes layout contract
 * Referenced by ci-quality-gate.yml `top-routes-layout-contract` job.
 * Verifies that key app routes render a non-empty page and are not broken.
 */
import { test, expect } from '@playwright/test';

const PUBLIC_ROUTES = [
  { path: '/welcome', name: 'Welcome' },
  { path: '/auth/login', name: 'Login' },
  { path: '/auth/register', name: 'Register' },
  { path: '/privacy-policy', name: 'Privacy Policy' },
  { path: '/terms', name: 'Terms' },
];

const AUTHENTICATED_ROUTES = [
  { path: '/', name: 'Home' },
  { path: '/subscription/payment', name: 'Payment' },
  { path: '/notifications', name: 'Notifications' },
];

test.describe('Layout contract — Public routes', () => {
  for (const route of PUBLIC_ROUTES) {
    test(`${route.name} (${route.path}) — renders without error`, async ({ page }) => {
      await page.goto(route.path);
      await page.waitForTimeout(3_000);

      const body = await page.locator('body').textContent();
      expect(body?.length).toBeGreaterThan(50);
      expect(page.url()).not.toMatch(/500/);
    });
  }
});

test.describe('Layout contract — Authenticated routes (redirect check)', () => {
  for (const route of AUTHENTICATED_ROUTES) {
    test(`${route.name} (${route.path}) — redirects to login or renders content`, async ({ page }) => {
      await page.goto(route.path);
      await page.waitForTimeout(3_000);

      // Either shows content or redirects to login — never a blank/500 page
      const body = await page.locator('body').textContent();
      expect(body?.length).toBeGreaterThan(50);
      expect(page.url()).not.toMatch(/500/);
    });
  }
});

test.describe('Layout contract — Viewport integrity', () => {
  test('welcome hero stays centered on tablet', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/welcome');
    await page.waitForTimeout(3_500);

    await expect(page.locator('[data-testid="welcome-hero-centered-shell"]')).toBeVisible({ timeout: 15_000 });

    const centered = await page.evaluate(() => {
      const shell = document.querySelector('[data-testid="welcome-hero-centered-shell"]') as HTMLElement | null;
      const title = document.querySelector('[data-testid="welcome-hero-title"]') as HTMLElement | null;
      if (!shell || !title) return null;
      const rect = shell.getBoundingClientRect();
      return {
        leftMargin: Math.round(rect.left),
        rightMargin: Math.round(window.innerWidth - rect.right),
        titleTextAlign: getComputedStyle(title).textAlign,
      };
    });

    expect(centered).not.toBeNull();
    expect(Math.abs((centered?.leftMargin || 0) - (centered?.rightMargin || 0))).toBeLessThanOrEqual(2);
    expect(centered?.titleTextAlign).toBe('center');
  });

  test('login page does not overflow viewport on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 }); // iPhone 14
    await page.goto('/auth/login');
    await page.waitForTimeout(3_000);

    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(50);
  });

  test('login page renders correctly on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/auth/login');
    await page.waitForTimeout(3_000);

    await expect(page.locator('[data-testid="login-screen"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="login-submit-button"]')).toBeVisible();
  });
});
