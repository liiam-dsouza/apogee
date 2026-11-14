import type { Rocket } from '@/lib/api'

export type FinSet = Rocket['fins'][number]

/**
 * One fin's outline, metres from the root leading edge: x aft, y outward from
 * the body tube. Mirrors `outline()` on the fin models in simcore, including
 * RocketPy's square trailing edge when a trapezoid's sweep is unset.
 */
export function finOutline(f: FinSet): [number, number][] {
  if (f.kind === 'free_form') return f.points
  const sweep = f.sweep_length_m ?? f.root_chord_m - f.tip_chord_m
  return [
    [0, 0],
    [sweep, f.span_m],
    [sweep + f.tip_chord_m, f.span_m],
    [f.root_chord_m, 0],
  ]
}

export function finRootChord(f: FinSet): number {
  return f.kind === 'free_form' ? f.points[f.points.length - 1][0] : f.root_chord_m
}

export function finSpan(f: FinSet): number {
  return Math.max(...finOutline(f).map(([, y]) => y))
}

/** Overall length, nose tip to the aftmost component, as `Rocket.length_m()` in simcore. */
export function rocketLength(rocket: Rocket): number {
  return Math.max(
    rocket.nose.length_m,
    rocket.motor_position_m,
    ...rocket.fins.map((f) => f.position_m + finRootChord(f)),
    rocket.tail ? rocket.tail.position_m + rocket.tail.length_m : 0,
  )
}
