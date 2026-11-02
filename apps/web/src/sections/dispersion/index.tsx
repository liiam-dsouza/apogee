import { Download, Play } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Explainer } from '@/components/Explainer'
import { collection, line, type LonLat } from '@/components/map/geo'
import { PointLayer } from '@/components/map/PointLayer'
import { MapScale, SiteLayers } from '@/components/map/SiteLayers'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { Map, MapControls, MapGeoJSON, MapMarker, MarkerContent, useMap } from '@/components/ui/map'
import { api, type CampaignResult, type MonteCarloParameters, type Probability } from '@/lib/api'
import { useCampaign, useRunCampaign } from '@/lib/campaign'
import { overlayColors } from '@/lib/mapStyles'
import { formatSI } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'


/** The map shows even with no mission open (it is the range overview), with a prompt. */
export function Centre() {
  return <DispersionMap />
}

function DispersionMap() {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  const site = useMissionStore((s) => s.draft?.site ?? null)
  const units = usePrefs((s) => s.units)
  const campaign = useCampaign(missionId)
  const result = campaign.data

  return (
    <div className="relative h-full">
      <Map
        key={missionId ?? 'none'}
        className="absolute inset-0 bg-background"
        center={site ? [site.longitude_deg, site.latitude_deg] : [0, 20]}
        zoom={site ? 12 : 1.5}
      >
        <MapControls position="bottom-right" showCompass />
        <MapScale unit={units} />
        {site && <SiteLayers site={site} />}
        {result && <CampaignLayers result={result} />}
      </Map>
      <div className="pointer-events-none absolute inset-x-0 top-0 flex p-4">
        <div className="pointer-events-auto w-full max-w-md space-y-3 rounded-md border border-border bg-surface/95 p-4 shadow-lg backdrop-blur">
          {!missionId ? (
            <p className="text-sm">Open a mission with a launch site to see its range here.</p>
          ) : !site ? (
            <p className="text-sm">This mission has no launch site yet. Add one in the Site section.</p>
          ) : result ? (
            <CampaignTiles result={result} />
          ) : (
            <p className="text-sm">Run a campaign from the pane to plot where the rocket could land.</p>
          )}
          <ProblemNotice error={campaign.error} />
          <Explainer methodsHref="/docs/methods/monte-carlo">
            The flight is run hundreds of times, each with its uncertain inputs drawn from their distributions (Latin
            hypercube sampling). The wind is perturbed as a whole profile, with smaller height-correlated noise, so the
            ellipse is not artificially small. Each ellipse is expected to hold the stated share of landings.
          </Explainer>
        </div>
      </div>
    </div>
  )
}

function CampaignLayers({ result }: { result: CampaignResult }) {
  const { resolvedTheme } = useMap()
  const units = usePrefs((s) => s.units)
  const c = overlayColors[resolvedTheme]
  const [hover, setHover] = useState<{ properties: { index: number; apogee: number }; x: number; y: number } | null>(
    null,
  )
  const points = useMemo(
    () => ({
      type: 'FeatureCollection' as const,
      features: result.points.map((p) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [p.longitude_deg, p.latitude_deg] },
        properties: { index: p.index, apogee: p.apogee_agl_m },
      })),
    }),
    [result.points],
  )
  const pointPaint = useMemo(
    () => ({
      'circle-radius': 3.5,
      'circle-color': c.primary,
      'circle-opacity': 0.75,
      'circle-stroke-width': 1,
      'circle-stroke-color': resolvedTheme === 'dark' ? '#0f1720' : '#ffffff',
    }),
    [c.primary, resolvedTheme],
  )
  const ellipses = result.summary.ellipses

  return (
    <>
      {ellipses.map((e, i) => (
        <MapGeoJSON
          key={e.probability}
          id={`ellipse-${i}`}
          data={collection([line([...e.polygon, e.polygon[0]] as LonLat[])])}
          fillPaint={false}
          linePaint={{
            'line-color': c.foreground,
            'line-width': i === 1 ? 2 : 1.25,
            'line-dasharray': i === 0 ? [1, 0] : i === 1 ? [4, 2] : [1, 2],
            'line-opacity': 0.9,
          }}
        />
      ))}
      <PointLayer id="landings" data={points} paint={pointPaint} onHover={setHover} />
      {ellipses[1] && (
        // One direct label, on the 95% ellipse at the end of its long axis; the legend names the rest.
        <MapMarker longitude={ellipses[1].polygon[0][0]} latitude={ellipses[1].polygon[0][1]}>
          <MarkerContent>
            <span className="pointer-events-none ml-10 rounded bg-background/80 px-1 text-xs text-foreground">95%</span>
          </MarkerContent>
        </MapMarker>
      )}
      {hover && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-lg"
          style={{ left: hover.x, top: hover.y - 8 }}
        >
          <p className="font-medium">Sample {hover.properties.index}</p>
          <p className="tabular-nums">Apogee {formatSI(hover.properties.apogee, 'altitude', units)}</p>
        </div>
      )}
    </>
  )
}

