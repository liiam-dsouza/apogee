import { describe, expect, it } from 'vitest'
import { binValues, quantile, ticks } from './bins'

describe('histogram bins', () => {
  it('puts every value in exactly one bin, on round edges', () => {
    const values = Array.from({ length: 200 }, (_, i) => 3000 + ((i * 37) % 200))
    const bins = binValues(values)
    expect(bins.reduce((n, b) => n + b.count, 0)).toBe(200)
    expect(bins[0].lo).toBeLessThanOrEqual(3000)
    expect(bins.at(-1)!.hi).toBeGreaterThanOrEqual(3199)
    const width = bins[0].hi - bins[0].lo
    expect(bins.every((b) => Math.abs(b.hi - b.lo - width) < 1e-9)).toBe(true)
    expect([1, 2, 2.5, 5].some((m) => Number.isInteger(width / m) || Number.isInteger(m / width))).toBe(true)
  })

  it('handles a single repeated value', () => {
    expect(binValues([5, 5, 5])).toEqual([{ lo: 5, hi: 5, count: 3 }])
    expect(binValues([])).toEqual([])
  })

  it('takes quantiles by interpolation', () => {
    expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3)
    expect(quantile([0, 10], 0.95)).toBeCloseTo(9.5)
    expect(ticks(0, 100, 4)).toEqual([0, 25, 50, 75, 100])
  })
})
