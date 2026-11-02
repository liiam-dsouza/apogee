import path from 'node:path'
import { expect, test } from '@playwright/test'

test.skip(!process.env.E2E_BASE_URL, 'needs a live stack: set E2E_BASE_URL')

const BUNDLE = path.resolve(import.meta.dirname, '../../../missions/examples/calisto.mission.zip')
const CALISTO_ID = '01JCALISTO0000000000000000'

test('import the Calisto bundle, fly it, and run a small campaign', async ({ page, request }) => {
  test.setTimeout(180_000) // the first run also starts the worker's process pool
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

    // A small Monte Carlo campaign: landings, ellipses and a CSV of every sample.
    await page.getByRole('link', { name: 'Dispersion' }).click()
    await page.getByLabel('Samples').fill('20')
    await page.getByRole('button', { name: 'Run campaign' }).click()
    await expect(page.getByText('Campaign complete')).toBeVisible({ timeout: 120_000 })
    await expect(page.getByText('20 of 20 samples')).toBeVisible()
    await expect(page.getByText('95% landing ellipse')).toBeVisible()
    const csvHref = await page.getByRole('link', { name: 'Every sample as CSV' }).getAttribute('href')
    const csv = await (await request.get(csvHref!)).text()
    expect(csv.trim().split('\n')).toHaveLength(21)

    await page.getByRole('link', { name: 'Monte Carlo results' }).click()
    await expect(page.getByRole('img', { name: /histogram of 20 samples/ })).toHaveCount(8)
    await page.screenshot({ path: 'test-results/montecarlo-results.png' })

    // Judge it against AURC 2026: Calisto's drogue descends at about 18 m/s, under Spec 5.3.2's 20.
    await page.getByRole('link', { name: 'Go / no-go' }).click()
    await page.getByLabel('Profile').selectOption('aurc-2026')
    await page.getByLabel('Category').selectOption('10k-cots')
    await expect(page.getByText('NO-GO', { exact: true })).toBeVisible()
    const drogue = page.getByRole('row', { name: /Descent under drogue/ })
    await expect(drogue).toContainText('Fail')
    await expect(drogue).toContainText('Spec 5.3.2')
    await expect(page.getByRole('row', { name: /Rail departure/ })).toContainText('Pass')
    await expect(page.getByRole('region', { name: 'Apogee score' })).toContainText('of 350')
    await page.screenshot({ path: 'test-results/go-no-go.png', fullPage: true })

    // The motor: its curve and class.
    await page.getByRole('link', { name: 'Motor' }).click()
    await expect(page.getByText(/M class/)).toBeVisible()
    await expect(page.getByRole('img', { name: /Thrust against time/ })).toBeVisible()

    // Recovery: size the drogue for 25 m/s where the main takes over, and use it.
    await page.getByRole('link', { name: 'Recovery' }).click()
    const drogueRow = page.getByRole('row', { name: /^Drogue/ })
    await expect(drogueRow).toContainText('to 800 m')
    await page.getByLabel('Wanted descent rate under Drogue').fill('25')
    await drogueRow.getByRole('button', { name: 'Use this CdS' }).click()
    await expect(drogueRow.getByRole('cell').nth(4)).toHaveText('25.0 m/s')
    await page.screenshot({ path: 'test-results/recovery.png', fullPage: true })
  } finally {
    await request.delete(`/api/missions/${CALISTO_ID}`)
  }
})
