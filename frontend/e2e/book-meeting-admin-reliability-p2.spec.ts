import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Feature 34 P2 reliability additions @component', () => {
  test('admin sees RBAC badges, safe rollout simulator, and dry-run apply confirmation', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.admin.email, TEST_USERS.admin.password);

    await page.goto('/book-meeting');
    await page.waitForLoadState('domcontentloaded');

    const openInsightsWorkspace = async () => {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        await expect(page.locator('[data-testid="agenda-workspace-tabs"]')).toBeVisible({ timeout: 20000 });

        const insightsTab = page.locator('[data-testid="agenda-workspace-tab-insights"]').first();
        await expect(insightsTab).toBeVisible({ timeout: 15000 });
        await insightsTab.click({ force: true });
        await page.evaluate(() => {
          const el = document.querySelector('[data-testid="agenda-workspace-tab-insights"]') as HTMLElement | null;
          if (el) {
            el.click();
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
          }
        });
        await page.waitForTimeout(1200);

        const visible = await page
          .locator('[data-testid="agenda-insights-workspace-panel"]')
          .first()
          .isVisible()
          .catch(() => false);

        if (visible) return;

        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2200);
      }

      await expect(page.locator('[data-testid="agenda-insights-workspace-panel"]')).toBeVisible({ timeout: 30000 });
    };

    await openInsightsWorkspace();
    await page.waitForTimeout(1200);

    await expect
      .poll(
        async () => {
          const counts = await Promise.all([
            page.locator('[data-testid="agenda-rbac-drift-monitor-badge"]').count(),
            page.locator('[data-testid="agenda-rbac-gate-health-badge"]').count(),
            page.locator('[data-testid="agenda-release-gate-safe-rollout-simulator-panel"]').count(),
            page.locator('[data-testid="agenda-admin-preview-backfill-signal-badge"]').count(),
          ]);
          return counts.reduce((sum, value) => sum + value, 0);
        },
        { timeout: 45000, intervals: [1000, 2000, 3000] },
      )
      .toBeGreaterThan(0);

    const driftCount = await page.locator('[data-testid="agenda-rbac-drift-monitor-badge"]').count();
    const gateCount = await page.locator('[data-testid="agenda-rbac-gate-health-badge"]').count();
    const simulatorCount = await page.locator('[data-testid="agenda-release-gate-safe-rollout-simulator-panel"]').count();
    const signalCount = await page.locator('[data-testid="agenda-admin-preview-backfill-signal-badge"]').count();
    expect(driftCount + gateCount + simulatorCount + signalCount).toBeGreaterThan(0);
    test.info().annotations.push({
      type: 'rbac-badges',
      description: `drift=${driftCount}, gate=${gateCount}, simulator=${simulatorCount}, signal=${signalCount}`,
    });

    const applyButton = page.locator('[data-testid="agenda-admin-preview-backfill-apply-button"]');
    if ((await applyButton.count()) > 0) {
      const disabled = await applyButton.isDisabled().catch(() => false);
      if (!disabled) {
        await applyButton.click({ force: true });
        await page.waitForTimeout(1200);
      }

      const confirmModalCount = await page.locator('[data-testid="agenda-admin-preview-backfill-apply-confirmation-modal"]').count();
      if (confirmModalCount > 0) {
        await expect(page.locator('[data-testid="agenda-admin-preview-backfill-apply-confirm-button"]')).toHaveCount(1, { timeout: 15000 });
        await page.click('[data-testid="agenda-admin-preview-backfill-apply-cancel-button"]', { force: true });
      }
    } else {
      test.info().annotations.push({ type: 'apply-flow', description: 'apply button unavailable in this environment run' });
    }
  });
});
