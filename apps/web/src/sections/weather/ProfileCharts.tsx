import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { formatSI, fromSI, unitFor } from '@/lib/units'
import { usePrefs } from '@/stores/prefs'
import { toWindPoints, type WindPoint } from './wind'

/** Linear interpolation of a profile at height h (clamped at the ends). */
function at(points: WindPoint[], h: number): WindPoint | null {
  if (points.length === 0) return null
  if (h <= points[0].h) return points[0]
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]
    const b = points[i]
    if (h <= b.h) {
      const t = (h - a.h) / (b.h - a.h)
      const u = a.u + t * (b.u - a.u)
      const v = a.v + t * (b.v - a.v)
      return toWindPoints([{ altitude_m: h, wind_u_ms: u, wind_v_ms: v, pressure_pa: 1, temperature_k: 1 }], 0)[0]
    }
  }
  return points[points.length - 1]
}

/** Points from the pad to maxH, with the profile interpolated exactly at maxH. */
function clip(points: WindPoint[], maxH: number): WindPoint[] {
  const inside = points.filter((p) => p.h >= 0 && p.h < maxH)
  const top = at(points, maxH)
  return top && points[points.length - 1].h >= maxH ? [...inside, top] : inside
}

/** Height labels for the hodograph, dropping any that would sit on top of one already placed. */
function spacedLabels(
  points: WindPoint[],
  heights: number[],
  px: (p: WindPoint) => number,
  py: (p: WindPoint) => number,
): { h: number; p: WindPoint }[] {
  const placed: { h: number; p: WindPoint }[] = []
  for (const h of heights) {
    const p = at(points, h)
    if (p && placed.every((q) => Math.hypot(px(q.p) - px(p), py(q.p) - py(p)) > 48)) placed.push({ h, p })
  }
  return placed
}

/** Up to ~`count` round tick values covering [lo, hi]. */
function ticks(lo: number, hi: number, count = 5): number[] {
  const span = hi - lo || 1
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(10)))
  return out
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

export interface ProfileSeries {
  label: string
  points: WindPoint[]
  /** The flown profile is the data; a dashed muted line is reference context. */
  role: 'flown' | 'reference'
}

const HEIGHT = 340
const PAD = { top: 12, right: 16, bottom: 32, left: 56 }

/**
 * One wind quantity against height above the pad. Height is vertical, as it is
 * in the sky. Hover reads every series at the pointer's height.
 */
