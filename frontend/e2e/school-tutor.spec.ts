import { test, expect } from '@playwright/test';

test.describe('Learning Coach @component', () => {
  test('loads learning coach workspace and key controls', async ({ page }) => {
    await page.goto('/features/school-tutor');
    await page.waitForTimeout(2500);

    // Verify root element loads
    await expect(page.locator('text=Learning Coach')).toBeVisible();
    
    // Verify tabs are present
    await expect(page.locator('[data-testid="learning-coach-tab-curricula"]')).toBeVisible();
    await expect(page.locator('[data-testid="learning-coach-tab-profile"]')).toBeVisible();
    await expect(page.locator('[data-testid="learning-coach-tab-progress"]')).toBeVisible();
    await expect(page.locator('[data-testid="learning-coach-tab-streaks"]')).toBeVisible();
    
    // Verify create curriculum section
    await expect(page.locator('[data-testid="learning-coach-create-curriculum-title"]')).toBeVisible();
  });

  test('navigates between tabs without crashing', async ({ page }) => {
    await page.goto('/features/school-tutor');
    await page.waitForTimeout(2500);

    // Start on curricula tab
    await expect(page.locator('[data-testid="learning-coach-create-curriculum-title"]')).toBeVisible();
    
    // Click profile tab
    await page.click('[data-testid="learning-coach-tab-profile"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="learning-coach-profile-title"]')).toBeVisible();
    
    // Click progress tab
    await page.click('[data-testid="learning-coach-tab-progress"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="learning-coach-progress-title"]')).toBeVisible();
    
    // Click streaks tab
    await page.click('[data-testid="learning-coach-tab-streaks"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="learning-coach-streaks-title"]')).toBeVisible();
    
    // Return to curricula tab
    await page.click('[data-testid="learning-coach-tab-curricula"]');
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="learning-coach-create-curriculum-title"]')).toBeVisible();
  });
});
