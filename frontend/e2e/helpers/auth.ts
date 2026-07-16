/**
 * Shared authentication helper for Playwright e2e suites.
 * Uses credentials from test_credentials.md.
 */
import { expect } from '@playwright/test';

const E2E_BYPASS_HEADER = {
  'X-E2E-Test-Bypass': process.env.E2E_RATE_LIMIT_BYPASS_TOKEN || 'playwright-e2e',
  'X-Requested-With': 'XMLHttpRequest',
};

export const TEST_USERS = {
  admin: {
    email: 'admin@realaicoach.app',
    password: 'NewAdminPass2026!',
  },
  nonAdminDelegated: {
    email: 'curation.1779076352@example.com',
    password: 'NovaV2#2026!Aa',
  },
  regular: {
    email: 'nova.v2.1779074133@example.com',
    password: 'NovaV2#2026!Aa',
  },
  basic: {
    email: 'f22.basic.20260613@example.com',
    password: 'F22Basic#2026Aa',
  },
  free: {
    email: 'p1.free.1779113329@example.com',
    password: 'P1Free#2026!Aa',
  },
};

type TestCredential = {
  email: string;
  password: string;
};

async function dismissPasskeyEnrollmentPromptIfVisible(page) {
  const prompt = page.locator('[data-testid="passkey-enrollment-modal"]');
  const visible = await prompt.isVisible().catch(() => false);
  if (!visible) return;

  const notNow = page.locator('[data-testid="passkey-enrollment-not-now-button"]');
  await expect(notNow).toBeVisible({ timeout: 10_000 });
  await notNow.click({ force: true });
}

async function waitForAnyPostLoginSignal(page) {
  const signals = [
    '[data-testid="agenda-workspace-tabs"]',
    '[data-testid="agenda-insights-workspace-panel"]',
    '[data-testid="dashboard-overview"]',
    '[data-testid="home-dashboard-root"]',
    '[data-testid="main-navigation-sidebar"]',
    '[data-testid="top-navigation-sign-out"]',
  ];

  for (const selector of signals) {
    const visible = await page.locator(selector).first().isVisible().catch(() => false);
    if (visible) return;
  }

  await page.waitForTimeout(1200);
}

async function waitForRouteAccessGuardToSettle(page) {
  const checkingAccessCopy = page.getByText('Checking access', { exact: false });
  const spinnerVisible = await checkingAccessCopy.isVisible().catch(() => false);
  if (!spinnerVisible) return;

  await expect.poll(async () => {
    const stillVisible = await checkingAccessCopy.isVisible().catch(() => false);
    return stillVisible;
  }, { timeout: 40_000, intervals: [500, 1000, 2000, 3000] }).toBe(false);
}

async function assertAuthenticatedServerSession(page) {
  await expect
    .poll(
      async () => {
        const result = await page.request.get('/api/auth/me', {
          headers: E2E_BYPASS_HEADER,
        });
        return result.status();
      },
      { timeout: 20_000, intervals: [500, 1000, 1500] },
    )
    .toBe(200);
}

/**
 * Log in using the email/password form.
 * Waits for the success overlay OR the post-login redirect away from /auth/login.
 */
export async function loginAs(
  page,
  email,
  password,
) {
  await page.goto('/auth/login');
  await page.waitForSelector('[data-testid="login-screen"]', { timeout: 20_000 });

  await page.fill('[data-testid="login-email-input"]', email);
  await page.fill('[data-testid="login-password-input"]', password);
  await page.click('[data-testid="login-submit-button"]');

  // Some users get a post-login biometric enrollment prompt that blocks redirect.
  await dismissPasskeyEnrollmentPromptIfVisible(page);

  // Session persistence source-of-truth: server session must be active.
  // Retry once for slow auth risk evaluation paths under heavy load.
  let sessionOk = false;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      await assertAuthenticatedServerSession(page);
      sessionOk = true;
      break;
    } catch {
      if (attempt === 2) {
        throw new Error('session_establish_timeout');
      }
      await page.waitForTimeout(2000);
    }
  }

  if (!sessionOk) {
    throw new Error('session_establish_failed');
  }

  // Then ensure UI leaves /auth/login (or force to app route if delayed).
  const redirected = await page
    .waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 20_000 })
    .then(() => true)
    .catch(() => false);

  if (!redirected) {
    await page.goto('/features');
    await expect(page).not.toHaveURL(/\/auth\/login/);
  }

  await waitForRouteAccessGuardToSettle(page);
  await waitForAnyPostLoginSignal(page);
}

