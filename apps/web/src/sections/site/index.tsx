import { Check, MapPin, Plus, Satellite, Trash2, Undo2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Explainer } from '@/components/Explainer'
import { collection, line, polygon, type LonLat } from '@/components/map/geo'
import { MapScale, SiteLayers } from '@/components/map/SiteLayers'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { Map, MapControls, MapGeoJSON, MapMarker, MarkerContent, useMap } from '@/components/ui/map'
import type { Issue, Site } from '@/lib/api'
import { basemapSource, overlayColors, satelliteAvailable, satelliteStyle } from '@/lib/mapStyles'
import { useIssuesAt } from '@/lib/mission/validation'
import { useMissionStore } from '@/stores/mission'
import { systemOf } from '@/lib/units'
import { usePrefs } from '@/stores/prefs'
import { DRAW_LABEL, MIN_POINTS, useDrawing } from './drawing'

/**
 * Starting values for a new site's rail. Placeholders the team must check
 * against their own rail; position comes from the user.
 */
const NEW_RAIL = { elevation_m: 0, rail_length_m: 6, inclination_deg: 85, heading_deg: 0 }

const SATELLITE_STYLES = { dark: satelliteStyle, light: satelliteStyle }

function useSite() {
  return useMissionStore((s) => s.draft?.site ?? null)
}

function useEditSite() {
  const edit = useMissionStore((s) => s.edit)
  return (recipe: (site: Site) => void) =>
    edit((d) => {
      if (d.site) recipe(d.site)
    })
}

function createSite([lon, lat]: LonLat) {
  useMissionStore.getState().edit((d) => {
    d.site = { latitude_deg: lat, longitude_deg: lon, ...NEW_RAIL, boundary: null, hazards: [], access_roads: [] }
  })
}

/** Commits the in-progress drawing into the mission, if it has enough points. */
function useFinishDrawing() {
  const editSite = useEditSite()
  return () => {
    const { target, points, cancel } = useDrawing.getState()
    if (!target || points.length < MIN_POINTS[target.kind]) return
    editSite((site) => {
      if (target.kind === 'boundary') site.boundary = points
      else if (target.kind === 'hazard') site.hazards = [...(site.hazards ?? []), points]
      else site.access_roads = [...(site.access_roads ?? []), points]
    })
    cancel()
  }
}

export function Centre() {
  return (
    <RequireMission>
      <SiteMap />
    </RequireMission>
  )
}

function SiteMap() {
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  const site = useSite()
  const units = usePrefs((s) => s.display)
  const editSite = useEditSite()
  const drawing = useDrawing((s) => s.target !== null)
  const satellite = usePrefs((s) => s.satellite) && satelliteAvailable
  const setSatellite = usePrefs((s) => s.setSatellite)
  // Leaving the section abandons a half-drawn shape.
  useEffect(() => () => useDrawing.getState().cancel(), [])

  return (
    <div className="relative h-full">
      <Map
        // Re-centre when a different mission is opened.
        key={missionId}
        className="absolute inset-0 bg-background"
        center={site ? [site.longitude_deg, site.latitude_deg] : [0, 20]}
        zoom={site ? 13 : 1.5}
        styles={satellite ? SATELLITE_STYLES : undefined}
        // Imagery is dark whatever the app theme, so overlays use their dark-theme colours.
        theme={satellite ? 'dark' : undefined}
      >
        <MapControls position="bottom-right" showCompass />
        <MapScale unit={systemOf(units)} />
        {site && (
          <SiteLayers
            site={site}
            onPadMove={([lon, lat]) =>
              editSite((s) => {
                s.longitude_deg = lon
                s.latitude_deg = lat
              })
            }
          />
        )}
        <MapClicks />
        <FlyToNewPad />
        <DrawingPreview />
      </Map>
      <DrawingToolbar />
      {satelliteAvailable && (
        <button
          type="button"
          aria-pressed={satellite}
          onClick={() => setSatellite(!satellite)}
          className={`absolute top-4 right-4 flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-sm shadow-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${satellite ? 'bg-brand text-primary-foreground' : 'bg-background hover:bg-accent'}`}
        >
          <Satellite className="size-4" /> Satellite
        </button>
      )}
      {basemapSource === 'none' && !drawing && (
        <p className="pointer-events-none absolute right-4 bottom-4 left-4 mx-auto max-w-md rounded-md bg-surface/90 px-3 py-2 text-center text-xs text-muted-foreground md:right-auto md:left-4 md:mx-0">
          No basemap: you're offline and no map tiles are downloaded, so the map shows only your site. Use the scale
          bar to draw the range around the pad.
        </p>
      )}
    </div>
  )
}

