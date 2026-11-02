/**
 * Unit conversion at the UI edge. Everything in the mission config, the API
 * and the stores is SI, except angles, which are degrees
 * (docs/adr/0001-angles-in-degrees.md). These functions are the only place a
 * display unit should ever be produced or parsed.
 */

export type UnitSystem = 'metric' | 'imperial'

/**
 * `length` is component-scale (fins, tubes: in), `distance` is range-scale
 * (rail length, drift: ft), `altitude` is height (ft). All metres in SI.
 */
export type Quantity =
  | 'length'
  | 'distance'
  | 'altitude'
  | 'speed'
  | 'acceleration'
  | 'mass'
  | 'force'
  | 'impulse'
  | 'pressure'
  | 'dynamic_pressure'
  | 'temperature'
  | 'angle'
  | 'energy'
  /** Dimensionless, e.g. an exponent. */
  | 'ratio'
  | 'area'
  | 'time'
  | 'density'

export interface Unit {
  symbol: string
  /** Extra decimals when formatting: a coarse unit (g, km) needs more than the SI default. */
  extraDigits?: number
  /** SI value → display value */
  fromSI: (si: number) => number
  /** display value → SI value */
  toSI: (display: number) => number
}

const linear = (symbol: string, factor: number, offset = 0): Unit => ({
  symbol,
  fromSI: (si) => si / factor - offset,
  toSI: (v) => (v + offset) * factor,
})

const FT = 0.3048
const LB = 0.45359237
const LBF = 4.4482216152605

const UNITS: Record<UnitSystem, Record<Quantity, Unit>> = {
  metric: {
    length: linear('m', 1),
    distance: linear('m', 1),
    altitude: linear('m', 1),
    speed: linear('m/s', 1),
    acceleration: linear('m/s²', 1),
    mass: linear('kg', 1),
    force: linear('N', 1),
    impulse: linear('N·s', 1),
    pressure: linear('hPa', 100),
    dynamic_pressure: linear('kPa', 1000),
    temperature: linear('°C', 1, 273.15),
    angle: linear('°', 1),
    energy: linear('J', 1),
    ratio: linear('', 1),
    area: linear('m²', 1),
    time: linear('s', 1),
    density: linear('kg/m³', 1),
  },
  imperial: {
    length: linear('in', FT / 12),
    distance: linear('ft', FT),
    altitude: linear('ft', FT),
    speed: linear('ft/s', FT),
    acceleration: linear('ft/s²', FT),
    mass: linear('lb', LB),
    force: linear('lbf', LBF),
    impulse: linear('lbf·s', LBF),
    pressure: linear('psi', 6894.757293168),
    dynamic_pressure: linear('psi', 6894.757293168),
    temperature: {
      symbol: '°F',
      fromSI: (k) => ((k - 273.15) * 9) / 5 + 32,
      toSI: (f) => ((f - 32) * 5) / 9 + 273.15,
    },
    angle: linear('°', 1),
    energy: linear('ft·lbf', FT * LBF),
    ratio: linear('', 1),
    area: linear('ft²', FT * FT),
    time: linear('s', 1),
    density: linear('lb/ft³', LB / FT ** 3),
  },
}

const G0 = 9.80665
const coarse = (unit: Unit, extraDigits: number): Unit => ({ ...unit, extraDigits })
const CELSIUS: Unit = linear('°C', 1, 273.15)
const FAHRENHEIT: Unit = UNITS.imperial.temperature

/**
 * Every unit each quantity can be shown in, by symbol. The first two are always
 * the metric and imperial defaults; the rest are extra choices in Settings.
 */
export const UNIT_CHOICES: Record<Quantity, Unit[]> = {
  altitude: [linear('m', 1), linear('ft', FT), coarse(linear('km', 1000), 2)],
  distance: [linear('m', 1), linear('ft', FT), coarse(linear('km', 1000), 2), coarse(linear('mi', 1609.344), 2)],
  length: [linear('m', 1), linear('in', FT / 12), linear('mm', 0.001), linear('cm', 0.01), linear('ft', FT)],
  speed: [linear('m/s', 1), linear('ft/s', FT), linear('km/h', 1 / 3.6), linear('mph', 0.44704), linear('kn', 1852 / 3600)],
  acceleration: [linear('m/s²', 1), linear('ft/s²', FT), coarse(linear('g', G0), 1)],
  mass: [linear('kg', 1), linear('lb', LB), linear('g', 0.001), linear('oz', LB / 16)],
  force: [linear('N', 1), linear('lbf', LBF), coarse(linear('kN', 1000), 2), coarse(linear('kgf', G0), 1)],
  impulse: [linear('N·s', 1), linear('lbf·s', LBF)],
  pressure: [linear('hPa', 100), linear('psi', 6894.757293168), linear('kPa', 1000), linear('Pa', 1), linear('inHg', 3386.389)],
  dynamic_pressure: [linear('kPa', 1000), linear('psi', 6894.757293168), linear('Pa', 1)],
  temperature: [CELSIUS, FAHRENHEIT, linear('K', 1)],
  angle: [linear('°', 1)],
  energy: [linear('J', 1), linear('ft·lbf', FT * LBF), coarse(linear('kJ', 1000), 2)],
  ratio: [linear('', 1)],
  area: [linear('m²', 1), linear('ft²', FT * FT), linear('cm²', 1e-4), linear('in²', (FT / 12) ** 2)],
  time: [linear('s', 1)],
  density: [linear('kg/m³', 1), linear('lb/ft³', LB / FT ** 3), linear('g/cm³', 1000)],
}

/** A display preference: a system, with any quantity set to its own unit (by symbol). */
export interface UnitPrefs {
  system: UnitSystem
  choice: Partial<Record<Quantity, string>>
}

/** Either a plain system or a system with per-quantity choices. */
export type Units = UnitSystem | UnitPrefs

/** The system a preference starts from (for things that only know metric or imperial, like a map scale). */
export function systemOf(units: Units): UnitSystem {
  return typeof units === 'string' ? units : units.system
}

export function unitFor(quantity: Quantity, units: Units): Unit {
  if (typeof units !== 'string') {
    const symbol = units.choice[quantity]
    const chosen = symbol === undefined ? undefined : UNIT_CHOICES[quantity].find((u) => u.symbol === symbol)
    if (chosen) return chosen
  }
  return UNITS[systemOf(units)][quantity]
}

export function fromSI(si: number, quantity: Quantity, units: Units): number {
  return unitFor(quantity, units).fromSI(si)
}

export function toSI(display: number, quantity: Quantity, units: Units): number {
  return unitFor(quantity, units).toSI(display)
}

export function formatSI(si: number, quantity: Quantity, units: Units, fractionDigits = 0): string {
  const unit = unitFor(quantity, units)
  const digits = fractionDigits + (unit.extraDigits ?? 0)
  const value = unit.fromSI(si).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  return unit.symbol ? `${value} ${unit.symbol}` : value
}
