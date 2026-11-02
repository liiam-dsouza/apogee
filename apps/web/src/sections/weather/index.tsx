import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CloudDownload, Plus, Trash2, Wind } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type Environment, type ForecastInfo, type ResolvedProfile, type SurfaceWind } from '@/lib/api'
import { useIssuesAt } from '@/lib/mission/validation'
import { formatSI, fromSI, toSI, unitFor } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'
import { WindCharts, type ProfileSeries } from './ProfileCharts'
import { toWindPoints } from './wind'

/** Starting values for a measured surface wind; the speed and direction are the user's. */
const NEW_SURFACE_WIND: Omit<SurfaceWind, 'speed_ms' | 'direction_deg'> = {
  height_m: 2,
  alpha: 0.14,
  blend_depth_m: 300,
}

/** A forecast older than this is flagged; one older than STALE_H is flagged loudly. */
const AGEING_H = 6
const STALE_H = 24

const RANGES = [
  { label: '1 km', m: 1000 },
  { label: '3 km', m: 3000 },
  { label: '10 km', m: 10_000 },
] as const

const weatherKeys = {
  forecasts: (lat: number, lon: number) => ['weather', 'forecasts', lat.toFixed(3), lon.toFixed(3)] as const,
}

function useEnvironment() {
  return useMissionStore((s) => s.draft?.environment ?? null)
}

function useEditEnvironment() {
  const edit = useMissionStore((s) => s.edit)
  return (recipe: (env: Environment) => void) =>
    edit((d) => {
      d.environment ??= {}
      recipe(d.environment)
    })
}

function hoursSince(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 3_600_000
}

