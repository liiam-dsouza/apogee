import type { Rocket } from '@/lib/api'

/** Nose radius at distance x from the tip (same profiles as the importer and RocketPy). */
function noseRadius(kind: Rocket['nose']['kind'], x: number, L: number, R: number): number {
  const u = Math.min(Math.max(x / L, 0), 1)
  switch (kind) {
    case 'conical':
      return R * u
    case 'tangent_ogive': {
      const rho = (R * R + L * L) / (2 * R)
      return Math.sqrt(Math.max(rho * rho - (L - x) ** 2, 0)) + R - rho
    }
    case 'elliptical':
      return R * Math.sqrt(Math.max(2 * u - u * u, 0))
    case 'parabolic':
      return R * (2 * u - u * u)
    case 'von_karman':
    case 'lvhaack': {
      const k = kind === 'lvhaack' ? 1 / 3 : 0
      const th = Math.acos(1 - 2 * u)
      return (R / Math.sqrt(Math.PI)) * Math.sqrt(Math.max(th - Math.sin(2 * th) / 2 + k * Math.sin(th) ** 3, 0))
    }
  }
}

/**
 * The airframe drawn to scale, nose left, with the dry centre of mass marked.
 * Dimensions come straight from the mission, metres aft of the nose tip.
 */
export function RocketSideView({ rocket }: { rocket: Rocket }) {
  const R = rocket.radius_m
  const L = Math.max(
    rocket.nose.length_m,
    rocket.motor_position_m,
    ...rocket.fins.map((f) => f.position_m + f.root_chord_m),
    rocket.tail ? rocket.tail.position_m + rocket.tail.length_m : 0,
  )
  const span = Math.max(0, ...rocket.fins.map((f) => f.span_m))
  const half = R + span
  const pad = half * 0.25
  const vb = { x: -pad, y: -half - pad, w: L + 2 * pad, h: 2 * (half + pad) }

  const n = 60
  const nose = Array.from({ length: n + 1 }, (_, i) => {
    const x = (rocket.nose.length_m * i) / n
    return [x, noseRadius(rocket.nose.kind, x, rocket.nose.length_m, R)] as const
  })
  const bodyEnd = rocket.tail ? rocket.tail.position_m : L
  const outline = [
    ...nose.map(([x, y]) => `${x},${-y}`),
    `${bodyEnd},${-R}`,
    ...(rocket.tail ? [`${rocket.tail.position_m + rocket.tail.length_m},${-rocket.tail.bottom_radius_m}`,
      `${rocket.tail.position_m + rocket.tail.length_m},${rocket.tail.bottom_radius_m}`] : [`${bodyEnd},${R}`]),
    `${bodyEnd},${R}`,
    ...[...nose].reverse().map(([x, y]) => `${x},${y}`),
  ].join(' ')

  const finPaths = rocket.fins.flatMap((f, i) => {
    const sweep = f.sweep_length_m ?? (f.root_chord_m - f.tip_chord_m) / 2
    const le = f.position_m
    const fin = (sign: number) =>
      `M${le},${sign * R} L${le + sweep},${sign * (R + f.span_m)} L${le + sweep + f.tip_chord_m},${sign * (R + f.span_m)} L${le + f.root_chord_m},${sign * R} Z`
    return [<path key={`${i}u`} d={fin(-1)} />, <path key={`${i}d`} d={fin(1)} />]
  })

  const cg = rocket.dry_cg_m
  const stroke = vb.w / 600

  return (
    <figure className="space-y-2">
      <svg
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        className="w-full"
        style={{ maxHeight: 220 }}
        role="img"
        aria-label={`Side view of the rocket, ${L.toFixed(2)} m long`}
      >
        <g className="fill-surface-2 stroke-foreground" strokeWidth={stroke} strokeLinejoin="round">
          {finPaths}
          <polygon points={outline} />
        </g>
        {/* Nose-to-body joint, so the separate parts read. */}
        <line x1={rocket.nose.length_m} x2={rocket.nose.length_m} y1={-R} y2={R} className="stroke-muted-foreground" strokeWidth={stroke * 0.6} />
        <g aria-label="Dry centre of mass">
          <circle cx={cg} cy={0} r={R * 0.45} className="fill-background stroke-foreground" strokeWidth={stroke} />
          <path d={`M${cg - R * 0.45},0 A${R * 0.45},${R * 0.45} 0 0 1 ${cg},${-R * 0.45} L${cg},0 Z M${cg + R * 0.45},0 A${R * 0.45},${R * 0.45} 0 0 1 ${cg},${R * 0.45} L${cg},0 Z`} className="fill-foreground" />
        </g>
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        Drawn to scale, nose on the left. The quartered circle is the centre of mass without the motor.
      </figcaption>
    </figure>
  )
}
