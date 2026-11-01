import { useEffect, useMemo } from 'react'
import { MapGeoJSON, MapMarker, MarkerContent, useMap } from '@/components/ui/map'
import type { Site } from '@/lib/api'
import { overlayColors } from '@/lib/mapStyles'
import { collection, destination, line, polygon, type LonLat } from './geo'

/** Length of the rail-heading indicator drawn from the pad. */
const HEADING_LINE_M = 300

/**
 * The launch site on a map: range boundary, hazard zones, access roads, the
 * pad and the rail heading. Shared by every section that shows the range.
 */
export function SiteLayers({
  site,
  onPadMove,
}: {
  site: Site
  /** Makes the pad draggable. Receives the new position in degrees. */
  onPadMove?: (lonLat: LonLat) => void
}) {
  const { resolvedTheme } = useMap()
  const c = overlayColors[resolvedTheme]
  const pad: LonLat = [site.longitude_deg, site.latitude_deg]

  const paints = useMemo(
    () => ({
      boundaryFill: { 'fill-color': c.primary, 'fill-opacity': 0.06 },
      boundaryLine: { 'line-color': c.primary, 'line-width': 2 },
      hazardFill: { 'fill-color': c.nogo, 'fill-opacity': 0.25 },
      hazardLine: { 'line-color': c.nogo, 'line-width': 1.5 },
      roadLine: { 'line-color': c.foreground, 'line-width': 2, 'line-dasharray': [2, 1.5] },
      headingLine: { 'line-color': c.primary, 'line-width': 2 },
    }),
    [c],
  )

  const boundary = useMemo(
    () => collection(site.boundary ? [polygon(site.boundary as LonLat[])] : []),
    [site.boundary],
  )
  const hazards = useMemo(
    () => collection((site.hazards ?? []).map((h) => polygon(h as LonLat[]))),
    [site.hazards],
  )
  const roads = useMemo(() => collection((site.access_roads ?? []).map((r) => line(r as LonLat[]))), [site.access_roads])
  const heading = useMemo(
    () => collection([line([pad, destination(pad, site.heading_deg, HEADING_LINE_M)])]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [site.longitude_deg, site.latitude_deg, site.heading_deg],
  )

  return (
    <>
      <MapGeoJSON id="site-boundary" data={boundary} fillPaint={paints.boundaryFill} linePaint={paints.boundaryLine} />
      <MapGeoJSON id="site-hazards" data={hazards} fillPaint={paints.hazardFill} linePaint={paints.hazardLine} />
      <MapGeoJSON id="site-roads" data={roads} fillPaint={false} linePaint={paints.roadLine} />
      <MapGeoJSON id="site-heading" data={heading} fillPaint={false} linePaint={paints.headingLine} />
      <MapMarker
        longitude={pad[0]}
        latitude={pad[1]}
        draggable={Boolean(onPadMove)}
        onDragEnd={({ lng, lat }) => onPadMove?.([lng, lat])}
      >
        <MarkerContent>
          <span
            aria-label="Launch pad"
            className="block size-4 rotate-45 border-2 border-background bg-primary shadow"
          />
        </MarkerContent>
      </MapMarker>
    </>
  )
}

/** A metric/imperial scale bar, so distances read correctly even on a blank basemap. */
export function MapScale({ unit }: { unit: 'metric' | 'imperial' }) {
  const { map, mapLib } = useMap()
  useEffect(() => {
    if (!map || !mapLib) return
    const control = new mapLib.ScaleControl({ unit, maxWidth: 120 })
    map.addControl(control, 'bottom-left')
    return () => {
      // When the whole map unmounts, Map.remove() has already removed every
      // control; removing it again throws inside MapLibre.
      if (map.hasControl(control)) map.removeControl(control)
    }
  }, [map, mapLib, unit])
  return null
}
