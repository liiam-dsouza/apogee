import { describe, expect, it } from 'vitest'
import { SECTION_BY_ID } from '@/app/sections'
import { PAGE_BY_SLUG } from '@/sections/docs/pages'
import { TOUR_STEPS } from './steps'

describe('tour', () => {
  it('links only to docs pages that exist', () => {
    const missing = TOUR_STEPS.flatMap((s) => (s.docs ? [s.docs] : [])).filter(
      (href) => !PAGE_BY_SLUG.has(href.replace(/^\/docs\//, '')),
    )
    expect(missing).toEqual([])
  })

  it('opens only sections that exist', () => {
    const missing = TOUR_STEPS.flatMap((s) => (s.route ? [s.route.slice(1)] : [])).filter((id) => !SECTION_BY_ID[id])
    expect(missing).toEqual([])
  })
})
