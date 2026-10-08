import { defineConfig } from '@playwright/test'

const baseURL = process.env.P6_GATEWAY || 'http://localhost:8090'

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 60_000,
  use: {
    baseURL,
    channel: process.env.PLAYWRIGHT_CHANNEL,
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
})
