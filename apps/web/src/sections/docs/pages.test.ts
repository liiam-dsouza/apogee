import { describe, expect, it } from 'vitest'
import { PAGE_BY_SLUG, PAGES, renderDoc, resolveDocLink, searchDocs } from './pages'

describe('docs', () => {
  it('bundles the repo docs, with Start here first', () => {
    expect(PAGES[0].slug).toBe('start-here')
    expect(PAGE_BY_SLUG.get('methods/weather')?.title).toBe('Weather and wind: method')
  })

  it('resolves relative links to in-app routes', () => {
    expect(resolveDocLink('guides/first-flight', '../methods/flight.md')).toBe('/docs/methods/flight')
    expect(resolveDocLink('start-here', 'methods/flight.md#validation')).toBe('/docs/methods/flight#validation')
    expect(resolveDocLink('methods/flight', 'https://docs.rocketpy.org')).toBe('https://docs.rocketpy.org')
    // Leaves docs/: a repo file, not a page.
    expect(resolveDocLink('start-here', '../README.md')).toBeNull()
  })

  it('has no broken links between pages', () => {
    const broken: string[] = []
    for (const page of PAGES) {
      for (const [, href] of page.body.matchAll(/\]\(([^)\s]+)\)/g)) {
        if (/^[a-z]+:|^#|^\//i.test(href) || !href.split('#')[0].endsWith('.md')) continue
        if (resolveDocLink(page.slug, href) === null) broken.push(`${page.slug}: ${href}`)
      }
    }
    expect(broken).toEqual([])
  })

  it('renders headings with ids and rewrites links', () => {
    const html = renderDoc(PAGE_BY_SLUG.get('start-here')!)
    expect(html).toContain('<h2 id="your-first-week">')
    expect(html).toContain('href="/docs/guides/first-flight"')
  })

  it('searches titles and bodies', () => {
    expect(searchDocs('anemometer').map((r) => r.page.slug)).toContain('guides/launch-day-weather')
    expect(searchDocs('weather')[0].page.title).toMatch(/weather/i)
  })
})
