import { existsSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'

const ROOT = path.resolve(import.meta.dirname, '../../..')
const LANIUS = path.join(ROOT, 'data/Lanius.ork')
const M1340W = path.join(ROOT, 'tests/fixtures/motors/AeroTech_M1340W.eng')

test.skip(!process.env.E2E_BASE_URL, 'needs a live stack: set E2E_BASE_URL')
test.skip(!existsSync(LANIUS), "needs the team's data/Lanius.ork")

test('import Lanius from OpenRocket, review it, use it and fly it', async ({ page, request }) => {
  test.setTimeout(90_000)
  const created = await request.post('/api/missions', {
    data: {
      meta: { name: 'e2e OpenRocket import' },
      site: { latitude_deg: -30.66481, longitude_deg: 143.196302, elevation_m: 220, rail_length_m: 6, inclination_deg: 85, heading_deg: 0 },
    },
  })
  const id = (await created.json()).mission.meta.id
  try {
    await page.goto(`/missions?id=${id}`)
    await page.getByRole('button', { name: 'Open in editor' }).click()
    await page.getByRole('link', { name: 'Rocket' }).click()
    await page.locator('input[accept=".ork"]').setInputFiles(LANIUS)
    await page.locator('input[accept=".eng"]').setInputFiles(M1340W)
    await page.getByRole('button', { name: 'Import and review' }).click()

    await expect(page.getByRole('heading', { name: 'Review the import: Lanius' })).toBeVisible({ timeout: 60_000 })
    const comparison = page.getByRole('region', { name: 'Comparison with OpenRocket' })
    await expect(comparison.getByRole('row', { name: /^Apogee/ })).toContainText('Agrees')
    await expect(comparison).not.toContainText('Check this')

    await page.getByRole('button', { name: 'Use this rocket' }).click()
    await expect(page.getByRole('img', { name: /Side view of the rocket, 3\.25 m long/ })).toBeVisible()

    await page.getByRole('link', { name: 'Single flight' }).click()
    await page.getByRole('button', { name: 'Run flight' }).click()
    await expect(page.getByRole('cell', { name: 'main deploys' })).toBeVisible({ timeout: 60_000 })
  } finally {
    await request.delete(`/api/missions/${id}`)
  }
})
