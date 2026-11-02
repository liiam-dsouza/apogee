import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CloudDownload, Wind } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type Environment, type ForecastInfo, type ResolvedProfile, type SurfaceWind } from '@/lib/api'
import { formatSI } from '@/lib/units'
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
      { label: wind ? 'Flown (blended)' : 'Forecast', points: toWindPoints(flown, elevation), role: 'flown' },
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
  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">
          {profile
            ? profile.valid_utc
              ? `Forecast for ${localTime(profile.valid_utc)}`
              : `Profile: ${profile.source}`
            : wind
              ? 'Measured surface wind, calm aloft'
              : 'Standard atmosphere, no wind'}
        </h2>
        {profile?.fetched_utc && <AgeBadge fetched={profile.fetched_utc} />}
        {profile && <p className="text-xs text-muted-foreground">{profile.source}</p>}
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
  const units = usePrefs((s) => s.units)
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

function WeatherPane() {
  const site = useMissionStore((s) => s.draft?.site ?? null)
  const environment = useEnvironment()
  const editEnvironment = useEditEnvironment()
  if (!site) return <p className="p-4 text-sm text-muted-foreground">Add the launch site first.</p>
  const atmosphere = environment?.atmosphere
  const usingForecast = atmosphere?.kind === 'profile'

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Wind aloft</h2>
        {usingForecast ? (
          <div className="space-y-2 rounded-md border border-border px-3 py-2">
            <p className="text-sm">
              {atmosphere.valid_utc ? `Forecast for ${localTime(atmosphere.valid_utc)}` : atmosphere.source}
            </p>
            {atmosphere.fetched_utc && <AgeBadge fetched={atmosphere.fetched_utc} />}
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                editEnvironment((env) => {
                  env.atmosphere = { kind: 'standard' }
                })
              }
            >
              Use the standard atmosphere instead
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Standard atmosphere: no wind aloft.</p>
        )}
        <ForecastPicker latitude={site.latitude_deg} longitude={site.longitude_deg} elevation={site.elevation_m} />
      </section>
      <SurfaceWindEditor />
    </div>
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
