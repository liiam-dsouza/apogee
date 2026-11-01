import path from 'node:path'
import { expect, test } from '@playwright/test'

test.skip(!process.env.E2E_BASE_URL, 'needs a live stack: set E2E_BASE_URL')

const BUNDLE = path.resolve(import.meta.dirname, '../../../missions/examples/calisto.mission.zip')
const CALISTO_ID = '01JCALISTO0000000000000000'

test('import the Calisto bundle and fly it', async ({ page, request }) => {
  test.setTimeout(90_000) // the first run also starts the worker's process pool
  await request.delete(`/api/missions/${CALISTO_ID}`) // start clean; 404 is fine
  try {
    await page.goto('/missions')
    await page.locator('input[type="file"]').setInputFiles(BUNDLE)
    await page.getByRole('button', { name: 'Open in editor' }).click()
    await page.getByRole('link', { name: 'Single flight' }).click()

    const resultResponse = page.waitForResponse(
      (r) => /\/api\/results\/[0-9a-f]+$/.test(new URL(r.url()).pathname) && r.ok(),
      { timeout: 60_000 },
    )
    await page.getByRole('button', { name: 'Run flight' }).click()
    const { summary } = await (await resultResponse).json()
    // Within the golden tolerance of the reference flight (platforms differ by centimetres)...
    expect(summary.apogee_agl_m).toBeGreaterThan(3305.44 * (1 - 2e-4))
    expect(summary.apogee_agl_m).toBeLessThan(3305.44 * (1 + 2e-4))
    // ...and the page shows exactly what the API returned (metric by default).
    const apogee = `${Math.round(summary.apogee_agl_m).toLocaleString('en-US')} m`
    await expect(page.getByRole('region', { name: 'Key numbers' }).getByText(apogee, { exact: true })).toBeVisible()
    await expect(page.getByRole('img', { name: /against time/ })).toHaveCount(6)
    await expect(page.getByRole('region', { name: 'Where these numbers came from' })).toContainText('1.13.0')
    await expect(page.getByRole('cell', { name: 'Drogue deploys' })).toBeVisible()

    await page.screenshot({ path: 'test-results/flight-dark.png', fullPage: true })

    // Same inputs again: the stored result is reused.
    await page.getByRole('button', { name: 'Run flight' }).click()
    await expect(page.getByText('stored result was reused')).toBeVisible()
  } finally {
    await request.delete(`/api/missions/${CALISTO_ID}`)
  }
})
