import type * as GeoJSON from 'geojson'

export type LonLat = [number, number]

const EARTH_RADIUS_M = 6_371_000

/** Point `distanceM` along `bearingDeg` (clockwise from north). Spherical; fine at range scale. */
export function destination([lon, lat]: LonLat, bearingDeg: number, distanceM: number): LonLat {
  const toRad = Math.PI / 180
  const d = distanceM / EARTH_RADIUS_M
  const b = bearingDeg * toRad
  const lat1 = lat * toRad
  const lon1 = lon * toRad
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(b))
  const lon2 =
    lon1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2))
  return [lon2 / toRad, lat2 / toRad]
}

/** A closed GeoJSON polygon from an open ring (the config stores rings open). */
export function polygon(ring: LonLat[]): GeoJSON.Feature<GeoJSON.Polygon> {
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } }
}

export function collection<G extends GeoJSON.Geometry>(
  features: GeoJSON.Feature<G>[],
): GeoJSON.FeatureCollection<G> {
  return { type: 'FeatureCollection', features }
}

export function line(points: LonLat[]): GeoJSON.Feature<GeoJSON.LineString> {
  return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: points } }
}
