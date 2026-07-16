import { test, expect } from '@playwright/test';

test.describe('Workflow Builder @component', () => {
  test('loads workflow builder shell and key controls', async ({ page }) => {
    await page.goto('/features/ai-automations');
    await page.waitForTimeout(2500);

    // Verify root element loads
    await expect(page.locator('[data-testid="workflow-builder-root"]')).toBeVisible();
    
    // Verify header and usage stats
    await expect(page.locator('[data-testid="workflow-builder-header"]')).toBeVisible();
    await expect(page.locator('[data-testid="workflow-builder-usage-stats"]')).toBeVisible();
    
    // Verify tabs are present
    await expect(page.locator('[data-testid="workflow-builder-tabs"]')).toBeVisible();
    await expect(page.locator('[data-testid="workflow-builder-tab-workflows"]')).toBeVisible();
    await expect(page.locator('[data-testid="workflow-builder-tab-templates"]')).toBeVisible();
    await expect(page.locator('[data-testid="workflow-builder-tab-analytics"]')).toBeVisible();
    
    // Verify create workflow button is visible
    await expect(page.locator('[data-testid="workflow-builder-create-button"]')).toBeVisible();
  });

  test('opens create workflow modal and validates form controls', async ({ page }) => {
    await page.goto('/features/ai-automations');
    await page.waitForTimeout(2500);

    // Click create workflow button
    await page.click('[data-testid="workflow-builder-create-button"]');
    await page.waitForTimeout(800);

    // Verify modal opened
    await expect(page.locator('[data-testid="workflow-builder-create-modal"]')).toBeVisible();
    
    // Verify form inputs are present
    await expect(page.locator('[data-testid="workflow-builder-name-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="workflow-builder-description-input"]')).toBeVisible();
    
    // Verify buttons
    await expect(page.locator('[data-testid="workflow-builder-cancel-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="workflow-builder-submit-button"]')).toBeVisible();

    // Fill in workflow details
    await page.fill('[data-testid="workflow-builder-name-input"]', 'Playwright Test Workflow');
    await page.fill('[data-testid="workflow-builder-description-input"]', 'This is an automated test workflow for validation.');

    // Click create button
    await page.click('[data-testid="workflow-builder-submit-button"]');
    await page.waitForTimeout(1500);

    // Verify we're back on the main screen (modal should close)
    await expect(page.locator('[data-testid="workflow-builder-root"]')).toBeVisible();
  });
});
