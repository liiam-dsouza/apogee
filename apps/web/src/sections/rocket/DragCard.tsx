import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { FileUp, Sparkles } from 'lucide-react'
import { useMemo, useRef } from 'react'
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { Button } from '@/components/ui/button'
import { api, type DragCurve, type DragResponse, type Mission, type SurfaceFinish } from '@/lib/api'
import { useDebounced } from '@/lib/mission/useDebounced'
import type { FinSet } from '@/lib/rocket'
import { useMissionStore } from '@/stores/mission'

const FINISHES: [SurfaceFinish, string][] = [
  ['mirror', 'Mirror'],
  ['polished', 'Polished (0.5 µm)'],
  ['sheet_metal', 'Aircraft sheet metal (2 µm)'],
  ['optimum', 'Optimum paint (5 µm)'],
  ['smooth', 'Smooth paint (20 µm)'],
  ['normal', 'Regular paint (60 µm)'],
  ['unfinished', 'Unfinished (150 µm)'],
  ['rough_unfinished', 'Rough unfinished (250 µm)'],
  ['rough', 'Rough (500 µm)'],
]

const CROSS_SECTIONS: [FinSet['cross_section'], string][] = [
  ['square', 'Square edges'],
  ['rounded', 'Rounded edges'],
  ['airfoil', 'Airfoil'],
]

/** Mach numbers the breakdown table shows. */
const BREAKDOWN_MACH = [0.3, 0.8, 1.2]

const ESTIMATE: DragCurve = { estimate: true }

type Source = 'estimate' | 'table' | 'constant'

function sourceOf(c: DragCurve): Source {
  if (c.estimate) return 'estimate'
  return c.table ? 'table' : 'constant'
}

const selectClass = 'h-9 w-full rounded-md border border-border bg-background px-2 text-sm'