function percent(p: number): string {
  if (p === 0) return '0%'
  return p < 0.01 ? `${(p * 100).toFixed(1)}%` : `${Math.round(p * 100)}%`
}

function ProbabilityTile({ label, value }: { label: string; value: Probability | null | undefined }) {
  if (!value) return <Tile label={label} value="—" detail="No polygon drawn" />
  return (
    <Tile
      label={label}
      value={percent(value.p)}
      detail={`${value.count} of ${value.of}; at most ${percent(value.upper_95)} at 95% confidence`}
      tone={value.upper_95 >= 0.05 ? 'nogo' : value.upper_95 >= 0.01 ? 'caution' : undefined}
    />
  )
}

function Tile({ label, value, detail, tone }: { label: string; value: ReactNode; detail?: string; tone?: 'nogo' | 'caution' }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn('font-display text-2xl font-semibold tabular-nums', tone === 'nogo' && 'text-nogo', tone === 'caution' && 'text-caution')}>
        {value}
      </p>
      {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
    </div>
  )
}

/** Line styles match CampaignLayers: solid 68%, dashed 95%, dotted 99.7%; points are landings. */
function EllipseLegend() {
  const items: { label: string; dash?: string; width: number }[] = [
    { label: '68%', width: 1.25 },
    { label: '95%', dash: '4 2', width: 2 },
    { label: '99.7%', dash: '1 2', width: 1.25 },
  ]
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
      <li className="flex items-center gap-1.5">
        <svg width="10" height="10" aria-hidden>
          <circle cx="5" cy="5" r="3.5" className="fill-primary" />
        </svg>
        Landing
      </li>
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" x2="22" y1="3" y2="3" strokeWidth={i.width} strokeDasharray={i.dash} className="stroke-foreground" />
          </svg>
          {i.label} of landings
        </li>
      ))}
    </ul>
  )
}

