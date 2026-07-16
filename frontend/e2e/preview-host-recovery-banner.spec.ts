import { test, expect } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'https://coach-web-preview.preview.emergentagent.com';

test.describe('Preview Host Recovery Banner', () => {
  test('shows one-load recovery banner when wrapper path is recovered', async ({ page }) => {
    await page.goto(`${BASE}/?previewHostRecovered=1`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1200);

    const banner = page.getByTestId('preview-host-recovery-banner');
    await expect(banner).toBeVisible();
    await expect(page.getByTestId('preview-host-recovery-banner-title')).toContainText('Recovered to latest preview build');

    await page.getByTestId('preview-host-recovery-banner-dismiss-button').click({ force: true });
    await expect(banner).toBeHidden();
  });
});
