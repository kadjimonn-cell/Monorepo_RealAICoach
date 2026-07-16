import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

async function gotoWelcome(page) {
  await page.goto('/welcome');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1800);
  await page.locator('[data-testid="growth-plan-upgrade-strip"]').scrollIntoViewIfNeeded();
  await expect(page.locator('[data-testid="growth-plan-upgrade-strip"]')).toBeVisible({ timeout: 20000 });
}

test.describe('Welcome growth intelligence plan-aware conversion strip @component', () => {
  test('visitor sees account-creation conversion strip and locked insights', async ({ page }) => {
    await gotoWelcome(page);

    await expect(page.locator('[data-testid="growth-plan-state-pill"]')).toContainText('Preview mode');
    await expect(page.locator('[data-testid="growth-plan-cta-button"]')).toContainText('Start free');
    await expect(page.locator('[data-testid="growth-benchmark-personalized-story"]')).toContainText('public platform momentum');
    await expect(page.locator('[data-testid="growth-plan-destination-chip"]')).toContainText('Create account');
    await expect(page.locator('[data-testid="growth-plan-insight-card-0-locked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-1-locked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-2-locked"]')).toBeVisible();
  });

  test('free user sees Basic upgrade messaging', async ({ page }) => {
    await loginAsViaApi(page, TEST_USERS.free.email, TEST_USERS.free.password);
    await gotoWelcome(page);

    await expect(page.locator('[data-testid="growth-plan-state-pill"]')).toContainText('Free plan');
    await expect(page.locator('[data-testid="growth-plan-cta-button"]')).toContainText('Upgrade to Basic');
    await expect(page.locator('[data-testid="growth-benchmark-personalized-story"]')).toContainText('Basic unlocks forecast confidence');
    await expect(page.locator('[data-testid="growth-plan-destination-chip"]')).toContainText('Subscription plans');
    await expect(page.locator('[data-testid="growth-plan-insight-card-0-locked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-1-locked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-2-locked"]')).toBeVisible();
  });

  test('basic user unlocks forecast confidence but not premium benchmark correlation', async ({ page }) => {
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);
    await gotoWelcome(page);

    await expect(page.locator('[data-testid="growth-plan-state-pill"]')).toContainText('Basic plan');
    await expect(page.locator('[data-testid="growth-plan-cta-button"]')).toContainText('Upgrade to Premium');
    await expect(page.locator('[data-testid="growth-benchmark-personalized-story"]')).toContainText('Premium adds correlation depth');
    await expect(page.locator('[data-testid="growth-plan-destination-chip"]')).toContainText('Subscription plans');
    await expect(page.locator('[data-testid="growth-plan-insight-card-0-unlocked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-1-locked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-2-locked"]')).toBeVisible();
  });

  test('admin premium actor sees fully unlocked insights', async ({ page }) => {
    await loginAsViaApi(page, TEST_USERS.admin.email, TEST_USERS.admin.password);
    await gotoWelcome(page);

    await expect(page.locator('[data-testid="growth-plan-state-pill"]')).toContainText('Premium unlocked');
    await expect(page.locator('[data-testid="growth-plan-cta-button"]')).toContainText('Open dashboard');
    await expect(page.locator('[data-testid="growth-benchmark-personalized-story"]')).toContainText('Correlation intelligence is live');
    await expect(page.locator('[data-testid="growth-plan-destination-chip"]')).toContainText('Dashboard forecast workspace');
    await expect(page.locator('[data-testid="growth-plan-insight-card-0-unlocked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-1-unlocked"]')).toBeVisible();
    await expect(page.locator('[data-testid="growth-plan-insight-card-2-unlocked"]')).toBeVisible();
  });
});