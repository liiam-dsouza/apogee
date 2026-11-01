import { layers, namedFlavor, type Flavor } from '@protomaps/basemaps'
import type * as MapLibreGL from 'maplibre-gl'
import { Protocol } from 'pmtiles'

/**
 * Basemap styles for every map in the app. Nothing here touches the network
 * beyond the stack itself, so maps work on a field laptop with no internet.
 *
 * - With `VITE_MAP_PMTILES` set (a URL the stack serves, e.g.
 *   `/tiles/basemap.pmtiles`), draws a vector basemap from that file, coloured
 *   to match the app theme.
 * - Without it, a blank style: the themed container shows through and only
 *   the app's own layers (site, boundary, landing points) are drawn.
 *
 * Label layers are omitted for now because they need a glyph server; add them
 * once glyphs are self-hosted alongside the tiles.
 */

const PMTILES_URL = import.meta.env.VITE_MAP_PMTILES

/** Whether a real basemap is configured (otherwise maps draw only app layers). */
export const hasBasemap = Boolean(PMTILES_URL)

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

function basemap(url: string, flavor: Flavor): MapLibreGL.StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'vector',
        url: `pmtiles://${url}`,
        attribution: '© OpenStreetMap contributors',
      },
    },
    layers: layers('basemap', flavor).filter(
      (l) => l.type !== 'symbol',
    ) as MapLibreGL.LayerSpecification[],
  }
}

export const mapStyles: { dark: MapLibreGL.StyleSpecification; light: MapLibreGL.StyleSpecification } =
  PMTILES_URL
    ? { dark: basemap(PMTILES_URL, DARK_FLAVOR), light: basemap(PMTILES_URL, LIGHT_FLAVOR) }
    : { dark: blank, light: blank }

let protocolsRegistered = false

/** Lets MapLibre read `pmtiles://` sources directly from a single file. */
export function registerMapProtocols(lib: typeof MapLibreGL) {
  if (protocolsRegistered) return
  lib.addProtocol('pmtiles', new Protocol().tile)
  protocolsRegistered = true
}
