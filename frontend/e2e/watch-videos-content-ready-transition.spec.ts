import { test, expect } from '@playwright/test';
import { TEST_USERS, loginAsViaApi } from './helpers/auth';

test.describe('Watch Videos content-ready transition @component', () => {
  test('skeleton overlay dissolves and content fade container remains visible', async ({ page }) => {
    test.setTimeout(90_000);
    await loginAsViaApi(page, TEST_USERS.admin.email, TEST_USERS.admin.password);

    await page.goto('/features/watch-videos');

    await expect(page.locator('[data-testid="watch-videos-v2-content-ready-transition-root"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-testid="watch-videos-v2-content-ready-fade-container"]')).toBeVisible({ timeout: 30_000 });

    await page.waitForTimeout(1800);

    await expect(page.locator('[data-testid="watch-videos-v2-stats"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-testid="watch-videos-v2-player-card"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-testid="watch-videos-v2-grid"]')).toBeVisible({ timeout: 30_000 });

    const skeletonOverlay = page.locator('[data-testid="watch-videos-v2-content-ready-skeleton-overlay"]');
    const overlayCount = await skeletonOverlay.count();
    if (overlayCount > 0) {
      await expect(skeletonOverlay).not.toBeVisible({ timeout: 20_000 });
    }
  });
});