function ProfilePlot({
  title,
  series,
  maxH,
  value,
  domain,
  format,
  axisFormat,
  wrap,
  measured,
}: {
  title: string
  series: ProfileSeries[]
  maxH: number
  value: (p: WindPoint) => number
  domain: [number, number]
  format: (v: number) => string
  axisFormat: (v: number) => string
  /** Direction wraps at 360°: break the line rather than draw across the chart. */
  wrap?: boolean
  measured?: { h: number; value: number; label: string }
}) {
  const [host, width] = useWidth<HTMLDivElement>()
  const units = usePrefs((s) => s.display)
  const [hoverH, setHoverH] = useState<number | null>(null)
  const w = Math.max(width - PAD.left - PAD.right, 10)
  const h = HEIGHT - PAD.top - PAD.bottom
  const x = (v: number) => PAD.left + ((v - domain[0]) / (domain[1] - domain[0])) * w
  const y = (alt: number) => PAD.top + h - (alt / maxH) * h
  const altUnit = unitFor('altitude', units)

  const paths = series.map((s) => {
    const pts = clip(s.points, maxH)
    let d = ''
    pts.forEach((p, i) => {
      const jump = wrap && i > 0 && Math.abs(value(p) - value(pts[i - 1])) > 180
      d += `${i === 0 || jump ? 'M' : 'L'}${x(value(p)).toFixed(1)},${y(p.h).toFixed(1)}`
    })
    return { ...s, d }
  })

  const readout = hoverH == null ? null : series.map((s) => ({ s, p: at(s.points, hoverH) }))

  return (
    <figure className="min-w-0 space-y-1">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <div ref={host} className="relative">
        {width > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={`${title} against height above the pad`}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const alt = ((PAD.top + h - (e.clientY - r.top)) / h) * maxH
              setHoverH(alt >= 0 && alt <= maxH ? alt : null)
            }}
            onPointerLeave={() => setHoverH(null)}
            className="touch-none"
          >
            {ticks(0, fromSI(maxH, 'altitude', units)).map((t) => {
              const alt = t * (altUnit.toSI(1) - altUnit.toSI(0))
              return (
                <g key={t}>
                  <line x1={PAD.left} x2={PAD.left + w} y1={y(alt)} y2={y(alt)} className="stroke-chart-grid" />
                  <text x={PAD.left - 8} y={y(alt)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-xs">
                    {t.toLocaleString()}
                  </text>
                </g>
              )
            })}
            {ticks(domain[0], domain[1], wrap ? 4 : 5).map((t) => (
              <g key={t}>
                <line x1={x(t)} x2={x(t)} y1={PAD.top} y2={PAD.top + h} className="stroke-chart-grid" />
                <text x={x(t)} y={HEIGHT - 10} textAnchor="middle" className="fill-muted-foreground text-xs">
                  {axisFormat(t)}
                </text>
              </g>
            ))}
            <text x={8} y={PAD.top} dy="0.7em" className="fill-muted-foreground text-xs">
              {altUnit.symbol}
            </text>
            {paths.map((p) => (
              <path
                key={p.label}
                d={p.d}
                fill="none"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeDasharray={p.role === 'reference' ? '5 4' : undefined}
                className={p.role === 'reference' ? 'stroke-muted-foreground' : 'stroke-chart-1'}
              />
            ))}
            {measured && measured.h <= maxH && (
              <circle
                cx={x(measured.value)}
                cy={y(measured.h)}
                r={5}
                strokeWidth={2}
                className="fill-chart-1 stroke-background"
              >
                <title>{measured.label}</title>
              </circle>
            )}
            {hoverH != null && (
              <line x1={PAD.left} x2={PAD.left + w} y1={y(hoverH)} y2={y(hoverH)} className="stroke-muted-foreground" strokeWidth={1} />
            )}
            {readout?.map(({ s, p }) =>
              p ? (
                <circle
                  key={s.label}
                  cx={x(value(p))}
                  cy={y(hoverH!)}
                  r={4}
                  strokeWidth={2}
                  className={s.role === 'reference' ? 'fill-muted-foreground stroke-background' : 'fill-chart-1 stroke-background'}
                />
              ) : null,
            )}
          </svg>
        )}
        {readout && hoverH != null && (
          <Tooltip top={y(hoverH)} left={PAD.left + 8}>
            <p className="font-medium">{formatSI(hoverH, 'altitude', units)} above the pad</p>
            {readout.map(({ s, p }) =>
              p ? (
                <p key={s.label} className="tabular-nums">
                  <span className="text-muted-foreground">{s.label}:</span> {format(value(p))}
                </p>
              ) : null,
            )}
          </Tooltip>
        )}
      </div>
    </figure>
  )
}

function Tooltip({ top, left, children }: { top: number; left: number; children: ReactNode }) {
  return (
    <div
      className="pointer-events-none absolute z-10 -translate-y-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-lg"
      style={{ top: top - 6, left }}
    >
      {children}
    </div>
  )
}

/**
 * The wind as a path in the (east, north) plane: each point is the wind vector
 * at one height. A straight path is a constant direction; curvature is veer or back.
 */
function Hodograph({ series, maxH, labelHeights }: { series: ProfileSeries[]; maxH: number; labelHeights: number[] }) {
  const [host, width] = useWidth<HTMLDivElement>()
  const units = usePrefs((s) => s.display)
  const [hover, setHover] = useState<{ p: WindPoint; s: ProfileSeries } | null>(null)
  const size = Math.min(width, HEIGHT)
  const inRange = series.map((s) => ({ ...s, points: clip(s.points, maxH) }))
  const maxSpeed = Math.max(1, ...inRange.flatMap((s) => s.points.map((p) => p.speed)))
  const ringStep = ticks(0, maxSpeed, 3)[1] ?? maxSpeed
  const radius = Math.ceil(maxSpeed / ringStep) * ringStep
  const c = size / 2
  const k = (c - 22) / radius
  // The vector points where the wind blows to; north is up.
  const px = (p: WindPoint) => c + p.u * k
  const py = (p: WindPoint) => c - p.v * k
  const flown = inRange.find((s) => s.role === 'flown')

  return (
    <figure className="min-w-0 space-y-1">
      <figcaption className="text-sm font-medium">Hodograph</figcaption>
      <div ref={host} className="relative">
        {size > 0 && (
          <svg width={size} height={size} role="img" aria-label="Hodograph: wind vector at each height">
            {Array.from({ length: Math.round(radius / ringStep) }, (_, i) => (i + 1) * ringStep).map((r) => (
              <g key={r}>
                <circle cx={c} cy={c} r={r * k} fill="none" className="stroke-chart-grid" />
                <text x={c + 4} y={c - r * k} dy="1em" className="fill-muted-foreground text-xs">
                  {formatSI(r, 'speed', units)}
                </text>
              </g>
            ))}
            <line x1={c} x2={c} y1={8} y2={size - 8} className="stroke-chart-grid" />
            <line x1={8} x2={size - 8} y1={c} y2={c} className="stroke-chart-grid" />
            <text x={c} y={10} textAnchor="middle" className="fill-muted-foreground text-xs">
              N
            </text>
            {inRange.map((s) => (
              <polyline
                key={s.label}
                points={s.points.map((p) => `${px(p).toFixed(1)},${py(p).toFixed(1)}`).join(' ')}
                fill="none"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeDasharray={s.role === 'reference' ? '5 4' : undefined}
                className={s.role === 'reference' ? 'stroke-muted-foreground' : 'stroke-chart-1'}
              />
            ))}
            {flown &&
              spacedLabels(flown.points, labelHeights.filter((lh) => lh <= maxH), px, py).map(({ h: lh, p }) => (
                <g key={lh}>
                  <circle cx={px(p)} cy={py(p)} r={3.5} strokeWidth={2} className="fill-chart-1 stroke-background" />
                  <text x={px(p) + 7} y={py(p)} dy="0.32em" className="fill-muted-foreground text-xs">
                    {formatSI(lh, 'altitude', units)}
                  </text>
                </g>
              ))}
            {inRange.flatMap((s) =>
              s.points.map((p, i) => (
                <circle
                  key={`${s.label}-${i}`}
                  cx={px(p)}
                  cy={py(p)}
                  r={8}
                  fill="transparent"
                  onPointerEnter={() => setHover({ p, s })}
                  onPointerLeave={() => setHover(null)}
                />
              )),
            )}
          </svg>
        )}
        {hover && (
          <Tooltip top={py(hover.p)} left={Math.min(px(hover.p), size - 140)}>
            <p className="font-medium">
              {hover.s.label}, {formatSI(hover.p.h, 'altitude', units)} above the pad
            </p>
            <p className="tabular-nums">
              {formatSI(hover.p.speed, 'speed', units, 1)} from {Math.round(hover.p.from)}°
            </p>
          </Tooltip>
        )}
      </div>
    </figure>
  )
}