/** Map clicks add drawing points, or place the pad when the mission has no site yet. */
function MapClicks() {
  const { map } = useMap()
  const hasSite = useMissionStore((s) => Boolean(s.draft?.site))
  const drawing = useDrawing((s) => s.target !== null)

  useEffect(() => {
    if (!map) return
    // Reads current state at click time, so it subscribes once per map.
    const onClick = (e: { lngLat: { lng: number; lat: number } }) => {
      const p: LonLat = [e.lngLat.lng, e.lngLat.lat]
      if (useDrawing.getState().target) useDrawing.getState().add(p)
      else if (!useMissionStore.getState().draft?.site) createSite(p)
    }
    map.on('click', onClick)
    return () => {
      map.off('click', onClick)
    }
  }, [map])

  useEffect(() => {
    if (!map) return
    map.getCanvas().style.cursor = drawing || !hasSite ? 'crosshair' : ''
  }, [map, drawing, hasSite])
  return null
}

/** When the pad is first placed (from the pane or a click), bring it into view. */
function FlyToNewPad() {
  const { map } = useMap()
  const site = useSite()
  const hadSite = useRef(site !== null)
  useEffect(() => {
    if (!map || !site || hadSite.current) return
    hadSite.current = true
    map.flyTo({ center: [site.longitude_deg, site.latitude_deg], zoom: 13 })
  }, [map, site])
  return null
}

function DrawingPreview() {
  const { resolvedTheme } = useMap()
  const target = useDrawing((s) => s.target)
  const points = useDrawing((s) => s.points)
  const c = overlayColors[resolvedTheme]
  const color = target?.kind === 'hazard' ? c.hazard : target?.kind === 'road' ? c.foreground : c.primary
  const paint = useMemo(
    () => ({
      fill: { 'fill-color': color, 'fill-opacity': 0.15 },
      line: { 'line-color': color, 'line-width': 2, 'line-dasharray': [1, 1] },
    }),
    [color],
  )
  const data = useMemo(() => {
    if (points.length < 2) return collection([])
    return target?.kind !== 'road' && points.length >= 3 ? collection([polygon(points)]) : collection([line(points)])
  }, [points, target])

  if (!target) return null
  return (
    <>
      <MapGeoJSON id="site-drawing" data={data} fillPaint={target.kind === 'road' ? false : paint.fill} linePaint={paint.line} />
      {points.map(([lon, lat], i) => (
        <MapMarker key={i} longitude={lon} latitude={lat}>
          <MarkerContent>
            <span className="block size-2.5 rounded-full border-2 border-background" style={{ background: color }} />
          </MarkerContent>
        </MapMarker>
      ))}
    </>
  )
}

function DrawingToolbar() {
  const target = useDrawing((s) => s.target)
  const count = useDrawing((s) => s.points.length)
  const removeLast = useDrawing((s) => s.removeLast)
  const cancel = useDrawing((s) => s.cancel)
  const finish = useFinishDrawing()

  useEffect(() => {
    if (!target) return
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'Enter') finish()
      else if (e.key === 'Escape') cancel()
      else if (e.key === 'Backspace') removeLast()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [target, finish, cancel, removeLast])

  if (!target) return null
  const min = MIN_POINTS[target.kind]
  return (
    <div className="absolute top-4 left-4 flex max-w-[calc(100%-2rem)] flex-wrap items-center gap-2 rounded-md border border-border bg-surface/95 p-2 shadow-lg backdrop-blur">
      <p className="px-1 text-sm" aria-live="polite">
        Drawing the {DRAW_LABEL[target.kind]}: {count === 0 ? 'click the map to add points.' : `${count} of at least ${min} points.`}
      </p>
      <Button size="sm" variant="ghost" onClick={removeLast} disabled={count === 0}>
        <Undo2 /> Remove last point
      </Button>
      <Button size="sm" variant="primary" onClick={finish} disabled={count < min}>
        <Check /> Finish
      </Button>
      <Button size="sm" variant="ghost" onClick={cancel}>
        <X /> Cancel
      </Button>
    </div>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <SitePane />
    </RequireMission>
  )
}

function SitePane() {
  const site = useSite()
  const editSite = useEditSite()
  if (!site) return <NewSite />

  const field = (
    name: keyof typeof NEW_RAIL | 'latitude_deg' | 'longitude_deg',
    label: string,
    quantity: 'angle' | 'altitude' | 'distance',
    decimals: number,
  ) => (
    <QuantityField
      schema="Site"
      name={name}
      path={`site.${name}`}
      label={label}
      quantity={quantity}
      decimals={decimals}
      value={site[name]}
      onChange={(v) =>
        editSite((s) => {
          s[name] = v
        })
      }
    />
  )

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Launch pad</h2>
        <div className="grid grid-cols-2 gap-3">
          {field('latitude_deg', 'Latitude', 'angle', 6)}
          {field('longitude_deg', 'Longitude', 'angle', 6)}
        </div>
        {field('elevation_m', 'Elevation', 'altitude', 1)}
      </section>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Rail</h2>
        {field('rail_length_m', 'Rail length', 'distance', 2)}
        <div className="grid grid-cols-2 gap-3">
          {field('inclination_deg', 'Inclination', 'angle', 1)}
          {field('heading_deg', 'Heading', 'angle', 1)}
        </div>
      </section>
      <RangeGeometry site={site} />
      <Explainer methodsHref="/docs/methods/site">
        The boundary polygon is what the dispersion analysis tests landing points against. Hazard zones are places the
        rocket must not land; a pad inside one is an error. Rail length, inclination and heading set the initial
        conditions of every flight.
      </Explainer>
    </div>
  )
}

