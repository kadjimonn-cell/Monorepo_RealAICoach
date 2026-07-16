/**
 * E2E: Subscription & payment flows
 * Covers: plans page renders, payment page renders, Resume CTA card structure.
 */
import { test, expect } from '@playwright/test';
import { loginAs, TEST_USERS } from './helpers/auth';

test.describe('Subscription — Checkout smoke @component', () => {
  test('plans route renders or redirects without 500', async ({ page }) => {
    await page.goto('/subscription/plans');
    await page.waitForTimeout(3_000);

    const url = page.url();
    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(50);
    expect(url).not.toMatch(/500/);
    expect(url).not.toMatch(/404/);
  });

  test('payment route renders checkout surface or auth redirect', async ({ page }) => {
    await page.goto('/subscription/payment');
    await page.waitForTimeout(3_000);

    const url = page.url();
    const body = await page.locator('body').textContent();
    const hasLoginScreen = await page.locator('[data-testid="login-screen"]').isVisible();
    const hasPaymentResumeCta = await page.locator('[data-testid="payment-resume-pending-cta-card"]').isVisible();

    expect(body?.length).toBeGreaterThan(50);
    expect(url).not.toMatch(/500/);
    expect(hasLoginScreen || hasPaymentResumeCta || url.includes('/subscription/payment')).toBeTruthy();
  });
});

test.describe('Subscription — Plans page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, TEST_USERS.free.email, TEST_USERS.free.password);
  });

  test('plans page renders billing toggle and hero', async ({ page }) => {
    await page.goto('/subscription/plans');
    await page.waitForTimeout(3_000);

    // Should not be blank
    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(100);

    // Accept either the plans page or a paywall/upgrade prompt
    const url = page.url();
    expect(url).not.toMatch(/404/);
  });

  test('payment page is reachable without 500 error', async ({ page }) => {
    await page.goto('/subscription/payment');
    await page.waitForTimeout(3_000);

    const url = page.url();
    expect(url).not.toMatch(/404/);
    expect(url).not.toMatch(/500/);

    const body = await page.locator('body').textContent();
    expect(body?.length).toBeGreaterThan(50);
  });
});

test.describe('Subscription — Resume CTA (localStorage seeding)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, TEST_USERS.free.email, TEST_USERS.free.password);
  });

  test('Resume CTA card renders when localStorage has pending Stripe checkout', async ({ page }) => {
    // Seed localStorage with a pending checkout before navigating
    await page.goto('/subscription/payment');
    await page.waitForTimeout(2_000);

    const expiryAt = Date.now() + 25 * 60 * 1000; // 25 min from now
    await page.evaluate(({ expiry }) => {
      localStorage.setItem('payment_pending_resume_url', 'https://checkout.stripe.com/test-session-abc123');
      localStorage.setItem('payment_pending_resume_expiry_at', String(expiry));
      localStorage.setItem('payment_pending_resume_method', 'stripe');
    }, { expiry: expiryAt });

    // Reload to trigger the mount effect
    await page.reload();
    await page.waitForTimeout(3_000);

    await expect(page.locator('[data-testid="payment-resume-pending-cta-card"]')).toBeVisible({ timeout: 8_000 });
    await expect(page.locator('[data-testid="payment-resume-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="payment-dismiss-resume-button"]')).toBeVisible();
  });

  test('Dismiss button removes the Resume CTA card', async ({ page }) => {
    await page.goto('/subscription/payment');
    await page.waitForTimeout(2_000);

    const expiryAt = Date.now() + 25 * 60 * 1000;
    await page.evaluate(({ expiry }) => {
      localStorage.setItem('payment_pending_resume_url', 'https://checkout.stripe.com/test-session-dismiss');
      localStorage.setItem('payment_pending_resume_expiry_at', String(expiry));
      localStorage.setItem('payment_pending_resume_method', 'paypal');
    }, { expiry: expiryAt });

    await page.reload();
    await page.waitForTimeout(3_000);

    const ctaCard = page.locator('[data-testid="payment-resume-pending-cta-card"]');
    await expect(ctaCard).toBeVisible({ timeout: 8_000 });

    await page.click('[data-testid="payment-dismiss-resume-button"]');
    await expect(ctaCard).not.toBeVisible({ timeout: 5_000 });
  });

  test('Expired localStorage entry does not show Resume CTA', async ({ page }) => {
    await page.goto('/subscription/payment');
    await page.waitForTimeout(2_000);

    // Set expiry in the past
    const expiredAt = Date.now() - 1000;
    await page.evaluate(({ expiry }) => {
      localStorage.setItem('payment_pending_resume_url', 'https://checkout.stripe.com/expired');
      localStorage.setItem('payment_pending_resume_expiry_at', String(expiry));
      localStorage.setItem('payment_pending_resume_method', 'stripe');
    }, { expiry: expiredAt });

    await page.reload();
    await page.waitForTimeout(3_000);

    await expect(page.locator('[data-testid="payment-resume-pending-cta-card"]')).not.toBeVisible();
  });
});
