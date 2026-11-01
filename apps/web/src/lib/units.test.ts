import { describe, expect, it } from 'vitest'
import { formatSI, fromSI, toSI, type Quantity, type UnitSystem } from './units'

describe('units', () => {
  it('round-trips every quantity in both systems', () => {
    const quantities: Quantity[] = [
      'length', 'distance', 'altitude', 'speed', 'acceleration', 'mass', 'force',
      'impulse', 'pressure', 'temperature', 'angle', 'energy',
    ]
    for (const system of ['metric', 'imperial'] as UnitSystem[]) {
      for (const q of quantities) {
        expect(toSI(fromSI(123.456, q, system), q, system)).toBeCloseTo(123.456, 9)
      }
    }
  })

  it('converts known values', () => {
    expect(fromSI(3048, 'altitude', 'imperial')).toBeCloseTo(10000, 6)
    expect(fromSI(273.15, 'temperature', 'metric')).toBeCloseTo(0, 9)
    expect(fromSI(373.15, 'temperature', 'imperial')).toBeCloseTo(212, 9)
    expect(fromSI(101325, 'pressure', 'metric')).toBeCloseTo(1013.25, 9)
    expect(fromSI(84, 'angle', 'imperial')).toBe(84) // stored in degrees (ADR 0001)
  })

  it('formats with the unit symbol', () => {
    expect(formatSI(3048, 'altitude', 'imperial')).toBe('10,000 ft')
  })
})
