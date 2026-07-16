import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Global admin visibility lockdown @component', () => {
  test('non-admin cannot see admin analytics tabs/pages', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('[data-testid="home-executive-overview-band-title"]')).toContainText('Personal AI Command Center', {
      timeout: 20000,
    });
    await expect(page.locator('[data-testid="home-executive-overview-section-jump"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="home-progress-rail"]')).toHaveCount(0);

    await page.goto('/features');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('[data-testid="features-lifecycle-open-button"]')).toHaveCount(0);

    await page.goto('/admin-console');
    await page.waitForTimeout(2500);
    const adminConsoleVisible = await page.locator('[data-testid="admin-console-page"]').count();
    expect(adminConsoleVisible).toBe(0);
    await expect(page).not.toHaveURL(/\/admin-console$/);

    await expect(page.locator('[data-testid="sidebar-nav-admin-console"]')).toHaveCount(0);
  });
});