function age(iso: string): string {
  const h = hoursSince(iso)
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min ago`
  if (h < 48) return `${Math.round(h)} h ago`
  return `${Math.round(h / 24)} days ago`
}

const localTime = (iso: string, withDay = true) =>
  new Date(iso).toLocaleString(undefined, {
    weekday: withDay ? 'short' : undefined,
    day: withDay ? 'numeric' : undefined,
    month: withDay ? 'short' : undefined,
    hour: '2-digit',
    minute: '2-digit',
  })

/** Forecast age, worded and coloured by how much it should worry you. */
function AgeBadge({ fetched }: { fetched: string }) {
  const h = hoursSince(fetched)
  const tone = h >= STALE_H ? 'text-nogo' : h >= AGEING_H ? 'text-caution' : 'text-muted-foreground'
  return (
    <span className={cn('text-sm', tone)}>
      Fetched {age(fetched)}
      {h >= STALE_H ? ': fetch a new one if you can' : ''}
    </span>
  )
}

export function Centre() {
  return (
    <RequireMission>
      <WeatherCentre />
    </RequireMission>
  )
}

function WeatherCentre() {
  const environment = useEnvironment()
  const site = useMissionStore((s) => s.draft?.site ?? null)
  const [range, setRange] = useState<number>(3000)
  const [table, setTable] = useState(false)
  const atmosphere = environment?.atmosphere
  const wind = environment?.surface_wind ?? null
  const elevation = site?.elevation_m ?? 0

  const effective = useQuery({
    queryKey: ['weather', 'effective', environment, elevation],
    queryFn: () => api.effectiveProfile(environment ?? {}, elevation),
    enabled: site !== null,
    placeholderData: keepPreviousData,
  })

  const series = useMemo<ProfileSeries[]>(() => {
    const flown = effective.data?.levels
    if (!flown) return []
    const out: ProfileSeries[] = [
      {
        label: wind ? 'Flown (blended)' : atmosphere?.kind === 'manual' ? 'Entered' : 'Forecast',
        points: toWindPoints(flown, elevation),
        role: 'flown',
      },
    ]
    if (wind && atmosphere?.kind === 'profile') {
      out.push({ label: 'Forecast', points: toWindPoints(atmosphere.levels, elevation), role: 'reference' })
    }
    return out
  }, [effective.data, wind, atmosphere, elevation])

  if (!site) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          Weather is for a place. Add the launch site first.
        </p>
        <Link to="/site" className="text-primary underline-offset-4 hover:underline">
          Go to Site
        </Link>
      </div>
    )
  }

  const profile = atmosphere?.kind === 'profile' ? atmosphere : null
  const manual = atmosphere?.kind === 'manual' ? atmosphere : null
  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">
          {profile
            ? profile.valid_utc
              ? `Forecast for ${localTime(profile.valid_utc)}`
              : `Profile: ${profile.source}`
            : manual
              ? 'Wind entered by hand'
              : wind
              ? 'Measured surface wind, calm aloft'
              : 'Standard atmosphere, no wind'}
        </h2>
        {profile?.fetched_utc && <AgeBadge fetched={profile.fetched_utc} />}
        {profile && <p className="text-xs text-muted-foreground">{profile.source}</p>}
        {manual?.note && <p className="text-sm text-muted-foreground">{manual.note}</p>}
      </header>

      {series.length === 0 ? (
        <p className="max-w-[60ch] text-muted-foreground">
          Flights run in still air. Fetch a forecast in the pane to fly in the wind expected at the site, or enter a
          measured surface wind.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label="Height range" className="flex rounded-md border border-border p-0.5">
              {RANGES.map((r) => (
                <button
                  key={r.m}
                  type="button"
                  aria-pressed={range === r.m}
                  onClick={() => setRange(r.m)}
                  className={cn(
                    'rounded px-2.5 py-1 text-sm',
                    range === r.m ? 'bg-surface text-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground">above the pad</span>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setTable((t) => !t)}>
              {table ? 'Show charts' : 'Show table'}
            </Button>
          </div>
          {table ? (
            <LevelTable levels={effective.data?.levels ?? []} elevation={elevation} maxH={range} />
          ) : (
            <WindCharts
              series={series}
              maxH={range}
              measured={wind ? { h: wind.height_m ?? 2, speed: wind.speed_ms, from: wind.direction_deg } : undefined}
            />
          )}
        </>
      )}
      <ProblemNotice error={effective.error} />
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/weather">
          A forecast is fetched once and cached, then stored in the mission, so every run is reproducible offline. A
          measured surface wind follows a power law near the ground and fades into the forecast by the blend depth.
          Directions are where the wind blows from.
        </Explainer>
      </div>
    </div>
  )
}

function LevelTable({
  levels,
  elevation,
  maxH,
}: {
  levels: NonNullable<ResolvedProfile['levels']>
  elevation: number
  maxH: number
}) {
  const units = usePrefs((s) => s.display)
  const rows = toWindPoints(levels, elevation)
    .map((p, i) => ({ p, lv: levels[i] }))
    .filter(({ p }) => p.h >= 0 && p.h <= maxH)
  return (
    <div className="overflow-x-auto">
      <table className="w-full max-w-3xl text-sm tabular-nums">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-1 pr-4 font-normal">Above pad</th>
            <th className="py-1 pr-4 font-normal">Speed</th>
            <th className="py-1 pr-4 font-normal">From</th>
            <th className="py-1 pr-4 font-normal">Temperature</th>
            <th className="py-1 font-normal">Pressure</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ p, lv }) => (
            <tr key={lv.altitude_m} className="border-t border-border">
              <td className="py-1 pr-4">{formatSI(p.h, 'altitude', units)}</td>
              <td className="py-1 pr-4">{formatSI(p.speed, 'speed', units, 1)}</td>
              <td className="py-1 pr-4">{Math.round(p.from)}°</td>
              <td className="py-1 pr-4">{formatSI(lv.temperature_k, 'temperature', units, 1)}</td>
              <td className="py-1">{formatSI(lv.pressure_pa, 'pressure', units, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <WeatherPane />
    </RequireMission>
  )
}

type Source = 'standard' | 'profile' | 'manual'

const SOURCES: { id: Source; label: string }[] = [
  { id: 'standard', label: 'Standard' },
  { id: 'profile', label: 'Forecast' },
  { id: 'manual', label: 'By hand' },
]

function WeatherPane() {
  const site = useMissionStore((s) => s.draft?.site ?? null)
  const atmosphere = useEnvironment()?.atmosphere
  const editEnvironment = useEditEnvironment()
  const kind: Source = atmosphere?.kind ?? 'standard'
  // Which editor is showing. Picking Forecast changes nothing until an hour is used.
  const [shown, setShown] = useState<Source>(kind)
  if (!site) return <p className="p-4 text-sm text-muted-foreground">Add the launch site first.</p>

  const choose = (source: Source) => {
    setShown(source)
    if (source === 'standard' && kind !== 'standard') {
      editEnvironment((env) => {
        env.atmosphere = { kind: 'standard' }
      })
    }
  }

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Wind aloft</h2>
        <div role="radiogroup" aria-label="Wind aloft from" className="flex rounded-md border border-border p-0.5">
          {SOURCES.map((src) => (
            <button
              key={src.id}
              type="button"
              role="radio"
              aria-checked={shown === src.id}
              onClick={() => choose(src.id)}
              className={cn(
                'flex-1 rounded px-2 py-1 text-sm',
                shown === src.id ? 'bg-surface text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {src.label}
              {kind === src.id && shown !== src.id && <span className="sr-only"> (in use)</span>}
            </button>
          ))}
        </div>

        {shown === 'standard' && <p className="text-sm text-muted-foreground">Standard atmosphere: no wind aloft.</p>}
        {shown === 'profile' && (
          <>
            {atmosphere?.kind === 'profile' ? (
              <div className="space-y-1 rounded-md border border-border px-3 py-2">
                <p className="text-sm">
                  In use: {atmosphere.valid_utc ? `forecast for ${localTime(atmosphere.valid_utc)}` : atmosphere.source}
                </p>
                {atmosphere.fetched_utc && <AgeBadge fetched={atmosphere.fetched_utc} />}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Pick a forecast hour to fly in it.</p>
            )}
            <ForecastPicker latitude={site.latitude_deg} longitude={site.longitude_deg} elevation={site.elevation_m} />
          </>
        )}
        {shown === 'manual' && <ManualProfileEditor />}
      </section>
      <SurfaceWindEditor />
    </div>
  )
}

/** Heights (m above the pad) a new manual table starts with when copying a forecast. */
const COPY_HEIGHTS = [0, 300, 1000, 2000, 3000, 5000]

function ManualProfileEditor() {
  const atmosphere = useEnvironment()?.atmosphere
  const elevation = useMissionStore((s) => s.draft?.site?.elevation_m ?? 0)
  const editEnvironment = useEditEnvironment()
  const units = usePrefs((s) => s.display)
  const issues = useIssuesAt('environment.atmosphere', { nested: true })

  if (atmosphere?.kind !== 'manual') {
    const forecast = atmosphere?.kind === 'profile' ? atmosphere : null
    const start = () =>
      editEnvironment((env) => {
        const points = forecast ? toWindPoints(forecast.levels, elevation) : []
        const levels = forecast
          ? COPY_HEIGHTS.map((h) => {
              const p = points.reduce((best, q) => (Math.abs(q.h - h) < Math.abs(best.h - h) ? q : best))
              return { height_m: h, speed_ms: Number(p.speed.toFixed(1)), direction_deg: Math.round(p.from) % 360 }
            })
          : [{ height_m: 0, speed_ms: 0, direction_deg: 0 }]
        env.atmosphere = { kind: 'manual', note: forecast ? 'Started from a forecast' : '', levels }
      })
    return (
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Type in a wind table, e.g. from the range safety officer's briefing. Heights are above the pad.
        </p>
        <Button size="sm" onClick={start}>
          {forecast ? 'Start from the forecast in use' : 'Start a table'}
        </Button>
      </div>
    )
  }

  const levels = atmosphere.levels
  const setLevel = (i: number, key: 'height_m' | 'speed_ms' | 'direction_deg', si: number) =>
    editEnvironment((env) => {
      if (env.atmosphere?.kind === 'manual') env.atmosphere.levels[i][key] = si
    })
  const sortByHeight = () =>
    editEnvironment((env) => {
      if (env.atmosphere?.kind === 'manual') env.atmosphere.levels.sort((a, b) => a.height_m - b.height_m)
    })
  const hUnit = unitFor('altitude', units)
  const sUnit = unitFor('speed', units)

  return (
    <div className="space-y-3">
      <label className="block space-y-1 text-sm">
        <span>Where the numbers came from</span>
        <input
          value={atmosphere.note ?? ''}
          onChange={(e) =>
            editEnvironment((env) => {
              if (env.atmosphere?.kind === 'manual') env.atmosphere.note = e.target.value
            })
          }
          placeholder="e.g. RSO briefing, 09:00"
          className="h-9 w-full rounded-md border border-border bg-background px-3"
        />
      </label>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="pb-1 font-normal">Height ({hUnit.symbol})</th>
              <th className="pb-1 font-normal">Speed ({sUnit.symbol})</th>
              <th className="pb-1 font-normal">From (°)</th>
              <th className="pb-1" />
            </tr>
          </thead>
          <tbody>
            {levels.map((lv, i) => (
              <tr key={i}>
                <td className="pr-1 pb-1">
                  <NumberCell
                    label={`Height of level ${i + 1}`}
                    value={fromSI(lv.height_m, 'altitude', units)}
                    onChange={(v) => setLevel(i, 'height_m', toSI(v, 'altitude', units))}
                    onBlur={sortByHeight}
                  />
                </td>
                <td className="pr-1 pb-1">
                  <NumberCell
                    label={`Speed at level ${i + 1}`}
                    value={fromSI(lv.speed_ms, 'speed', units)}
                    decimals={1}
                    onChange={(v) => setLevel(i, 'speed_ms', toSI(v, 'speed', units))}
                  />
                </td>
                <td className="pr-1 pb-1">
                  <NumberCell
                    label={`Direction at level ${i + 1}`}
                    value={lv.direction_deg}
                    onChange={(v) => setLevel(i, 'direction_deg', v)}
                  />
                </td>
                <td className="pb-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove level ${i + 1}`}
                    disabled={levels.length === 1}
                    onClick={() =>
                      editEnvironment((env) => {
                        if (env.atmosphere?.kind === 'manual') env.atmosphere.levels.splice(i, 1)
                      })
                    }
                  >
                    <Trash2 />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button
        size="sm"
        onClick={() =>
          editEnvironment((env) => {
            if (env.atmosphere?.kind !== 'manual') return
            const last = env.atmosphere.levels[env.atmosphere.levels.length - 1]
            env.atmosphere.levels.push({ ...last, height_m: last.height_m + 500 })
          })
        }
      >
        <Plus /> Add level
      </Button>
      {issues.map((i) => (
        <p key={`${i.path}-${i.code}`} className="text-xs text-nogo">
          {i.message}
        </p>
      ))}
      <div className="grid grid-cols-2 gap-3">
        <OptionalQuantity
          label="Pad temperature"
          quantity="temperature"
          value={atmosphere.surface_temperature_k ?? null}
          onChange={(k) =>
            editEnvironment((env) => {
              if (env.atmosphere?.kind === 'manual') env.atmosphere.surface_temperature_k = k
            })
          }
        />
        <OptionalQuantity
          label="Station pressure"
          quantity="pressure"
          value={atmosphere.surface_pressure_pa ?? null}
          onChange={(pa) =>
            editEnvironment((env) => {
              if (env.atmosphere?.kind === 'manual') env.atmosphere.surface_pressure_pa = pa
            })
          }
        />
      </div>
      <p className="text-xs text-muted-foreground">
        The wind is held constant above the top level. Temperature and pressure follow the standard atmosphere,
        shifted to the pad's if you enter them (station pressure, not sea-level). A hot day thins the air and
        raises apogee.
      </p>
    </div>
  )
}

