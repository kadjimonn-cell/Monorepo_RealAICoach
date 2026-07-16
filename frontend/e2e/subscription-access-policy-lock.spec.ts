import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Global subscription access policy lock @component', () => {
  test('free user is limited and basic user is almost unlimited (route-level)', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.free.email, TEST_USERS.free.password);

    await page.goto('/job-platform-employer');
    await page.waitForTimeout(1700);
    await expect(page).toHaveURL(/\/subscription\/plans/);

    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    await page.goto('/job-platform-employer');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1200);
    await expect(page).not.toHaveURL(/\/subscription\/plans/);
  });
});
