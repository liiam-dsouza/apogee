import { devices, expect, test } from '@playwright/test'

// A team member on the launch field, on the laptop's address from their phone.
test.use({ ...devices['Pixel 7'] })

test('the sections menu reaches every section on a phone', async ({ page }) => {
  await page.goto('/missions')
  const menu = page.getByRole('button', { name: 'Sections' })
  await menu.click()
  const hrefs = await page
    .getByRole('dialog')
    .getByRole('link')
    .evaluateAll((as) => as.map((a) => a.getAttribute('href')!))
  expect(hrefs.length).toBeGreaterThan(10)
  await page.keyboard.press('Escape')

  for (const href of hrefs) {
    await menu.click()
    await page.getByRole('dialog').locator(`a[href="${href}"]`).click()
    await expect(page).toHaveURL(href)
    await expect(page.getByRole('dialog')).toBeHidden()
    // Nothing pushes the page wider than the screen.
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      page.viewportSize()!.width,
    )
  }
})

test('on a phone the pane is a tab beside the centre', async ({ page }) => {
  await page.goto('/docs')
  const contents = page.getByRole('tab', { name: 'Contents' })
  await contents.click()
  await expect(contents).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('searchbox', { name: 'Search the docs' })).toBeVisible()

  // Picking a page from the contents shows it.
  await page.getByRole('navigation', { name: 'Documentation' }).getByRole('link').nth(1).click()
  await expect(page.getByRole('tab', { name: 'Page' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('article.doc-prose')).toBeVisible()
})
