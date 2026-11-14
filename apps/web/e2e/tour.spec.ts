import { expect, test } from '@playwright/test'

test('Help starts the tour, which walks the sections and can be skipped', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Help: take the tour' }).click()
  const card = page.getByRole('dialog')
  await expect(card.getByRole('heading', { name: 'Welcome to Apogee' })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Previous' })).toBeDisabled()

  await card.getByRole('button', { name: 'Next' }).click()
  await expect(card.getByRole('heading', { name: 'Sections' })).toBeVisible()
  // The card sits beside the rail it explains, not on top of it.
  const rail = await page.locator('[data-tour="rail-sections"]').boundingBox()
  const box = await card.boundingBox()
  expect(box!.x).toBeGreaterThan(rail!.x + rail!.width)

  await card.getByRole('button', { name: 'Next' }).click()
  await expect(page).toHaveURL('/missions')
  await page.keyboard.press('ArrowLeft')
  await expect(card.getByRole('heading', { name: 'Sections' })).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(card).toBeHidden()
})

test('the tour ends on the docs when asked to read more', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Help: take the tour' }).click()
  await page.getByRole('link', { name: 'Read more in the docs' }).click()
  await expect(page).toHaveURL('/docs/start-here')
  await expect(page.getByRole('dialog')).toBeHidden()
})

test('without the API the tour carries on without its example', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Help: take the tour' }).click()
  await expect(page.getByRole('dialog').getByText(/Couldn't open the example/)).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Next' }).click()
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Sections' })).toBeVisible()
})

test('the home screen launches the tour', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /New to Apogee\?/ }).click()
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Welcome to Apogee' })).toBeVisible()
})
