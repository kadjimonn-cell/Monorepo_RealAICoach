import { defineConfig, devices } from '@playwright/test';
import fs from 'fs';

const baseURL = process.env.E2E_BASE_URL;
const systemChromiumPath = '/usr/bin/chromium';
const chromiumExecutablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
  || (fs.existsSync(systemChromiumPath) ? systemChromiumPath : undefined);

if (!baseURL) {
  throw new Error('E2E_BASE_URL is required for Playwright snapshot tests');
}

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  retries: 2,
  workers: 4,
  use: {
    baseURL,
    extraHTTPHeaders: {
      'X-E2E-Test-Bypass': process.env.E2E_RATE_LIMIT_BYPASS_TOKEN || 'playwright-e2e',
      'X-Requested-With': 'XMLHttpRequest',
    },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    launchOptions: {
      ...(chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : {}),
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 800 } },
    },
    {
      name: 'tablet-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 1366 } },
    },
    {
      name: 'mobile-chromium',
      use: { ...devices['Pixel 7'] },
    },
  ],
});