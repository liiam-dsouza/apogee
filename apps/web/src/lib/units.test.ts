import { describe, expect, it } from 'vitest'
import { formatSI, fromSI, toSI, UNIT_CHOICES, type Quantity, type UnitSystem } from './units'

describe('units', () => {
  it('round-trips every quantity in both systems', () => {
    const quantities: Quantity[] = [
      'length', 'distance', 'altitude', 'speed', 'acceleration', 'mass', 'force',
      'impulse', 'pressure', 'dynamic_pressure', 'temperature', 'angle', 'energy',
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

describe('per-quantity units', () => {
  it('a choice overrides the system for that quantity only', () => {
    const prefs = { system: 'metric' as const, choice: { acceleration: 'g', altitude: 'ft' } }
    expect(fromSI(9.80665 * 10, 'acceleration', prefs)).toBeCloseTo(10, 9)
    expect(formatSI(3048, 'altitude', prefs)).toBe('10,000 ft')
    expect(formatSI(25, 'speed', prefs)).toBe('25 m/s') // not chosen: the system's
  })

  it('every choice round-trips and an unknown symbol falls back', () => {
    for (const [q, units] of Object.entries(UNIT_CHOICES) as [Quantity, { symbol: string }[]][]) {
      for (const u of units) {
        const prefs = { system: 'metric' as const, choice: { [q]: u.symbol } }
        expect(toSI(fromSI(123.456, q, prefs), q, prefs)).toBeCloseTo(123.456, 9)
      }
    }
    expect(fromSI(1000, 'altitude', { system: 'imperial', choice: { altitude: 'parsecs' } })).toBeCloseTo(3280.84, 2)
  })
})

describe('coarse units', () => {
  it('get extra decimals', () => {
    expect(formatSI(105.27, 'acceleration', { system: 'metric', choice: { acceleration: 'g' } })).toBe('10.7 g')
    expect(formatSI(1234, 'distance', { system: 'metric', choice: { distance: 'km' } })).toBe('1.23 km')
  })
})
