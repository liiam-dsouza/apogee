import { useMutation, useQuery } from '@tanstack/react-query'
import { Calculator, CircleX, PackagePlus } from 'lucide-react'
import { useState } from 'react'
import { create } from 'zustand'
import { ticks } from '@/components/charts/bins'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { RuleTable } from '@/components/RuleTable'
import { Button } from '@/components/ui/button'
import { api, type BallastSolution, type Mission } from '@/lib/api'
import { formatSI, fromSI, toSI, unitFor, type Units } from '@/lib/units'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'
import { useSectionLayout } from '@/app/sectionLayout'

/** The latest solve per mission, and the draft it was for (to say when it no longer matches). */
const useSolves = create<{
  byMission: Record<string, { resultId: string; draft: Mission }>
  record: (draft: Mission, resultId: string) => void
}>()((set) => ({
  byMission: {},
  record: (draft, resultId) =>
    set((s) => ({ byMission: { ...s.byMission, [draft.meta.id!]: { resultId, draft } } })),
}))

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function useSolve() {
  const record = useSolves((s) => s.record)
  return useMutation({
    mutationFn: async (draft: Mission) => {
      let run = await api.solveBallast(draft)
      while (run.status === 'queued' || run.status === 'running') {
        await sleep(1000)
        const job = await api.getJob(run.job_id!)
        if (job.status === 'done') run = { ...run, status: 'done' }
        else if (job.status === 'failed' || job.status === 'not_found')
          run = { ...run, status: 'failed', error: job.error ?? 'The job was lost.' }
      }
      if (run.status === 'failed') throw new Error(`The solve failed: ${run.error}`)
      return { draft, resultId: run.result_id }
    },
    // Only a finished solve is recorded: asking for an unfinished one would 404.
    onSuccess: ({ draft, resultId }) => record(draft, resultId),
  })
}

function useSolution() {
  const draft = useMissionStore((s) => s.draft)
  const latest = useSolves((s) => (draft?.meta.id ? s.byMission[draft.meta.id] : undefined))
  const query = useQuery({
    queryKey: ['ballast', latest?.resultId],
    queryFn: () => api.getBallast(latest!.resultId),
    enabled: Boolean(latest),
    retry: false,
    staleTime: Infinity,
  })
  // Installing the answer changes only installed_kg, which doesn't change the question.
  const changed =
    latest !== undefined &&
    draft !== null &&
    JSON.stringify({ ...latest.draft, ballast: { ...latest.draft.ballast, installed_kg: 0 } }) !==
      JSON.stringify({ ...draft, ballast: { ...draft.ballast, installed_kg: 0 } })
  return { ...query, changed }
}

export function Centre() {
  return (
    <RequireMission>
      <BallastCentre />
    </RequireMission>
  )
}