/** A measured value that may be left blank (blank means "use the standard atmosphere"). */
function OptionalQuantity({
  label,
  quantity,
  value,
  onChange,
}: {
  label: string
  quantity: 'temperature' | 'pressure'
  value: number | null
  onChange: (si: number | null) => void
}) {
  const units = usePrefs((s) => s.display)
  const [editing, setEditing] = useState<string | null>(null)
  const text = editing ?? (value == null ? '' : Number(fromSI(value, quantity, units).toFixed(1)).toString())
  return (
    <label className="block space-y-1 text-sm">
      <span>{label}</span>
      <span className="flex h-9 items-center rounded-md border border-border bg-background focus-within:border-primary">
        <input
          inputMode="decimal"
          value={text}
          placeholder="standard"
          onFocus={() => setEditing(text)}
          onBlur={() => setEditing(null)}
          onChange={(e) => {
            setEditing(e.target.value)
            const raw = e.target.value.trim()
            if (raw === '') onChange(null)
            else if (Number.isFinite(Number(raw))) onChange(toSI(Number(raw), quantity, units))
          }}
          className="h-full min-w-0 flex-1 bg-transparent px-3 tabular-nums outline-none"
        />
        <span className="pr-3 text-muted-foreground">{unitFor(quantity, units).symbol}</span>
      </span>
    </label>
  )
}

