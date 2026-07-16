import { test, expect } from '@playwright/test';

test.describe('Decision Coach @component', () => {
  test('loads decision coach workspace and key controls', async ({ page }) => {
    await page.goto('/features/ai-cognitive');
    await page.waitForTimeout(2500);

    // Verify tabs are present
    await expect(page.locator('[data-testid="decision-coach-tabs"]')).toBeVisible();
    await expect(page.locator('[data-testid="decision-coach-tab-decisions"]')).toBeVisible();
    await expect(page.locator('[data-testid="decision-coach-tab-templates"]')).toBeVisible();
    await expect(page.locator('[data-testid="decision-coach-tab-analytics"]')).toBeVisible();
    
    // Verify main content area loads
    await expect(page.locator('[data-testid="decision-coach-content"]')).toBeVisible();
    
    // Verify usage stats display
    await expect(page.locator('[data-testid="decision-coach-usage-stats"]')).toBeVisible();
    
    // Verify create button is visible
    await expect(page.locator('[data-testid="decision-coach-create-button"]')).toBeVisible();
  });

  test('navigates between tabs without crashing', async ({ page }) => {
    await page.goto('/features/ai-cognitive');
    await page.waitForTimeout(2500);

    // Start on decisions tab
    await expect(page.locator('[data-testid="decision-coach-tab-decisions"]')).toBeVisible();
    
    // Click templates tab
    await page.click('[data-testid="decision-coach-tab-templates"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="decision-coach-content"]')).toBeVisible();
    
    // Click analytics tab
    await page.click('[data-testid="decision-coach-tab-analytics"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="decision-coach-content"]')).toBeVisible();
    
    // Return to decisions tab
    await page.click('[data-testid="decision-coach-tab-decisions"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="decision-coach-create-button"]')).toBeVisible();
  });
});
