import { test, expect } from '@playwright/test';

test.describe('Relationship Coach @component', () => {
  test('loads workspace and tab shell', async ({ page }) => {
    await page.goto('/features/ai-found-love');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="rc-workspace"]')).toBeVisible();
    await expect(page.locator('[data-testid="rc-tab-dashboard"]')).toBeVisible();
    await expect(page.locator('[data-testid="rc-tab-advisor"]')).toBeVisible();
    await expect(page.locator('[data-testid="rc-tab-important-dates"]')).toBeVisible();
    await expect(page.locator('[data-testid="rc-tab-analytics"]')).toBeVisible();
  });

  test('navigates key tabs and shows expected panels', async ({ page }) => {
    await page.goto('/features/ai-found-love');
    await page.waitForTimeout(2500);

    await page.click('[data-testid="rc-tab-advisor"]');
    await page.waitForTimeout(600);
    await expect(page.locator('[data-testid="rc-advice-submit"]')).toBeVisible();

    await page.click('[data-testid="rc-tab-important-dates"]');
    await page.waitForTimeout(600);
    await expect(page.locator('[data-testid="rc-add-date-btn"]')).toBeVisible();

    await page.click('[data-testid="rc-tab-conv-lab"]');
    await page.waitForTimeout(600);
    await expect(page.locator('[data-testid="rc-conv-submit"]')).toBeVisible();
  });
});
