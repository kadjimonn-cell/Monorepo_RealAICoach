import { test, expect } from '@playwright/test';

test.describe('Public visitor paywall routing @routing', () => {
  test('mini apps mobile money alias sends visitors to register', async ({ page }) => {
    await page.goto('/mini-apps/mobile-money', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2500);

    await expect(page).toHaveURL(/\/auth\/register/);
    await expect(page).toHaveURL(/source=feature-entry-mobile-money/);
    await expect(page).toHaveURL(/return_to=%2Fmini-apps%2Fmobile-money/);
  });
});