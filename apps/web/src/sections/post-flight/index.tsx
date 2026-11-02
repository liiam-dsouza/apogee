import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, FileUp, Sigma } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { create } from 'zustand'
import { ticks } from '@/components/charts/bins'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type LogPreview, type PostflightFit } from '@/lib/api'
import { formatSI, fromSI, unitFor } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** The uploaded log, its column mapping, and the latest fit. */
const usePostflight = create<{
  log: LogPreview | null
  timeColumn: string
  altitudeColumn: string
  altitudeUnits: 'm' | 'ft'
  fitImpulse: boolean
  fitId: string | null
  setLog: (log: LogPreview) => void
  set: (patch: Partial<{ timeColumn: string; altitudeColumn: string; altitudeUnits: 'm' | 'ft'; fitImpulse: boolean; fitId: string | null }>) => void
}>()((set) => ({
  log: null,
  timeColumn: '',
  altitudeColumn: '',
  altitudeUnits: 'm',
  fitImpulse: false,
  fitId: null,
  setLog: (log) =>
    set({
      log,
      timeColumn: log.time_column ?? log.columns[0] ?? '',
      altitudeColumn: log.altitude_column ?? log.columns[1] ?? '',
      altitudeUnits: log.altitude_units,
      fitId: null,
    }),
  set: (patch) => set(patch),
}))

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function useFit() {
  const fitId = usePostflight((s) => s.fitId)
  return useQuery({
    queryKey: ['postflight', fitId],
    queryFn: () => api.getPostflightFit(fitId!),
    enabled: Boolean(fitId),
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
  const fit = useFit()
  const units = usePrefs((s) => s.display)
  const edit = useMissionStore((s) => s.edit)
  const current = useMissionStore((s) => s.draft?.rocket?.drag.multiplier)

  if (!log) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          After a flight, upload the altimeter log in the pane: the prediction is fitted to what really happened.
        </p>
        <div className="max-w-xl">
          <Explainer methodsHref="/docs/methods/post-flight">
            Any CSV with a header row: time in seconds and altitude in metres or feet, above the pad or above sea
            level (the readings on the pad are taken as zero). Featherweight, Eggtimer and TeleMetrum exports all work
            once their time and altitude columns are chosen.
          </Explainer>
        </div>
      </div>
    )
  }

  const f = fit.data
  const alt = (m: number) => formatSI(m, 'altitude', units)
  return (
    <div className="h-full space-y-6 overflow-y-auto p-6">
      <ProblemNotice error={fit.error} />
      {!f ? (
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
          <p className="text-sm text-muted-foreground">Check the columns in the pane, then fit.</p>
        </section>
      ) : (
        <>
          <section aria-label="Fit" className="space-y-3">
            <dl className="flex flex-wrap gap-x-10 gap-y-3">
              <Fact label="Measured apogee" value={alt(f.measured_apogee_m)} detail="From the log" />
              <Fact
                label="Predicted"
                value={alt(f.predicted_apogee_m)}
                detail={`${signed(f.predicted_apogee_m - f.measured_apogee_m, units)} off; RMS ${alt(f.rms_before_m)} over the ascent`}
              />
              <Fact
                label="Fitted"
                value={alt(f.fitted_apogee_m)}
                detail={`${signed(f.fitted_apogee_m - f.measured_apogee_m, units)} off; RMS ${alt(f.rms_after_m)}`}
              />
              <Fact
                label="Drag multiplier"
                value={f.drag_multiplier.toFixed(3)}
                detail={`was ${f.drag_multiplier_before.toFixed(3)}`}
              />
              {f.fitted_impulse && (
                <Fact label="Impulse" value={`${(f.impulse_scale * 100).toFixed(1)}%`} detail="of the thrust curve's" />
              )}
            </dl>
            <Button
              variant="primary"
              disabled={current !== undefined && Math.abs(current - f.drag_multiplier) < 1e-4}
              onClick={() =>
                edit((d) => {
                  if (d.rocket) d.rocket.drag.multiplier = Number(f.drag_multiplier.toFixed(4))
                })
              }
            >
              <Check />
              {current !== undefined && Math.abs(current - f.drag_multiplier) < 1e-4
                ? 'The mission uses this drag'
                : 'Use the fitted drag multiplier'}
            </Button>
            {f.fitted_impulse && (
              <p className="text-xs text-muted-foreground">
                The mission has no field for an impulse scale: if the motor consistently under- or over-performs, use a
                thrust curve that matches it, or widen the impulse spread in Dispersion.
              </p>
            )}
          </section>
          <AltitudeChart fit={f} />
        </>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/post-flight">
          The log is aligned with the prediction at launch, and the ascent is compared from launch to apogee. The drag
          multiplier (and, if asked, the impulse) is fitted by least squares over repeated ascent-only flights, along with
          a small time offset, because a barometric log can't place liftoff exactly. Use the fitted values for the next
          prediction.
        </Explainer>
      </div>
    </div>
  )
}

function signed(m: number, units: Parameters<typeof formatSI>[2]) {
  const v = Math.round(fromSI(m, 'altitude', units))
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)} ${unitFor('altitude', units).symbol}`
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

function PostflightPane() {
  const draft = useMissionStore((s) => s.draft!)
  const { log, timeColumn, altitudeColumn, altitudeUnits, fitImpulse, setLog, set } = usePostflight()
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({ mutationFn: api.uploadFlightLog, onSuccess: setLog })
  const run = useMutation({
    mutationFn: async () => {
      let r = await api.fitPostflight({
        mission: draft,
        log_sha256: log!.sha256,
        time_column: timeColumn,
        altitude_column: altitudeColumn,
        altitude_units: altitudeUnits,
        fit_impulse: fitImpulse,
      })
      while (r.status === 'queued' || r.status === 'running') {
        await sleep(1000)
        const job = await api.getJob(r.job_id!)
        if (job.status === 'done') r = { ...r, status: 'done' }
        else if (job.status === 'failed' || job.status === 'not_found')
          r = { ...r, status: 'failed', error: job.error ?? 'The job was lost.' }
      }
      if (r.status === 'failed') throw new Error(`The fit failed: ${r.error}`)
      return r.result_id
    },
    // Only a finished fit is recorded: asking for an unfinished one would 404.
    onSuccess: (id) => set({ fitId: id }),
  })

  const select = (label: string, value: string, onChange: (v: string) => void) => (
    <label className="block space-y-1 text-sm">
      <span>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-border bg-background px-2"
      >
        {log?.columns.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <div className="space-y-5 p-4">
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
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Columns</h2>
          {select('Time (seconds)', timeColumn, (v) => set({ timeColumn: v }))}
          {select('Altitude', altitudeColumn, (v) => set({ altitudeColumn: v }))}
          <div role="radiogroup" aria-label="Altitude units" className="flex rounded-md border border-border p-0.5">
            {(['m', 'ft'] as const).map((u) => (
              <button
                key={u}
                type="button"
                role="radio"
                aria-checked={altitudeUnits === u}
                onClick={() => set({ altitudeUnits: u })}
                className={cn(
                  'flex-1 rounded px-2 py-1 text-sm',
                  altitudeUnits === u ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {u === 'm' ? 'Metres' : 'Feet'}
              </button>
            ))}
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={fitImpulse} onChange={(e) => set({ fitImpulse: e.target.checked })} />
            <span>
              Also fit the motor's impulse
              <span className="block text-xs text-muted-foreground">
                Only if the boost looks off too: drag and impulse trade against each other.
              </span>
            </span>
          </label>
          <Button variant="primary" className="w-full" disabled={run.isPending} onClick={() => run.mutate()}>
            <Sigma /> {run.isPending ? 'Fitting: about 30 flights' : 'Fit the prediction to this log'}
          </Button>
          <ProblemNotice error={run.error} />
        </section>
      )}
    </div>
  )
}
