/** Displaying constraint metrics in the user's units: shared by the go/no-go board and the ballast report. */
import { fromSI, unitFor, type Quantity } from '@/lib/units'
import { usePrefs } from '@/stores/prefs'

/** How each metric converts to the user's units; null shows it as stored. */
export const METRIC_QUANTITY: Record<string, Quantity | null> = {
  apogee_agl_m: 'altitude',
  main_deploy_agl_m: 'altitude',
  drift_m: 'distance',
  rail_exit_velocity_ms: 'speed',
  landing_speed_ms: 'speed',
  drogue_descent_rate_ms: 'speed',
  max_acceleration_ms2: 'acceleration',
  max_dynamic_pressure_pa: 'dynamic_pressure',
  landing_kinetic_energy_j: 'energy',
  cloud_clearance_m: 'altitude',
  visibility_m: 'distance',
  surface_wind_ms: 'speed',
  sun_elevation_deg: 'angle',
}

/** Metrics from the launch conditions, not a flight: judged once, whatever a rule says to judge them on. */
export const CONDITION_METRICS = new Set(['cloud_cover_pct', 'visibility_m', 'surface_wind_ms', 'sun_elevation_deg'])

export const JUDGED: Record<string, string> = {
  nominal: 'Single flight',
  p50: 'Half of flights',
  p95: '95% of flights',
  p99: '99% of flights',
  worst: 'Every flight',
  conditions: 'Launch conditions',
}

export function useMetricFormat() {
  const units = usePrefs((s) => s.display)
  return (metric: string, si: number, storedUnits = '') => {
    const q = METRIC_QUANTITY[metric]
    const shown = q ? fromSI(si, q, units) : si
    const symbol = q ? unitFor(q, units).symbol : storedUnits === '1' ? '' : storedUnits
    const digits = Math.abs(shown) >= 100 ? 0 : Math.abs(shown) >= 10 ? 1 : 2
    return `${shown.toLocaleString(undefined, { maximumFractionDigits: digits })}${symbol ? ` ${symbol}` : ''}`
  }
}
