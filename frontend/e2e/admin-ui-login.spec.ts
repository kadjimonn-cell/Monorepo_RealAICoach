import { test, expect } from '@playwright/test';
import { TEST_USERS } from './helpers/auth';

test.describe('Admin UI login contract @component', () => {
  test('admin login via form reaches admin workspace without false error state', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForSelector('[data-testid="login-screen"]', { timeout: 20_000 });

    await expect(page.locator('[data-testid="login-email-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-password-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-submit-button"]')).toBeVisible();

    await page.locator('[data-testid="login-email-input"]').click();
    await page.locator('[data-testid="login-email-input"]').pressSequentially(TEST_USERS.admin.email, { delay: 20 });
    await page.locator('[data-testid="login-password-input"]').click();
    await page.locator('[data-testid="login-password-input"]').pressSequentially(TEST_USERS.admin.password, { delay: 20 });
    await page.locator('[data-testid="login-submit-button"]').click();

    await expect.poll(async () => {
      const response = await page.request.get('/api/auth/me', {
        headers: {
          'X-E2E-Test-Bypass': process.env.E2E_RATE_LIMIT_BYPASS_TOKEN || 'playwright-e2e',
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      return response.status();
    }, { timeout: 20_000, intervals: [500, 1000, 1500] }).toBe(200);

    await page.goto('/admin-console?category=overview&tab=ops-command-center');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).not.toHaveURL(/\/auth\/login/);
    await expect(page.locator('[data-testid="login-error"]')).toHaveCount(0);

    const workspaceSignals = [
      page.locator('[data-testid="admin-console-title"]'),
      page.locator('[data-testid="admin-nav-ops-console"]'),
      page.getByText(/operations console/i).first(),
    ];

    let foundWorkspace = false;
    for (const signal of workspaceSignals) {
      if (await signal.isVisible().catch(() => false)) {
        foundWorkspace = true;
        break;
      }
    }

    expect(foundWorkspace).toBeTruthy();
  });
});