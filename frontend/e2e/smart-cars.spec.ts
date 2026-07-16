import { test, expect } from '@playwright/test';

test.describe('Mobility Assistant @component', () => {
  test('loads smart-cars route and primary shell', async ({ page }) => {
    await page.goto('/features/smart-cars');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="feature-layout-title-smart-cars"]')).toBeVisible();
    await expect(page.locator('[data-testid="feature-actions-bar"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobility-tab-search"]')).toBeVisible();
  });

  test('core action tabs are accessible', async ({ page }) => {
    await page.goto('/features/smart-cars');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="mobility-tab-tradein"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobility-tab-finance"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobility-tab-trip"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobility-tab-insurance"]')).toBeVisible();
  });
});
