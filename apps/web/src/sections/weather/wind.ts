import type { ProfileLevel } from '@/lib/api'

/** A level as the charts read it: height above the pad, speed, and where the wind blows from. */
export interface WindPoint {
  h: number
  u: number
  v: number
  speed: number
  from: number
}

export function toWindPoints(levels: ProfileLevel[], padElevation: number): WindPoint[] {
  return levels.map((lv) => ({
    h: lv.altitude_m - padElevation,
    u: lv.wind_u_ms,
    v: lv.wind_v_ms,
    speed: Math.hypot(lv.wind_u_ms, lv.wind_v_ms),
    from: (((Math.atan2(-lv.wind_u_ms, -lv.wind_v_ms) * 180) / Math.PI) % 360 + 360) % 360,
  }))
}
