import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

const PREMIUM_SURFACES = [
  '/features/content-studio',
  '/features/decision-coach',
  '/features/ai-automations',
  '/features/analytics-reports',
  '/features/ai-enterprise',
  '/mini-apps/ai-accounting',
  '/mini-apps/creator-exchange',
  '/subscription/mobile-money',
];

test.describe('Free-limited expanded premium surfaces @component', () => {
  async function checkRouteWithRetry(page, route: string) {
    const attempts = 4;
    let lastStatus = 0;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const decision = await page.request.post('/api/access-control/check-route', {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'X-E2E-Test-Bypass': process.env.E2E_RATE_LIMIT_BYPASS_TOKEN || 'playwright-e2e',
        },
        data: { path: route, method: 'GET' },
      });

      lastStatus = decision.status();
      if (lastStatus === 200) {
        return decision;
      }

      if (lastStatus === 429 && attempt < attempts) {
        let waitMs = 700 * attempt;
        try {
          const payload = await decision.json();
          const detail = payload?.detail;
          if (detail && typeof detail === 'object') {
            const retryAfter = Number(detail.retry_after_seconds || detail.retryAfterSeconds || 0);
            if (Number.isFinite(retryAfter) && retryAfter > 0) {
              waitMs = Math.max(waitMs, Math.min(retryAfter * 1000 + 250, 9000));
            }
          }
        } catch {
          // keep default wait
        }
        await page.waitForTimeout(waitMs);
        continue;
      }

      return decision;
    }

    throw new Error(`check_route_failed_status_${lastStatus}`);
  }

  test('free user is limited on expanded premium surfaces', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.free.email, TEST_USERS.free.password);

    for (const route of PREMIUM_SURFACES) {
      const decision = await checkRouteWithRetry(page, route);
      expect(decision.status()).toBe(200);
      const payload = await decision.json();
      expect(payload.allowed).toBe(false);
    }

    // Keep one concrete UI redirect assertion on an actual premium surface route.
    await page.goto('/job-platform-employer');
    await page.waitForTimeout(1200);
    await expect(page).toHaveURL(/\/subscription\/plans/);
  });

  test('basic user is allowed on expanded premium surfaces', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    for (const route of PREMIUM_SURFACES) {
      const decision = await checkRouteWithRetry(page, route);
      expect(decision.status()).toBe(200);
      const payload = await decision.json();
      expect(payload.allowed).toBe(true);
    }
  });
});