function CampaignTiles({ result }: { result: CampaignResult }) {
  const units = usePrefs((s) => s.units)
  const { state, summary } = result
  const ellipse95 = summary.ellipses[1]
  const running = state.status === 'running'
  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <p className="flex justify-between text-sm">
          <span>{running ? 'Running' : state.status === 'done' ? 'Campaign complete' : `Campaign ${state.status}`}</span>
          <span className="tabular-nums text-muted-foreground">
            {state.samples_done} of {state.samples} samples
          </span>
        </p>
        <div className="h-1.5 overflow-hidden rounded-full bg-background" role="progressbar" aria-valuenow={state.samples_done} aria-valuemax={state.samples} aria-label="Campaign progress">
          <div className="h-full bg-chart-1 transition-[width]" style={{ width: `${(100 * state.samples_done) / state.samples}%` }} />
        </div>
        {summary.failed > 0 && (
          <p className="text-xs text-caution">
            {summary.failed} sample{summary.failed > 1 ? 's' : ''} failed to simulate; see the CSV.
          </p>
        )}
        {state.chunk_errors.map((e) => (
          <p key={e} className="text-xs text-nogo">
            {e}
          </p>
        ))}
        {state.status === 'stalled' && (
          <p className="text-xs text-caution">Some samples have no job (the stack restarted). Run it again to resume.</p>
        )}
      </div>
      <EllipseLegend />
      <div className="grid grid-cols-2 gap-3">
        <ProbabilityTile label="Lands outside the boundary" value={summary.outside_boundary} />
        <ProbabilityTile label="Lands in a hazard zone" value={summary.in_hazard} />
        <Tile
          label="95% landing ellipse"
          value={ellipse95 ? `${formatSI(2 * ellipse95.semi_major_m, 'distance', units)}` : '—'}
          detail={ellipse95 ? `by ${formatSI(2 * ellipse95.semi_minor_m, 'distance', units)}, long axis ${Math.round(ellipse95.bearing_deg)}°` : undefined}
        />
        <Tile
          label="Mean drift"
          value={
            summary.landing_center_east_m != null
              ? formatSI(Math.hypot(summary.landing_center_east_m, summary.landing_center_north_m ?? 0), 'distance', units)
              : '—'
          }
          detail="From the pad to the centre of the ellipses"
        />
      </div>
    </div>
  )
}

// --- Pane: campaign settings ------------------------------------------------------

type ParamKey = keyof MonteCarloParameters
type Display = 'percent' | 'deg' | 'length' | 'seconds' | 'altitude' | 'speed'

const PARAMS: { key: ParamKey; label: string; display: Display }[] = [
  { key: 'total_impulse', label: 'Total impulse', display: 'percent' },
  { key: 'burn_time', label: 'Burn time', display: 'percent' },
  { key: 'dry_mass', label: 'Dry mass', display: 'percent' },
  { key: 'dry_cg', label: 'Dry centre of mass', display: 'length' },
  { key: 'drag', label: 'Drag coefficient', display: 'percent' },
  { key: 'rail_inclination', label: 'Rail inclination', display: 'deg' },
  { key: 'rail_heading', label: 'Rail heading', display: 'deg' },
  { key: 'parachute_cd_s', label: 'Parachute CdS', display: 'percent' },
  { key: 'deployment_lag', label: 'Deployment lag', display: 'seconds' },
  { key: 'deploy_altitude', label: 'Deploy altitude', display: 'altitude' },
  { key: 'wind_speed', label: 'Wind speed (whole profile)', display: 'percent' },
  { key: 'wind_direction', label: 'Wind direction (whole profile)', display: 'deg' },
  { key: 'wind_layers', label: 'Wind noise between heights', display: 'speed' },
]

const DEFAULT_SIGMA: Record<ParamKey, number> = {
  total_impulse: 0.03,
  burn_time: 0.05,
  dry_mass: 0.005,
  dry_cg: 0.005,
  drag: 0.1,
  rail_inclination: 0.5,
  rail_heading: 2,
  parachute_cd_s: 0.1,
  deployment_lag: 0.3,
  deploy_altitude: 10,
  wind_speed: 0.15,
  wind_direction: 10,
  wind_layers: 1,
}

/** The model's defaults, for a mission saved before campaigns existed. */
const DEFAULT_CAMPAIGN = { samples: 200, seed: 1, wind_correlation_m: 750 }

export function Pane() {
  return (
    <RequireMission compact>
      <CampaignPane />
    </RequireMission>
  )
}

