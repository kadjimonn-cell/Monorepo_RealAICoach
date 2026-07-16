import { test, expect } from '@playwright/test';

test.describe('Property Decision Advisor @component', () => {
  test('loads buy-smart-home route and shell tabs', async ({ page }) => {
    await page.goto('/features/buy-smart-home');
    await page.waitForTimeout(2500);

    await expect(page.locator('text=Property Decision Advisor')).toBeVisible();
    await expect(page.locator('[data-testid="buy-smart-home-tab-search"]')).toBeVisible();
    await expect(page.locator('[data-testid="buy-smart-home-tab-map"]')).toBeVisible();
    await expect(page.locator('[data-testid="buy-smart-home-tab-valuation"]')).toBeVisible();
  });

  test('search and valuation controls are visible', async ({ page }) => {
    await page.goto('/features/buy-smart-home');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="buy-smart-home-search-location"]')).toBeVisible();
    await expect(page.locator('[data-testid="buy-smart-home-search-button"]')).toBeVisible();

    await page.click('[data-testid="buy-smart-home-tab-valuation"]');
    await page.waitForTimeout(600);
    await expect(page.locator('[data-testid="buy-smart-home-valuation-address"]')).toBeVisible();
    await expect(page.locator('[data-testid="buy-smart-home-valuation-button"]')).toBeVisible();
  });
});
