import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, CircleCheck, CircleHelp, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { api, type StoreUsage } from '@/lib/api'
import { basemapSource } from '@/lib/mapStyles'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs, type Theme } from '@/stores/prefs'
import { UNIT_CHOICES, unitFor, type Quantity, type UnitSystem } from '@/lib/units'

export function Centre() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl space-y-10 p-6">
        <Display />
        <FieldReadiness />
        <System />
        <Storage />
        <p className="text-sm text-muted-foreground">Made with ❤️ by <a href="https://www.linkedin.com/in/liam-d-souza/" className="hover:underline">Liam D'Souza</a></p>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="font-display text-xl font-semibold">{title}</h2>
      {children}
    </section>
  )
}

function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="w-28 text-sm text-muted-foreground">{label}</span>
      <div role="radiogroup" aria-label={label} className="flex rounded-md border border-border p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={cn(
              'rounded px-3 py-1 text-sm',
              value === o.value ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Quantities a flight reports, in the order they appear on the results. */
const UNIT_ROWS: { q: Quantity; label: string; example: string }[] = [
  { q: 'altitude', label: 'Altitude', example: 'apogee, deployment heights' },
  { q: 'speed', label: 'Speed', example: 'rail exit, max speed, descent rates' },
  { q: 'acceleration', label: 'Acceleration', example: 'max acceleration' },
  { q: 'dynamic_pressure', label: 'Dynamic pressure', example: 'max q' },
  { q: 'distance', label: 'Distance', example: 'drift, rail length' },
  { q: 'energy', label: 'Energy', example: 'landing kinetic energy' },
  { q: 'mass', label: 'Mass', example: 'dry mass, propellant, ballast' },
  { q: 'length', label: 'Component length', example: 'diameter, fins, radii' },
  { q: 'force', label: 'Force', example: 'thrust' },
  { q: 'impulse', label: 'Impulse', example: 'total impulse' },
  { q: 'area', label: 'Area', example: 'parachute CdS' },
  { q: 'pressure', label: 'Air pressure', example: 'weather profiles' },
  { q: 'temperature', label: 'Temperature', example: 'weather profiles' },
  { q: 'density', label: 'Density', example: 'propellant' },
]

