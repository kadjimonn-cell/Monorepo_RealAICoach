import { test, expect } from '@playwright/test';

test.describe('Fitness Planner Pro @component', () => {
  test('loads fitness workspace and key controls', async ({ page }) => {
    await page.goto('/features/fitness');
    await page.waitForTimeout(2500);

    // Verify root element loads
    await expect(page.locator('text=Fitness Planner Pro')).toBeVisible();
    
    // Verify tabs are present
    await expect(page.locator('[data-testid="fitness-tab-plans"]')).toBeVisible();
    await expect(page.locator('[data-testid="fitness-tab-progress"]')).toBeVisible();
    await expect(page.locator('[data-testid="fitness-tab-exercises"]')).toBeVisible();
    
    // Verify create workout section
    await expect(page.locator('[data-testid="fitness-generate-workout-button"]')).toBeVisible();
  });

  test('navigates between tabs without crashing', async ({ page }) => {
    await page.goto('/features/fitness');
    await page.waitForTimeout(2500);

    // Start on workout plans tab
    await expect(page.locator('text=Fitness Planner Pro')).toBeVisible();
    
    // Click progress tab
    await page.click('[data-testid="fitness-tab-progress"]');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Fitness Planner Pro')).toBeVisible();
    
    // Click exercises tab
    await page.click('[data-testid="fitness-tab-exercises"]');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Fitness Planner Pro')).toBeVisible();
    
    // Return to workout plans
    await page.click('[data-testid="fitness-tab-plans"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="fitness-generate-workout-button"]')).toBeVisible();
  });
});
