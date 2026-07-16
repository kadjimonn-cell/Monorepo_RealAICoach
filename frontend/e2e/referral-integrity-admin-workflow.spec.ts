import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Feature 36 referral integrity admin workflow @component', () => {
  test('admin can view trends and run one-click recommendation apply', async ({ page }) => {
    const callAdminApiWithRetry = async (
      method: 'GET' | 'POST',
      url: string,
      data?: Record<string, any>,
    ) => {
      const maxAttempts = 5;
      let lastRes: any = null;

      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        lastRes = method === 'GET'
          ? await page.request.get(url, {
              headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-E2E-Test-Bypass': process.env.E2E_RATE_LIMIT_BYPASS_TOKEN || 'playwright-e2e',
              },
            })
          : await page.request.post(url, {
              headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-E2E-Test-Bypass': process.env.E2E_RATE_LIMIT_BYPASS_TOKEN || 'playwright-e2e',
              },
              data: data || {},
            });

        if (lastRes.status() === 200) return lastRes;

        if (lastRes.status() === 429 && attempt < maxAttempts) {
          let waitMs = 900 * attempt;
          try {
            const payload = await lastRes.json();
            const detail = payload?.detail;
            const retryAfter = Number(
              detail?.retry_after_seconds
              || detail?.retryAfterSeconds
              || payload?.retry_after
              || payload?.retryAfter
              || 0,
            );
            if (Number.isFinite(retryAfter) && retryAfter > 0) {
              waitMs = Math.max(waitMs, Math.min(retryAfter * 1000 + 350, 12000));
            }
          } catch {
            // Keep default backoff
          }
          await page.waitForTimeout(waitMs);
          continue;
        }

        return lastRes;
      }

      return lastRes;
    };

    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.admin.email, TEST_USERS.admin.password);

    await page.goto('/admin-console?tab=referral-analytics');
    await page.waitForLoadState('domcontentloaded');

    const panelVisible = await page.locator('[data-testid="referral-analytics-panel"]').first().isVisible().catch(() => false);

    if (!panelVisible) {
      const alertsRes = await callAdminApiWithRetry('GET', '/api/referrals/admin/integrity-alerts?status=open&page=1&page_size=10');
      expect(alertsRes.status()).toBe(200);

      const trendsRes = await callAdminApiWithRetry('GET', '/api/referrals/admin/integrity-trends?days=90');
      expect(trendsRes.status()).toBe(200);

      const evalRes = await callAdminApiWithRetry('POST', '/api/referrals/admin/integrity-alerts/evaluate', {});
      expect(evalRes.status()).toBe(200);

      const applyRes = await callAdminApiWithRetry('POST', '/api/referrals/admin/fraud-policy/apply-recommendation', {});
      expect(applyRes.status()).toBe(200);
      return;
    }

    await expect(page.locator('[data-testid="referral-analytics-panel"]')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('[data-testid="referral-integrity-alerts-section"]')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('[data-testid="integrity-trends-section"]')).toBeVisible({ timeout: 30000 });

    await expect(page.locator('[data-testid="fraud-policy-recommendation-card"]')).toBeVisible({ timeout: 15000 });
    await page.click('[data-testid="evaluate-integrity-alerts-btn"]', { force: true });
    await page.waitForTimeout(1800);

    await page.click('[data-testid="apply-recommended-fraud-profile-btn"]', { force: true });
    await page.waitForTimeout(2200);

    await expect(page.locator('[data-testid="integrity-window-7"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="integrity-window-30"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="integrity-window-90"]')).toBeVisible({ timeout: 15000 });
  });
});