function NewSite() {
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const latN = Number(lat)
  const lonN = Number(lon)
  const valid =
    lat.trim() !== '' && lon.trim() !== '' && Math.abs(latN) <= 90 && Math.abs(lonN) <= 180 && Number.isFinite(latN + lonN)

  return (
    <form
      className="space-y-4 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) createSite([lonN, latN])
      }}
    >
      <p className="text-sm">
        Enter the pad's coordinates{basemapSource !== 'none' ? ', or click the map where the pad is' : ''}. You can drag the pad on the
        map afterwards.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1 text-sm">
          <span>Latitude (°)</span>
          <input value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" placeholder="-31.0500"
            className="h-9 w-full rounded-md border border-border bg-background px-3 tabular-nums" />
        </label>
        <label className="space-y-1 text-sm">
          <span>Longitude (°)</span>
          <input value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" placeholder="136.5300"
            className="h-9 w-full rounded-md border border-border bg-background px-3 tabular-nums" />
        </label>
      </div>
      <Button type="submit" variant="primary" disabled={!valid}>
        <MapPin /> Add launch site
      </Button>
      <p className="text-xs text-muted-foreground">
        The rail starts at {NEW_RAIL.rail_length_m} m, {NEW_RAIL.inclination_deg}° inclination, heading north. Check these
        against your rail.
      </p>
    </form>
  )
}

function RangeGeometry({ site }: { site: Site }) {
  const editSite = useEditSite()
  const start = useDrawing((s) => s.start)
  const drawing = useDrawing((s) => s.target !== null)
  const boundaryIssues = useIssuesAt('site.boundary')
  const hazardIssues = useIssuesAt('site.hazards', { nested: true })
  const hazards = site.hazards ?? []
  const roads = site.access_roads ?? []

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Range</h2>

      <Row
        label="Boundary"
        detail={site.boundary ? `${site.boundary.length} points` : 'Not drawn'}
        issues={boundaryIssues}
      >
        <Button size="sm" disabled={drawing} onClick={() => start({ kind: 'boundary' })}>
          {site.boundary ? 'Redraw' : 'Draw'}
        </Button>
        {site.boundary && (
          <Button size="sm" variant="ghost" aria-label="Remove boundary" onClick={() => editSite((s) => { s.boundary = null })}>
            <Trash2 />
          </Button>
        )}
      </Row>

      {hazards.map((h, i) => (
        <Row
          key={i}
          label={`Hazard ${i + 1}`}
          detail={`${h.length} points`}
          issues={hazardIssues.filter((x) => x.path === `site.hazards[${i}]`)}
        >
          <Button size="sm" variant="ghost" aria-label={`Remove hazard ${i + 1}`}
            onClick={() => editSite((s) => { s.hazards = (s.hazards ?? []).filter((_, j) => j !== i) })}>
            <Trash2 />
          </Button>
        </Row>
      ))}

      {roads.map((r, i) => (
        <Row key={i} label={`Access road ${i + 1}`} detail={`${r.length} points`}>
          <Button size="sm" variant="ghost" aria-label={`Remove access road ${i + 1}`}
            onClick={() => editSite((s) => { s.access_roads = (s.access_roads ?? []).filter((_, j) => j !== i) })}>
            <Trash2 />
          </Button>
        </Row>
      ))}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={drawing} onClick={() => start({ kind: 'hazard' })}>
          <Plus /> Hazard zone
        </Button>
        <Button size="sm" disabled={drawing} onClick={() => start({ kind: 'road' })}>
          <Plus /> Access road
        </Button>
      </div>
    </section>
  )
}

function Row({
  label,
  detail,
  issues = [],
  children,
}: {
  label: string
  detail: string
  issues?: Issue[]
  children: ReactNode
}) {
  return (
    <div className="rounded-md border border-border px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-sm">{label}</span>
        <span className="text-sm text-muted-foreground">{detail}</span>
        <span className="ml-auto flex items-center gap-1">{children}</span>
      </div>
      {issues.map((i) => (
        <p key={i.code} className={`mt-1 text-xs ${i.severity === 'error' ? 'text-nogo' : 'text-caution'}`}>
          {i.message}
        </p>
      ))}
    </div>
  )
}