/**
 * Login through API for higher stability in regression suites.
 * Shares cookie jar with the page context.
 */
export async function loginAsViaApi(page, email, password) {
  const maxAttempts = 8;
  let loginRes = null as any;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    loginRes = await page.request.post('/api/auth/login', {
      headers: E2E_BYPASS_HEADER,
      data: { email, password },
    });

    if ([200, 201].includes(loginRes.status())) {
      break;
    }

    if ([429, 503].includes(loginRes.status()) && attempt < maxAttempts) {
      let retryAfterSeconds = 2;
      try {
        const payload = await loginRes.json();
        const detail = payload?.detail;
        if (detail && typeof detail === 'object') {
          const candidate = Number(detail.retry_after_seconds || detail.retryAfterSeconds || 0);
          if (Number.isFinite(candidate) && candidate > 0) {
            retryAfterSeconds = candidate;
          }
        }
      } catch {
        // fallback keep default retry delay
      }

      await page.waitForTimeout(Math.min(retryAfterSeconds * 1000 + 250, 8000));
      continue;
    }

    if (loginRes.status() === 401 && attempt < maxAttempts) {
      let shouldRetry = false;
      let retryAfterSeconds = 2;
      try {
        const payload = await loginRes.json();
        const detail = payload?.detail;
        const detailText =
          typeof detail === 'string'
            ? detail.toLowerCase()
            : typeof detail?.message === 'string'
              ? detail.message.toLowerCase()
              : '';
        if (detailText.includes('too many') || detailText.includes('wait') || detailText.includes('rate')) {
          shouldRetry = true;
          const candidate = Number(detail?.retry_after_seconds || detail?.retryAfterSeconds || 0);
          if (Number.isFinite(candidate) && candidate > 0) {
            retryAfterSeconds = candidate;
          }
        }
      } catch {
        // Ignore parse errors
      }

      if (shouldRetry) {
        await page.waitForTimeout(Math.min(retryAfterSeconds * 1000 + 300, 9000));
        continue;
      }
    }

    break;
  }

  if (![200, 201].includes(loginRes?.status?.() ?? 0)) {
    throw new Error(`api_login_failed_${loginRes?.status?.() ?? 'unknown'}`);
  }

  let payload: any = null;
  try {
    payload = await loginRes.json();
  } catch {
    payload = null;
  }

  if (payload?.requires_2fa === true || payload?.requires_otp === true) {
    throw new Error('auth_requires_2fa');
  }

  const cookies = await page.context().cookies();
  const token = cookies.find(c => c.name === 'session_token')?.value;
  if (!token) {
    const payload = await loginRes.json();
    if (payload.token) {
      const url = new URL(page.url() || 'http://localhost:3000');
      await page.context().addCookies([{
        name: 'session_token',
        value: payload.token,
        domain: url.hostname,
        path: '/',
      }]);
    }
  }

  await assertAuthenticatedServerSession(page);
  await page.goto('/features');
}

export async function loginAsAnyViaApi(page, candidates: TestCredential[]): Promise<string> {
  let lastError: any = null;

  for (const candidate of candidates) {
    try {
      await loginAsViaApi(page, candidate.email, candidate.password);
      return candidate.email;
    } catch (error: any) {
      lastError = error;
      const reason = String(error?.message || '').toLowerCase();
      if (reason.includes('2fa') || reason.includes('otp') || reason.includes('429') || reason.includes('rate')) {
        continue;
      }
      continue;
    }
  }

  throw new Error(`login_as_any_via_api_failed: ${String(lastError?.message || 'unknown')}`);
}

/** Navigate to login page and assert unauthenticated state. */
export async function assertOnLoginPage(page) {
  await expect(page.locator('[data-testid="login-screen"]')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-testid="login-submit-button"]')).toBeVisible();
}