function Display() {
  const { theme, setTheme, units, setUnits, display, setUnitChoice } = usePrefs()
  const custom = Object.keys(display.choice).length > 0
  return (
    <Section title="Display">
      <Choice<Theme>
        label="Theme"
        value={theme}
        options={[
          { value: 'dark', label: 'Dark' },
          { value: 'light', label: 'Light (sunlight)' },
        ]}
        onChange={setTheme}
      />
      <Choice<UnitSystem>
        label="Units"
        value={units}
        options={[
          { value: 'metric', label: 'Metric' },
          { value: 'imperial', label: 'Imperial' },
        ]}
        onChange={setUnits}
      />
      <p className="text-xs text-muted-foreground">
        {custom
          ? 'Some quantities below are set individually. Choosing Metric or Imperial resets them all.'
          : 'Choose a system, then change any quantity below on its own.'}
      </p>
      <div className="space-y-2">
        {UNIT_ROWS.map(({ q, label, example }) => {
          const current = unitFor(q, display).symbol
          return (
            <div key={q} className="flex flex-wrap items-center gap-3">
              <span className="w-40 text-sm">
                {label}
                <span className="block text-xs text-muted-foreground">{example}</span>
              </span>
              <div role="radiogroup" aria-label={`${label} unit`} className="flex rounded-md border border-border p-0.5">
                {UNIT_CHOICES[q].map((u) => (
                  <button
                    key={u.symbol}
                    type="button"
                    role="radio"
                    aria-checked={current === u.symbol}
                    onClick={() => setUnitChoice(q, u.symbol === systemDefault(q, units) ? null : u.symbol)}
                    className={cn(
                      'min-w-12 rounded px-2.5 py-1 text-sm',
                      current === u.symbol ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {u.symbol}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        Display only: missions are always stored in SI units (angles in degrees), whatever is shown.
      </p>
    </Section>
  )
}

function systemDefault(q: Quantity, system: UnitSystem): string {
  return unitFor(q, system).symbol
}

type Check = { ok: boolean | null; label: string; detail: ReactNode }

/** What must be on this machine before the launch site, where there is often no internet. */
function FieldReadiness() {
  const draft = useMissionStore((s) => s.draft)
  const isDirty = useMissionStore((s) => s.isDirty)
  const site = draft?.site
  const forecasts = useQuery({
    queryKey: ['weather', 'forecasts', site?.latitude_deg.toFixed(3), site?.longitude_deg.toFixed(3)],
    queryFn: () => api.listForecasts(site!.latitude_deg, site!.longitude_deg),
    enabled: Boolean(site),
    // Age is taken when the list arrives (newest first), not on every render.
    select: (list) => ({
      newest: list[0],
      hoursOld: list[0] ? (Date.now() - new Date(list[0].fetched_utc).getTime()) / 3_600_000 : null,
    }),
  })
  const board = useQuery({
    queryKey: ['go-no-go', draft],
    queryFn: () => api.goNoGoBoard(draft!),
    enabled: Boolean(draft),
    retry: false,
  })

  if (!draft) {
    return (
      <Section title="Ready for the field?">
        <p className="text-sm text-muted-foreground">Open a mission to check it is ready to fly offline.</p>
      </Section>
    )
  }
  const atmosphere = draft.environment?.atmosphere
  const newest = forecasts.data?.newest
  const hoursOld = forecasts.data?.hoursOld ?? null
  const checks: Check[] = [
    {
      ok: Boolean(draft.rocket && draft.motor && draft.site),
      label: 'Rocket, motor and site',
      detail: draft.rocket && draft.motor && draft.site ? 'All set.' : 'Something is missing: the flight can\'t run.',
    },
    {
      ok: board.data ? board.data.flight.available : null,
      label: 'Single flight run for this mission',
      detail: board.data?.flight.available ? 'Stored, so it shows offline.' : <Link className="text-primary hover:underline" to="/flight">Run it in Single flight.</Link>,
    },
    {
      ok: board.data ? board.data.campaign.samples_done >= board.data.campaign.samples : null,
      label: 'Monte Carlo campaign run',
      detail: board.data
        ? `${board.data.campaign.samples_done} of ${board.data.campaign.samples} flights stored.`
        : 'Checking.',
    },
    {
      ok: site ? (newest ? hoursOld! < 24 : false) : null,
      label: 'Forecast cached for the site',
      detail: !site
        ? 'Needs a site.'
        : newest
          ? `Newest fetched ${Math.round(hoursOld!)} h ago. ${atmosphere?.kind === 'profile' ? 'The mission uses a forecast.' : 'The mission doesn\'t use it yet.'}`
          : 'None. Fetch one in Weather while you have internet.',
    },
    {
      ok: basemapSource === 'local',
      label: 'Offline map tiles',
      detail:
        basemapSource === 'local'
          ? 'Installed: the map works with no internet.'
          : 'Not installed: offline, the map shows only the site\'s own shapes. See the README for the tiles profile.',
    },
    {
      ok: !isDirty,
      label: 'Mission saved',
      detail: isDirty ? 'Unsaved changes: save before you leave.' : 'Saved.',
    },
  ]
  return (
    <Section title="Ready for the field?">
      <p className="text-sm text-muted-foreground">For {draft.meta.name}: what must be on this machine before you lose internet.</p>
      <ul className="space-y-2">
        {checks.map((c) => {
          const Icon = c.ok == null ? CircleHelp : c.ok ? CircleCheck : CircleAlert
          return (
            <li key={c.label} className="flex items-start gap-3">
              <Icon
                className={cn('mt-0.5 size-5 shrink-0', c.ok == null ? 'text-muted-foreground' : c.ok ? 'text-go' : 'text-caution')}
                aria-label={c.ok == null ? 'Unknown' : c.ok ? 'Ready' : 'Not ready'}
              />
              <div>
                <p className="text-sm">{c.label}</p>
                <p className="text-xs text-muted-foreground">{c.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </Section>
  )
}

function System() {
  const info = useQuery({ queryKey: ['system', 'info'], queryFn: api.systemInfo, refetchInterval: 10_000 })
  const d = info.data
  const rows: [string, ReactNode][] = d
    ? [
        ['RocketPy', d.rocketpy_version],
        ['simcore', d.simcore_version],
        ['Build', d.git_sha],
        ['Job queue', d.queue_available ? 'Reachable' : 'Not reachable: simulations can\'t run'],
        ['Workers', d.worker_count === 0 ? 'None running' : `${d.worker_count} running`],
        ['Field mode', d.field_mode ? 'On: opens on the go/no-go board' : 'Off'],
      ]
    : []
  return (
    <Section title="System">
      <ProblemNotice error={info.error} />
      <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </Section>
  )
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  const units = ['kB', 'MB', 'GB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`
}

function Storage() {
  const qc = useQueryClient()
  const storage = useQuery({ queryKey: ['system', 'storage'], queryFn: api.storage })
  const clear = useMutation({
    mutationFn: api.clearStore,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['system', 'storage'] }),
  })
  return (
    <Section title="Storage">
      <p className="text-sm text-muted-foreground">
        What this machine holds besides the missions themselves. Computed results can be cleared: they are recomputed
        on the next run.
      </p>
      <ProblemNotice error={storage.error ?? clear.error} />
      <table className="w-full text-sm tabular-nums">
        <tbody>
          {storage.data?.map((s) => (
            <StoreRow key={s.name} store={s} onClear={() => clear.mutate(s.name)} clearing={clear.isPending} />
          ))}
        </tbody>
      </table>
      <div className="max-w-xl">
        <Explainer>
          Thrust curves, drag tables and cached forecasts can't be cleared here: a mission may need them to fly
          offline, and a forecast can't be fetched again once its time has passed.
        </Explainer>
      </div>
    </Section>
  )
}

function StoreRow({ store, onClear, clearing }: { store: StoreUsage; onClear: () => void; clearing: boolean }) {
  const [confirming, setConfirming] = useState(false)
  return (
    <tr className="border-t border-border">
      <td className="py-2 pr-4">{store.label}</td>
      <td className="py-2 pr-4 text-muted-foreground">{store.items} items</td>
      <td className="py-2 pr-4 text-muted-foreground">{bytes(store.bytes)}</td>
      <td className="py-2 text-right">
        {store.recomputable && store.items > 0 &&
          (confirming ? (
            <span className="inline-flex items-center gap-2">
              Clear?
              <button
                type="button"
                className="text-nogo hover:underline"
                disabled={clearing}
                onClick={() => {
                  onClear()
                  setConfirming(false)
                }}
              >
                Clear
              </button>
              <button type="button" className="text-muted-foreground hover:underline" onClick={() => setConfirming(false)}>
                Keep
              </button>
            </span>
          ) : (
            <button
              type="button"
              aria-label={`Clear ${store.label}`}
              className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
              onClick={() => setConfirming(true)}
            >
              <Trash2 className="size-4" /> Clear
            </button>
          ))}
      </td>
    </tr>
  )
}
