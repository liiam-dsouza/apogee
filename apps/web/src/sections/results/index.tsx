import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { Link } from 'react-router'
import { Histogram } from '@/components/charts/Histogram'
import { Explainer } from '@/components/Explainer'
import { RequireMission } from '@/components/RequireMission'
import { api, type Distribution } from '@/lib/api'
import { useCampaign } from '@/lib/campaign'
import { fromSI, unitFor, type Quantity } from '@/lib/units'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** How each output is shown: its quantity for unit conversion (null: shown as is) and precision. */
const DISPLAY: Record<string, { quantity: Quantity | null; digits: number; symbol?: string }> = {
  apogee_agl_m: { quantity: 'altitude', digits: 0 },
  apogee_time_s: { quantity: null, digits: 1, symbol: 's' },
  rail_exit_velocity_ms: { quantity: 'speed', digits: 1 },
  stability_margin_at_rail_exit_cal: { quantity: null, digits: 2, symbol: 'cal' },
  min_stability_margin_cal: { quantity: null, digits: 2, symbol: 'cal' },
  max_mach: { quantity: null, digits: 2 },
  max_dynamic_pressure_pa: { quantity: 'dynamic_pressure', digits: 1 },
  max_acceleration_ms2: { quantity: 'acceleration', digits: 0 },
  drift_m: { quantity: 'distance', digits: 0 },
  landing_speed_ms: { quantity: 'speed', digits: 1 },
  flight_time_s: { quantity: null, digits: 0, symbol: 's' },
}

/** The histograms shown, in order: the numbers a launch decision turns on. */
const SHOWN = [
  'apogee_agl_m',
  'rail_exit_velocity_ms',
  'max_mach',
  'min_stability_margin_cal',
  'drift_m',
  'landing_speed_ms',
  'max_dynamic_pressure_pa',
  'flight_time_s',
]

function useFormat() {
  const units = usePrefs((s) => s.display)
  return (name: string) => {
    const d = DISPLAY[name] ?? { quantity: null, digits: 2 }
    const symbol = d.quantity ? unitFor(d.quantity, units).symbol : d.symbol
    const toShown = (si: number) => (d.quantity ? fromSI(si, d.quantity, units) : si)
    const format = (shown: number) =>
      `${shown.toLocaleString(undefined, { minimumFractionDigits: d.digits, maximumFractionDigits: d.digits })}${symbol ? ` ${symbol}` : ''}`
    return { toShown, format }
  }
}

export function Centre() {
  return (
    <RequireMission>
      <ResultsCentre />
    </RequireMission>
  )
}

function useDistributions(campaignId: string | undefined, samplesDone: number | undefined) {
  return useQuery({
    // Refetch as the campaign fills in.
    queryKey: ['campaigns', campaignId, 'distributions', samplesDone],
    queryFn: () => api.campaignDistributions(campaignId!),
    enabled: Boolean(campaignId),
    placeholderData: (prev) => prev,
  })
}

function ResultsCentre() {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  const campaign = useCampaign(missionId)
  const dists = useDistributions(campaign.id, campaign.data?.state.samples_done)
  const formatFor = useFormat()

  if (!campaign.id) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          No campaign yet. Run one from Dispersion to see how much each number varies.
        </p>
        <Link to="/dispersion" className="text-primary underline-offset-4 hover:underline">
          Go to Dispersion
        </Link>
      </div>
    )
  }

  const byName = new Map((dists.data ?? []).map((d: Distribution) => [d.name, d]))
  const state = campaign.data?.state
  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">
          {state ? `Spread across ${state.samples_done} flights` : 'Spread across the campaign'}
        </h2>
        {state && (
          <p className="text-sm text-muted-foreground">
            {state.status === 'running' ? `Still running: ${state.samples_done} of ${state.samples}. ` : ''}Each chart
            is one output across every sample.
          </p>
        )}
      </header>
      <div className="grid gap-x-8 gap-y-6 md:grid-cols-2 xl:grid-cols-3">
        {SHOWN.map((name) => {
          const d = byName.get(name)
          if (!d || d.values.length === 0) return null
          const { toShown, format } = formatFor(name)
          return <Histogram key={name} title={d.label} values={d.values.map(toShown)} format={format} />
        })}
      </div>
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/monte-carlo">
          Percentiles are counted from the samples, not assumed normal. The 5% and 95% lines bound the middle 90% of
          flights. With a few hundred samples the extreme tails are uncertain; the probabilities on the Dispersion map
          carry their confidence bound for that reason.
        </Explainer>
      </div>
    </div>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <ResultsPane />
    </RequireMission>
  )
}

function ResultsPane() {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  const campaign = useCampaign(missionId)
  const formatFor = useFormat()
  const stats = campaign.data?.summary.stats ?? []
  if (!campaign.id) return <p className="p-4 text-sm text-muted-foreground">No campaign yet.</p>
  return (
    <div className="space-y-4 p-4">
      <h2 className="text-sm font-semibold">Every output</h2>
      <div className="overflow-x-auto">
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
            {stats
              .filter((s) => DISPLAY[s.name])
              .map((s) => {
                const { toShown, format } = formatFor(s.name)
                return (
                  <tr key={s.name} className="border-t border-border align-top">
                    <td className="py-1 pr-2 text-xs">{s.label}</td>
                    <td className="py-1 pr-2">{format(toShown(s.p5))}</td>
                    <td className="py-1 pr-2">{format(toShown(s.p50))}</td>
                    <td className="py-1">{format(toShown(s.p95))}</td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </div>
      <a
        href={api.campaignCsvUrl(campaign.id)}
        download
        className="flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
      >
        <Download className="size-4" /> Every sample as CSV
      </a>
    </div>
  )
}