function BallastCentre() {
  const solve = useSolve()
  const { data, changed, error } = useSolution()
  const units = usePrefs((s) => s.display)
  const installed = useMissionStore((s) => s.draft?.ballast?.installed_kg ?? 0)
  const edit = useMissionStore((s) => s.edit)
  const alt = (m: number) => formatSI(m, 'altitude', units)
  const mass = (kg: number) => formatBallast(kg, units)

  if (!data) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          {solve.isPending
            ? 'Solving: about a hundred flights, a minute or two.'
            : 'Set the target and the ballast bay in the pane, then solve.'}
        </p>
        <ProblemNotice error={solve.error ?? (changed ? null : error)} />
      </div>
    )
  }

  const failing = data.report?.rows.filter((r) => r.outcome === 'no_go') ?? []
  return (
    <div className="space-y-6 p-6">
      {changed && (
        <p className="rounded-md border border-caution/50 bg-caution/10 p-3 text-sm">
          The mission has changed since this solve. Solve again before using the number.
        </p>
      )}
      {data.status !== 'ok' ? (
        <header className="space-y-1">
          <h2 className="font-display text-3xl font-semibold">
            {data.status === 'too_low' ? 'Short of the target with no ballast' : 'Over the target with the bay full'}
          </h2>
          <p className="text-muted-foreground">
            Target {alt(data.target_apogee_m)} ({data.target_source}).{' '}
            {data.status === 'too_low'
              ? 'Ballast only lowers apogee: this needs a bigger motor or less drag.'
              : `Even ${mass(data.curve.at(-1)?.mass_kg ?? 0)} isn't enough. Raise the bay's maximum or change the design.`}
          </p>
        </header>
      ) : (
        <section aria-label="Recommendation" className="space-y-3">
          {failing.length > 0 && (
            <p className="flex items-start gap-2 rounded-md border border-nogo/50 bg-nogo/10 p-3 text-sm">
              <CircleX className="mt-0.5 size-4 shrink-0 text-nogo" aria-hidden />
              <span>
                <strong>Do not fly this as it stands:</strong> {failing.length} hard rule
                {failing.length > 1 ? 's fail' : ' fails'} at this mass. See the report below.
              </span>
            </p>
          )}
          <p className="font-display text-4xl font-semibold">
            Add {data.increments} × {mass(data.increment_kg)}{' '}
            <span className="text-muted-foreground">({mass(data.recommended_kg!)})</span>
          </p>
          <dl className="flex flex-wrap gap-x-10 gap-y-2">
            <Fact
              label="Nominal apogee"
              value={alt(data.apogee_agl_m!)}
              detail={`${formatSigned(data.apogee_agl_m! - data.target_apogee_m, units)} from the ${alt(data.target_apogee_m)} target`}
            />
            <Fact
              label={`90% of ${data.samples} flights`}
              value={`${alt(data.apogee_p5_m!)} to ${alt(data.apogee_p95_m!)}`}
              detail="Monte Carlo at this mass"
            />
            {data.gradient_m_per_100g != null && (
              <Fact
                label="Sensitivity"
                value={`${formatSigned(data.gradient_m_per_100g, units)} per ${mass(0.1)}`}
                detail="Apogee change for each step near the answer"
              />
            )}
          </dl>
          <p className="text-xs text-muted-foreground">
            Target from {data.target_source}. Exact answer {mass(data.exact_kg!)}, rounded to your increment.
          </p>
          <Button
            variant="primary"
            disabled={Math.abs(installed - data.recommended_kg!) < 1e-9 || changed}
            onClick={() => edit((d) => void ((d.ballast ??= { installed_kg: 0, increment_kg: 0.05, max_kg: 2 }).installed_kg = data.recommended_kg!))}
          >
            <PackagePlus />
            {Math.abs(installed - data.recommended_kg!) < 1e-9 ? 'Installed' : 'Install this ballast'}
          </Button>
        </section>
      )}

      <ApogeeCurve solution={data} />

      {data.report && (
        <section aria-label="Constraint report" className="space-y-2">
          <h3 className="text-sm font-semibold">
            At this mass{data.built_in_checks ? ': built-in checks (the mission has no rules of its own)' : ''}
          </h3>
          <RuleTable rows={data.report.rows} />
        </section>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/ballast">
          Apogee falls steadily as mass is added, so the mass that hits the target is found by a root search over
          ascent-only flights. It is rounded to your increment, then re-checked: a full flight and a small Monte Carlo
          at that mass, judged on the mission's rules. Ballast moves the centre of mass, so stability and rail exit
          change with it.
        </Explainer>
      </div>
    </div>
  )
}

/** Ballast in the units it is handled in: grams (or ounces) for plates, kilograms (or pounds) for totals. */
function formatBallast(kg: number, units: Units) {
  const imperial = ['lb', 'oz'].includes(unitFor('mass', units).symbol)
  if (!imperial) return kg < 1 ? `${Math.round(kg * 1000)} g` : `${kg.toFixed(2)} kg`
  const lb = kg / 0.45359237
  return lb < 1 ? `${(lb * 16).toFixed(1)} oz` : `${lb.toFixed(2)} lb`
}

function formatSigned(m: number, units: Units) {
  const shown = fromSI(m, 'altitude', units)
  const sign = shown > 0 ? '+' : shown < 0 ? '−' : ''
  return `${sign}${Math.abs(shown).toLocaleString(undefined, { maximumFractionDigits: 0 })} ${unitFor('altitude', units).symbol}`
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

const W = 560
const H = 220
const PAD = { top: 12, right: 16, bottom: 30, left: 56 }

/** Apogee against ballast from the flights the solve flew, with the target and the answer marked. */
function ApogeeCurve({ solution }: { solution: BallastSolution }) {
  const units = usePrefs((s) => s.display)
  const pts = solution.curve
  if (pts.length < 2) return null
  const xs = pts.map((p) => p.mass_kg)
  const ys = [...pts.map((p) => p.apogee_agl_m), solution.target_apogee_m]
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)]
  const pad = (y1 - y0) * 0.08 || 10
  const x = (v: number) => PAD.left + ((v - x0) / (x1 - x0 || 1)) * (W - PAD.left - PAD.right)
  const y = (v: number) => PAD.top + (1 - (v - (y0 - pad)) / (y1 - y0 + 2 * pad)) * (H - PAD.top - PAD.bottom)
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.mass_kg)},${y(p.apogee_agl_m)}`).join('')
  const rec = solution.recommended_kg
  return (
    <figure className="max-w-2xl space-y-1">
      <figcaption className="text-sm font-medium">Apogee against ballast</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Apogee against added ballast, with the target">
        {ticks(fromSI(y0 - pad, 'altitude', units), fromSI(y1 + pad, 'altitude', units), 4).map((t) => {
          const si = toSI(t, 'altitude', units)
          return (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(si)} y2={y(si)} className="stroke-chart-grid" />
              <text x={PAD.left - 6} y={y(si)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[11px]">
                {t.toLocaleString()}
              </text>
            </g>
          )
        })}
        {ticks(fromSI(x0, 'mass', units), fromSI(x1, 'mass', units), 5).map((t) => (
          <text key={t} x={x(toSI(t, 'mass', units))} y={H - 10} textAnchor="middle" className="fill-muted-foreground text-[11px]">
            {t.toLocaleString()} {unitFor('mass', units).symbol}
          </text>
        ))}
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(solution.target_apogee_m)}
          y2={y(solution.target_apogee_m)}
          strokeDasharray="5 4"
          className="stroke-foreground"
        />
        <text x={W - PAD.right} y={y(solution.target_apogee_m) - 6} textAnchor="end" className="fill-muted-foreground text-[11px]">
          target
        </text>
        <path d={path} fill="none" strokeWidth={2} className="stroke-chart-1" />
        {pts.map((p) => (
          <circle key={p.mass_kg} cx={x(p.mass_kg)} cy={y(p.apogee_agl_m)} r={3} className="fill-chart-1" />
        ))}
        {rec != null && solution.apogee_agl_m != null && (
          <circle cx={x(rec)} cy={y(solution.apogee_agl_m)} r={6} strokeWidth={2} className="fill-background stroke-chart-1">
            <title>Recommended</title>
          </circle>
        )}
      </svg>
    </figure>
  )
}

// --- Pane ---------------------------------------------------------------------------

export function Pane() {
  return (
    <RequireMission compact>
      <BallastPane />
    </RequireMission>
  )
}

const DEFAULT_BALLAST: NonNullable<Mission['ballast']> = { installed_kg: 0, increment_kg: 0.05, max_kg: 2 }

function BallastPane() {
  const layout = useSectionLayout()
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const b = draft.ballast ?? DEFAULT_BALLAST
  const solve = useSolve()
  const units = usePrefs((s) => s.display)
  const editBallast = (recipe: (x: NonNullable<Mission['ballast']>) => void) =>
    edit((d) => recipe((d.ballast ??= { ...DEFAULT_BALLAST })))
  const category = draft.constraints?.category
  const [targetText, setTargetText] = useState<string | null>(null)
  const shownTarget = b.target_apogee_m == null ? '' : String(Math.round(fromSI(b.target_apogee_m, 'altitude', units)))

  return (
    <div className="space-y-5 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Target</h2>
        <label className="block space-y-1 text-sm">
          <span>Target apogee (above the pad)</span>
          <span className="flex h-9 items-center rounded-md border border-border bg-background focus-within:border-primary">
            <input
              inputMode="decimal"
              value={targetText ?? shownTarget}
              placeholder={category ? 'competition category' : 'required'}
              onFocus={() => setTargetText(shownTarget)}
              onBlur={() => setTargetText(null)}
              onChange={(e) => {
                setTargetText(e.target.value)
                const n = Number(e.target.value)
                editBallast((x) => {
                  x.target_apogee_m = e.target.value.trim() === '' || !(n > 0) ? null : toSI(n, 'altitude', units)
                })
              }}
              className="h-full min-w-0 flex-1 bg-transparent px-3 tabular-nums outline-none"
            />
            <span className="pr-3 text-muted-foreground">{unitFor('altitude', units).symbol}</span>
          </span>
        </label>
        <p className="text-xs text-muted-foreground">
          {category
            ? 'Leave blank to use the competition category chosen in Go / no-go.'
            : 'Or choose a competition category in Go / no-go to use its target.'}
        </p>
      </section>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Ballast bay</h2>
        <QuantityField
          schema="Ballast"
          name="position_m"
          path="ballast.position_m"
          label="Bay centre, aft of the nose tip"
          quantity="distance"
          decimals={3}
          value={b.position_m ?? 0}
          onChange={(v) => editBallast((x) => void (x.position_m = v))}
        />
        <div className="grid grid-cols-2 gap-3">
          <QuantityField
            schema="Ballast"
            name="increment_kg"
            path="ballast.increment_kg"
            label="Increment"
            quantity="mass"
            decimals={3}
            value={b.increment_kg}
            onChange={(v) => editBallast((x) => void (x.increment_kg = v))}
          />
          <QuantityField
            schema="Ballast"
            name="max_kg"
            path="ballast.max_kg"
            label="Bay holds at most"
            quantity="mass"
            decimals={2}
            value={b.max_kg}
            onChange={(v) => editBallast((x) => void (x.max_kg = v))}
          />
        </div>
      </section>
      <Button variant="primary" className="w-full" disabled={solve.isPending} onClick={() => {
          solve.mutate(draft)
          layout.showCentre()
        }}>
        <Calculator /> {solve.isPending ? 'Solving' : 'Solve'}
      </Button>
      <ProblemNotice error={solve.error} />
      <section className="space-y-2 rounded-md border border-border p-3">
        <h2 className="text-sm font-semibold">Installed</h2>
        <p className="text-sm">
          {b.installed_kg > 0
            ? `${formatBallast(b.installed_kg, units)} at the bay. Every flight includes it.`
            : 'No ballast. Flights fly the rocket as designed.'}
        </p>
        {b.installed_kg > 0 && (
          <Button size="sm" variant="ghost" onClick={() => editBallast((x) => void (x.installed_kg = 0))}>
            Remove ballast
          </Button>
        )}
      </section>
    </div>
  )
}