/** A compact numeric input for table cells; keeps partial typing ("1.") until blur. */
function NumberCell({
  label,
  value,
  onChange,
  onBlur,
  decimals = 0,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  onBlur?: () => void
  decimals?: number
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const text = editing ?? Number(value.toFixed(decimals)).toString()
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      value={text}
      onFocus={() => setEditing(text)}
      onBlur={() => {
        setEditing(null)
        onBlur?.()
      }}
      onChange={(e) => {
        setEditing(e.target.value)
        const n = Number(e.target.value)
        if (e.target.value.trim() !== '' && Number.isFinite(n)) onChange(n)
      }}
      className="h-8 w-full min-w-0 rounded-md border border-border bg-background px-2 tabular-nums"
    />
  )
}

/** Nearest forecast hour at or after now, else the last one. */
function defaultHour(hours: string[]): string {
  const now = Date.now()
  return hours.find((h) => new Date(h).getTime() >= now - 30 * 60_000) ?? hours[hours.length - 1]
}

function ForecastPicker({ latitude, longitude, elevation }: { latitude: number; longitude: number; elevation: number }) {
  const qc = useQueryClient()
  const editEnvironment = useEditEnvironment()
  const cached = useQuery({
    queryKey: weatherKeys.forecasts(latitude, longitude),
    queryFn: () => api.listForecasts(latitude, longitude),
  })
  const fetchNew = useMutation({
    mutationFn: () => api.fetchForecast(latitude, longitude),
    onSuccess: (info) => {
      qc.setQueryData<ForecastInfo[]>(weatherKeys.forecasts(latitude, longitude), (old) => [info, ...(old ?? [])])
      setForecastId(info.id)
    },
  })
  const [forecastId, setForecastId] = useState<string | null>(null)
  const forecast = cached.data?.find((f) => f.id === forecastId) ?? cached.data?.[0] ?? null
  // The hour picked applies to the forecast it was picked in.
  const [picked, setPicked] = useState<{ forecastId: string; hour: string } | null>(null)
  const chosenHour =
    picked && picked.forecastId === forecast?.id ? picked.hour : forecast ? defaultHour(forecast.hours) : null

  const apply = useMutation({
    mutationFn: () => api.forecastProfile(forecast!.id, chosenHour!, elevation),
    onSuccess: (profile) =>
      editEnvironment((env) => {
        env.atmosphere = profile
      }),
  })

  const days = useMemo(() => {
    const groups = new Map<string, string[]>()
    for (const h of forecast?.hours ?? []) {
      const day = new Date(h).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })
      groups.set(day, [...(groups.get(day) ?? []), h])
    }
    return [...groups]
  }, [forecast])

  return (
    <div className="space-y-3">
      <Button size="sm" onClick={() => fetchNew.mutate()} disabled={fetchNew.isPending}>
        <CloudDownload /> {fetchNew.isPending ? 'Fetching…' : 'Fetch forecast'}
      </Button>
      <ProblemNotice error={fetchNew.error} />

      {cached.data && cached.data.length > 0 && (
        <div className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span>Cached forecast</span>
            <select
              value={forecast?.id}
              onChange={(e) => setForecastId(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2"
            >
              {cached.data.map((f) => (
                <option key={f.id} value={f.id}>
                  Fetched {localTime(f.fetched_utc)} ({age(f.fetched_utc)})
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm">
            <span>Launch time (your time zone)</span>
            <select
              value={chosenHour ?? ''}
              onChange={(e) => forecast && setPicked({ forecastId: forecast.id, hour: e.target.value })}
              className="h-9 w-full rounded-md border border-border bg-background px-2 tabular-nums"
            >
              {days.map(([day, hours]) => (
                <optgroup key={day} label={day}>
                  {hours.map((h) => (
                    <option key={h} value={h}>
                      {localTime(h, false)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <Button size="sm" variant="primary" disabled={!chosenHour || apply.isPending} onClick={() => apply.mutate()}>
            Use this hour
          </Button>
          <ProblemNotice error={apply.error} />
          {forecast && (
            <p className="text-xs text-muted-foreground">
              Model grid point {forecast.grid_latitude.toFixed(3)}, {forecast.grid_longitude.toFixed(3)}, terrain{' '}
              {forecast.grid_elevation_m.toFixed(0)} m. The profile starts at your pad's elevation ({elevation.toFixed(0)}{' '}
              m).
            </p>
          )}
        </div>
      )}
      {cached.data?.length === 0 && (
        <p className="text-xs text-muted-foreground">No forecasts cached for this site yet. Fetching needs internet.</p>
      )}
    </div>
  )
}

function SurfaceWindEditor() {
  const wind = useEnvironment()?.surface_wind ?? null
  const editEnvironment = useEditEnvironment()

  const field = (
    name: keyof SurfaceWind & ('speed_ms' | 'direction_deg' | 'height_m' | 'alpha' | 'blend_depth_m'),
    label: string,
    quantity: 'speed' | 'angle' | 'length' | 'distance' | 'ratio',
    decimals: number,
  ) => (
    <QuantityField
      schema="SurfaceWind"
      name={name}
      path={`environment.surface_wind.${name}`}
      label={label}
      quantity={quantity}
      decimals={decimals}
      value={wind?.[name] ?? 0}
      onChange={(v) =>
        editEnvironment((env) => {
          if (env.surface_wind) env.surface_wind[name] = v
        })
      }
    />
  )

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Measured surface wind</h2>
      {wind ? (
        <>
          <div className="grid grid-cols-2 gap-3">
            {field('speed_ms', 'Speed', 'speed', 1)}
            {field('direction_deg', 'From', 'angle', 0)}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {field('height_m', 'Anemometer height', 'length', 1)}
            {field('alpha', 'Exponent (alpha)', 'ratio', 2)}
          </div>
          {field('blend_depth_m', 'Blend depth', 'distance', 0)}
          {wind.measured_utc && (
            <p className="text-xs text-muted-foreground">Measured {localTime(wind.measured_utc)}.</p>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              editEnvironment((env) => {
                env.surface_wind = null
              })
            }
          >
            Remove surface wind
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Measure the wind at the pad with an anemometer and enter it here. It replaces the forecast near the ground.
          </p>
          <Button
            size="sm"
            onClick={() =>
              editEnvironment((env) => {
                env.surface_wind = {
                  ...NEW_SURFACE_WIND,
                  speed_ms: 0,
                  direction_deg: 0,
                  measured_utc: new Date().toISOString(),
                }
              })
            }
          >
            <Wind /> Add surface wind
          </Button>
        </>
      )}
    </section>
  )
}
