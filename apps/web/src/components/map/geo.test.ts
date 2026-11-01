import { describe, expect, it } from 'vitest'
import { destination, polygon } from './geo'

describe('geo', () => {
  it('moves north by the right distance', () => {
    // 1 degree of latitude ≈ 111.2 km on the mean-radius sphere.
    const [lon, lat] = destination([136.5, -31], 0, 111_195)
    expect(lon).toBeCloseTo(136.5, 9)
    expect(lat).toBeCloseTo(-30, 3)
  })

  it('closes polygon rings', () => {
    const ring: [number, number][] = [[0, 0], [1, 0], [1, 1]]
    expect(polygon(ring).geometry.coordinates[0]).toEqual([[0, 0], [1, 0], [1, 1], [0, 0]])
  })
})
