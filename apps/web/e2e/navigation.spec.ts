import { expect, test } from '@playwright/test'

const rail = (page: import('@playwright/test').Page) => page.getByRole('navigation', { name: 'Sections' })

test('every rail button navigates and shows its tooltip, from any section', async ({ page }) => {
  await page.goto('/missions')
  const hrefs = await rail(page).getByRole('link').evaluateAll((as) => as.map((a) => a.getAttribute('href')!))
  expect(hrefs.length).toBeGreaterThan(10)

  // Two laps, so every button is tried with every other section active
  // (including the bottom-pinned ones, which is where this used to break).
  for (const _lap of [1, 2]) {
    for (const href of hrefs) {
      const link = rail(page).locator(`a[href="${href}"]`)
      await link.hover()
      await expect(page.getByRole('tooltip')).toBeVisible()
      await link.click()
      await expect(page).toHaveURL(href)
      await expect(link).toHaveAttribute('aria-current', 'page')
    }
  }
})

test('the active indicator stays inside its own button', async ({ page }) => {
  for (const href of ['/missions', '/settings', '/docs']) {
    await page.goto(href)
    const link = rail(page).locator(`a[href="${href}"]`)
    const indicator = link.locator('span.absolute.inset-0')
    // Let the shared-layout animation settle.
    await expect(async () => {
      const [l, i] = await Promise.all([link.boundingBox(), indicator.boundingBox()])
      expect(i!.y).toBeGreaterThanOrEqual(l!.y - 1)
      expect(i!.y + i!.height).toBeLessThanOrEqual(l!.y + l!.height + 1)
    }).toPass()
  }
})
