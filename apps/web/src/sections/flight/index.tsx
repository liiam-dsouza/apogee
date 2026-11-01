import { Play } from 'lucide-react'
import { useMemo, useState } from 'react'
import { TimeSeriesChart, type ChartEvent } from '@/components/charts/TimeSeriesChart'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import type { FlightSummary, ResultRecord, Series } from '@/lib/api'
import { formatSI, fromSI, unitFor, type Quantity, type UnitSystem } from '@/lib/units'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'
import { useFlightRuns, useResult, useRunFlight, useSeries } from './run'

interface Channel {
  name: string
  title: string
  quantity: Quantity | null
  /** Unit label when there is no quantity (dimensionless channels). */
  unit?: string
  /** Show only up to apogee: the channel means little under canopy. */
  ascentOnly?: boolean
  peak?: boolean
}

const CHANNELS: Channel[] = [
  { name: 'altitude_agl_m', title: 'Altitude above the pad', quantity: 'altitude', peak: true },
  { name: 'vertical_velocity_ms', title: 'Vertical velocity', quantity: 'speed' },
  { name: 'acceleration_ms2', title: 'Acceleration', quantity: 'acceleration' },
  { name: 'mach', title: 'Mach number', quantity: null, unit: '', ascentOnly: true },
  { name: 'dynamic_pressure_pa', title: 'Dynamic pressure', quantity: 'dynamic_pressure', ascentOnly: true },
  { name: 'stability_margin_cal', title: 'Stability margin', quantity: null, unit: 'cal', ascentOnly: true },
]

