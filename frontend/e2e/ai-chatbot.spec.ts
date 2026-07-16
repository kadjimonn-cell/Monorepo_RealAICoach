import { test, expect } from '@playwright/test';

test.describe('Personal AI Assistant v2 @component', () => {
  test('loads workspace shell and key controls', async ({ page }) => {
    await page.goto('/features/ai-chatbot');
    await page.waitForTimeout(2500);

    await expect(page.locator('[data-testid="personal-ai-assistant-v2-root"]')).toBeVisible();
    await expect(page.locator('[data-testid="personal-ai-assistant-sessions-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="personal-ai-assistant-create-session-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="personal-ai-assistant-chat-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="personal-ai-assistant-send-button"]')).toBeVisible();
  });

  test('creates action and memory without crashing', async ({ page }) => {
    await page.goto('/features/ai-chatbot');
    await page.waitForTimeout(2500);

    await page.fill('[data-testid="personal-ai-assistant-new-action-input"]', 'Validate launch checklist');
    await page.click('[data-testid="personal-ai-assistant-create-action-button"]');
    await page.waitForTimeout(1500);

    await page.fill('[data-testid="personal-ai-assistant-new-memory-input"]', 'Prefer concise and action-oriented responses.');
    await page.click('[data-testid="personal-ai-assistant-add-memory-button"]');
    await page.waitForTimeout(1500);

    await expect(page.locator('[data-testid="personal-ai-assistant-v2-root"]')).toBeVisible();
    await expect(page.locator('[data-testid="personal-ai-assistant-actions-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="personal-ai-assistant-memory-card"]')).toBeVisible();
  });
});
