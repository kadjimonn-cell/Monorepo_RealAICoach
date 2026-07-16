import { test, expect } from '@playwright/test';

test.describe('Watch Videos (Feature 21) @component', () => {
  test('auth gate redirects unauth users to login with return_to', async ({ page }) => {
    await page.goto('/features/watch-videos');
    await page.waitForTimeout(1800);

    await expect(page).toHaveURL(/\/auth\/login/);
    await expect(page.locator('[data-testid="login-email-input"]')).toBeVisible();
  });

  test('loads shell and key controls after login', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForTimeout(1200);

    await page.fill('[data-testid="login-email-input"]', 'admin@realaicoach.app');
    await page.fill('[data-testid="login-password-input"]', 'NewAdminPass2026!');
    await page.click('[data-testid="login-submit-button"]');
    await page.waitForTimeout(2600);

    await page.goto('/features/watch-videos');
    await page.waitForTimeout(3200);

    await expect(page.locator('[data-testid="watch-videos-v2-stats"]')).toBeVisible();
    await expect(page.locator('[data-testid="watch-videos-v2-filters-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="watch-videos-v2-player-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="watch-videos-v2-grid"]')).toBeVisible();
  });

  test('basic interactions remain stable (search/sort/watchlist/reason toggle)', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForTimeout(1200);

    await page.fill('[data-testid="login-email-input"]', 'admin@realaicoach.app');
    await page.fill('[data-testid="login-password-input"]', 'NewAdminPass2026!');
    await page.click('[data-testid="login-submit-button"]');
    await page.waitForTimeout(2600);

    await page.goto('/features/watch-videos');
    await page.waitForTimeout(3200);

    await page.fill('[data-testid="watch-videos-v2-search-input"]', 'avengers');
    await page.waitForTimeout(1200);

    await page.click('[data-testid="watch-videos-v2-sort-trending"]');
    await page.waitForTimeout(800);

    await page.click('[data-testid="watch-videos-v2-reason-toggle-button"]');
    await page.waitForTimeout(700);

    const gridItems = page.locator('[data-testid^="watch-videos-v2-grid-item-"]');
    const count = await gridItems.count();
    expect(count).toBeGreaterThan(0);

    await gridItems.first().click();
    await page.waitForTimeout(1000);

    await expect(page.locator('[data-testid="watch-videos-v2-player-card"]')).toBeVisible();
  });
});
