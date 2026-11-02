import { expect, test } from '@playwright/test'

// Map layers (boundaries, landing points) need MapLibre's web worker. If the
// server sends it with the wrong content type the worker never starts and only
// DOM markers draw, with no visible error. nginx once did exactly that for .mjs.
test('the map worker starts, so map layers can render', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (m) => m.type() === 'error' && !/status of 404|Failed to load resource/.test(m.text()) && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  const worker = page.waitForResponse((r) => /maplibre-gl-worker.*\.m?js$/.test(r.url()))
  await page.goto('/dispersion')
  const response = await worker
  expect(response.headers()['content-type']).toMatch(/javascript/)
  await page.waitForTimeout(1500)
  expect(errors).toEqual([])
})
