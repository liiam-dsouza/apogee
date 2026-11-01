import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { usePrefs } from '@/stores/prefs'

export interface ChartEvent {
  t: number
  label: string
}

const HEIGHT = 168

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function withAlpha(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

const formatValue = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 10 ? 2 : 0 })

/**
 * One channel against time. Small multiples share a `syncKey`, so the
 * crosshair (and each header's readout) moves across all of them together.
 */
export function TimeSeriesChart({
  title,
  unit,
  t,
  y,
  events = [],
  markPeak = false,
  syncKey,
}: {
  title: string
  unit: string
  t: number[]
  y: number[]
  events?: ChartEvent[]
  /** Mark and label the maximum (e.g. apogee). Labels stay selective. */
  markPeak?: boolean
  syncKey: string
}) {
  const host = useRef<HTMLDivElement>(null)
  const theme = usePrefs((s) => s.theme)
  const [readout, setReadout] = useState<{ t: number; y: number } | null>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const series = token('--chart-1')
    const grid = token('--chart-grid')
    const ink = token('--muted-foreground')
    const surface = token('--background')
    const font = `12px ${getComputedStyle(document.body).fontFamily}`
    const peakIdx = markPeak ? y.reduce((best, v, i) => (v > y[best] ? i : best), 0) : -1

    const axis = { stroke: ink, font, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid, width: 1 } }

    const plot = new uPlot(
      {
        width: el.clientWidth,
        height: HEIGHT,
        legend: { show: false },
        cursor: {
          sync: { key: syncKey },
          points: { size: 8, fill: series, stroke: surface, width: 2 },
          y: false,
        },
        scales: { x: { time: false } },
        axes: [
          { ...axis, values: (_, ticks) => ticks.map((v) => `${v} s`) },
          { ...axis, size: 56, values: (_, ticks) => ticks.map(formatValue) },
        ],
        series: [
          {},
          { stroke: series, width: 2, fill: withAlpha(series, 0.1), points: { show: false } },
        ],
        hooks: {
          setCursor: [
            (u) => {
              const i = u.cursor.idx
              // A synced cursor beyond this chart's window (e.g. descent, on an
              // ascent-only chart) clamps to the last point; show nothing instead.
              const at = u.cursor.left != null && u.cursor.left >= 0 ? u.posToVal(u.cursor.left, 'x') : null
              const xs = u.data[0]
              const inside = at != null && at >= xs[0] && at <= xs[xs.length - 1]
              setReadout(i == null || !inside ? null : { t: xs[i], y: u.data[1][i] as number })
            },
          ],
          draw: [
            (u) => {
              const { ctx } = u
              const { left, top, width, height } = u.bbox
              const dpr = devicePixelRatio
              const pad = 4 * dpr
              const lineH = 13 * dpr
              ctx.save()
              ctx.font = `${11 * dpr}px ${getComputedStyle(document.body).fontFamily}`
              // uPlot leaves textAlign 'center' from its axis labels; every box below assumes 'left'.
              ctx.textAlign = 'left'
              ctx.textBaseline = 'top'

              // Labels claim boxes; a label that would overlap one already
              // placed is dropped (its line stays; the events table names it).
              const taken: { x0: number; x1: number; y0: number; y1: number }[] = []
              const free = (b: (typeof taken)[number]) =>
                taken.every((o) => b.x1 <= o.x0 || b.x0 >= o.x1 || b.y1 <= o.y0 || b.y0 >= o.y1)

              // The peak is the one direct label that matters: place it first.
              let peak: { px: number; py: number; text: string } | null = null
              if (peakIdx >= 0) {
                const px = u.valToPos(t[peakIdx], 'x', true)
                const py = u.valToPos(y[peakIdx], 'y', true)
                const text = `${formatValue(y[peakIdx])}${unit ? ` ${unit}` : ''}`
                const w = ctx.measureText(text).width
                // Above and right of the dot: the curve falls away to the right.
                const box = { x0: px + 6 * dpr, x1: px + 6 * dpr + w, y0: py - 6 * dpr - lineH, y1: py - 6 * dpr }
                taken.push(box)
                peak = { px, py, text }
              }

              for (const ev of events) {
                const x = Math.round(u.valToPos(ev.t, 'x', true))
                ctx.strokeStyle = ink
                ctx.globalAlpha = 0.5
                ctx.lineWidth = dpr
                ctx.beginPath()
                ctx.moveTo(x, top)
                ctx.lineTo(x, top + height)
                ctx.stroke()
                ctx.globalAlpha = 1
                const w = ctx.measureText(ev.label).width
                // Right of the line, or left of it at the right edge.
                const right = { x0: x + pad, x1: x + pad + w, y0: top, y1: top + lineH }
                const leftSide = { x0: x - pad - w, x1: x - pad, y0: top, y1: top + lineH }
                const box = right.x1 <= left + width ? right : leftSide
                if (box.x0 >= left && free(box)) {
                  taken.push({ ...box, x0: box.x0 - pad, x1: box.x1 + pad })
                  ctx.fillStyle = ink
                  ctx.fillText(ev.label, box.x0, top + 2 * dpr)
                }
              }

              if (peak) {
                ctx.beginPath()
                ctx.arc(peak.px, peak.py, 4 * dpr, 0, Math.PI * 2)
                ctx.fillStyle = series
                ctx.strokeStyle = surface
                ctx.lineWidth = 2 * dpr
                ctx.fill()
                ctx.stroke()
                ctx.fillStyle = token('--foreground')
                ctx.textBaseline = 'bottom'
                ctx.fillText(peak.text, peak.px + 6 * dpr, peak.py - 6 * dpr)
              }
              ctx.restore()
            },
          ],
        },
      },
      [t, y],
      el,
    )

    const resize = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height: HEIGHT }))
    resize.observe(el)
    return () => {
      resize.disconnect()
      plot.destroy()
    }
  }, [t, y, events, markPeak, syncKey, unit, theme])

  return (
    <figure className="space-y-1">
      <figcaption className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium text-foreground">
          {title} {unit && <span className="font-normal text-muted-foreground">({unit})</span>}
        </span>
        <span className="tabular-nums text-muted-foreground" aria-live="off">
          {readout ? (
            <>
              <strong className="font-semibold text-foreground">
                {formatValue(readout.y)}
                {unit && ` ${unit}`}
              </strong>{' '}
              at {readout.t.toFixed(2)} s
            </>
          ) : (
            ' '
          )}
        </span>
      </figcaption>
      <div ref={host} className="w-full" role="img" aria-label={`${title} against time`} />
    </figure>
  )
}
