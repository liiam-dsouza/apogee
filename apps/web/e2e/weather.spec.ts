import { expect, test } from '@playwright/test'

test.skip(!process.env.E2E_BASE_URL, 'needs a live stack: set E2E_BASE_URL')

test('fetch a forecast, pick the hour, blend in a measured surface wind', async ({ page, request }) => {
  const created = await request.post('/api/missions', { data: { meta: { name: `e2e weather ${Date.now()}` } } })
  const id = (await created.json()).mission.meta.id as string

  try {
    await page.goto(`/missions?id=${id}`)
    await page.getByRole('button', { name: 'Open in editor' }).click()
    await page.getByRole('link', { name: 'Site' }).click()
    await page.getByLabel('Latitude (°)').fill('-30.66481')
    await page.getByLabel('Longitude (°)').fill('143.196302')
    await page.getByRole('button', { name: 'Add launch site' }).click()
    await page.getByRole('link', { name: 'Weather' }).click()
    await expect(page.getByRole('heading', { name: 'Standard atmosphere, no wind' })).toBeVisible()

    const fetched = page.waitForResponse((r) => r.url().endsWith('/api/weather/forecasts') && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Fetch forecast' }).click()
    test.skip((await fetched).status() === 503, 'Open-Meteo is not reachable from the stack')

    await page.getByRole('button', { name: 'Use this hour' }).click()
    await expect(page.getByRole('heading', { name: /Forecast for/ })).toBeVisible()
    await expect(page.getByText(/Fetched \d+ min ago/).first()).toBeVisible()
    await expect(page.getByRole('img', { name: /Wind speed/ })).toBeVisible()

    await page.getByRole('button', { name: 'Add surface wind' }).click()
    await page.getByRole('textbox', { name: 'Speed', exact: true }).fill('6')
    await page.getByRole('textbox', { name: 'From', exact: true }).fill('200')
    await expect(page.getByText('Flown (blended)')).toBeVisible()

    await page.getByRole('button', { name: 'Show table' }).click()
    await expect(page.getByRole('columnheader', { name: 'Speed' })).toBeVisible()

    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByRole('button', { name: 'Saved' })).toBeVisible()
    const saved = await (await request.get(`/api/missions/${id}`)).json()
    expect(saved.mission.environment.atmosphere.kind).toBe('profile')
    expect(saved.mission.environment.surface_wind.direction_deg).toBe(200)
  } finally {
    await request.delete(`/api/missions/${id}`)
  }
})
