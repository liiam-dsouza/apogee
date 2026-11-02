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
 */
export const overlayColors = {
  dark: { primary: '#a9b8ff', nogo: '#ef5b5b', caution: '#e8b13a', foreground: '#e6ecf2' },
  light: { primary: '#2438b8', nogo: '#b3121b', caution: '#8a5a00', foreground: '#000000' },
} as const

const blank: MapLibreGL.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': 'rgba(0, 0, 0, 0)' } }],
}

// Literal hex values: MapLibre paints on canvas and cannot read CSS variables.
// Keep in step with the tokens in index.css.
const DARK_FLAVOR: Flavor = {
  ...namedFlavor('dark'),
  background: '#0f1720',
  earth: '#17212c',
  water: '#0b1118',
}

const LIGHT_FLAVOR: Flavor = {
  ...namedFlavor('light'),
  background: '#ffffff',
  earth: '#f1f3f6',
  water: '#c4d3e6',
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
