import { create } from 'zustand'

/**
 * The example the tour opens: loading it, flying it, or why it couldn't.
 * `conflict` means unsaved changes to another mission are in the way.
 */
export type DemoStatus = 'idle' | 'conflict' | 'loading' | 'flying' | 'ready' | 'skipped' | 'failed'

/** The guided tour: whether it is running, which step it is on, and its example mission. Not persisted. */
interface TourState {
  active: boolean
  step: number
  demo: DemoStatus
  demoError: string | null
  start: () => void
  go: (step: number) => void
  stop: () => void
  setDemo: (demo: DemoStatus, error?: string | null) => void
}

export const useTour = create<TourState>()((set) => ({
  active: false,
  step: 0,
  demo: 'idle',
  demoError: null,
  start: () => set({ active: true, step: 0, demo: 'idle', demoError: null }),
  go: (step) => set({ step }),
  stop: () => set({ active: false }),
  setDemo: (demo, error = null) => set({ demo, demoError: error }),
}))
