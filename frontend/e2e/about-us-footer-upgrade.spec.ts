import { test, expect } from '@playwright/test';
import { loginAsViaApi, TEST_USERS } from './helpers/auth';

test.describe('Footer About Us upgrade @component', () => {
  test('welcome footer About Us opens dedicated /about-us with premium CTA block', async ({ page }) => {
    await page.goto('/welcome');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('[data-testid="footer-link-about-us"]')).toBeVisible({ timeout: 25000 });
    await page.click('[data-testid="footer-link-about-us"]', { force: true });

    await expect(page).toHaveURL(/\/about-us$/);
    await expect(page.locator('[data-testid="about-us-page"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-hero-title"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-leadership-section"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-testimonials-section"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-cta-start-trial"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-cta-book-demo"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-cta-variant-badge"]')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('[data-testid="about-us-cta-variant-copy"]')).toBeVisible({ timeout: 20000 });
  });

  test('legacy /about route redirects to /about-us', async ({ page }) => {
    await page.goto('/auth/login');
    await loginAsViaApi(page, TEST_USERS.basic.email, TEST_USERS.basic.password);

    await page.goto('/about');
    await expect(page).toHaveURL(/\/about-us$/);
    await expect(page.locator('[data-testid="about-us-page"]')).toBeVisible({ timeout: 20000 });
  });

  test('about-us CTA buttons navigate to register and book demo flows', async ({ page }) => {
    await page.goto('/about-us');
    await expect(page).toHaveURL(/\/about-us$/);

    await expect(page.locator('[data-testid="about-us-cta-start-trial"]')).toBeVisible({ timeout: 20000 });
    await page.click('[data-testid="about-us-cta-start-trial"]', { force: true });
    await expect(page).toHaveURL(/\/auth\/register/);

    await page.goto('/about-us');
    await expect(page).toHaveURL(/\/about-us$/);
    await expect(page.locator('[data-testid="about-us-cta-variant-badge"]')).toBeVisible({ timeout: 20000 });

    await expect(page.locator('[data-testid="about-us-cta-book-demo"]')).toBeVisible({ timeout: 20000 });
    await page.click('[data-testid="about-us-cta-book-demo"]', { force: true });
    await expect(page).toHaveURL(/\/contact\?intent=demo/);
  });

  test('about-us CTA experiment assignment stays stable across reloads', async ({ page }) => {
    await page.goto('/about-us');
    await expect(page.locator('[data-testid="about-us-cta-variant-badge"]')).toBeVisible({ timeout: 20000 });

    const initialVariant = await page.locator('[data-testid="about-us-cta-variant-badge"]').textContent();
    await page.reload();
    await expect(page.locator('[data-testid="about-us-cta-variant-badge"]')).toBeVisible({ timeout: 20000 });
    const reloadedVariant = await page.locator('[data-testid="about-us-cta-variant-badge"]').textContent();

    expect((initialVariant || '').trim().length).toBeGreaterThan(5);
    expect((initialVariant || '').trim()).toBe((reloadedVariant || '').trim());
  });
});
