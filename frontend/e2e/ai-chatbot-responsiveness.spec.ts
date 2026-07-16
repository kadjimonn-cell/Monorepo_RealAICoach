import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

const TEST_MESSAGE = 'Please give me one concise action for today.';

test.describe('AI Chatbot responsiveness across breakpoints @component', () => {
  test('authenticated non-admin sees responsive conversation flow on desktop/tablet/mobile', async ({ page }, testInfo) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    await page.goto('/features/ai-chatbot');
    await page.waitForLoadState('domcontentloaded');

    const root = page.locator('[data-testid="personal-ai-assistant-v2-root"]');
    await expect(root).toBeVisible({ timeout: 20000 });

    const input = page.locator('[data-testid="personal-ai-assistant-composer-input"]');
    const sendButton = page.locator('[data-testid="personal-ai-assistant-send-button"]');
    const messagesScroll = page.locator('[data-testid="personal-ai-assistant-messages-scroll"]');
    const modeScroll = page.locator('[data-testid="personal-ai-assistant-mode-scroll"]');

    await expect(input).toBeVisible();
    await expect(sendButton).toBeVisible();
    await expect(messagesScroll).toBeVisible();
    await expect(modeScroll).toBeVisible();

    await input.fill(TEST_MESSAGE);
    await sendButton.click();

    await expect(page.locator('text=You').first()).toBeVisible({ timeout: 30000 });
    await expect(page.locator('text=Assistant').first()).toBeVisible({ timeout: 60000 });

    const userEcho = page.getByText(TEST_MESSAGE, { exact: false });
    await expect(userEcho.first()).toBeVisible({ timeout: 30000 });

    const assistantMessages = page.locator('[data-testid^="personal-ai-assistant-message-"]');
    await expect(assistantMessages.first()).toBeVisible();

    const viewportName = testInfo.project.name;
    console.log(`PASS responsive flow on ${viewportName}`);
  });
});
