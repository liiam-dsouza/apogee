import { Explainer } from '@/components/Explainer'
import { MapScale, SiteLayers } from '@/components/map/SiteLayers'
import { PaneStub } from '@/components/SectionStub'
import { Map, MapControls } from '@/components/ui/map'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

export function Centre() {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  const site = useMissionStore((s) => s.draft?.site ?? null)
  const units = usePrefs((s) => s.units)

  const prompt = !missionId
    ? 'Open a mission with a launch site to see its range here.'
    : !site
      ? 'This mission has no launch site yet. Add one in the Site section.'
      : 'Run a campaign to plot where the rocket could land.'

  return (
    <div className="relative h-full">
      {/* Full-bleed map; landing points and ellipses will layer on top of the site. */}
      <Map
        key={missionId ?? 'none'}
        className="absolute inset-0 bg-background"
        center={site ? [site.longitude_deg, site.latitude_deg] : [0, 20]}
        zoom={site ? 12 : 1.5}
      >
        <MapControls position="bottom-right" showCompass />
        <MapScale unit={units} />
        {site && <SiteLayers site={site} />}
      </Map>
      <div className="pointer-events-none absolute inset-x-0 top-0 flex p-4">
        <div className="pointer-events-auto w-full max-w-md space-y-3 rounded-md border border-border bg-surface/95 p-4 shadow-lg backdrop-blur">
          <p className="text-sm text-foreground">{prompt}</p>
          <Explainer methodsHref="/docs/methods/monte-carlo">
            Runs the flight hundreds of times with each uncertain input drawn from its distribution (Latin hypercube
            sampling). Wind is perturbed coherently with altitude, so the ellipse is not artificially small. The
            ellipses are fitted from the covariance of the landing points.
          </Explainer>
        </div>
      </div>
    </div>
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Monte Carlo"
      fields={['Sample count', 'Seed', 'Wind perturbation', 'Parameter distributions', 'Run campaign', 'Progress']}
    />
  )
}
