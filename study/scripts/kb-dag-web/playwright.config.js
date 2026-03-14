const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/suites',
  timeout: 15000,
  retries: 1,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  globalSetup: './tests/helpers/global-setup.js',
  globalTeardown: './tests/helpers/global-teardown.js',
  use: {
    baseURL: 'http://localhost:9909',
    headless: true,
    viewport: { width: 1400, height: 900 },
    actionTimeout: 5000,
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
