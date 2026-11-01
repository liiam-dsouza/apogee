/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FIELD_MODE?: string
  /** URL of the basemap PMTiles file served by the stack; blank basemap if unset. */
  readonly VITE_MAP_PMTILES?: string
}
