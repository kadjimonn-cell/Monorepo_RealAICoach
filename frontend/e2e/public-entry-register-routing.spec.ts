import { test, expect } from '@playwright/test';

test.describe('Public entry register-first routing @routing', () => {
  test('mini-app aliases redirect visitors to register', async ({ page }) => {
    const cases = [
      {
        route: '/mini-apps',
        expectedSource: 'feature-entry',
        expectedReturnTo: '%2Fmini-apps',
      },
      {
        route: '/mini-apps/creator-exchange',
        expectedSource: 'feature-entry-creator-exchange',
        expectedReturnTo: '%2Fmini-apps%2Fcreator-exchange',
      },
      {
        route: '/mini-apps/job-platform',
        expectedSource: 'feature-entry-job-platform',
        expectedReturnTo: '%2Fmini-apps%2Fjob-platform',
      },
    ];

    for (const item of cases) {
      await page.goto(item.route, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2200);
      await expect(page).toHaveURL(/\/auth\/register/);
      await expect(page).toHaveURL(new RegExp(`source=${item.expectedSource}`));
      await expect(page).toHaveURL(new RegExp(`return_to=${item.expectedReturnTo}`));
    }
  });

  test('footer protected links redirect visitors to register', async ({ page }) => {
    await page.goto('/pricing', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2500);

    const cases = [
      {
        testId: 'footer-link-learning-hub',
        expectedSource: 'footer-learninghub',
        expectedReturnTo: '%2Fai-learning-hub',
      },
      {
        testId: 'footer-link-content-library',
        expectedSource: 'footer-contentlibrary',
        expectedReturnTo: '%2Fcontent-library',
      },
      {
        testId: 'footer-link-my-analytics',
        expectedSource: 'footer-myanalytics',
        expectedReturnTo: '%2Fmy-analytics',
      },
    ];

    for (const item of cases) {
      await page.goto('/pricing', { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      const target = page.locator(`[data-testid="${item.testId}"]`);
      await target.scrollIntoViewIfNeeded();
      await expect(target).toBeVisible();
      await target.click();

      await expect(page).toHaveURL(/\/auth\/register/);
      await expect(page).toHaveURL(new RegExp(`source=${item.expectedSource}`));
      await expect(page).toHaveURL(new RegExp(`return_to=${item.expectedReturnTo}`));
    }
  });
});