/** Drag on the Rocket page: where each curve comes from, the estimate's inputs, and the curves themselves. */
export function DragCard() {
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const rocket = draft.rocket!
  const { power_off: off, power_on: on, multiplier } = rocket.drag
  const allEstimated = sourceOf(off) === 'estimate' && sourceOf(on) === 'estimate'
  const anyEstimated = sourceOf(off) === 'estimate' || sourceOf(on) === 'estimate'
  const sameCurve = JSON.stringify(off) === JSON.stringify(on)

  const debounced = useDebounced(draft, 400)
  const drag = useQuery({
    queryKey: ['rocket', 'drag', debounced],
    queryFn: () => api.rocketDrag(debounced),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })

  const editDrag = (recipe: (d: NonNullable<Mission['rocket']>['drag']) => void) =>
    edit((d) => recipe(d.rocket!.drag))

  return (
    <section aria-label="Drag" className="max-w-4xl space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h3 className="font-display text-xl font-semibold">Drag</h3>
          <p className="text-sm text-muted-foreground">
            {allEstimated
              ? 'Estimated from the rocket’s shape, finish and fins.'
              : anyEstimated
                ? 'One curve is estimated from the shape; the other is set by hand.'
                : 'Set by hand. The estimate is shown next to it for comparison.'}
          </p>
        </div>
        {!allEstimated && (
          <Button
            variant="primary"
            size="sm"
            onClick={() =>
              editDrag((d) => {
                d.power_off = ESTIMATE
                d.power_on = ESTIMATE
              })
            }
          >
            <Sparkles />
            Switch to the estimate
          </Button>
        )}
      </header>

      <div className="grid gap-4 rounded-md border border-border p-3 md:grid-cols-[minmax(0,18rem)_1fr]">
        <div className="space-y-3">
          <CurveSource
            label="Power off (coasting)"
            path="rocket.drag.power_off"
            curve={off}
            onChange={(c) =>
              editDrag((d) => {
                // Power-on follows while it is the same curve.
                if (sameCurve) d.power_on = c
                d.power_off = c
              })
            }
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={sameCurve}
              onChange={(e) =>
                editDrag((d) => {
                  d.power_on = e.target.checked ? structuredClone(d.power_off) : ESTIMATE
                })
              }
            />
            Power on uses the same setting
          </label>
          {!sameCurve && (
            <CurveSource
              label="Power on (motor burning)"
              path="rocket.drag.power_on"
              curve={on}
              onChange={(c) => editDrag((d) => void (d.power_on = c))}
            />
          )}
          <QuantityField
            schema="Drag"
            name="multiplier"
            path="rocket.drag.multiplier"
            label="Multiplier"
            quantity="ratio"
            decimals={3}
            value={multiplier}
            onChange={(v) => editDrag((d) => void (d.multiplier = v))}
          />
          {anyEstimated && (
            <>
              <label className="block space-y-1 text-sm">
                <span>Surface finish</span>
                <select
                  value={rocket.surface_finish}
                  onChange={(e) => edit((d) => void (d.rocket!.surface_finish = e.target.value as SurfaceFinish))}
                  className={selectClass}
                >
                  {FINISHES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>
              {rocket.fins.map((f, i) => (
                <label key={i} className="block space-y-1 text-sm">
                  <span>Fin set {i + 1} edges</span>
                  <select
                    value={f.cross_section}
                    onChange={(e) =>
                      edit((d) => void (d.rocket!.fins[i].cross_section = e.target.value as FinSet['cross_section']))
                    }
                    className={selectClass}
                  >
                    {CROSS_SECTIONS.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </>
          )}
        </div>
        <div className="min-w-0 space-y-3">
          <ProblemNotice error={drag.error} />
          {drag.data && <DragCurves data={drag.data} allEstimated={allEstimated} />}
        </div>
      </div>

      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/drag">
          The estimate adds up drag part by part, as OpenRocket does: skin friction over the whole surface (it falls as the
          Reynolds number grows, so it changes with speed and altitude), the nose and boat-tail, the fin edges, and the
          base. While the motor burns, its exhaust fills the nozzle and that part of the base stops dragging. In flight the
          drag also rises with the angle of attack, up to 1.3 × at 17°. Expect it within about 15% below Mach 0.8, and
          less certain through Mach 1. A post-flight fit sets the multiplier from real altimeter data.
        </Explainer>
      </div>
    </section>
  )
}

/** One curve's source: estimate, a CSV table, or a constant CD. */
function CurveSource({
  label,
  path,
  curve,
  onChange,
}: {
  label: string
  path: string
  curve: DragCurve
  onChange: (c: DragCurve) => void
}) {
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const file = useRef<HTMLInputElement>(null)
  const source = sourceOf(curve)
  const upload = useMutation({
    mutationFn: (f: File) => api.uploadAsset(f, 'drag_table'),
    onSuccess: (info) => {
      edit((d) => {
        d.assets = { ...d.assets, [info.sha256]: { kind: 'drag_table', filename: info.filename, size: info.size } }
      })
      onChange({ estimate: false, table: info.sha256 })
    },
  })
  const tableName = curve.table ? (draft.assets?.[curve.table]?.filename ?? `${curve.table.slice(0, 12)}…`) : null

  return (
    <div className="space-y-2">
      <label className="block space-y-1 text-sm">
        <span>{label}</span>
        <select
          value={source}
          onChange={(e) => {
            const v = e.target.value as Source
            if (v === 'estimate') onChange(ESTIMATE)
            else if (v === 'constant') onChange({ estimate: false, constant_cd: 0.45 })
            else file.current?.click()
          }}
          className={selectClass}
        >
          <option value="estimate">Estimate from the shape</option>
          <option value="table">CD against Mach table (CSV)</option>
          <option value="constant">Constant CD</option>
        </select>
      </label>
      <input
        ref={file}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) upload.mutate(f)
          e.target.value = ''
        }}
      />
      {source === 'table' && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="truncate text-muted-foreground" title={tableName ?? undefined}>
            {tableName}
          </span>
          <Button size="sm" variant="ghost" onClick={() => file.current?.click()} disabled={upload.isPending}>
            <FileUp />
            Replace
          </Button>
        </div>
      )}
      {source === 'constant' && (
        <QuantityField
          schema="DragCurve"
          name="constant_cd"
          path={`${path}.constant_cd`}
          label="CD"
          quantity="ratio"
          decimals={3}
          value={curve.constant_cd ?? 0.45}
          onChange={(v) => onChange({ estimate: false, constant_cd: v })}
        />
      )}
      {upload.isPending && <p className="text-sm text-muted-foreground">Uploading…</p>}
      <ProblemNotice error={upload.error} />
    </div>
  )
}

function DragCurves({ data, allEstimated }: { data: DragResponse; allEstimated: boolean }) {
  const points = data.points
  const mach = useMemo(() => points.map((p) => p.mach), [points])
  // Estimated: the two phases. Otherwise what flies (reference ink) against the estimate.
  const main = useMemo(
    () => points.map((p) => (allEstimated ? p.estimate_off : p.power_off)),
    [points, allEstimated],
  )
  const compare = useMemo(
    () =>
      allEstimated
        ? { y: points.map((p) => p.estimate_on), label: 'power on' }
        : { y: points.map((p) => p.estimate_off), label: 'estimate' },
    [points, allEstimated],
  )
  const rows = BREAKDOWN_MACH.map((m) => points.find((p) => Math.abs(p.mach - m) < 1e-6)).filter((p) => p != null)

  return (
    <div className="space-y-3">
      <TimeSeriesChart
        title={allEstimated ? 'Estimated CD' : 'Power-off CD'}
        unit=""
        t={mach}
        y={main}
        label={allEstimated ? 'power off' : 'flown'}
        compare={compare}
        syncKey="rocket-drag"
        xUnit=""
        xLabel="Mach"
        height={180}
      />
      <p className="flex flex-wrap gap-x-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-5 bg-foreground" aria-hidden />
          {allEstimated ? 'Power off' : 'Flown (power off)'}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 border-t-2 border-dashed border-[var(--chart-2)]" aria-hidden />
          {allEstimated ? 'Power on: the exhaust fills part of the base' : 'Estimate from the shape'}
        </span>
      </p>
      <table className="w-full text-sm tabular-nums">
        <caption className="pb-1 text-left text-xs text-muted-foreground">
          Estimated power-off CD by part, at {data.elevation_m.toFixed(0)} m
        </caption>
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="text-left font-normal">Mach</th>
            <th className="text-right font-normal">Friction</th>
            <th className="text-right font-normal">Nose</th>
            <th className="text-right font-normal">Tail</th>
            <th className="text-right font-normal">Fins</th>
            <th className="text-right font-normal">Base</th>
            <th className="text-right font-normal text-foreground">Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.mach}>
              <td>{p.mach}</td>
              {[p.friction, p.nose, p.tail, p.fins, p.base].map((v, i) => (
                <td key={i} className="text-right">
                  {v.toFixed(3)}
                </td>
              ))}
              <td className="text-right font-medium">{p.estimate_off.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.notes.length > 0 && (
        <ul className="list-inside list-disc text-xs text-muted-foreground">
          {data.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
