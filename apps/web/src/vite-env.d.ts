/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FIELD_MODE?: string
  /** URL of the basemap PMTiles file served by the stack; blank basemap if unset. */
  readonly VITE_MAP_PMTILES?: string
}

/** File Handling API (Chromium, installed app only): .apg files opened from the OS. */
interface LaunchParams {
  readonly files: readonly FileSystemFileHandle[]
}

interface Window {
  readonly launchQueue?: { setConsumer(consumer: (params: LaunchParams) => void): void }
}
