import { defineConfig, devices } from '@playwright/test';

const isLive = process.env.PLAYWRIGHT_LIVE === '1' || process.env.PLAYWRIGHT_LIVE === 'true';

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  webServer: isLive
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://127.0.0.1:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 15000,
      },
  projects: [
    {
      name: 'mocked',
      testMatch: /.*(?<!live)\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'live',
      testMatch: /.*\.live\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
