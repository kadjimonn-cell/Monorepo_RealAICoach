import { test, expect } from '@playwright/test';

test.describe('Smart Writing Studio v2 @component', () => {
  test('loads writing workspace shell and key controls', async ({ page }) => {
    await page.goto('/features/ai-writer');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="smart-writing-studio-v2-root"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-writing-studio-doc-list-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-writing-studio-editor-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-writing-studio-run-button"]')).toBeVisible();
  });

  test('creates a document and allows local draft save flow', async ({ page }) => {
    await page.goto('/features/ai-writer');
    await page.waitForTimeout(2500);

    await page.fill('[data-testid="smart-writing-studio-new-doc-title-input"]', 'Playwright Writer Doc');
    await page.fill('[data-testid="smart-writing-studio-editor-input"]', 'This is a deterministic draft body for Smart Writing Studio validation.');

    await page.click('[data-testid="smart-writing-studio-create-doc-button"]');
    await page.waitForTimeout(1200);

    await expect(page.locator('[data-testid^="smart-writing-studio-doc-item-"]').first()).toBeVisible();

    await page.click('[data-testid="smart-writing-studio-save-draft-button"]');
    await page.waitForTimeout(1000);

    await expect(page.locator('[data-testid="smart-writing-studio-editor-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="smart-writing-studio-task-controls-card"]')).toBeVisible();
  });
});