function CampaignPane() {
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const run = useRunCampaign()
  const campaign = useCampaign(draft.meta.id)
  const mc: NonNullable<typeof draft.monte_carlo> = draft.monte_carlo ?? DEFAULT_CAMPAIGN
  const editMc = (recipe: (m: NonNullable<typeof draft.monte_carlo>) => void) =>
    edit((d) => recipe((d.monte_carlo ??= { ...DEFAULT_CAMPAIGN })))
  const changed = campaign.startedFrom !== undefined && campaign.startedFrom !== draft

  const setSpread = (key: ParamKey, patch: { enabled?: boolean; sigma?: number }) =>
    editMc((m) => {
      const params = (m.parameters ??= {})
      params[key] = { enabled: true, sigma: DEFAULT_SIGMA[key], ...params[key], ...patch }
    })

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Campaign</h2>
        <div className="grid grid-cols-2 gap-3">
          <IntField
            label="Samples"
            value={mc.samples}
            onChange={(v) => editMc((m) => void (m.samples = v))}
          />
          <IntField label="Seed" value={mc.seed} onChange={(v) => editMc((m) => void (m.seed = v))} />
        </div>
        <Button
          variant="primary"
          className="w-full"
          disabled={run.isPending}
          onClick={() => run.mutate(draft)}
        >
          <Play /> {run.isPending ? 'Starting' : 'Run campaign'}
        </Button>
        <ProblemNotice error={run.error} />
        {changed && (
          <p className="text-xs text-caution">The mission has changed since the campaign shown. Run it again.</p>
        )}
        {campaign.id && (
          <a
            href={api.campaignCsvUrl(campaign.id)}
            download
            className="flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
          >
            <Download className="size-4" /> Every sample as CSV
          </a>
        )}
        <p className="text-xs text-muted-foreground">
          The same mission and seed always give the same samples, and a finished campaign is reused.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Uncertain inputs</h2>
        <p className="text-xs text-muted-foreground">One standard deviation each. Untick an input to hold it fixed.</p>
        <ul className="space-y-1.5">
          {PARAMS.map((p) => {
            const spread = mc.parameters?.[p.key] ?? { enabled: true, sigma: DEFAULT_SIGMA[p.key] }
            return (
              <li key={p.key} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`Vary ${p.label}`}
                  checked={spread.enabled}
                  onChange={(e) => setSpread(p.key, { enabled: e.target.checked })}
                />
                <span className={cn('flex-1 text-sm', !spread.enabled && 'text-muted-foreground')}>{p.label}</span>
                <SigmaField
                  label={`${p.label} spread`}
                  display={p.display}
                  sigma={spread.sigma}
                  disabled={!spread.enabled}
                  onChange={(sigma) => setSpread(p.key, { sigma })}
                />
              </li>
            )
          })}
        </ul>
        <QuantityField
          schema="MonteCarlo"
          name="wind_correlation_m"
          path="monte_carlo.wind_correlation_m"
          label="Wind noise correlation height"
          quantity="distance"
          decimals={0}
          value={mc.wind_correlation_m}
          onChange={(v) => editMc((m) => void (m.wind_correlation_m = v))}
        />
      </section>
      <CampaignStats />
    </div>
  )
}

function IntField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  const [editing, setEditing] = useState<string | null>(null)
  return (
    <label className="block space-y-1 text-sm">
      <span>{label}</span>
      <input
        inputMode="numeric"
        value={editing ?? String(value)}
        onFocus={() => setEditing(String(value))}
        onBlur={() => setEditing(null)}
        onChange={(e) => {
          setEditing(e.target.value)
          const n = Number(e.target.value)
          if (Number.isInteger(n) && n >= 0) onChange(n)
        }}
        className="h-9 w-full rounded-md border border-border bg-background px-3 tabular-nums"
      />
    </label>
  )
}

