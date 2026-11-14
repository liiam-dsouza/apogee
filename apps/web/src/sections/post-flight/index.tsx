import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, FileText, FileUp, Printer, Sigma } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { create } from 'zustand'
import { ticks } from '@/components/charts/bins'
import { TimeSeriesChart, type ChartEvent } from '@/components/charts/TimeSeriesChart'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import {
  api,
  type ChannelComparison,
  type FitRequest,
  type LogPreview,
  type Mission,
  type PostflightFit,
  type PostflightReport,
  type ReportMetric,
} from '@/lib/api'
import { formatSI, fromSI, unitFor, type Quantity, type Units } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'
import { useSectionLayout } from '@/app/sectionLayout'

type VelocityUnits = 'm/s' | 'ft/s'
type AccelerationUnits = 'm/s2' | 'ft/s2' | 'g'

interface Mapping {
  timeColumn: string
  altitudeColumn: string
  altitudeUnits: 'm' | 'ft'
  /** '' means not in the log: derived from altitude. */
  velocityColumn: string
  velocityUnits: VelocityUnits
  accelerationColumn: string
  accelerationUnits: AccelerationUnits
  fitImpulse: boolean
}

/** The uploaded log, its column mapping, the latest report and fit, and the drafts they were made from. */
const usePostflight = create<
  Mapping & {
    log: LogPreview | null
    report: { id: string; draft: Mission } | null
    fitId: string | null
    setLog: (log: LogPreview) => void
    set: (patch: Partial<Mapping & { report: { id: string; draft: Mission } | null; fitId: string | null }>) => void
  }
>()((set) => ({
  log: null,
  timeColumn: '',
  altitudeColumn: '',
  altitudeUnits: 'm',
  velocityColumn: '',
  velocityUnits: 'm/s',
  accelerationColumn: '',
  accelerationUnits: 'm/s2',
  fitImpulse: false,
  report: null,
  fitId: null,
  setLog: (log) =>
    set({
      log,
      timeColumn: log.time_column ?? log.columns[0] ?? '',
      altitudeColumn: log.altitude_column ?? log.columns[1] ?? '',
      altitudeUnits: log.altitude_units,
      velocityColumn: log.velocity_column ?? '',
      velocityUnits: log.velocity_units ?? 'm/s',
      accelerationColumn: log.acceleration_column ?? '',
      accelerationUnits: log.acceleration_units ?? 'm/s2',
      report: null,
      fitId: null,
    }),
  set: (patch) => set(patch),
}))

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Start a post-flight job and wait for it; resolves to the stored result id. */
async function runJob(start: () => ReturnType<typeof api.fitPostflight>, what: string) {
  let r = await start()
  while (r.status === 'queued' || r.status === 'running') {
    await sleep(1000)
    const job = await api.getJob(r.job_id!)
    if (job.status === 'done') r = { ...r, status: 'done' }
    else if (job.status === 'failed' || job.status === 'not_found')
      r = { ...r, status: 'failed', error: job.error ?? 'The job was lost.' }
  }
  if (r.status === 'failed') throw new Error(`The ${what} failed: ${r.error}`)
  return r.result_id
}

function useFit() {
  const fitId = usePostflight((s) => s.fitId)
  return useQuery({
    queryKey: ['postflight', 'fit', fitId],
    queryFn: () => api.getPostflightFit(fitId!),
    enabled: Boolean(fitId),
    staleTime: Infinity,
  })
}

