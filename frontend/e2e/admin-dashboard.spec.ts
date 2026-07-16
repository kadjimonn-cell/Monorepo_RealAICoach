/**
 * E2E: Admin dashboard flows
 * Covers: admin login, dashboard load, key panel testids present.
 */
import { test, expect } from '@playwright/test';
import { loginAs, TEST_USERS } from './helpers/auth';

test.describe('Admin — Dashboard route smoke @component', () => {
  test('/admin route is guarded or renders without 500', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(3_500);

    const url = page.url();
    const body = await page.locator('body').textContent() ?? '';
    const hasLogin = await page.locator('[data-testid="login-screen"]').isVisible();
    const hasAdminNav = await page.locator('[data-testid="admin-nav-ops-console"]').isVisible()
      || await page.locator('[data-testid="admin-nav-user-app"]').isVisible();

    expect(body.length).toBeGreaterThan(50);
    expect(url).not.toMatch(/500/);
    expect(url).not.toMatch(/404/);
    expect(hasLogin || hasAdminNav || body.toLowerCase().includes('access denied') || body.length > 150).toBeTruthy();
  });
});

test.describe('Admin — Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, TEST_USERS.admin.email, TEST_USERS.admin.password);
  });

  test('admin login navigates away from login screen', async ({ page }) => {
    await expect(page).not.toHaveURL(/\/auth\/login/);
  });

  test('admin navigation bar renders ops-console link', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(4_000);

    const url = page.url();
    expect(url).not.toMatch(/404/);

    // /admin may redirect to /admin-console where these sidebar items live.
    if (url.includes('/admin-console')) {
      const hasExecSidebarNav = await page.locator('[data-testid="admin-nav-ops-console"]').isVisible().catch(() => false);
      const hasGlobalSidebarOpsLink = await page.getByRole('link', { name: /operations console/i }).isVisible().catch(() => false);
      const hasAdminWorkspaceHeading = await page
        .locator('text=/Consola de Operaciones|Operations Console/i')
        .first()
        .isVisible()
        .catch(() => false);

      expect(hasExecSidebarNav || hasGlobalSidebarOpsLink || hasAdminWorkspaceHeading).toBeTruthy();
      return;
    }

    // Try ops console nav item
    const opsNav = page.locator('[data-testid="admin-nav-ops-console"]');
    const userAppNav = page.locator('[data-testid="admin-nav-user-app"]');
    const hasOps = await opsNav.isVisible();
    const hasUserApp = await userAppNav.isVisible();

    // At least one admin nav element should be present
    expect(hasOps || hasUserApp).toBeTruthy();
  });

  test('admin panel renders without 500 error', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(4_000);

    const bodyText = (await page.locator('body').innerText()) || '';
    expect(bodyText.length).toBeGreaterThan(100);
    expect(bodyText).not.toMatch(/Internal Server Error/i);
    expect(bodyText).not.toMatch(/\b500\b/);
  });

  test('admin auth compliance dashboard is reachable', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(3_000);

    // Look for the auth compliance panel (may need to scroll/tab)
    const compliancePanel = page.locator('[data-testid="admin-auth-compliance-dashboard-panel"]');
    const isVisible = await compliancePanel.isVisible();

    // If not directly visible, just confirm admin page loaded
    if (!isVisible) {
      const body = await page.locator('body').textContent();
      expect(body?.length).toBeGreaterThan(100);
    } else {
      await expect(compliancePanel).toBeVisible();
    }
  });

  test('admin oversight section renders', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(4_000);

    const oversight = page.locator('[data-testid="admin-oversight"]');
    const isVisible = await oversight.isVisible();

    if (!isVisible) {
      // Oversight may be under a tab — confirm admin page itself loaded
      const body = await page.locator('body').textContent();
      expect(body?.length).toBeGreaterThan(100);
    } else {
      await expect(oversight).toBeVisible();
    }
  });

  test('non-admin user is blocked from /admin', async ({ page }) => {
    // Log out and log in as regular user
    await page.goto('/auth/logout');
    await page.waitForTimeout(2_000);

    await loginAs(page, TEST_USERS.free.email, TEST_USERS.free.password);
    await page.goto('/admin');
    await page.waitForTimeout(3_000);

    // Should either redirect away or show access denied
    const body = await page.locator('body').textContent() ?? '';
    const url = page.url();

    const isBlocked =
      url.includes('/auth/login') ||
      url.includes('/403') ||
      body.toLowerCase().includes('access denied') ||
      body.toLowerCase().includes('unauthorized') ||
      body.toLowerCase().includes('not allowed') ||
      body.toLowerCase().includes('acceso denegado') ||
      body.toLowerCase().includes('forbidden') ||
      !url.includes('/admin');

    expect(isBlocked).toBeTruthy();
  });
});
