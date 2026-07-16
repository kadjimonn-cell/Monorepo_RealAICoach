import { test, expect } from '@playwright/test';

test.describe('Video Creator Studio @component', () => {
  test('loads ai-video route and shell', async ({ page }) => {
    await page.goto('/features/ai-video');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="video-studio-root"]')).toBeVisible();
    await expect(page.locator('[data-testid="video-studio-tab-projects"]')).toBeVisible();
    await expect(page.locator('[data-testid="video-studio-tab-script"]')).toBeVisible();
    await expect(page.locator('[data-testid="video-studio-tab-thumbnails"]')).toBeVisible();
  });

  test('project creation controls are visible', async ({ page }) => {
    await page.goto('/features/ai-video');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="video-studio-new-project-button"]')).toBeVisible();
    await page.click('[data-testid="video-studio-new-project-button"]');
    await page.waitForTimeout(400);
    await expect(page.locator('[data-testid="video-studio-create-project-title-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="video-studio-create-project-submit-button"]')).toBeVisible();
  });
});
