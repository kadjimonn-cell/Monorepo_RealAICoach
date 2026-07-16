import { test, expect } from '@playwright/test';

test.describe('Health Guide @component', () => {
  test('loads health guide workspace and key controls', async ({ page }) => {
    await page.goto('/features/medimate');
    await page.waitForTimeout(2500);

    // Verify page title loads
    await expect(page.locator('text=Health Guide')).toBeVisible();
    
    // Verify tabs are present
    await expect(page.locator('[data-testid="health-guide-tab-profile"]')).toBeVisible();
    await expect(page.locator('[data-testid="health-guide-tab-symptoms"]')).toBeVisible();
    await expect(page.locator('[data-testid="health-guide-tab-medications"]')).toBeVisible();
    await expect(page.locator('[data-testid="health-guide-tab-wearables"]')).toBeVisible();
    await expect(page.locator('[data-testid="health-guide-tab-insights"]')).toBeVisible();
  });

  test('navigates between health tabs without crashing', async ({ page }) => {
    await page.goto('/features/medimate');
    await page.waitForTimeout(2500);

    // Start on profile tab
    await expect(page.locator('[data-testid="health-guide-tab-profile"]')).toBeVisible();
    
    // Click symptoms tab
    await page.click('[data-testid="health-guide-tab-symptoms"]');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Health Guide')).toBeVisible();
    
    // Click medications tab
    await page.click('[data-testid="health-guide-tab-medications"]');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Health Guide')).toBeVisible();
    
    // Click wearables tab
    await page.click('[data-testid="health-guide-tab-wearables"]');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Health Guide')).toBeVisible();
    
    // Click insights tab
    await page.click('[data-testid="health-guide-tab-insights"]');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Health Guide')).toBeVisible();
    
    // Return to profile tab
    await page.click('[data-testid="health-guide-tab-profile"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="health-guide-tab-profile"]')).toBeVisible();
  });
});
