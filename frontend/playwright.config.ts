import { defineConfig } from '@playwright/test'

const baseURL = process.env.P6_GATEWAY || 'http://localhost:8090'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
})
