import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Check, Play, Search } from 'lucide-react'
import { useState } from 'react'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { Button } from '@/components/ui/button'
import { api, type FinderRequest, type FinderRow } from '@/lib/api'
import { formatSI } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'
import { useApplyMotor } from './apply'

/** Standard motor-mount diameters, as the server rounds to. */
const DIAMETERS_MM = [13, 18, 24, 29, 38, 54, 75, 98, 152]
/** 10,000 ft: the commonest competition target, until the board names one. */
const DEFAULT_TARGET_M = 3048
/** Rows before "Show all". */
const SHOWN = 15

const VERDICT = {
  go: { label: 'GO', className: 'text-go' },
  no_go: { label: 'NO-GO', className: 'text-nogo' },
  incomplete: { label: 'Incomplete', className: 'text-caution' },
} as const

/** Rank ThrustCurve.org motors that fit the mount against a target apogee, and fly the best. */
export function MotorFinder() {
  const draft = useMissionStore((s) => s.draft!)
  const settings = draft.constraints
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.listProfiles, staleTime: Infinity })
  const categoryTarget = profiles.data
    ?.find((p) => p.id === settings?.profile)
    ?.categories?.find((c) => c.id === settings?.category)?.apogee_target_m

  const [target, setTarget] = useState<number | null>(null)
  const [diameter, setDiameter] = useState<number | null>(null)
  const [length, setLength] = useState<number | null>(null)
  const [discontinued, setDiscontinued] = useState(false)
  const [alsoFly, setAlsoFly] = useState<string[]>([])
  const [asked, setAsked] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const apply = useApplyMotor()

  const ready = Boolean(draft.rocket && draft.site)
  const request: FinderRequest = {
    mission: draft,
    target_apogee_m: target ?? categoryTarget ?? DEFAULT_TARGET_M,
    // Unset: the server takes the current motor's case.
    mount: diameter != null && length != null ? { diameter_mm: diameter, max_length_mm: length } : null,
    flights: 8,
    also_fly: alsoFly,
    discontinued,
  }
  const finder = useQuery({
    queryKey: ['motors', 'finder', request],
    queryFn: () => api.findMotors(request),
    enabled: asked && ready,
    placeholderData: keepPreviousData,
    // The flights run as jobs: ask again until every one has landed.
    refetchInterval: (q) =>
      q.state.data?.rows.some((r) => r.run && (r.run.status === 'queued' || r.run.status === 'running')) ? 1000 : false,
  })
  const found = asked ? finder.data : undefined
  const rows = found ? (showAll ? found.rows : found.rows.slice(0, SHOWN)) : []
  const flying = found?.rows.filter((r) => r.run && r.run.status !== 'done' && r.run.status !== 'failed').length ?? 0

  return (
    <section aria-label="Motor finder" className="max-w-6xl space-y-4" data-tour="motor-finder">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">Motor finder</h2>
        <p className="text-sm text-muted-foreground">
          Every ThrustCurve.org motor that fits the mount, screened against the target apogee; the closest are flown in
          full and judged on the go/no-go board's rules.
        </p>
      </header>
      {!ready ? (
        <p className="text-sm text-muted-foreground">The finder needs a rocket and a launch site.</p>
      ) : (
        <form
          className="grid max-w-3xl grid-cols-1 items-end gap-3 sm:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]"
          onSubmit={(e) => {
            e.preventDefault()
            setAsked(true)
          }}
        >
          <QuantityField
            schema="FinderRequest"
            name="target_apogee_m"
            path="target_apogee_m"
            label={target == null && categoryTarget != null ? 'Target apogee (category)' : 'Target apogee'}
            quantity="altitude"
            decimals={0}
            value={request.target_apogee_m!}
            onChange={setTarget}
          />
          <label className="block space-y-1 text-sm">
            <span>Mount diameter</span>
            <select
              value={diameter ?? found?.mount.diameter_mm ?? ''}
              onChange={(e) => {
                setDiameter(Number(e.target.value))
                setLength((l) => l ?? found?.mount.max_length_mm ?? 1000)
              }}
              className="h-9 w-full rounded-md border border-border bg-background px-2"
            >
              {diameter == null && found == null && <option value="">The motor's</option>}
              {DIAMETERS_MM.map((d) => (
                <option key={d} value={d}>
                  {d} mm
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm">
            <span>Longest motor (mm)</span>
            <input
              type="number"
              min={1}
              inputMode="numeric"
              value={length ?? found?.mount.max_length_mm ?? ''}
              placeholder="The motor's"
              onChange={(e) => {
                setLength(e.target.value === '' ? null : Number(e.target.value))
                setDiameter((d) => d ?? found?.mount.diameter_mm ?? 54)
              }}
              className="h-9 w-full rounded-md border border-border bg-background px-3 tabular-nums"
            />
          </label>
          <label className="flex h-9 items-center gap-2 text-sm">
            <input type="checkbox" checked={discontinued} onChange={(e) => setDiscontinued(e.target.checked)} />
            Out of production too
          </label>
          {!asked && (
            <Button type="submit" variant="primary">
              <Search /> Find motors
            </Button>
          )}
        </form>
      )}
      <ProblemNotice error={asked ? finder.error : null} />
      {found && (
        <>
          <p className="text-xs text-muted-foreground">
            {found.rows.length} of {found.catalogue_count} {found.mount.diameter_mm} mm motors fit a{' '}
            {found.mount.max_length_mm} mm mount. Catalogue from{' '}
            {new Date(found.catalogue_fetched_at * 1000).toLocaleDateString()}.
            {flying > 0 && ` Flying ${flying}.`}
            {!found.curves_fetched && ' ThrustCurve.org could not be reached for some thrust curves: those are only screened.'}
          </p>
          {found.rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm tabular-nums">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="pr-4 pb-2 font-normal">Motor</th>
                    <th className="pr-4 pb-2 font-normal">Impulse</th>
                    <th className="pr-4 pb-2 font-normal">Screened</th>
                    <th className="pr-4 pb-2 font-normal">Apogee</th>
                    <th className="pr-4 pb-2 font-normal">Off the rail</th>
                    <th className="pr-4 pb-2 font-normal">Min stability</th>
                    <th className="pr-4 pb-2 font-normal" title="Thrust to weight">
                      T/W
                    </th>
                    <th className="pr-4 pb-2 font-normal">Board</th>
                    <th className="pb-2 font-normal" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <Row
                      key={r.candidate.motor_id}
                      row={r}
                      target={found.target_apogee_m}
                      current={draft.motor?.thrust_curve === r.asset?.sha256}
                      onFly={() => setAlsoFly((ids) => [...ids, r.candidate.motor_id])}
                      onUse={() => {
                        // The mount stays as searched, not the new motor's case.
                        setDiameter(found.mount.diameter_mm)
                        setLength(found.mount.max_length_mm)
                        apply({ motor: r.motor!, asset: r.asset! })
                      }}
                    />
                  ))}
                </tbody>
              </table>
              {found.rows.length > SHOWN && (
                <Button variant="ghost" size="sm" className="mt-2" onClick={() => setShowAll((v) => !v)}>
                  {showAll ? 'Show fewer' : `Show all ${found.rows.length}`}
                </Button>
              )}
            </div>
          )}
        </>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/motor-finder">
          Each motor is first screened as a point mass from its catalogue numbers: average thrust, burn time and masses,
          with this rocket's drag. The eight nearest the target are then flown in full with their real thrust curves and
          judged on the board's rules, all on that one flight, so a rule on the 95th percentile of a campaign is judged
          on the nominal flight here. Flown motors are listed first: GO, then nearest the target. Run a Monte Carlo
          campaign on the one you choose.
        </Explainer>
      </div>
    </section>
  )
}

function Row({
  row,
  target,
  current,
  onFly,
  onUse,
}: {
  row: FinderRow
  target: number
  current: boolean
  onFly: () => void
  onUse: () => void
}) {
  const units = usePrefs((s) => s.display)
  const { candidate: c, estimate: e, flown: f, judgement: j, run } = row
  const pending = run != null && (run.status === 'queued' || run.status === 'running')
  const miss = (apogee: number) => {
    const off = ((apogee - target) / target) * 100
    return `${off >= 0 ? '+' : ''}${off.toFixed(1)}%`
  }
  return (
    <tr className={cn('border-t border-border align-top', !f && 'text-muted-foreground')}>
      <td className="py-2 pr-4">
        <span className={cn('font-medium', f && 'text-foreground')}>
          {c.manufacturer} {c.designation}
        </span>
        <span className="block text-xs text-muted-foreground">
          {[c.type === 'SU' ? 'Single use' : c.type, c.case_info, c.propellant, `${Math.round(c.length_mm)} mm`]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </td>
      <td className="py-2 pr-4">
        {c.impulse_class} {formatSI(c.total_impulse_ns, 'impulse', units)}
      </td>
      <td className="py-2 pr-4">{formatSI(e.apogee_agl_m, 'altitude', units)}</td>
      {run?.status === 'failed' ? (
        <td colSpan={5} className="py-2 text-nogo">
          The flight failed: {run.error}
        </td>
      ) : pending ? (
        <td colSpan={5} className="py-2">
          Flying
        </td>
      ) : f && j ? (
        <>
          <td className="py-2 pr-4">
            <span className="font-medium">{formatSI(f.apogee_agl_m, 'altitude', units)}</span>
            <span className="block text-xs text-muted-foreground">{miss(f.apogee_agl_m)}</span>
          </td>
          <td className="py-2 pr-4">{formatSI(f.rail_exit_velocity_ms, 'speed', units, 1)}</td>
          <td className="py-2 pr-4">{f.min_stability_margin_cal.toFixed(2)} cal</td>
          <td className="py-2 pr-4">{f.thrust_to_weight.toFixed(1)}</td>
          <td className="py-2 pr-4">
            <span className={cn('font-medium', VERDICT[j.verdict].className)}>{VERDICT[j.verdict].label}</span>
            {j.points != null && <span className="ml-2 text-xs text-muted-foreground">{Math.round(j.points)} pts</span>}
            {j.failing.length > 0 && (
              <span className="block max-w-[24ch] text-xs text-muted-foreground">
                {j.failing[0]}
                {j.failing.length > 1 && ` and ${j.failing.length - 1} more`}
              </span>
            )}
          </td>
        </>
      ) : (
        <td colSpan={5} className="py-2 text-xs">
          {!run && 'Screened only'}
        </td>
      )}
      <td className="py-2 text-right">
        {f && row.motor && row.asset ? (
          current ? (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Check className="size-3.5" /> In use
            </span>
          ) : (
            <Button size="sm" onClick={onUse}>
              Use
            </Button>
          )
        ) : (
          !run && (
            <Button size="sm" variant="ghost" onClick={onFly} aria-label={`Fly ${c.designation}`}>
              <Play /> Fly
            </Button>
          )
        )}
      </td>
    </tr>
  )
}
