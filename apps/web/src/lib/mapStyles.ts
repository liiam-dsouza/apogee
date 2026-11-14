import { layers, namedFlavor, type Flavor } from '@protomaps/basemaps'
import type * as MapLibreGL from 'maplibre-gl'
import { Protocol } from 'pmtiles'

/**
 * Basemap styles for every map in the app, chosen once at load:
 *
 * - `local`: `VITE_MAP_PMTILES` is set (a file the stack serves, e.g.
 *   `/tiles/basemap.pmtiles`). Works with no internet; this is the field setup.
 *   Coloured to match the app theme; no labels yet (they need a glyph server).
 * - `online`: no local tiles, but the browser is online. OpenFreeMap's styles
 *   (OpenStreetMap data, free, no key). Basemap tiles are not part of the
 *   simulation path, so fetching them is allowed; simulations never wait on them.
 * - `none`: no local tiles and offline. A blank style; only the app's own
 *   layers (site, boundary, landing points) draw.
 *
 * Satellite imagery (`satelliteStyle`) is an opt-in alternative for the site
 * map whenever the browser is online, whatever the basemap source.
 */

const PMTILES_URL = import.meta.env.VITE_MAP_PMTILES

const ONLINE_STYLES = {
  dark: 'https://tiles.openfreemap.org/styles/dark',
  light: 'https://tiles.openfreemap.org/styles/positron',
} as const

export type BasemapSource = 'local' | 'online' | 'none'

function chooseSource(): BasemapSource {
  if (PMTILES_URL) return 'local'
  if (typeof navigator !== 'undefined' && navigator.onLine) return 'online'
  return 'none'
}

export const basemapSource: BasemapSource = chooseSource()

/**
 * Overlay colours for app layers (site, boundary, landing points). Literal
 * hex because MapLibre paints on canvas; mirrors the tokens in index.css.
 * `primary` is the accent; hazard zones are gold (`hazard`) so they never read
 * as the accent.
 */
export const overlayColors = {
  dark: { primary: '#ff3b1a', hazard: '#f5c542', caution: '#e8b13a', foreground: '#ededed', background: '#0d0d0d' },
  light: { primary: '#e8002b', hazard: '#a07800', caution: '#8a5a00', foreground: '#0d0d0d', background: '#f5f5f5' },
  pink: { primary: '#c4006a', hazard: '#a07800', caution: '#8a5a00', foreground: '#3d0020', background: '#ffd1e8' },
} as const

/** HSL lightness (0 to 1) and alpha of a CSS colour, or null if `value` isn't one MapLibre styles use. */
function lightnessAndAlpha(value: string): [number, number] | null {
  const s = value.trim().toLowerCase()
  const hex = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/.exec(s)?.[1]
  if (hex) {
    const full = hex.length <= 4 ? [...hex].map((c) => c + c).join('') : hex
    const [r, g, b, a = 255] = (full.match(/../g) ?? []).map((h) => parseInt(h, 16))
    return [(Math.max(r, g, b) + Math.min(r, g, b)) / 510, a / 255]
  }
  const fn = /^(rgba?|hsla?)\(([^)]*)\)$/.exec(s)
  if (!fn) return null
  const parts = fn[2].split(/[\s,/]+/).filter(Boolean).map((p) => parseFloat(p))
  if (parts.length < 3 || parts.some(Number.isNaN)) return null
  const alpha = parts[3] ?? 1
  if (fn[1].startsWith('hsl')) return [parts[2] / 100, alpha]
  return [(Math.max(...parts.slice(0, 3)) + Math.min(...parts.slice(0, 3))) / 510, alpha]
}

/** Every colour in a style value moved to pink, keeping its lightness (capped at the pink page's). */
function pinkify(value: unknown): unknown {
  if (typeof value === 'string') {
    const la = lightnessAndAlpha(value)
    if (!la) return value
    const [l, a] = la
    return `hsla(330, 100%, ${(Math.min(l, 0.91) * 100).toFixed(1)}%, ${a})`
  }
  if (Array.isArray(value)) return value.map(pinkify)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, pinkify(v)]))
  }
  return value
}

/**
 * The pink theme's basemap: whatever the light basemap is (local, online or
 * blank), recoloured as it loads. Pass on every style load, since MapLibre
 * otherwise keeps the last transform.
 */
export function basemapTransform(pink: boolean): MapLibreGL.TransformStyleFunction {
  if (!pink) return (_previous, next) => next
  return (_previous, next) => ({
    ...next,
    layers: next.layers.map((l) => ('paint' in l && l.paint ? { ...l, paint: pinkify(l.paint) } : l)),
  }) as MapLibreGL.StyleSpecification
}

const blank: MapLibreGL.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': 'rgba(0, 0, 0, 0)' } }],
}

// Literal hex values: MapLibre paints on canvas and cannot read CSS variables.
// Keep in step with the tokens in index.css.
const DARK_FLAVOR: Flavor = {
  ...namedFlavor('dark'),
  background: '#0d0d0d',
  earth: '#181818',
  water: '#0a0c0f',
}

const LIGHT_FLAVOR: Flavor = {
  ...namedFlavor('light'),
  background: '#f5f5f5',
  earth: '#e6e6e6',
  water: '#c9d3dc',
}

function pmtilesStyle(url: string, flavor: Flavor): MapLibreGL.StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'vector',
        url: `pmtiles://${url}`,
        attribution: '© OpenStreetMap contributors',
      },
    },
    layers: layers('basemap', flavor).filter((l) => l.type !== 'symbol') as MapLibreGL.LayerSpecification[],
  }
}

type StyleOption = MapLibreGL.StyleSpecification | string

function chooseStyles(): { dark: StyleOption; light: StyleOption } {
  if (basemapSource === 'local' && PMTILES_URL) {
    return { dark: pmtilesStyle(PMTILES_URL, DARK_FLAVOR), light: pmtilesStyle(PMTILES_URL, LIGHT_FLAVOR) }
  }
  if (basemapSource === 'online') return ONLINE_STYLES
  return { dark: blank, light: blank }
}

export const mapStyles = chooseStyles()

/** Whether satellite imagery can be fetched (it is never stored locally). */
export const satelliteAvailable = typeof navigator !== 'undefined' && navigator.onLine

/** Esri World Imagery raster tiles (free with attribution, no key). Same style for both themes. */
export const satelliteStyle: MapLibreGL.StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Powered by Esri · Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    },
  },
  layers: [{ id: 'satellite', type: 'raster', source: 'satellite' }],
}

let protocolsRegistered = false

/** Lets MapLibre read `pmtiles://` sources directly from a single file. */
export function registerMapProtocols(lib: typeof MapLibreGL) {
  if (protocolsRegistered) return
  lib.addProtocol('pmtiles', new Protocol().tile)
  protocolsRegistered = true
}
