import { useEffect, useMemo, useRef, useState } from 'react'
import { binValues, quantile, ticks } from './bins'

const HEIGHT = 180
const PAD = { top: 22, right: 12, bottom: 28, left: 36 }

/**
 * One output's spread across a campaign. The median and the 5th and 95th
 * percentiles are marked; hover a bar for its count and range.
 */
export function Histogram({
  title,
  values,
  format,
  axisFormat = format,
}: {
  title: string
  /** In display units already. */
  values: number[]
  format: (v: number) => string
  axisFormat?: (v: number) => string
}) {
  const host = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  useEffect(() => {
    const el = host.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const bins = useMemo(() => binValues(values), [values])
  const sorted = useMemo(() => [...values].sort((a, b) => a - b), [values])
  if (bins.length === 0) return null
  const lo = bins[0].lo
  const hi = bins[bins.length - 1].hi === lo ? lo + 1 : bins[bins.length - 1].hi
  const maxCount = Math.max(...bins.map((b) => b.count))
  const w = Math.max(width - PAD.left - PAD.right, 10)
  const h = HEIGHT - PAD.top - PAD.bottom
  const x = (v: number) => PAD.left + ((v - lo) / (hi - lo)) * w
  const y = (c: number) => PAD.top + h - (c / maxCount) * h
  const marks = [
    { q: 0.05, label: '5%' },
    { q: 0.5, label: 'median' },
    { q: 0.95, label: '95%' },
  ].map((m) => ({ ...m, v: quantile(sorted, m.q) }))
  const hovered = hover == null ? null : bins[hover]

  return (
    <figure className="min-w-0 space-y-1">
      <figcaption className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{title}</span>
        <span className="text-xs text-muted-foreground tabular-nums">median {format(marks[1].v)}</span>
      </figcaption>
      <div ref={host} className="relative">
        {width > 0 && (
          <svg width={width} height={HEIGHT} role="img" aria-label={`${title}: histogram of ${values.length} samples`}>
            {ticks(0, maxCount, 3).filter(Number.isInteger).map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={PAD.left + w} y1={y(t)} y2={y(t)} className="stroke-chart-grid" />
                <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[10px]">
                  {t}
                </text>
              </g>
            ))}
            {bins.map((b, i) => {
              const bx = x(b.lo) + 1
              const bw = Math.max(1, x(b.hi) - x(b.lo) - 2)
              const top = y(b.count)
              const r = Math.min(2, bw / 2, PAD.top + h - top)
              return (
                <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
                  {b.count > 0 && (
                    <path
                      d={`M${bx},${PAD.top + h}V${top + r}q0,-${r} ${r},-${r}h${bw - 2 * r}q${r},0 ${r},${r}V${PAD.top + h}Z`}
                      className={hover === i ? 'fill-chart-1' : 'fill-chart-1/75'}
                    />
                  )}
                  {/* Hit target: the whole column, taller than the bar. */}
                  <rect x={x(b.lo)} y={PAD.top} width={x(b.hi) - x(b.lo)} height={h} fill="transparent" />
                </g>
              )
            })}
            {marks.map((m) => (
              <g key={m.label} className="pointer-events-none">
                <line
                  x1={x(m.v)}
                  x2={x(m.v)}
                  y1={PAD.top - 4}
                  y2={PAD.top + h}
                  strokeWidth={m.q === 0.5 ? 1.5 : 1}
                  strokeDasharray={m.q === 0.5 ? undefined : '3 3'}
                  className="stroke-foreground"
                />
                <text
                  x={x(m.v)}
                  y={PAD.top - 8}
                  textAnchor={m.q === 0.05 ? 'end' : m.q === 0.95 ? 'start' : 'middle'}
                  className="fill-muted-foreground text-[10px]"
                >
                  {m.label}
                </text>
              </g>
            ))}
            {ticks(lo, hi, 4).map((t) => (
              <text
                key={t}
                x={x(t)}
                y={HEIGHT - 8}
                // Keep the end labels inside the chart.
                textAnchor={x(t) > PAD.left + w - 24 ? 'end' : x(t) < PAD.left + 24 ? 'start' : 'middle'}
                className="fill-muted-foreground text-[10px]"
              >
                {axisFormat(t)}
              </text>
            ))}
          </svg>
        )}
        {hovered && (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-lg"
            style={{ left: x((hovered.lo + hovered.hi) / 2), top: y(hovered.count) - 6 }}
          >
            <p className="font-medium tabular-nums">
              {hovered.count} sample{hovered.count === 1 ? '' : 's'}
            </p>
            <p className="tabular-nums text-muted-foreground">
              {format(hovered.lo)} to {format(hovered.hi)}
            </p>
          </div>
        )}
      </div>
    </figure>
  )
}
