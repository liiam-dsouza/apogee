import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UnitSystem } from '@/lib/units'

export type Theme = 'dark' | 'light'

/** Right-pane width and collapsed state are persisted per section by the panel group (see SectionView). */
interface PrefsState {
  theme: Theme
  units: UnitSystem
  setTheme: (theme: Theme) => void
  setUnits: (units: UnitSystem) => void
}

export const usePrefs = create<PrefsState>()(
  persist(
    (set) => ({
      theme: 'dark',
      units: 'metric',
      setTheme: (theme) => set({ theme }),
      setUnits: (units) => set({ units }),
    }),
    { name: 'apogee.prefs' },
  ),
)
