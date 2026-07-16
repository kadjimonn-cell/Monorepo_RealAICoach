/**
 * E2E: Global admin visibility lock under authenticated sessions.
 * Verifies non-admin users cannot see admin tabs and cannot access admin routes.
 */
import { test, expect } from '@playwright/test';
import { loginAsAnyViaApi, loginAsViaApi, TEST_USERS } from './helpers/auth';

const ADMIN_NAV_TEST_IDS = [
  'sidebar-nav-admin',
  'sidebar-nav-admin-console',
  'sidebar-nav-team-management',
  'mobile-nav-admin',
  'mobile-nav-admin-console',
  'mobile-nav-team-management',
];

const BLOCKED_ROUTES = [
  '/admin',
  '/admin-console',
  '/team-management',
  '/policy-console',
  '/admin-system',
  '/executive-dashboard',
];

const ADMIN_ROUTE_PREFIXES = [
  '/admin',
  '/admin-console',
  '/team-management',
  '/policy-console',
  '/admin-system',
  '/executive-dashboard',
];

async function expectNoAdminTabsVisible(page) {
  for (const testId of ADMIN_NAV_TEST_IDS) {
    const locator = page.locator(`[data-testid="${testId}"]`);
    await expect(locator).toHaveCount(0);
  }
}

async function ensureNavigationSurfaceReady(page) {
  const hasDesktopSidebar = (await page.locator('[data-testid="app-shell-sidebar"]').count()) > 0;
  const hasMobileTopBar = (await page.locator('[data-testid="mobile-top-bar"]').count()) > 0;

  if (hasDesktopSidebar) return;

  if (hasMobileTopBar) {
    const toggle = page.locator('[data-testid="mobile-nav-toggle"]');
    if ((await toggle.count()) > 0) {
      await toggle.first().click({ force: true });
      await page.waitForTimeout(700);
    }
  }
}

test.describe('Global RBAC — authenticated non-admin admin-tab invisibility @component', () => {
  const nonAdminCandidates = [
    TEST_USERS.nonAdminDelegated,
    TEST_USERS.free,
    TEST_USERS.regular,
  ];

  test('non-admin authenticated session does not render admin sidebar tabs', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsAnyViaApi(page, nonAdminCandidates);

    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    await ensureNavigationSurfaceReady(page);

    await expectNoAdminTabsVisible(page);
  });

  test('non-admin authenticated session cannot access admin routes (redirect/block)', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsAnyViaApi(page, nonAdminCandidates);

    for (const route of BLOCKED_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState('domcontentloaded');
      
      // Wait for any loading state to complete (access check, auth check, etc.)
      await page.waitForFunction(() => {
        const body = document.body?.innerText?.toLowerCase() || '';
        return !body.includes('checking access') && !body.includes('authentification');
      }, { timeout: 15000 }).catch(() => {});
      
      // Additional wait for redirect to complete
      await page.waitForTimeout(1500);
      await ensureNavigationSurfaceReady(page);
      
      const url = page.url();
      const body = (await page.locator('body').innerText()).toLowerCase();

      const blockedByRedirect =
        url.includes('/dashboard') ||
        url.endsWith('/') ||
        url.includes('/welcome') ||
        url.includes('/auth/login');

      const blockedByMessage =
        body.includes('access denied') ||
        body.includes('admin access required') ||
        body.includes('forbidden') ||
        body.includes('not authorized') ||
        body.includes('unauthorized') ||
        body.includes('security verification') ||
        body.includes('cloudflare');

      const blockedByNoAdminState = !ADMIN_ROUTE_PREFIXES.some((prefix) => {
        try {
          return new URL(url).pathname.startsWith(prefix);
        } catch {
          return false;
        }
      });

      const blocked = blockedByRedirect || blockedByMessage || blockedByNoAdminState;

      expect(blocked, `Expected non-admin block/redirect for route ${route}. Got url=${url}`).toBeTruthy();
      await expectNoAdminTabsVisible(page);
    }
  });

  test('admin authenticated session can render admin tab(s)', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.admin.email, TEST_USERS.admin.password);

    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    
    // Wait for the sidebar to be visible (indicates page is fully loaded)
    await page.waitForSelector('[data-testid="app-shell-sidebar"], [data-testid="app-shell"]', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
    await ensureNavigationSurfaceReady(page);

    const adminNav = page.locator('[data-testid="sidebar-nav-admin"]');
    const adminConsoleNav = page.locator('[data-testid="sidebar-nav-admin-console"]');
    const teamManagementNav = page.locator('[data-testid="sidebar-nav-team-management"]');

    const rendered =
      (await adminNav.count()) > 0 ||
      (await adminConsoleNav.count()) > 0 ||
      (await teamManagementNav.count()) > 0;

    expect(rendered, 'Expected at least one admin sidebar tab for admin session').toBeTruthy();
  });
});
