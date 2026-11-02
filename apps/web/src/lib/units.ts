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

interface Unit {
  symbol: string
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

export function unitFor(quantity: Quantity, system: UnitSystem): Unit {
  return UNITS[system][quantity]
}

export function fromSI(si: number, quantity: Quantity, system: UnitSystem): number {
  return UNITS[system][quantity].fromSI(si)
}

export function toSI(display: number, quantity: Quantity, system: UnitSystem): number {
  return UNITS[system][quantity].toSI(display)
}

export function formatSI(
  si: number,
  quantity: Quantity,
  system: UnitSystem,
  fractionDigits = 0,
): string {
  const unit = UNITS[system][quantity]
  const value = unit.fromSI(si).toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
  return `${value} ${unit.symbol}`
}