/** A spread in the unit people think in: percent for relative inputs, the user's units otherwise. */
function SigmaField({
  label,
  display,
  sigma,
  disabled,
  onChange,
}: {
  label: string
  display: Display
  sigma: number
  disabled: boolean
  onChange: (sigma: number) => void
}) {
  const system = usePrefs((s) => s.units)
  const [editing, setEditing] = useState<string | null>(null)
  const { toShown, fromShown, suffix } = useMemo(() => {
    if (display === 'percent') return { toShown: (v: number) => v * 100, fromShown: (v: number) => v / 100, suffix: '%' }
    if (display === 'deg') return { toShown: (v: number) => v, fromShown: (v: number) => v, suffix: '°' }
    if (display === 'seconds') return { toShown: (v: number) => v, fromShown: (v: number) => v, suffix: 's' }
    const quantity = display === 'length' ? 'length' : display === 'altitude' ? 'altitude' : 'speed'
    const metric = system === 'metric'
    // length in metric is metres; show millimetres for the centre of mass.
    if (quantity === 'length' && metric) return { toShown: (v: number) => v * 1000, fromShown: (v: number) => v / 1000, suffix: 'mm' }
    const factor = metric ? 1 : quantity === 'length' ? 0.0254 : 0.3048
    return {
      toShown: (v: number) => v / factor,
      fromShown: (v: number) => v * factor,
      suffix: metric ? (quantity === 'speed' ? 'm/s' : 'm') : quantity === 'length' ? 'in' : quantity === 'speed' ? 'ft/s' : 'ft',
    }
  }, [display, system])
  const text = editing ?? `${Number(toShown(sigma).toPrecision(3))}`
  return (
    <span className="flex h-8 w-28 items-center rounded-md border border-border bg-background">
      <span className="pl-2 text-xs text-muted-foreground">±</span>
      <input
        aria-label={label}
        inputMode="decimal"
        disabled={disabled}
        value={text}
        onFocus={() => setEditing(text)}
        onBlur={() => setEditing(null)}
        onChange={(e) => {
          setEditing(e.target.value)
          const n = Number(e.target.value)
          if (e.target.value.trim() !== '' && Number.isFinite(n) && n >= 0) onChange(fromShown(n))
        }}
        className="h-full min-w-0 flex-1 bg-transparent px-1 text-right text-sm tabular-nums outline-none disabled:text-muted-foreground"
      />
      <span className="pr-2 text-xs text-muted-foreground">{suffix}</span>
    </span>
  )
}

const KEY_OUTPUTS: { name: string; quantity: 'altitude' | 'speed' | 'distance' | null; digits: number }[] = [
  { name: 'apogee_agl_m', quantity: 'altitude', digits: 0 },
  { name: 'rail_exit_velocity_ms', quantity: 'speed', digits: 1 },
  { name: 'max_mach', quantity: null, digits: 2 },
  { name: 'drift_m', quantity: 'distance', digits: 0 },
  { name: 'landing_speed_ms', quantity: 'speed', digits: 1 },
]

function CampaignStats() {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  const units = usePrefs((s) => s.units)
  const { data } = useCampaign(missionId)
  if (!data || data.summary.done === 0) return null
  const fmt = (v: number, q: (typeof KEY_OUTPUTS)[number]) =>
    q.quantity ? formatSI(v, q.quantity, units, q.digits) : v.toFixed(q.digits)
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">Spread so far</h2>
      <table className="w-full text-sm tabular-nums">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="pb-1 font-normal" />
            <th className="pb-1 font-normal">5%</th>
            <th className="pb-1 font-normal">Median</th>
            <th className="pb-1 font-normal">95%</th>
          </tr>
        </thead>
        <tbody>
          {KEY_OUTPUTS.map((q) => {
            const s = data.summary.stats.find((x) => x.name === q.name)
            if (!s) return null
            return (
              <tr key={q.name} className="border-t border-border">
                <td className="py-1 pr-2 text-xs">{s.label}</td>
                <td className="py-1 pr-2">{fmt(s.p5, q)}</td>
                <td className="py-1 pr-2">{fmt(s.p50, q)}</td>
                <td className="py-1">{fmt(s.p95, q)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {data.summary.apogee_mean_standard_error_m != null && (
        <p className="text-xs text-muted-foreground">
          Mean apogee settled to ±{formatSI(2 * data.summary.apogee_mean_standard_error_m, 'altitude', units)} (95%).
        </p>
      )}
    </section>
  )
}
