import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Quantity, UnitPrefs, UnitSystem } from '@/lib/units'

/** 'pink' is the status-bar easter egg: light underneath, pink tokens on top (see index.css). */
export type Theme = 'dark' | 'light' | 'pink'

/** Right-pane width and collapsed state are persisted per section by the panel group (see SectionView). */
interface PrefsState {
  theme: Theme
  /** The base system; `display` adds any per-quantity choices to it. */
  units: UnitSystem
  /** What every number is shown in. Pass this to the lib/units functions. */
  display: UnitPrefs
  /** Site map shows satellite imagery instead of the basemap. */
  satellite: boolean
  /** The rail shows section names beside the icons. */
  railExpanded: boolean
  setTheme: (theme: Theme) => void
  /** Switch to a system's defaults, clearing per-quantity choices. */
  setUnits: (units: UnitSystem) => void
  /** Show one quantity in a chosen unit (by symbol), or back to the system's with null. */
  setUnitChoice: (quantity: Quantity, symbol: string | null) => void
  setSatellite: (satellite: boolean) => void
  setRailExpanded: (railExpanded: boolean) => void
}

export const usePrefs = create<PrefsState>()(
  persist(
    (set) => ({
      theme: 'dark',
      units: 'metric',
      display: { system: 'metric', choice: {} },
      satellite: false,
      railExpanded: false,
      setTheme: (theme) => set({ theme }),
      setUnits: (units) => set({ units, display: { system: units, choice: {} } }),
      setUnitChoice: (quantity, symbol) =>
        set((s) => {
          const choice = { ...s.display.choice }
          if (symbol === null) delete choice[quantity]
          else choice[quantity] = symbol
          return { display: { system: s.units, choice } }
        }),
      setSatellite: (satellite) => set({ satellite }),
      setRailExpanded: (railExpanded) => set({ railExpanded }),
    }),
    {
      name: 'apogee.prefs',
      // Pink's song can't autoplay after a reload, so pink isn't kept: it comes back as light.
      partialize: ({ theme, ...rest }) => ({ ...rest, theme: theme === 'pink' ? 'light' : theme }),
      // Prefs saved before per-quantity units had no `display`: rebuild it from the system.
      merge: (saved, current) => {
        const s = { ...current, ...(saved as Partial<PrefsState>) }
        return s.display ? s : { ...s, display: { system: s.units, choice: {} } }
      },
    },
  ),
)
