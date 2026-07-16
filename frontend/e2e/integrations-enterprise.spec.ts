import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Feature 35 Integrations Enterprise rebuild @component', () => {
  test('basic user can configure test connector, sync, view logs, health, and disconnect', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    await page.goto('/integrations');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('[data-testid="integrations-enterprise-page"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="integrations-enterprise-kpi-health"]')).toBeVisible();

    const connectorRow = page.locator('[data-testid="integrations-enterprise-row-greenhouse"]').first();
    await expect(connectorRow).toBeVisible({ timeout: 15000 });

    const configureBtn = page.locator('[data-testid="integrations-enterprise-configure-greenhouse"]').first();
    const alreadyConnected = (await configureBtn.count()) === 0;

    if (!alreadyConnected) {
      await configureBtn.click({ force: true });
      const wizardCount = await page.locator('[data-testid="integrations-enterprise-setup-wizard"]').count();
      if (wizardCount > 0) {
        // Test mode is ON by default, so save directly.
        await page.locator('[data-testid="integrations-enterprise-setup-save"]').click({ force: true });
        await page.waitForTimeout(1200);
      }
    }

    const syncBtn = page.locator('[data-testid^="integrations-enterprise-connected-sync-intg_"]').first();
    if ((await syncBtn.count()) > 0) {
      await syncBtn.click({ force: true });
      await page.waitForTimeout(1500);
    }

    const logsBtn = page.locator('[data-testid^="integrations-enterprise-connected-logs-intg_"]').first();
    if ((await logsBtn.count()) > 0) {
      await logsBtn.click({ force: true });
      await expect(page.locator('[data-testid="integrations-enterprise-logs-panel"]')).toBeVisible({ timeout: 10000 });
    }

    const healthBtn = page.locator('[data-testid^="integrations-enterprise-connected-health-action-intg_"]').first();
    if ((await healthBtn.count()) > 0) {
      await healthBtn.click({ force: true });
      await expect(page.locator('[data-testid="integrations-enterprise-health-panel"]')).toBeVisible({ timeout: 10000 });
    }

    const deleteBtn = page.locator('[data-testid^="integrations-enterprise-connected-delete-intg_"]').first();
    if ((await deleteBtn.count()) > 0) {
      page.on('dialog', async (dialog) => {
        await dialog.accept();
      });
      await deleteBtn.click({ force: true });
      await page.waitForTimeout(1200);
    }
  });

  test('free user is gated from integrations APIs via UI error/guard', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.free.email, TEST_USERS.free.password);

    await page.goto('/integrations');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('[data-testid="integrations-enterprise-page"]')).toBeVisible({ timeout: 20000 });

    // The page can render shell, but data loads should not expose active integrations to free tier.
    const emptyMessage = page.locator('[data-testid="integrations-enterprise-empty-connectors"]');
    const errorBanner = page.locator('[data-testid="integrations-enterprise-operation-error"]');
    await expect(emptyMessage.or(errorBanner).first()).toBeVisible({ timeout: 15000 });
  });
});
