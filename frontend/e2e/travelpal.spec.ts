import { test, expect } from '@playwright/test';

test.describe('Travel Planner Pro @component', () => {
  test('loads travelpal workspace shell', async ({ page }) => {
    await page.goto('/features/travelpal');
    await page.waitForTimeout(2500);

    await expect(page.locator('text=Travel Planner Pro')).toBeVisible();
    await expect(page.locator('text=Trips')).toBeVisible();
    await expect(page.locator('text=Planning')).toBeVisible();
    await expect(page.locator('text=Budget Left')).toBeVisible();
  });

  test('primary sections and actions are visible', async ({ page }) => {
    await page.goto('/features/travelpal');
    await page.waitForTimeout(2500);

    await expect(page.locator('text=Create Trip')).toBeVisible();
    await expect(page.locator('text=AI Planner')).toBeVisible();
    await expect(page.locator('text=Trip List')).toBeVisible();
  });
});
