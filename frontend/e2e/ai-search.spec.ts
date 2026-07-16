import { test, expect } from '@playwright/test';

test.describe('Deep Research Navigator v2 @component', () => {
  test('loads workspace shell and key controls', async ({ page }) => {
    await page.goto('/features/ai-search');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="deep-research-navigator-v2-root"]')).toBeVisible();
    await expect(page.locator('[data-testid="deep-research-projects-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="deep-research-runner-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="deep-research-run-button"]')).toBeVisible();
  });

  test('creates project and saves insight without crashing', async ({ page }) => {
    await page.goto('/features/ai-search');
    await page.waitForTimeout(2500);

    await page.fill('[data-testid="deep-research-new-project-title-input"]', 'Playwright Research Project');
    await page.fill('[data-testid="deep-research-new-project-topic-input"]', 'Enterprise AI strategy');
    await page.click('[data-testid="deep-research-create-project-button"]');
    await page.waitForTimeout(1500);

    await page.fill('[data-testid="deep-research-insight-title-input"]', 'Initial validated signal');
    await page.fill('[data-testid="deep-research-insight-body-input"]', 'AI adoption requires strong governance and source transparency.');
    await page.click('[data-testid="deep-research-save-insight-button"]');
    await page.waitForTimeout(1500);

    await expect(page.locator('[data-testid="deep-research-insights-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="deep-research-navigator-v2-root"]')).toBeVisible();
  });
});
