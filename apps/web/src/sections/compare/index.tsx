import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { create } from 'zustand'
import { ticks } from '@/components/charts/bins'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { api, type Comparison, type ResultRecord, type Series } from '@/lib/api'
import { formatSI, fromSI, unitFor, type Quantity } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** Which two runs are compared. A is the baseline; differences read A to B. */
const usePick = create<{ a?: string; b?: string; set: (slot: 'a' | 'b', id: string) => void }>()((set) => ({
  set: (slot, id) => set({ [slot]: id }),
}))

const dateTime = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

function useRuns(allMissions: boolean) {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  return useQuery({
    queryKey: ['results', 'list', allMissions ? null : missionId],
    queryFn: () => api.listResults(allMissions ? undefined : missionId),
  })
}

/** The pick, defaulting to the two newest runs (older as A). */
function usePicked(runs: ResultRecord[] | undefined) {
  const { a, b } = usePick()
  const ids = new Set(runs?.map((r) => r.id))
  const pickedA = a && ids.has(a) ? a : runs?.[1]?.id
  const pickedB = b && ids.has(b) ? b : runs?.[0]?.id
  return { a: pickedA, b: pickedB }
}

export function Centre() {
  const [all] = useAllMissions()
  const runs = useRuns(all)
  const { a, b } = usePicked(runs.data)
  const cmp = useQuery({
    queryKey: ['results', 'compare', a, b],
    queryFn: () => api.compareResults(a!, b!),
    enabled: Boolean(a && b && a !== b),
    staleTime: Infinity,
  })

  if (runs.data && runs.data.length < 2) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          Compare needs two runs. Change something and run the single flight again, or include every mission's runs.
        </p>
      </div>
    )
  }
  const c = cmp.data
  return (
    <div className="h-full space-y-8 overflow-y-auto p-6">
      <ProblemNotice error={runs.error ?? cmp.error} />
      {a === b && <p className="text-sm text-muted-foreground">Choose two different runs in the pane.</p>}
      {c && (
        <>
          <Legend a={c.a} b={c.b} />
          <KeyNumbers a={c.a} b={c.b} />
          <Differences cmp={c} />
          <Charts a={c.a.id} b={c.b.id} />
        </>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/flight">
          Two stored single flights side by side, with every mission setting that differs between them. Runs are
          deterministic, so any difference in the numbers comes from a difference listed here (or from a different
          RocketPy or simcore version, shown under each run).
        </Explainer>
      </div>
    </div>
  )
}

function runName(r: ResultRecord) {
  return `${r.provenance.mission_name}, ${dateTime.format(new Date(r.provenance.computed_utc))}`
}

function Legend({ a, b }: { a: ResultRecord; b: ResultRecord }) {
  return (
    <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Legend">
      {[
        { label: 'A', r: a, color: 'bg-chart-1' },
        { label: 'B', r: b, color: 'bg-chart-2 [mask-image:repeating-linear-gradient(90deg,#000_0_6px,transparent_6px_10px)]' },
      ].map(({ label, r, color }) => (
        <li key={label} className="flex items-center gap-2">
          <span className={cn('h-0.5 w-6 rounded', color)} aria-hidden />
          <span className="font-medium">{label}</span>
          <span className="text-muted-foreground">
            {runName(r)} · RocketPy {r.provenance.rocketpy_version}
          </span>
        </li>
      ))}
    </ul>
  )
}

const NUMBERS: { label: string; get: (r: ResultRecord) => number | null | undefined; q: Quantity | null; digits: number; unit?: string }[] = [
  { label: 'Apogee', get: (r) => r.summary.apogee_agl_m, q: 'altitude', digits: 0 },
  { label: 'Rail exit velocity', get: (r) => r.summary.rail_exit_velocity_ms, q: 'speed', digits: 1 },
  { label: 'Stability at rail exit', get: (r) => r.summary.stability_margin_at_rail_exit_cal, q: null, digits: 2, unit: 'cal' },
  { label: 'Max Mach', get: (r) => r.summary.max_mach, q: null, digits: 2 },
  { label: 'Max acceleration', get: (r) => r.summary.max_acceleration_ms2, q: 'acceleration', digits: 0 },
  { label: 'Drift', get: (r) => r.summary.landing?.drift_distance_m, q: 'distance', digits: 0 },
  { label: 'Touchdown speed', get: (r) => r.summary.landing?.speed_ms, q: 'speed', digits: 1 },
]

function KeyNumbers({ a, b }: { a: ResultRecord; b: ResultRecord }) {
  const units = usePrefs((s) => s.display)
  const fmt = (v: number, q: Quantity | null, digits: number, unit?: string) =>
    q ? formatSI(v, q, units, digits) : `${v.toFixed(digits)}${unit ? ` ${unit}` : ''}`
  return (
    <section aria-label="Key numbers" className="space-y-2">
      <h2 className="text-sm font-semibold">Key numbers</h2>
      <div className="max-w-3xl overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="pb-1 font-normal" />
              <th className="pb-1 font-normal">A</th>
              <th className="pb-1 font-normal">B</th>
              <th className="pb-1 font-normal">B − A</th>
            </tr>
          </thead>
          <tbody>
            {NUMBERS.map((n) => {
              const va = n.get(a)
              const vb = n.get(b)
              if (va == null || vb == null) return null
              const d = vb - va
              const shownD = n.q ? fromSI(d, n.q, units) : d
              const pct = va !== 0 ? (100 * d) / Math.abs(va) : 0
              return (
                <tr key={n.label} className="border-t border-border">
                  <td className="py-1.5 pr-4">{n.label}</td>
                  <td className="py-1.5 pr-4 whitespace-nowrap">{fmt(va, n.q, n.digits, n.unit)}</td>
                  <td className="py-1.5 pr-4 whitespace-nowrap">{fmt(vb, n.q, n.digits, n.unit)}</td>
                  <td className="py-1.5 whitespace-nowrap text-muted-foreground">
                    {Math.abs(shownD) < 10 ** -n.digits / 2
                      ? 'same'
                      : `${shownD > 0 ? '+' : '−'}${Math.abs(shownD).toFixed(n.digits)}${n.q ? ` ${unitFor(n.q, units).symbol}` : ''} (${pct > 0 ? '+' : '−'}${Math.abs(pct).toFixed(1)}%)`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function show(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function Differences({ cmp }: { cmp: Comparison }) {
  return (
    <section aria-label="Settings that differ" className="space-y-2">
      <h2 className="text-sm font-semibold">What changed, A to B</h2>
      {!cmp.settings_known ? (
        <p className="text-sm text-muted-foreground">
          One of these runs was stored before runs kept their settings, so they can't be compared. Run it again to
          record them.
        </p>
      ) : cmp.differences.length === 0 ? (
        <p className="text-sm text-muted-foreground">The same mission settings: any difference is from the versions.</p>
      ) : (
        <div className="max-w-4xl overflow-x-auto">
          <table className="w-full text-sm">
            <tbody>
              {cmp.differences.map((d) => (
                <tr key={d.path} className="border-t border-border align-top">
                  <td className="py-1.5 pr-4 font-mono text-xs">{d.path}</td>
                  <td className="max-w-64 truncate py-1.5 pr-4 tabular-nums" title={show(d.a)}>
                    {show(d.a)}
                  </td>
                  <td className="max-w-64 truncate py-1.5 tabular-nums" title={show(d.b)}>
                    {show(d.b)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

const CHANNELS: { name: string; title: string; q: Quantity }[] = [
  { name: 'altitude_agl_m', title: 'Altitude above the pad', q: 'altitude' },
  { name: 'speed_ms', title: 'Speed', q: 'speed' },
  { name: 'vertical_velocity_ms', title: 'Vertical velocity', q: 'speed' },
]

function Charts({ a, b }: { a: string; b: string }) {
  const names = CHANNELS.map((c) => c.name)
  const sa = useQuery({ queryKey: ['results', a, 'series', names], queryFn: () => api.getSeries(a, names, 800), staleTime: Infinity })
  const sb = useQuery({ queryKey: ['results', b, 'series', names], queryFn: () => api.getSeries(b, names, 800), staleTime: Infinity })
  if (!sa.data || !sb.data) return null
  return (
    <div className="grid gap-6 xl:grid-cols-3">
      {CHANNELS.map((c) => (
        <OverlayChart
          key={c.name}
          title={c.title}
          q={c.q}
          a={sa.data.find((s) => s.name === c.name)!}
          b={sb.data.find((s) => s.name === c.name)!}
        />
      ))}
    </div>
  )
}

const H = 200
const PAD = { top: 10, right: 12, bottom: 26, left: 48 }

/** Two runs of one channel against time, with a crosshair readout of both. */
function OverlayChart({ title, q, a, b }: { title: string; q: Quantity; a: Series; b: Series }) {
  const units = usePrefs((s) => s.display)
  const host = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [hoverT, setHoverT] = useState<number | null>(null)
  useEffect(() => {
    const el = host.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const tMax = Math.max(a.t.at(-1) ?? 0, b.t.at(-1) ?? 0)
  const ys = [...a.y, ...b.y].map((v) => fromSI(v, q, units))
  const [y0, y1] = [Math.min(0, ...ys), Math.max(...ys)]
  const w = Math.max(width - PAD.left - PAD.right, 10)
  const h = H - PAD.top - PAD.bottom
  const x = (t: number) => PAD.left + (t / (tMax || 1)) * w
  const y = (v: number) => PAD.top + h - ((v - y0) / (y1 - y0 || 1)) * h
  const path = (s: Series) => s.t.map((t, i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(fromSI(s.y[i], q, units)).toFixed(1)}`).join('')
  const at = (s: Series, t: number) => {
    let i = 0
    while (i < s.t.length - 1 && s.t[i + 1] <= t) i++
    return s.t[i] <= t || i === 0 ? fromSI(s.y[i], q, units) : null
  }
  const symbol = unitFor(q, units).symbol
  return (
    <figure className="min-w-0 space-y-1">
      <figcaption className="text-sm font-medium">
        {title} <span className="text-muted-foreground">({symbol})</span>
      </figcaption>
      <div ref={host} className="relative">
        {width > 0 && (
          <svg
            width={width}
            height={H}
            role="img"
            aria-label={`${title}: run A and run B against time`}
            onPointerMove={(e) => {
              const t = ((e.clientX - e.currentTarget.getBoundingClientRect().left - PAD.left) / w) * tMax
              setHoverT(t >= 0 && t <= tMax ? t : null)
            }}
            onPointerLeave={() => setHoverT(null)}
          >
            {ticks(y0, y1, 4).map((v) => (
              <g key={v}>
                <line x1={PAD.left} x2={PAD.left + w} y1={y(v)} y2={y(v)} className="stroke-chart-grid" />
                <text x={PAD.left - 6} y={y(v)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[10px]">
                  {v.toLocaleString()}
                </text>
              </g>
            ))}
            {ticks(0, tMax, 5).map((t) => (
              <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                {t} s
              </text>
            ))}
            <path d={path(b)} fill="none" strokeWidth={2} strokeDasharray="6 4" className="stroke-chart-2" />
            <path d={path(a)} fill="none" strokeWidth={2} className="stroke-chart-1" />
            {hoverT != null && <line x1={x(hoverT)} x2={x(hoverT)} y1={PAD.top} y2={PAD.top + h} className="stroke-muted-foreground" />}
          </svg>
        )}
        {hoverT != null && (
          <div
            className="pointer-events-none absolute top-1 z-10 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-lg"
            style={{ left: Math.min(x(hoverT) + 8, width - 130) }}
          >
            <p className="font-medium tabular-nums">{hoverT.toFixed(1)} s</p>
            {[
              ['A', at(a, hoverT)],
              ['B', at(b, hoverT)],
            ].map(([label, v]) => (
              <p key={label as string} className="tabular-nums">
                <span className="text-muted-foreground">{label}:</span>{' '}
                {v == null ? '—' : `${(v as number).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${symbol}`}
              </p>
            ))}
          </div>
        )}
      </div>
    </figure>
  )
}

// --- Pane: choose the runs ------------------------------------------------------------

const useAllMissionsStore = create<{ all: boolean; setAll: (v: boolean) => void }>()((set) => ({
  all: false,
  setAll: (all) => set({ all }),
}))

function useAllMissions() {
  const { all, setAll } = useAllMissionsStore()
  return [all, setAll] as const
}

export function Pane() {
  const [all, setAll] = useAllMissions()
  const hasMission = useMissionStore((s) => s.draft !== null)
  const runs = useRuns(all || !hasMission)
  const { a, b } = usePicked(runs.data)
  const set = usePick((s) => s.set)
  const units = usePrefs((s) => s.display)
  return (
    <div className="space-y-4 p-4">
      <h2 className="text-sm font-semibold">Runs</h2>
      {hasMission && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
          Include every mission's runs
        </label>
      )}
      <ProblemNotice error={runs.error} />
      <ul className="space-y-2">
        {runs.data?.map((r) => (
          <li key={r.id} className="rounded-md border border-border p-2">
            <p className="text-sm">{runName(r)}</p>
            <p className="text-xs text-muted-foreground">
              Apogee {formatSI(r.summary.apogee_agl_m, 'altitude', units)}
              {r.ascent_only ? ', ascent only' : ''}
            </p>
            <div className="mt-1 flex gap-1" role="radiogroup" aria-label={`Use ${runName(r)} as`}>
              {(['a', 'b'] as const).map((slot) => {
                const on = (slot === 'a' ? a : b) === r.id
                return (
                  <button
                    key={slot}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    aria-label={`Run ${slot.toUpperCase()}`}
                    onClick={() => set(slot, r.id)}
                    className={cn(
                      'rounded px-2 py-0.5 text-xs',
                      on ? (slot === 'a' ? 'bg-chart-1 text-primary-foreground' : 'bg-chart-2 text-background') : 'text-muted-foreground hover:bg-surface-2',
                    )}
                  >
                    {slot.toUpperCase()}
                  </button>
                )
              })}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
