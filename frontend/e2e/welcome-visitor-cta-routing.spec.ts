import { test, expect } from '@playwright/test';

async function gotoWelcome(page: any, section?: 'features' | 'pricing') {
  const target = section ? `/welcome?section=${section}` : '/welcome';
  await page.goto(target, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2200);
  await expect(page.locator('[data-testid="welcome-page"]')).toBeVisible({ timeout: 20000 });
}

test.describe('Welcome visitor CTA routing @routing', () => {
  test('growth intelligence upgrade CTA sends visitors to register', async ({ page }) => {
    await gotoWelcome(page);

    await page.locator('[data-testid="growth-plan-upgrade-strip"]').scrollIntoViewIfNeeded();
    await expect(page.locator('[data-testid="growth-plan-cta-button"]')).toBeVisible();
    await page.locator('[data-testid="growth-plan-cta-button"]').click();

    await expect(page).toHaveURL(/\/auth\/register/);
    await expect(page).toHaveURL(/source=welcome-growth-intelligence/);
    await expect(page).toHaveURL(/return_to=%2Fwelcome%3Fsection%3Dpricing/);
  });

  test('capability compare plans CTA sends visitors to register', async ({ page }) => {
    await gotoWelcome(page, 'features');

    await page.locator('[data-testid="welcome-capability-secondary-cta"]').scrollIntoViewIfNeeded();
    await expect(page.locator('[data-testid="welcome-capability-secondary-cta"]')).toBeVisible();
    await page.locator('[data-testid="welcome-capability-secondary-cta"]').click();

    await expect(page).toHaveURL(/\/auth\/register/);
    await expect(page).toHaveURL(/source=welcome-capability-command-center-compare/);
    await expect(page).toHaveURL(/return_to=%2Fwelcome%3Fsection%3Dpricing/);
  });

  test('locked capability matrix CTA sends visitors to register', async ({ page }) => {
    await gotoWelcome(page, 'features');

    const firstLockedCta = page.locator('[data-testid^="welcome-capability-card-cta-"]').first();
    await firstLockedCta.scrollIntoViewIfNeeded();
    await expect(firstLockedCta).toBeVisible();
    await firstLockedCta.click();

    await expect(page).toHaveURL(/\/auth\/register/);
    await expect(page).toHaveURL(/source=welcome-capability-command-center/);
    await expect(page).toHaveURL(/return_to=%2Fwelcome%3Fsection%3Dfeatures/);
  });

  test('all pricing plan CTAs send visitors to register', async ({ page }) => {
    const planIds = ['free', 'basic', 'premium'];

    for (const planId of planIds) {
      await gotoWelcome(page, 'pricing');

      const cta = page.locator(`[data-testid="welcome-plan-${planId}-cta"]`);
      await cta.scrollIntoViewIfNeeded();
      await expect(cta).toBeVisible();
      await cta.click();

      await expect(page).toHaveURL(/\/auth\/register/);
      if (planId === 'free') {
        await expect(page).not.toHaveURL(/planId=/);
      } else {
        await expect(page).toHaveURL(new RegExp(`planId=${planId}`));
      }
    }
  });
});