import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UnitSystem } from '@/lib/units'

export type Theme = 'dark' | 'light'

/** Right-pane width and collapsed state are persisted per section by the panel group (see SectionView). */
interface PrefsState {
  theme: Theme
  units: UnitSystem
  /** Site map shows satellite imagery instead of the basemap. */
  satellite: boolean
  setTheme: (theme: Theme) => void
  setUnits: (units: UnitSystem) => void
  setSatellite: (satellite: boolean) => void
}

export const usePrefs = create<PrefsState>()(
  persist(
    (set) => ({
      theme: 'dark',
      units: 'metric',
      satellite: false,
      setTheme: (theme) => set({ theme }),
      setUnits: (units) => set({ units }),
      setSatellite: (satellite) => set({ satellite }),
    }),
    { name: 'apogee.prefs' },
  ),
)
