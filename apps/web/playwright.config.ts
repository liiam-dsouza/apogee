import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests. Keep these few and about whole journeys; unit behaviour
 * belongs in Vitest.
 *
 * By default they run against `vite preview` with no API, and journeys that
 * need the backend skip. Set E2E_BASE_URL to run everything against a live
 * stack, e.g. `E2E_BASE_URL=http://localhost:8080 pnpm test:e2e` after `make up`.
 */
const stackUrl = process.env.E2E_BASE_URL

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL: stackUrl ?? 'http://localhost:4173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: stackUrl
    ? undefined
    : {
        command: 'pnpm build && pnpm preview --port 4173 --strictPort',
        url: 'http://localhost:4173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
})
