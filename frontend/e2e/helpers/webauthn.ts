import { expect, type Page } from '@playwright/test';

export async function installVirtualAuthenticator(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return { cdp, authenticatorId };
}

export async function removeVirtualAuthenticator(cdp: any, authenticatorId: string) {
  if (!cdp || !authenticatorId) return;
  await cdp.send('WebAuthn.removeVirtualAuthenticator', { authenticatorId }).catch(() => {});
  await cdp.detach().catch(() => {});
}

export async function registerPasskeyFromSecurity(page: Page) {
  await page.goto('/security');
  await page.waitForTimeout(5000);
  await page.screenshot({ path: '/tmp/security.png' });
  const html = await page.content();
  require('fs').writeFileSync('/tmp/security.html', html);

  await page.waitForSelector('[data-testid="security-passkey-section"]', { timeout: 30_000 });

  const registerBtn = page.locator('[data-testid="security-passkey-register-btn"]');
  await expect(registerBtn).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1000);
  await registerBtn.evaluate(node => (node as HTMLElement).click());

  await expect
    .poll(
      async () => {
        const statusBadge = page.locator('[data-testid="security-passkey-status-badge-text"]');
        const text = await statusBadge.textContent().catch(() => '');
        return String(text || '').toLowerCase();
      },
      { timeout: 25_000, intervals: [800, 1200, 1800] },
    )
    .toContain('active');

  const list = page.locator('[data-testid="security-passkey-credential-list"]');
  await expect(list).toBeVisible({ timeout: 15_000 });
}

export async function loginWithPasskeyMode(page: Page) {
  await page.goto('/auth/login');
  await page.waitForSelector('[data-testid="login-screen"]', { timeout: 30_000 });
  await page.waitForSelector('[data-testid="login-email-input"]', { timeout: 30_000 });

  const knownEmail = page.locator('[data-testid="login-email-input"]');
  await knownEmail.fill('p1.free.1779113329@example.com');
  await page.waitForTimeout(1200);

  const passkeyModeBtn = page.locator('[data-testid="login-passkey-mode"]');
  await expect(passkeyModeBtn).toBeVisible({ timeout: 15_000 });
  await passkeyModeBtn.click({ force: true });

  const submit = page.locator('[data-testid="login-passkey-submit"]');
  await expect(submit).toBeVisible({ timeout: 20_000 });
  await submit.click({ force: true });

  await expect
    .poll(
      async () => {
        const res = await page.request.get('/api/auth/me', {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        return res.status();
      },
      { timeout: 20_000, intervals: [800, 1200, 1800] },
    )
    .toBe(200);

  await page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 20_000 }).catch(async () => {
    await page.goto('/features');
  });
}
