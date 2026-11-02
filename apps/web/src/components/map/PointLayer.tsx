import type { FeatureCollection, Point } from 'geojson'
import type * as MapLibreGL from 'maplibre-gl'
import { useEffect, useState } from 'react'
import { useMap } from '@/components/ui/map'

/**
 * Many points as one MapLibre circle layer: a thousand landing points as DOM
 * markers would crawl. Re-adds itself after a style swap (theme, satellite),
 * like MapGeoJSON. Hover reports the feature's properties.
 */
export function PointLayer<P extends Record<string, unknown>>({
  id,
  data,
  paint,
  onHover,
}: {
  id: string
  data: FeatureCollection<Point, P>
  paint: MapLibreGL.CircleLayerSpecification['paint']
  onHover?: (hit: { properties: P; x: number; y: number } | null) => void
}) {
  const { map, isLoaded } = useMap()
  const [hoverHandler] = useState(() => ({ current: onHover }))
  hoverHandler.current = onHover

  useEffect(() => {
    if (!isLoaded || !map) return
    map.addSource(id, { type: 'geojson', data })
    map.addLayer({ id, type: 'circle', source: id, paint })
    const move = (e: MapLibreGL.MapLayerMouseEvent) => {
      const f = e.features?.[0]
      if (!f) return
      map.getCanvas().style.cursor = 'pointer'
      hoverHandler.current?.({ properties: f.properties as P, x: e.point.x, y: e.point.y })
    }
    const leave = () => {
      map.getCanvas().style.cursor = ''
      hoverHandler.current?.(null)
    }
    map.on('mousemove', id, move)
    map.on('mouseleave', id, leave)
    return () => {
      map.off('mousemove', id, move)
      map.off('mouseleave', id, leave)
      try {
        if (map.getLayer(id)) map.removeLayer(id)
        if (map.getSource(id)) map.removeSource(id)
      } catch {
        // style may be mid-reload
      }
    }
    // Data and paint are synced below; re-adding on every change would flicker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, map, id])

  useEffect(() => {
    if (!isLoaded || !map) return
    ;(map.getSource(id) as MapLibreGL.GeoJSONSource | undefined)?.setData(data)
  }, [isLoaded, map, id, data])

  useEffect(() => {
    if (!isLoaded || !map || !map.getLayer(id) || !paint) return
    for (const [key, value] of Object.entries(paint)) map.setPaintProperty(id, key as 'circle-color', value as never)
  }, [isLoaded, map, id, paint])

  return null
}
