import { test, expect } from '@playwright/test';

const WRAPPER = 'https://app.emergent.sh/wo';

test.describe('Preview shell mismatch diagnostics', () => {
  test('shows mismatch banner on wrapper shell host and exposes direct-open CTA', async ({ page }) => {
    await page.goto(WRAPPER, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    const banner = page.getByTestId('preview-shell-mismatch-banner');
    await expect(banner).toBeVisible();
    await expect(page.getByTestId('preview-shell-open-direct-button')).toBeVisible();
  });
});
