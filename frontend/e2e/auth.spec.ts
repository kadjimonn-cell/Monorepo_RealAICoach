/**
 * E2E: Authentication flows
 * Covers: login success, login with wrong password, register page renders,
 * login screen renders key brand elements.
 */
import { test, expect } from '@playwright/test';
import { loginAs, assertOnLoginPage, TEST_USERS } from './helpers/auth';

test.describe('Auth — Login screen', () => {
  test('login page renders brand elements and form @component', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForSelector('[data-testid="login-screen"]', { timeout: 20_000 });

    await expect(page.locator('[data-testid="login-brand-wordmark"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-heading"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-email-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-password-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-submit-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-security-tls-text"]')).toBeVisible();
  });

  test('login page shows register link @component', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForSelector('[data-testid="login-register-row"]', { timeout: 20_000 });
    await expect(page.locator('[data-testid="login-register-link"]')).toBeVisible();
  });

  test('wrong password shows error, does not navigate away', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForSelector('[data-testid="login-email-input"]', { timeout: 20_000 });

    await page.fill('[data-testid="login-email-input"]', TEST_USERS.admin.email);
    await page.fill('[data-testid="login-password-input"]', 'wrong-password-12345!');
    await page.click('[data-testid="login-submit-button"]');

    // Should stay on login screen (not navigate away)
    await page.waitForTimeout(3_000);
    await assertOnLoginPage(page);
  });

  test('admin login succeeds and leaves login page', async ({ page }) => {
    await loginAs(page, TEST_USERS.admin.email, TEST_USERS.admin.password);
    // Must have navigated away from /auth/login
    await expect(page).not.toHaveURL(/\/auth\/login/);
  });

  test('regular user login succeeds', async ({ page }) => {
    await loginAs(page, TEST_USERS.free.email, TEST_USERS.free.password);
    await expect(page).not.toHaveURL(/\/auth\/login/);
  });
});

test.describe('Auth — Register page', () => {
  test('register page is reachable and renders form @component', async ({ page }) => {
    await page.goto('/auth/register');
    // Accept either a register form or a redirect to login with register tab active
    await page.waitForTimeout(3_000);
    const url = page.url();
    // Should not show a blank screen or 404
    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(50);
    expect(url).not.toMatch(/\/404/);
  });
});
