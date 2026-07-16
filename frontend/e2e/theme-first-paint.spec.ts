import { test, expect } from '@playwright/test';

const FIRST_PAINT_READY_TIMEOUT_MS = 45_000;

async function seedThemePreference(page, themeMode) {
  await page.addInitScript((mode) => {
    window.localStorage.setItem('app_theme', JSON.stringify({ themeMode: mode, darkMode: mode === 'dark' }));
  }, themeMode);
}

async function waitForFirstPaintThemeTokens(page, expectedTheme) {
  await page.goto('/auth/login', { waitUntil: 'domcontentloaded' });

  await page.waitForFunction(
    (theme) => {
      const root = document.documentElement;
      if (!root) return false;
      if (window.location.pathname !== '/auth/login') return false;
      if (root.getAttribute('data-theme-active') !== theme) return false;

      const styles = window.getComputedStyle(root);
      const requiredTokens = ['--app-bg', '--app-surface', '--app-primary'];
      return requiredTokens.every((token) => styles.getPropertyValue(token).trim() !== '');
    },
    expectedTheme,
    { timeout: FIRST_PAINT_READY_TIMEOUT_MS },
  );
}

async function snapshotThemeTokens(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const styles = getComputedStyle(root);
    return {
      themeActive: root.getAttribute('data-theme-active'),
      appBg: styles.getPropertyValue('--app-bg').trim(),
      appSurface: styles.getPropertyValue('--app-surface').trim(),
      appPrimary: styles.getPropertyValue('--app-primary').trim(),
    };
  });
}

test.describe('Theme first-paint token bootstrap', () => {
  test('dark mode tokens are present immediately after first paint @component', async ({ page }) => {
    await seedThemePreference(page, 'dark');
    await waitForFirstPaintThemeTokens(page, 'dark');

    const snapshot = await snapshotThemeTokens(page);

    expect(snapshot.themeActive).toBe('dark');
    expect(snapshot.appBg).not.toBe('');
    expect(snapshot.appSurface).not.toBe('');
    expect(snapshot.appPrimary).not.toBe('');
  });

  test('light mode tokens are present immediately after first paint @component', async ({ page }) => {
    await seedThemePreference(page, 'light');
    await waitForFirstPaintThemeTokens(page, 'light');

    const snapshot = await snapshotThemeTokens(page);

    expect(snapshot.themeActive).toBe('light');
    expect(snapshot.appBg).not.toBe('');
    expect(snapshot.appSurface).not.toBe('');
    expect(snapshot.appPrimary).not.toBe('');
  });
});
