import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { Button } from '@/components/ui/button'
import { api, type FailureOutcome } from '@/lib/api'
import { formatSI } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'
import { useFailuresAsked } from './failuresAsked'

/** Above this a landing is likely to break the rocket or hurt someone: IREC's and AURC's main limit. */
const SAFE_LANDING_MS = 11

/** The mission flown with each part of its recovery failed: how hard and how far it lands. */
export function Failures() {
  const draft = useMissionStore((s) => s.draft!)
  const units = usePrefs((s) => s.display)
  // Flying three missions is a deliberate act; after that, keep the answer current.
  const asked = useFailuresAsked((s) => s.missions.includes(draft.meta.id!))
  const ask = useFailuresAsked((s) => s.ask)
  const enabled = asked
  const failures = useQuery({
    queryKey: ['recovery', 'failures', draft],
    queryFn: () => api.recoveryFailures(draft),
    enabled,
    placeholderData: keepPreviousData,
    // The flights run as jobs: ask again until every one has landed.
    refetchInterval: (q) => (q.state.data?.outcomes.some((o) => o.run.status !== 'done' && o.run.status !== 'failed') ? 1000 : false),
  })
  const data = enabled ? failures.data : undefined

  return (
    <section aria-label="If recovery fails" className="max-w-5xl space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">If recovery fails</h2>
        <p className="text-sm text-muted-foreground">
          The questions a range safety officer asks: how hard it lands and how far it goes if part of the recovery fails.
        </p>
      </header>
      {!enabled && (
        <Button variant="primary" onClick={() => ask(draft.meta.id!)}>
          <Play /> Fly the failures
        </Button>
      )}
      <ProblemNotice error={enabled ? failures.error : null} />
      {data && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="pb-2 font-normal">What fails</th>
                <th className="pb-2 font-normal">Still opens</th>
                <th className="pb-2 font-normal">Opens at</th>
                <th className="pb-2 font-normal">Touchdown</th>
                <th className="pb-2 font-normal">Energy</th>
                <th className="pb-2 font-normal">Lands</th>
              </tr>
            </thead>
            <tbody>
              {data.outcomes.map((o) => (
                <Row key={o.mode} o={o} />
              ))}
            </tbody>
          </table>
          {data.nominal_landing_speed_ms != null && (
            <p className="mt-2 text-xs text-muted-foreground">
              With everything working it lands at {formatSI(data.nominal_landing_speed_ms, 'speed', units, 1)}.
            </p>
          )}
        </div>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/flight">
          Each row is the mission flown again without that device: if the drogue fails the rocket falls from apogee until
          the main opens, much faster than planned; if the main fails it lands under the drogue; with nothing open it comes
          in ballistic, nose first as a stable rocket does. Energy is the whole rocket as one body. These are ordinary
          flights, so they are cached and appear in Compare.
        </Explainer>
      </div>
    </section>
  )
}

function Row({ o }: { o: FailureOutcome }) {
  const units = usePrefs((s) => s.display)
  const pending = o.run.status === 'queued' || o.run.status === 'running'
  const speed = o.landing_speed_ms
  return (
    <tr className="border-t border-border align-top">
      <td className="py-2 pr-4 font-medium">{o.label}</td>
      <td className="py-2 pr-4">{o.devices.length ? o.devices.join(', ') : 'Nothing'}</td>
      {o.run.status === 'failed' ? (
        <td colSpan={4} className="py-2 text-nogo">
          The flight failed: {o.run.error}
        </td>
      ) : pending ? (
        <td colSpan={4} className="py-2 text-muted-foreground">
          Flying
        </td>
      ) : (
        <>
          <td className="py-2 pr-4">{o.opening_speed_ms == null ? '—' : formatSI(o.opening_speed_ms, 'speed', units)}</td>
          <td className={cn('py-2 pr-4 font-medium', speed != null && speed > SAFE_LANDING_MS && 'text-nogo')}>
            {speed == null ? '—' : formatSI(speed, 'speed', units, 1)}
          </td>
          <td className="py-2 pr-4">{o.landing_energy_j == null ? '—' : formatSI(o.landing_energy_j, 'energy', units)}</td>
          <td className="py-2">
            {o.drift_m == null ? '—' : `${formatSI(o.drift_m, 'distance', units)} from the pad`}
            {o.outside_boundary === true && <span className="block text-nogo">Outside the range boundary</span>}
            {o.outside_boundary === false && <span className="block text-muted-foreground">Inside the boundary</span>}
          </td>
        </>
      )}
    </tr>
  )
}
