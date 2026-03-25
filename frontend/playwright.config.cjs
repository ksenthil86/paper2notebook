// @ts-check
const { defineConfig } = require('@playwright/test')

module.exports = defineConfig({
  testDir: '../tests/e2e',
  outputDir: '../tests/screenshots',
  timeout: 15000,
  use: {
    baseURL: 'http://localhost:5173',
    screenshot: 'only-on-failure',
    headless: true,
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 15000,
  },
})
