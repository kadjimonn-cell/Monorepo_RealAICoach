import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Feature 36 referrals enterprise rebuild @component', () => {
  test('user can navigate growth/earnings/missions/history workspaces', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    await page.goto('/referrals');
    await page.waitForLoadState('domcontentloaded');

    const waitForStableReferralsUI = async () => {
      const recoveryOverlay = page.getByText('Taking longer than expected', { exact: false });
      const accessOverlay = page.getByText('Checking access', { exact: false });

      await expect
        .poll(
          async () => {
            const [recoveryVisible, accessVisible] = await Promise.all([
              recoveryOverlay.isVisible().catch(() => false),
              accessOverlay.isVisible().catch(() => false),
            ]);
            return recoveryVisible || accessVisible;
          },
          { timeout: 50000, intervals: [700, 1200, 2000, 3000] },
        )
        .toBe(false);
    };

    await waitForStableReferralsUI();

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const workspaceVisible = await page.locator('[data-testid="referral-workspace-switcher"]').first().isVisible().catch(() => false);
      if (workspaceVisible) break;
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      await waitForStableReferralsUI();
    }

    await expect(page.locator('[data-testid="referral-hero-title"]')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('[data-testid="referral-workspace-switcher"]')).toBeVisible({ timeout: 30000 });

    await page.click('[data-testid="referral-workspace-tab-growth"]', { force: true });
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="sharing-kit-section"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="referral-history"]')).toBeVisible({ timeout: 15000 });

    await page.click('[data-testid="referral-workspace-tab-earnings"]', { force: true });
    await page.waitForTimeout(900);
    await expect
      .poll(
        async () => {
          const [tierVisible, commissionVisible] = await Promise.all([
            page.locator('[data-testid="referral-tier-status-card"]').first().isVisible().catch(() => false),
            page.locator('[data-testid="referral-commission-info"]').first().isVisible().catch(() => false),
          ]);
          return tierVisible || commissionVisible;
        },
        { timeout: 25000, intervals: [700, 1200, 1800, 2500] },
      )
      .toBe(true);
    await expect(page.locator('[data-testid="referral-commission-info"]')).toBeVisible({ timeout: 15000 });

    await page.click('[data-testid="referral-workspace-tab-missions"]', { force: true });
    await page.waitForTimeout(900);
    await expect(page.locator('[data-testid="milestone-tracker-section"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="challenge-program-section"]')).toBeVisible({ timeout: 15000 });

    await page.click('[data-testid="referral-workspace-tab-history"]', { force: true });
    await page.waitForTimeout(800);
    await expect(page.locator('[data-testid="referral-history"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="refresh-referrals-btn"]')).toBeVisible({ timeout: 15000 });
  });
});
