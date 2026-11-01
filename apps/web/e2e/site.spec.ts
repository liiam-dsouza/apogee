import { expect, test } from '@playwright/test'

test.skip(!process.env.E2E_BASE_URL, 'needs a live stack: set E2E_BASE_URL')

test('create a mission, place the site, draw the range and save it', async ({ page, request }) => {
  const name = `e2e site ${Date.now()}`
  // Start from the API so the test owns exactly one mission.
  const created = await request.post('/api/missions', { data: { meta: { name } } })
  const id = (await created.json()).mission.meta.id as string

  try {
    await page.goto(`/missions?id=${id}`)
    await page.getByRole('button', { name: 'Open in editor' }).click()
    await page.getByRole('link', { name: 'Site' }).click()

    // No site yet: enter the pad by coordinates.
    await page.getByLabel('Latitude (°)').fill('-31.05')
    await page.getByLabel('Longitude (°)').fill('136.53')
    await page.getByRole('button', { name: 'Add launch site' }).click()
    await expect(page.getByRole('button', { name: 'Save' })).toBeEnabled()

    // Unit edge: switch to imperial and enter rail length in feet.
    await page.evaluate(() => {
      const prefs = JSON.parse(localStorage.getItem('apogee.prefs') ?? '{"state":{}}')
      prefs.state.units = 'imperial'
      localStorage.setItem('apogee.prefs', JSON.stringify(prefs))
    })
    await page.reload()
    // A reload drops the unsaved draft: reopen and re-add, then continue in feet.
    await page.goto(`/missions?id=${id}`)
    await page.getByRole('button', { name: 'Open in editor' }).click()
    await page.getByRole('link', { name: 'Site' }).click()
    await page.getByLabel('Latitude (°)').fill('-31.05')
    await page.getByLabel('Longitude (°)').fill('136.53')
    await page.getByRole('button', { name: 'Add launch site' }).click()
    await page.getByRole('textbox', { name: 'Rail length', exact: true }).fill('20')

    // Live server validation flags an out-of-range inclination on the field itself.
    await page.getByRole('textbox', { name: 'Inclination', exact: true }).fill('95')
    await expect(page.getByText('Input should be less than or equal to 90')).toBeVisible()
    await page.getByRole('textbox', { name: 'Inclination', exact: true }).fill('84')
    await expect(page.getByText('Input should be less than or equal to 90')).toBeHidden()

    // Draw a boundary around the pad (map is centred on it).
    await page.getByRole('button', { name: 'Draw' }).click()
    const map = page.locator('.maplibregl-canvas')
    const box = (await map.boundingBox())!
    const cx = box.x + box.width / 2
    const cy = box.y + box.height / 2
    for (const [dx, dy] of [[-150, -150], [150, -150], [150, 150], [-150, 150]]) {
      await page.mouse.click(cx + dx, cy + dy)
    }
    await page.getByRole('button', { name: 'Finish' }).click()
    await expect(page.getByText('4 points')).toBeVisible()

    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByRole('button', { name: 'Saved' })).toBeVisible()

    const saved = (await (await request.get(`/api/missions/${id}`)).json()).mission.site
    expect(saved.latitude_deg).toBeCloseTo(-31.05, 6)
    expect(saved.rail_length_m).toBeCloseTo(20 * 0.3048, 6)
    expect(saved.inclination_deg).toBe(84)
    expect(saved.boundary).toHaveLength(4)
  } finally {
    await request.delete(`/api/missions/${id}`)
  }
})
