import { test, expect } from '@playwright/test';
import { loginAs, loginAsViaApi, TEST_USERS } from './helpers/auth';
import {
  installVirtualAuthenticator,
  loginWithPasskeyMode,
  registerPasskeyFromSecurity,
  removeVirtualAuthenticator,
} from './helpers/webauthn';

test.describe('Passkey virtual-authenticator regression @critical', () => {
  test('register passkey, logout, then login using passkey mode', async ({ page }) => {
    test.setTimeout(120_000);
    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
    const { cdp, authenticatorId } = await installVirtualAuthenticator(page);

    try {
      await loginAsViaApi(page, TEST_USERS.free.email, TEST_USERS.free.password);
      await registerPasskeyFromSecurity(page);

      await page.goto('/profile');
      const logoutCandidates = [
        '[data-testid="profile-logout-button"]',
        '[data-testid="profile-settings-logout-button"]',
        '[data-testid="settings-logout-button"]',
        '[data-testid="logout-button"]',
      ];
      let clicked = false;
      for (const selector of logoutCandidates) {
        const node = page.locator(selector);
        if (await node.count()) {
          await node.first().click({ force: true });
          clicked = true;
          break;
        }
      }

      if (!clicked) {
        await page.request.post('/api/auth/logout').catch(() => {});
        await page.goto('/auth/login');
      }

      await page.waitForSelector('[data-testid="login-screen"]', { timeout: 25_000 });
      await expect(page.locator('[data-testid="login-passkey-mode"]')).toBeVisible({ timeout: 15_000 });

      await loginWithPasskeyMode(page);
      await expect(page).not.toHaveURL(/\/auth\/login/);

      await page.goto('/security');
      await expect(page.locator('[data-testid="security-passkey-status-badge-text"]')).toContainText(/active/i);
    } finally {
      await removeVirtualAuthenticator(cdp, authenticatorId);
    }
  });
});
