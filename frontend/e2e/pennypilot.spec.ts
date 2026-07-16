import { test, expect } from '@playwright/test';

test.describe('Money Strategy Hub @component', () => {
  test('loads pennypilot workspace and key modules', async ({ page }) => {
    await page.goto('/features/pennypilot');
    await page.waitForTimeout(2500);

    await expect(page.locator('text=Money Strategy Hub')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-kpi-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-profile-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-budget-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-expense-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-advisor-card"]')).toBeVisible();
  });

  test('core actions are visible and interactive', async ({ page }) => {
    await page.goto('/features/pennypilot');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="money-strategy-profile-save-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-budget-create-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-expense-create-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-goal-create-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="money-strategy-advisor-run-button"]')).toBeVisible();
  });
});
