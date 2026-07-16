import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Contextual upgrade messaging @component', () => {
  test('free user sees route-specific upgrade copy on plans page after guard redirect', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.free.email, TEST_USERS.free.password);

    await page.goto('/features/decision-coach');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1500);

    await expect(page).toHaveURL(/\/subscription\/plans\?/);
    await expect(page.locator('[data-testid="subscription-contextual-upgrade-banner"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="subscription-contextual-upgrade-title"]')).toContainText('Decision Coach', {
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="subscription-contextual-upgrade-meta"]')).toContainText('Recommended plan: BASIC', {
      timeout: 15000,
    });
  });
});
