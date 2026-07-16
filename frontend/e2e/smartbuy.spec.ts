import { test, expect } from '@playwright/test';

test.describe('Smart Shopping Advisor @component', () => {
  test('loads smartbuy workspace and key modules', async ({ page }) => {
    await page.goto('/features/smartbuy');
    await page.waitForTimeout(2500);

    await expect(page.locator('text=Smart Shopping Advisor')).toBeVisible();
    await expect(page.locator('[data-testid="smart-shopping-root"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-shopping-tab-wishlists"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-shopping-tab-budgets"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-shopping-tab-ai"]')).toBeVisible();
  });

  test('primary actions are visible', async ({ page }) => {
    await page.goto('/features/smartbuy');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="smart-shopping-create-wishlist-button"]')).toBeVisible();

    await page.click('[data-testid="smart-shopping-tab-budgets"]');
    await page.waitForTimeout(600);
    await expect(page.locator('[data-testid="smart-shopping-create-budget-button"]')).toBeVisible();

    await page.click('[data-testid="smart-shopping-tab-ai"]');
    await page.waitForTimeout(600);
    await expect(page.locator('[data-testid="smart-shopping-ai-run-button"]')).toBeVisible();
  });
});