/** Issue paths -> the section that fixes them. */
function fixLink(path: string) {
  const section = path.split(/[.[]/)[0]
  const map: Record<string, [string, string]> = {
    rocket: ['/rocket', 'Edit the rocket'],
    motor: ['/motor', 'Edit the motor'],
    site: ['/site', 'Edit the site'],
    recovery: ['/recovery', 'Edit recovery'],
    environment: ['/weather', 'Edit the weather'],
  }
  const hit = map[section]
  return hit ? { href: hit[0], label: hit[1] } : null
}

function useCurrentRun() {
  const draft = useMissionStore((s) => s.draft)
  const run = useFlightRuns((s) => (draft?.meta.id ? s.byMission[draft.meta.id] : undefined))
  return { draft, run, stale: Boolean(run && draft && run.draft !== draft) }
}

export function Centre() {
  return (
    <RequireMission>
      <FlightResults />
    </RequireMission>
  )
}

function FlightResults() {
  const { run, stale } = useCurrentRun()
  const result = useResult(run?.resultId)
  const series = useSeries(run?.resultId, CHANNELS.map((c) => c.name))
  const units = usePrefs((s) => s.units)

  if (!run) {
    return (
      <div className="flex h-full flex-col justify-end gap-4 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          Run a flight to see its trajectory, key numbers and events.
        </p>
      </div>
    )
  }
  if (result.error || series.error) {
    return (
      <div className="p-6">
        <ProblemNotice error={result.error ?? series.error} />
      </div>
    )
  }
  if (!result.data || !series.data) return null

  const summary = result.data.summary
  return (
    // Refetch keeps the frame: the previous render stays, dimmed, with no layout jump.
    <div className="space-y-8 p-6" style={{ opacity: result.isFetching ? 0.6 : 1 }}>
      {stale && (
        <p role="status" className="rounded-md border border-caution/60 bg-caution/10 px-3 py-2 text-sm">
          The mission has changed since this flight was run. Run it again to update these numbers.
        </p>
      )}
      <Headline summary={summary} units={units} ascentOnly={result.data.ascent_only} />
      <Events summary={summary} units={units} />
      <Charts series={series.data} summary={summary} units={units} />
      <DataTable series={series.data} units={units} />
    </div>
  )
}

function Headline({ summary, units, ascentOnly }: { summary: FlightSummary; units: UnitSystem; ascentOnly: boolean }) {
  const apogee = unitFor('altitude', units)
  const landing = summary.landing
  const ascent: [string, string][] = [
    ['Rail exit velocity', formatSI(summary.rail_exit_velocity_ms, 'speed', units, 1)],
    ['Stability at rail exit', `${summary.stability_margin_at_rail_exit_cal.toFixed(2)} cal`],
    ['Max Mach', summary.max_mach.toFixed(2)],
    ['Max dynamic pressure', formatSI(summary.max_dynamic_pressure_pa, 'dynamic_pressure', units, 1)],
    ['Max acceleration', formatSI(summary.max_acceleration_ms2, 'acceleration', units, 0)],
  ]
  const descent: [string, string][] = landing
    ? [
        ['Drift from pad', formatSI(landing.drift_distance_m, 'distance', units, 0)],
        ['Touchdown speed', formatSI(landing.speed_ms, 'speed', units, 1)],
        ['Landing energy', formatSI(landing.kinetic_energy_j, 'energy', units, 0)],
        ['Flight time', `${landing.flight_time_s.toFixed(1)} s`],
      ]
    : []
  return (
    <section aria-label="Key numbers" className="space-y-5">
      <div>
        <p className="text-sm text-muted-foreground">Apogee above the pad</p>
        {/* Hero figure: same sans, proportional digits (the body defaults to tabular). */}
        <p className="text-6xl font-semibold tracking-tight" style={{ fontFeatureSettings: '"tnum" 0' }}>
          {Math.round(fromSI(summary.apogee_agl_m, 'altitude', units)).toLocaleString()}{' '}
          <span className="text-2xl font-medium text-muted-foreground">{apogee.symbol}</span>
        </p>
        <p className="text-sm text-muted-foreground">at {summary.apogee_time_s.toFixed(1)} s</p>
      </div>
      <TileGroup title="Ascent" tiles={ascent} />
      {ascentOnly ? (
        <p className="text-sm text-muted-foreground">Ascent only: the flight stopped at apogee, so there is no landing data.</p>
      ) : (
        <TileGroup title="Descent and landing" tiles={descent} />
      )}
    </section>
  )
}

function TileGroup({ title, tiles }: { title: string; tiles: [string, string][] }) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold">{title}</h2>
      <dl className="grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-3">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-md border border-border bg-surface px-3 py-2">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="text-lg font-semibold" style={{ fontFeatureSettings: '"tnum" 0' }}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function Events({ summary, units }: { summary: FlightSummary; units: UnitSystem }) {
  const rows: [string, number, string][] = [
    ['Ignition', 0, ''],
    ['Burnout', summary.burnout_time_s, ''],
    ['Apogee', summary.apogee_time_s, formatSI(summary.apogee_agl_m, 'altitude', units, 0)],
    ...(summary.parachute_events ?? []).map(
      (e) => [`${e.name} deploys`, e.triggered_s, formatSI(e.triggered_agl_m, 'altitude', units, 0)] as [string, number, string],
    ),
  ]
  if (summary.landing) rows.push(['Touchdown', summary.landing.flight_time_s, ''])
  rows.sort((a, b) => a[1] - b[1])
  return (
    <section aria-label="Events">
      <h2 className="mb-2 text-sm font-semibold">Events</h2>
      <table className="w-full max-w-xl text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-1 font-normal">Event</th>
            <th className="py-1 text-right font-normal">Time</th>
            <th className="py-1 text-right font-normal">Altitude</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map(([name, t, alt]) => (
            <tr key={name} className="border-t border-border">
              <td className="py-1.5">{name}</td>
              <td className="py-1.5 text-right">{t.toFixed(2)} s</td>
              <td className="py-1.5 text-right text-muted-foreground">{alt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function convert(s: Series, ch: Channel, units: UnitSystem, tMax: number) {
  const t: number[] = []
  const y: number[] = []
  for (let i = 0; i < s.t.length; i++) {
    if (s.t[i] > tMax) break
    t.push(s.t[i])
    y.push(ch.quantity ? fromSI(s.y[i], ch.quantity, units) : s.y[i])
  }
  return { t, y, unit: ch.quantity ? unitFor(ch.quantity, units).symbol : (ch.unit ?? '') }
}

function Charts({ series, summary, units }: { series: Series[]; summary: FlightSummary; units: UnitSystem }) {
  const events = useMemo<ChartEvent[]>(
    () => [
      { t: summary.burnout_time_s, label: 'Burnout' },
      { t: summary.apogee_time_s, label: 'Apogee' },
      ...(summary.parachute_events ?? [])
        .filter((e) => Math.abs(e.triggered_s - summary.apogee_time_s) > 0.5)
        .map((e) => ({ t: e.triggered_s, label: e.name })),
    ],
    [summary],
  )
  const prepared = useMemo(
    () =>
      CHANNELS.map((ch) => {
        const s = series.find((x) => x.name === ch.name)!
        const tMax = ch.ascentOnly ? summary.apogee_time_s : Infinity
        return { ch, ...convert(s, ch, units, tMax), events: events.filter((e) => e.t <= tMax) }
      }),
    [series, summary, units, events],
  )
  return (
    <section aria-label="Trajectory charts" className="grid gap-x-8 gap-y-6 xl:grid-cols-2">
      {prepared.map(({ ch, t, y, unit, events: ev }) => (
        <TimeSeriesChart
          key={ch.name}
          title={ch.ascentOnly ? `${ch.title}, ascent` : ch.title}
          unit={unit}
          t={t}
          y={y}
          events={ev}
          markPeak={ch.peak}
          syncKey="single-flight"
        />
      ))}
    </section>
  )
}

/** The charts' table-view twin: every channel at common times, so no value is hover-only. */
function DataTable({ series, units }: { series: Series[]; units: UnitSystem }) {
  const [open, setOpen] = useState(false)
  const rows = useMemo(() => {
    if (!open) return []
    const base = series.find((s) => s.name === 'altitude_agl_m')!
    const tEnd = base.t[base.t.length - 1]
    const times = Array.from({ length: 61 }, (_, i) => (tEnd * i) / 60)
    const interp = (s: Series, t: number) => {
      let j = s.t.findIndex((x) => x >= t)
      if (j <= 0) return s.y[Math.max(j, 0)]
      const f = (t - s.t[j - 1]) / (s.t[j] - s.t[j - 1])
      return s.y[j - 1] + f * (s.y[j] - s.y[j - 1])
    }
    return times.map((t) => ({ t, values: CHANNELS.map((ch) => interp(series.find((s) => s.name === ch.name)!, t)) }))
  }, [open, series])

  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)} className="text-sm">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Show the data as a table</summary>
      {open && (
        <div className="mt-3 max-h-96 overflow-auto rounded-md border border-border">
          <table className="w-full text-right tabular-nums">
            <thead className="sticky top-0 bg-surface text-xs text-muted-foreground">
              <tr>
                <th className="px-2 py-1 font-normal">Time (s)</th>
                {CHANNELS.map((ch) => (
                  <th key={ch.name} className="px-2 py-1 font-normal">
                    {ch.title}
                    {(ch.quantity || ch.unit) && ` (${ch.quantity ? unitFor(ch.quantity, units).symbol : ch.unit})`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.t} className="border-t border-border">
                  <td className="px-2 py-1">{r.t.toFixed(1)}</td>
                  {r.values.map((v, i) => (
                    <td key={CHANNELS[i].name} className="px-2 py-1">
                      {(CHANNELS[i].quantity ? fromSI(v, CHANNELS[i].quantity!, units) : v).toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <RunPane />
    </RequireMission>
  )
}

function RunPane() {
  const { draft, run } = useCurrentRun()
  const [ascentOnly, setAscentOnly] = useState(false)
  const mutation = useRunFlight()
  const result = useResult(run?.resultId)

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <Button
          variant="primary"
          className="w-full"
          disabled={!draft || mutation.isPending}
          onClick={() => draft && mutation.mutate({ draft, ascentOnly })}
        >
          <Play />
          {mutation.isPending ? 'Simulating' : 'Run flight'}
        </Button>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={ascentOnly} onChange={(e) => setAscentOnly(e.target.checked)} />
          <span>
            Ascent only
            <span className="block text-xs text-muted-foreground">Stops at apogee: faster, but no landing data.</span>
          </span>
        </label>
        <p className="text-xs text-muted-foreground">Runs the mission as it is now, including unsaved changes.</p>
        {run?.cached && !mutation.isPending && (
          <p className="text-xs text-muted-foreground">Same inputs as an earlier run, so its stored result was reused.</p>
        )}
        <ProblemNotice error={mutation.error} fixLink={fixLink} />
      </section>
      {result.data && <ProvenancePanel record={result.data} />}
      <Explainer methodsHref="/docs/methods/flight">
        A single deterministic flight with the nominal value of every input, simulated by RocketPy in six degrees of
        freedom. Useful for checking the design; not a prediction of what will happen on the day, because it ignores
        uncertainty in wind, motor and drag. The Dispersion section accounts for that.
      </Explainer>
    </div>
  )
}

function ProvenancePanel({ record }: { record: ResultRecord }) {
  const p = record.provenance
  const rows: [string, string][] = [
    ['Mission', p.mission_name],
    ['Config hash', p.mission_hash.slice(0, 16)],
    ['Atmosphere', p.atmosphere],
    ['Thrust curve', p.thrust_curve ? p.thrust_curve.slice(0, 16) : 'none'],
    ['Drag', p.drag],
    ['RocketPy', p.rocketpy_version],
    ['simcore', p.simcore_version],
    ['Build', p.git_sha],
    ['Seed', p.seed == null ? 'none (deterministic)' : String(p.seed)],
    ['Computed', new Date(p.computed_utc).toLocaleString()],
  ]
  return (
    <section aria-label="Where these numbers came from" className="space-y-2">
      <h2 className="text-sm font-semibold">Where these numbers came from</h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="break-words">{v}</dd>
          </div>
        ))}
      </dl>
      {record.warnings.length > 0 && (
        <ul className="text-xs text-caution">
          {record.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