export function WindCharts({
  series,
  maxH,
  measured,
}: {
  series: ProfileSeries[]
  maxH: number
  measured?: { h: number; speed: number; from: number }
}) {
  const units = usePrefs((s) => s.display)
  const maxSpeed = useMemo(
    () => Math.max(1, ...series.flatMap((s) => s.points.filter((p) => p.h <= maxH).map((p) => p.speed))),
    [series, maxH],
  )
  const speedTop = ticks(0, fromSI(maxSpeed, 'speed', units), 4).at(-1) ?? maxSpeed
  const speedDomain: [number, number] = [0, Math.max(unitFor('speed', units).toSI(speedTop), maxSpeed)]
  const labelHeights = [0, maxH / 4, maxH / 2, maxH]

  return (
    <div className="space-y-3">
      <Legend series={series} measured={Boolean(measured)} />
      <div className="grid gap-6 lg:grid-cols-3">
        <ProfilePlot
          title="Wind speed"
          series={series}
          maxH={maxH}
          value={(p) => p.speed}
          domain={speedDomain}
          format={(v) => formatSI(v, 'speed', units, 1)}
          axisFormat={(v) => fromSI(v, 'speed', units).toLocaleString(undefined, { maximumFractionDigits: 1 })}
          measured={measured && { h: measured.h, value: measured.speed, label: 'Measured' }}
        />
        <ProfilePlot
          title="Wind from"
          series={series}
          maxH={maxH}
          value={(p) => p.from}
          domain={[0, 360]}
          format={(v) => `${Math.round(v)}°`}
          axisFormat={(v) => ({ 0: 'N', 90: 'E', 180: 'S', 270: 'W', 360: 'N' })[v] ?? `${v}°`}
          wrap
          measured={measured && { h: measured.h, value: measured.from, label: 'Measured' }}
        />
        <Hodograph series={series} maxH={maxH} labelHeights={labelHeights} />
      </div>
    </div>
  )
}

function Legend({ series, measured }: { series: ProfileSeries[]; measured: boolean }) {
  if (series.length < 2 && !measured) return null
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      {series.map((s) => (
        <li key={s.label} className="flex items-center gap-2">
          <svg width="24" height="8" aria-hidden>
            <line
              x1="0"
              x2="24"
              y1="4"
              y2="4"
              strokeWidth={2}
              strokeDasharray={s.role === 'reference' ? '5 4' : undefined}
              className={s.role === 'reference' ? 'stroke-muted-foreground' : 'stroke-chart-1'}
            />
          </svg>
          {s.label}
        </li>
      ))}
      {measured && (
        <li className="flex items-center gap-2">
          <svg width="10" height="10" aria-hidden>
            <circle cx="5" cy="5" r="4" className="fill-chart-1" />
          </svg>
          Measured
        </li>
      )}
    </ul>
  )
}