function useReport() {
  const id = usePostflight((s) => s.report?.id)
  return useQuery({
    queryKey: ['postflight', 'report', id],
    queryFn: () => api.getPostflightReport(id!),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function Centre() {
  return (
    <RequireMission>
      <PostflightCentre />
    </RequireMission>
  )
}

function PostflightCentre() {
  const log = usePostflight((s) => s.log)
  const reportDraft = usePostflight((s) => s.report?.draft)
  const draft = useMissionStore((s) => s.draft)
  const report = useReport()
  const fit = useFit()

  if (!log) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          After a flight, upload the altimeter log in the pane: see how the rocket really flew against the simulation.
        </p>
        <div className="max-w-xl">
          <Explainer methodsHref="/docs/methods/post-flight">
            Any CSV with a header row: time in seconds and altitude in metres or feet, above the pad or above sea
            level (the readings on the pad are taken as zero). Vertical velocity and acceleration columns are used if
            the log has them, and derived from altitude if not. Featherweight, Eggtimer and TeleMetrum exports all work
            once their columns are chosen.
          </Explainer>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full space-y-10 overflow-y-auto p-6 print:h-auto print:overflow-visible print:p-0">
      <ProblemNotice error={report.error ?? fit.error} />
      {report.data ? (
        <Report report={report.data} filename={log.filename} stale={Boolean(reportDraft && draft !== reportDraft)} />
      ) : (
        <LogTable log={log} />
      )}
      {fit.data && <Calibration fit={fit.data} />}
    </div>
  )
}

function LogTable({ log }: { log: LogPreview }) {
  return (
    <section aria-label="Log preview" className="space-y-2">
      <h2 className="text-sm font-semibold">{log.filename}</h2>
      <div className="overflow-x-auto">
        <table className="text-sm tabular-nums">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              {log.columns.map((c) => (
                <th key={c} className="pr-6 pb-1 font-normal">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {log.rows.map((r, i) => (
              <tr key={i} className="border-t border-border">
                {r.map((v, j) => (
                  <td key={j} className="py-1 pr-6">
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-muted-foreground">Check the columns in the pane, then build the flight report.</p>
    </section>
  )
}

// --- Report ----------------------------------------------------------------------------

/** Display digits per quantity, for values and their errors. */
const DIGITS: Record<ReportMetric['quantity'], number> = { altitude: 0, speed: 1, acceleration: 1, time: 2 }

const fmt = (si: number | null | undefined, q: Quantity, units: Units, digits: number) =>
  si == null ? '—' : formatSI(si, q, units, digits)

/** Signed difference in display units (the units are all linear, so a difference converts like a value). */
function signed(si: number, q: Quantity, units: Units, digits: number) {
  const v = fromSI(si, q, units)
  const text = Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
  const zero = Number(text.replace(/[^\d.]/g, '')) === 0
  return `${zero ? '±' : v > 0 ? '+' : '−'}${text} ${unitFor(q, units).symbol}`
}

function pct(p: number | null | undefined) {
  if (p == null) return ''
  const text = Math.abs(p).toFixed(1)
  return `${Number(text) === 0 ? '±' : p > 0 ? '+' : '−'}${text}%`
}

/**
 * Prints in the light theme, whatever the screen shows, from the button or the
 * browser's own Print: the charts are canvases drawn in the theme's colours, so
 * they are redrawn (synchronously, before the page is laid out for paper) and
 * the theme is put back afterwards.
 */
function useLightPrint() {
  const setTheme = usePrefs((s) => s.setTheme)
  useEffect(() => {
    let before: ReturnType<typeof usePrefs.getState>['theme'] | null = null
    const onBefore = () => {
      before = usePrefs.getState().theme
      if (before === 'light') return
      // The charts read their colours before the shell's effect would set this: set it first.
      const root = document.documentElement
      root.dataset.theme = 'light'
      delete root.dataset.pink
      flushSync(() => setTheme('light'))
    }
    const onAfter = () => {
      if (before && before !== 'light') setTheme(before)
      before = null
    }
    window.addEventListener('beforeprint', onBefore)
    window.addEventListener('afterprint', onAfter)
    return () => {
      window.removeEventListener('beforeprint', onBefore)
      window.removeEventListener('afterprint', onAfter)
    }
  }, [setTheme])
}

function Report({ report, filename, stale }: { report: PostflightReport; filename: string; stale: boolean }) {
  const units = usePrefs((s) => s.display)
  const missionName = useMissionStore((s) => s.draft?.meta.name)
  useLightPrint()
  const metrics = Object.fromEntries(report.metrics.map((m) => [m.key, m]))
  const apogee = metrics.apogee
  const ascent = ['apogee_time', 'max_vertical_velocity', 'max_vertical_velocity_time', 'max_acceleration', 'burnout']
  const descent = report.metrics.filter((m) => m.key.startsWith('descent_rate_') || m.key === 'flight_time')

  return (
    <article data-print-report aria-label="Flight report" className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold">Flight report{missionName && `: ${missionName}`}</h1>
          <p className="text-sm text-muted-foreground">
            {filename} against a simulation of the mission (drag multiplier {report.drag_multiplier.toFixed(3)}).
            Errors are simulated minus measured: positive means the simulation overestimated.
          </p>
        </div>
        <Button onClick={() => window.print()} className="print:hidden">
          <Printer /> Print or save as PDF
        </Button>
      </header>
      {stale && (
        <p role="status" className="rounded-md border border-caution/60 bg-caution/10 px-3 py-2 text-sm print:hidden">
          The mission has changed since this report was built. Build it again to compare the current mission.
        </p>
      )}

      <section aria-label="Apogee" className="flex flex-wrap items-end gap-x-12 gap-y-4 break-inside-avoid">
        <Hero label="Measured apogee" si={apogee.measured} units={units} />
        <Hero label="Simulated" si={apogee.simulated} units={units} muted />
        <div className="pb-1">
          <p className="text-sm text-muted-foreground">Error</p>
          <p className="text-3xl font-semibold tabular-nums">
            {apogee.error == null ? '—' : signed(apogee.error, 'altitude', units, 0)}
          </p>
          <p className="text-sm text-muted-foreground">{pct(apogee.error_pct)}</p>
        </div>
      </section>

      <MetricGroup title="Ascent" metrics={ascent.map((k) => metrics[k]).filter(Boolean)} units={units} />
      <MetricGroup title="Descent and landing" metrics={descent} units={units} />
      <EventsTable report={report} units={units} />
      <ReportCharts report={report} units={units} />

      {report.warnings.length > 0 && (
        <section aria-label="Notes" className="space-y-1 break-inside-avoid">
          <h2 className="text-sm font-semibold">Notes</h2>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">
            {report.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="text-xs text-muted-foreground">
        Log aligned at launch ({report.launch_s.toFixed(2)} s in the log&apos;s own time, after a{' '}
        {report.shift_s >= 0 ? '+' : '−'}
        {Math.abs(report.shift_s).toFixed(2)} s offset to match the ascent); compared up to{' '}
        {report.log_end_s.toFixed(1)} s, where the log ends.
      </p>
      <ReportTable report={report} units={units} />
    </article>
  )
}

function Hero({ label, si, units, muted }: { label: string; si: number | null; units: Units; muted?: boolean }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p
        className={cn('text-6xl font-semibold tracking-tight', muted && 'text-muted-foreground')}
        style={{ fontFeatureSettings: '"tnum" 0' }}
      >
        {si == null ? '—' : Math.round(fromSI(si, 'altitude', units)).toLocaleString()}{' '}
        <span className="text-2xl font-medium text-muted-foreground">{unitFor('altitude', units).symbol}</span>
      </p>
    </div>
  )
}

function MetricGroup({ title, metrics, units }: { title: string; metrics: ReportMetric[]; units: Units }) {
  if (!metrics.length) return null
  return (
    <section aria-label={title} className="space-y-2 break-inside-avoid">
      <h2 className="text-sm font-semibold">{title}</h2>
      <dl className="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-3">
        {metrics.map((m) => {
          const d = DIGITS[m.quantity]
          return (
            <div key={m.key} className="rounded-md border border-border bg-surface px-3 py-2 break-inside-avoid">
              <dt className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
                {m.label}
                {m.derived && (
                  <span title="The log has no such column: derived from altitude" className="rounded border border-border px-1">
                    derived
                  </span>
                )}
              </dt>
              <dd className="text-lg font-semibold" style={{ fontFeatureSettings: '"tnum" 0' }}>
                {fmt(m.measured, m.quantity, units, d)}
              </dd>
              <dd className="text-xs text-muted-foreground tabular-nums">
                Simulated {fmt(m.simulated, m.quantity, units, d)}
                {m.error != null && (
                  <>
                    {' · '}
                    <span className="text-foreground">{signed(m.error, m.quantity, units, d)}</span> {pct(m.error_pct)}
                  </>
                )}
              </dd>
            </div>
          )
        })}
      </dl>
    </section>
  )
}

function EventsTable({ report, units }: { report: PostflightReport; units: Units }) {
  const delta = (a: number | null | undefined, b: number | null | undefined, q: Quantity, d: number) =>
    a == null || b == null ? '' : signed(b - a, q, units, d)
  return (
    <section aria-label="Events" className="break-inside-avoid">
      <h2 className="mb-2 text-sm font-semibold">Events</h2>
      <div className="max-w-4xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="text-right">
              <th className="py-1 text-left font-normal">Event</th>
              <th className="py-1 font-normal">Measured</th>
              <th className="py-1 font-normal">Simulated</th>
              <th className="py-1 font-normal">Error</th>
              <th className="py-1 pl-6 font-normal">Altitude measured</th>
              <th className="py-1 font-normal">Simulated</th>
              <th className="py-1 font-normal">Error</th>
            </tr>
          </thead>
          <tbody className="text-right tabular-nums">
            {report.events.map((e) => (
              <tr key={e.name} className="border-t border-border">
                <td className="py-1.5 text-left">{e.name}</td>
                <td className="py-1.5">{e.measured_s == null ? '—' : `${e.measured_s.toFixed(2)} s`}</td>
                <td className="py-1.5 text-muted-foreground">{e.simulated_s == null ? '—' : `${e.simulated_s.toFixed(2)} s`}</td>
                <td className="py-1.5">{delta(e.measured_s, e.simulated_s, 'time', 2)}</td>
                <td className="py-1.5 pl-6">{fmt(e.measured_agl_m, 'altitude', units, 0)}</td>
                <td className="py-1.5 text-muted-foreground">{fmt(e.simulated_agl_m, 'altitude', units, 0)}</td>
                <td className="py-1.5">{delta(e.measured_agl_m, e.simulated_agl_m, 'altitude', 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const CHANNEL: Record<ChannelComparison['name'], { title: string; quantity: Quantity; digits: number }> = {
  altitude_agl_m: { title: 'Altitude above the pad', quantity: 'altitude', digits: 0 },
  vertical_velocity_ms: { title: 'Vertical velocity', quantity: 'speed', digits: 1 },
  acceleration_ms2: { title: 'Acceleration', quantity: 'acceleration', digits: 1 },
}

function ReportCharts({ report, units }: { report: PostflightReport; units: Units }) {
  const events = useMemo<ChartEvent[]>(
    () =>
      report.events
        .filter((e) => e.name !== 'Launch' && e.name !== 'Touchdown' && e.measured_s != null)
        .map((e) => ({ t: e.measured_s!, label: e.name })),
    [report],
  )
  const prepared = useMemo(
    () =>
      report.channels.map((c) => {
        const meta = CHANNEL[c.name]
        const to = (v: number) => fromSI(v, meta.quantity, units)
        return {
          c,
          meta,
          unit: unitFor(meta.quantity, units).symbol,
          measured: c.measured.map(to),
          simulated: { y: c.simulated.map(to), label: 'Simulated' },
          residual: c.simulated.map((s, i) => to(s - c.measured[i])),
          events: events.filter((e) => e.t <= (c.t.at(-1) ?? 0)),
        }
      }),
    [report, units, events],
  )
  return (
    <section aria-label="Charts" className="space-y-2">
      <h2 className="text-sm font-semibold break-after-avoid">Log against simulation</h2>
      <ul className="flex flex-wrap gap-x-5 text-xs text-muted-foreground break-after-avoid" aria-label="Legend">
        <li className="flex items-center gap-2">
          <svg width="24" height="8" aria-hidden>
            <line x1="0" x2="24" y1="4" y2="4" strokeWidth={2} className="stroke-foreground" />
          </svg>
          Log
        </li>
        <li className="flex items-center gap-2">
          <svg width="24" height="8" aria-hidden>
            <line x1="0" x2="24" y1="4" y2="4" strokeWidth={2} strokeDasharray="6 4" className="stroke-chart-2" />
          </svg>
          Simulated
        </li>
      </ul>
      <div className="grid gap-x-8 gap-y-8 xl:grid-cols-2 print:grid-cols-1">
        {prepared.map(({ c, meta, unit, measured, simulated, residual, events: ev }) => (
          <div key={c.name} className="space-y-1 break-inside-avoid">
            <TimeSeriesChart
              title={`${meta.title}${c.ascent_only ? ', ascent' : ''}${c.derived ? ' (log derived from altitude)' : ''}`}
              unit={unit}
              t={c.t}
              y={measured}
              label="Log"
              compare={simulated}
              events={ev}
              syncKey="postflight-report"
            />
            <TimeSeriesChart
              title="Simulated − log"
              unit={unit}
              t={c.t}
              y={residual}
              height={96}
              zeroLine
              syncKey="postflight-report"
            />
            <p className="text-xs text-muted-foreground tabular-nums">
              RMS {formatSI(c.rms_error, meta.quantity, units, meta.digits)} · bias{' '}
              {signed(c.mean_error, meta.quantity, units, meta.digits)} · largest{' '}
              {signed(c.max_error, meta.quantity, units, meta.digits)} at {c.max_error_t.toFixed(1)} s
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}

/** The charts' table-view twin: every channel, log and simulated, at common times. */
function ReportTable({ report, units }: { report: PostflightReport; units: Units }) {
  const [open, setOpen] = useState(false)
  const rows = useMemo(() => {
    if (!open) return []
    const base = report.channels.find((c) => c.name === 'altitude_agl_m')!
    const tEnd = base.t.at(-1) ?? 0
    const at = (t: number[], y: number[], x: number) => {
      if (x > (t.at(-1) ?? 0)) return null
      let j = t.findIndex((v) => v >= x)
      if (j <= 0) return y[Math.max(j, 0)]
      const f = (x - t[j - 1]) / (t[j] - t[j - 1])
      return y[j - 1] + f * (y[j] - y[j - 1])
    }
    return Array.from({ length: 61 }, (_, i) => (tEnd * i) / 60).map((x) => ({
      t: x,
      values: report.channels.flatMap((c) => [at(c.t, c.measured, x), at(c.t, c.simulated, x)]),
    }))
  }, [open, report])
  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)} className="text-sm print:hidden">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Show the data as a table</summary>
      {open && (
        <div className="mt-3 max-h-96 overflow-auto rounded-md border border-border">
          <table className="w-full text-right tabular-nums">
            <thead className="sticky top-0 bg-surface text-xs text-muted-foreground">
              <tr>
                <th className="px-2 py-1 font-normal">Time (s)</th>
                {report.channels.flatMap((c) => {
                  const meta = CHANNEL[c.name]
                  const u = unitFor(meta.quantity, units).symbol
                  return [
                    <th key={`${c.name}-m`} className="px-2 py-1 font-normal">
                      {meta.title}, log ({u})
                    </th>,
                    <th key={`${c.name}-s`} className="px-2 py-1 font-normal">
                      simulated ({u})
                    </th>,
                  ]
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.t} className="border-t border-border">
                  <td className="px-2 py-1">{r.t.toFixed(1)}</td>
                  {r.values.map((v, i) => {
                    const q = CHANNEL[report.channels[Math.floor(i / 2)].name].quantity
                    return (
                      <td key={i} className="px-2 py-1">
                        {v == null ? '' : fromSI(v, q, units).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  )
}

// --- Calibration (the drag fit) ----------------------------------------------------------

function Calibration({ fit: f }: { fit: PostflightFit }) {
  const units = usePrefs((s) => s.display)
  const edit = useMissionStore((s) => s.edit)
  const current = useMissionStore((s) => s.draft?.rocket?.drag.multiplier)
  const alt = (m: number) => formatSI(m, 'altitude', units)
  const applied = current !== undefined && Math.abs(current - f.drag_multiplier) < 1e-4
  return (
    <section aria-label="Calibration" className="space-y-4 print:hidden">
      <h2 className="font-display text-xl font-semibold">Calibration</h2>
      <dl className="flex flex-wrap gap-x-10 gap-y-3">
        <Fact label="Measured apogee" value={alt(f.measured_apogee_m)} detail="From the log" />
        <Fact
          label="Predicted"
          value={alt(f.predicted_apogee_m)}
          detail={`${signed(f.predicted_apogee_m - f.measured_apogee_m, 'altitude', units, 0)} off; RMS ${alt(f.rms_before_m)} over the ascent`}
        />
        <Fact
          label="Fitted"
          value={alt(f.fitted_apogee_m)}
          detail={`${signed(f.fitted_apogee_m - f.measured_apogee_m, 'altitude', units, 0)} off; RMS ${alt(f.rms_after_m)}`}
        />
        <Fact label="Drag multiplier" value={f.drag_multiplier.toFixed(3)} detail={`was ${f.drag_multiplier_before.toFixed(3)}`} />
        {f.fitted_impulse && (
          <Fact label="Impulse" value={`${(f.impulse_scale * 100).toFixed(1)}%`} detail="of the thrust curve's" />
        )}
      </dl>
      <Button
        variant="primary"
        disabled={applied}
        onClick={() =>
          edit((d) => {
            if (d.rocket) d.rocket.drag.multiplier = Number(f.drag_multiplier.toFixed(4))
          })
        }
      >
        <Check />
        {applied ? 'The mission uses this drag' : 'Use the fitted drag multiplier'}
      </Button>
      <p className="max-w-xl text-xs text-muted-foreground">
        Using it changes the mission: build the report again to see the calibrated simulation against the log.
        {f.fitted_impulse &&
          ' The mission has no field for an impulse scale: if the motor consistently under- or over-performs, use a thrust curve that matches it, or widen the impulse spread in Dispersion.'}
      </p>
      <AltitudeChart fit={f} />
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/post-flight">
          The log is aligned with the prediction at launch, and the ascent is compared from launch to apogee. The drag
          multiplier (and, if asked, the impulse) is fitted by least squares over repeated ascent-only flights, along with
          a small time offset, because a barometric log can&apos;t place liftoff exactly. Use the fitted values for the
          next prediction.
        </Explainer>
      </div>
    </section>
  )
}

function Fact({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-display text-2xl font-semibold tabular-nums">{value}</dd>
      <dd className="text-xs text-muted-foreground">{detail}</dd>
    </div>
  )
}

const H = 300
const PAD = { top: 12, right: 16, bottom: 28, left: 56 }

/** The log against the prediction before and after the fit. */
function AltitudeChart({ fit }: { fit: PostflightFit }) {
  const units = usePrefs((s) => s.display)
  const host = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = host.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const series = [
    { key: 'measured', label: 'Log', curve: fit.measured, className: 'stroke-foreground', dash: undefined, width: 2.5 },
    { key: 'predicted', label: 'Predicted', curve: fit.predicted, className: 'stroke-chart-2', dash: '6 4', width: 2 },
    { key: 'fitted', label: 'Fitted', curve: fit.fitted, className: 'stroke-chart-1', dash: undefined, width: 2 },
  ]
  const tMax = Math.max(...series.map((s) => s.curve.t.at(-1) ?? 0))
  const yMax = Math.max(...series.flatMap((s) => s.curve.altitude_agl_m)) * 1.05
  const w = Math.max(width - PAD.left - PAD.right, 10)
  const h = H - PAD.top - PAD.bottom
  const x = (t: number) => PAD.left + (t / (tMax || 1)) * w
  const y = (m: number) => PAD.top + h - (m / (yMax || 1)) * h
  const symbol = unitFor('altitude', units).symbol
  return (
    <figure className="max-w-4xl space-y-2">
      <figcaption className="text-sm font-medium">
        Altitude above the pad, launch to apogee <span className="text-muted-foreground">({symbol})</span>
      </figcaption>
      <ul className="flex flex-wrap gap-x-5 text-xs text-muted-foreground" aria-label="Legend">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <svg width="24" height="8" aria-hidden>
              <line x1="0" x2="24" y1="4" y2="4" strokeWidth={s.width} strokeDasharray={s.dash} className={s.className} />
            </svg>
            {s.label}
          </li>
        ))}
      </ul>
      <div ref={host}>
        {width > 0 && (
          <svg width={width} height={H} role="img" aria-label="Altitude: the log, the prediction and the fit">
            {ticks(0, fromSI(yMax, 'altitude', units), 5).map((v) => {
              const si = v / fromSI(1, 'altitude', units)
              return (
                <g key={v}>
                  <line x1={PAD.left} x2={PAD.left + w} y1={y(si)} y2={y(si)} className="stroke-chart-grid" />
                  <text x={PAD.left - 6} y={y(si)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[11px]">
                    {v.toLocaleString()}
                  </text>
                </g>
              )
            })}
            {ticks(0, tMax, 6).map((t) => (
              <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="fill-muted-foreground text-[11px]">
                {t} s
              </text>
            ))}
            {series.map((s) => (
              <path
                key={s.key}
                d={s.curve.t.map((t, i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(s.curve.altitude_agl_m[i]).toFixed(1)}`).join('')}
                fill="none"
                strokeWidth={s.width}
                strokeDasharray={s.dash}
                className={s.className}
              />
            ))}
          </svg>
        )}
      </div>
    </figure>
  )
}

// --- Pane ------------------------------------------------------------------------------

export function Pane() {
  return (
    <RequireMission compact>
      <PostflightPane />
    </RequireMission>
  )
}

function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: [T, string][]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-md border border-border p-0.5">
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cn(
            'flex-1 rounded px-2 py-1 text-sm',
            value === v ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {text}
        </button>
      ))}
    </div>
  )
}

function PostflightPane() {
  const layout = useSectionLayout()
  const draft = useMissionStore((s) => s.draft!)
  const p = usePostflight()
  const { log, set } = p
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({ mutationFn: api.uploadFlightLog, onSuccess: p.setLog })
  const base = (): Omit<FitRequest, 'fit_impulse'> => ({
    mission: draft,
    log_sha256: log!.sha256,
    time_column: p.timeColumn,
    altitude_column: p.altitudeColumn,
    altitude_units: p.altitudeUnits,
  })
  const report = useMutation({
    mutationFn: async () => {
      const sent = draft
      const id = await runJob(
        () =>
          api.reportPostflight({
            ...base(),
            velocity_column: p.velocityColumn || null,
            velocity_units: p.velocityUnits,
            acceleration_column: p.accelerationColumn || null,
            acceleration_units: p.accelerationUnits,
          }),
        'report',
      )
      return { id, draft: sent }
    },
    // Only a finished job is recorded: asking for an unfinished one would 404.
    onSuccess: (r) => set({ report: r }),
  })
  const fit = useMutation({
    mutationFn: () => runJob(() => api.fitPostflight({ ...base(), fit_impulse: p.fitImpulse }), 'fit'),
    onSuccess: (id) => set({ fitId: id }),
  })

  const select = (label: string, value: string, onChange: (v: string) => void, optional?: string) => (
    <label className="block space-y-1 text-sm">
      <span>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-border bg-background px-2"
      >
        {optional && <option value="">{optional}</option>}
        {log?.columns.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Flight log</h2>
        <input
          ref={input}
          type="file"
          accept=".csv,.txt"
          className="hidden"
          aria-label="Flight log file"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) upload.mutate(file)
            e.target.value = ''
          }}
        />
        <Button className="w-full" onClick={() => input.current?.click()} disabled={upload.isPending}>
          <FileUp /> {upload.isPending ? 'Reading' : log ? 'Upload a different log' : 'Upload a log (.csv)'}
        </Button>
        <ProblemNotice error={upload.error} />
        {log && <p className="text-xs text-muted-foreground">{log.filename}</p>}
      </section>
      {log && (
        <>
          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Columns</h2>
            {select('Time (seconds)', p.timeColumn, (v) => set({ timeColumn: v }))}
            {select('Altitude', p.altitudeColumn, (v) => set({ altitudeColumn: v }))}
            <Segmented
              label="Altitude units"
              options={[
                ['m', 'Metres'],
                ['ft', 'Feet'],
              ]}
              value={p.altitudeUnits}
              onChange={(v) => set({ altitudeUnits: v })}
            />
            {select('Vertical velocity', p.velocityColumn, (v) => set({ velocityColumn: v }), 'Not in the log: derive it')}
            {p.velocityColumn && (
              <Segmented
                label="Velocity units"
                options={[
                  ['m/s', 'm/s'],
                  ['ft/s', 'ft/s'],
                ]}
                value={p.velocityUnits}
                onChange={(v) => set({ velocityUnits: v })}
              />
            )}
            {select(
              'Acceleration',
              p.accelerationColumn,
              (v) => set({ accelerationColumn: v }),
              'Not in the log: derive it',
            )}
            {p.accelerationColumn && (
              <Segmented
                label="Acceleration units"
                options={[
                  ['m/s2', 'm/s²'],
                  ['ft/s2', 'ft/s²'],
                  ['g', 'g'],
                ]}
                value={p.accelerationUnits}
                onChange={(v) => set({ accelerationUnits: v })}
              />
            )}
            <p className="text-xs text-muted-foreground">
              A channel the log doesn&apos;t have is derived from altitude and marked as derived. Acceleration as the
              accelerometer reads it: 1 g on the pad is fine.
            </p>
            <Button
              variant="primary"
              className="w-full"
              disabled={report.isPending}
              onClick={() => {
                report.mutate()
                layout.showCentre()
              }}
            >
              <FileText /> {report.isPending ? 'Simulating and comparing' : 'Build the flight report'}
            </Button>
            <ProblemNotice error={report.error} />
          </section>
          <section className="space-y-3">
            <h2 className="text-sm font-semibold">Calibrate</h2>
            <p className="text-xs text-muted-foreground">
              Fit the drag multiplier so the simulation matches this log&apos;s ascent, for the next prediction.
            </p>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={p.fitImpulse} onChange={(e) => set({ fitImpulse: e.target.checked })} />
              <span>
                Also fit the motor&apos;s impulse
                <span className="block text-xs text-muted-foreground">
                  Only if the boost looks off too: drag and impulse trade against each other.
                </span>
              </span>
            </label>
            <Button
              className="w-full"
              disabled={fit.isPending}
              onClick={() => {
                fit.mutate()
                layout.showCentre()
              }}
            >
              <Sigma /> {fit.isPending ? 'Fitting: about 30 flights' : 'Fit the prediction to this log'}
            </Button>
            <ProblemNotice error={fit.error} />
          </section>
        </>
      )}
    </div>
  )
}
