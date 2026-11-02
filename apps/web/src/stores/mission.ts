import { create, useStore } from 'zustand'
import { immer } from 'zustand/middleware/immer'
import { temporal, type TemporalState } from 'zundo'
import type { Mission } from '@/lib/api'

/**
 * The mission config draft: the single source of truth for every editor.
 * Undo/redo (zundo) tracks the draft only, not the dirty flag.
 */
interface MissionState {
  draft: Mission | null
  isDirty: boolean
  /** When unsaved changes restored after a reload were last written (ISO), until saved or discarded. */
  restoredFrom: string | null
  load: (mission: Mission) => void
  /** Reopen unsaved changes kept from before a reload. */
  restore: (draft: Mission, savedAt: string) => void
  edit: (recipe: (draft: Mission) => void) => void
  markSaved: () => void
}

export const useMissionStore = create<MissionState>()(
  temporal(
    immer((set) => ({
      draft: null,
      isDirty: false,
      restoredFrom: null,
      load: (mission) => {
        set({ draft: mission, isDirty: false, restoredFrom: null })
        // A newly opened mission starts with no history: undo must never
        // step back into whichever mission was open before.
        useMissionStore.temporal.getState().clear()
      },
      restore: (draft, savedAt) => {
        set({ draft, isDirty: true, restoredFrom: savedAt })
        useMissionStore.temporal.getState().clear()
      },
      edit: (recipe) =>
        set((state) => {
          if (!state.draft) return
          recipe(state.draft)
          state.isDirty = true
        }),
      markSaved: () => set({ isDirty: false, restoredFrom: null }),
    })),
    {
      partialize: (state) => ({ draft: state.draft }),
      limit: 200,
    },
  ),
)

export function useMissionHistory<T>(
  selector: (state: TemporalState<Pick<MissionState, 'draft'>>) => T,
): T {
  return useStore(useMissionStore.temporal, selector)
}
