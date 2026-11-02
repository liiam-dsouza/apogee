import { createContext, useContext } from 'react'

export interface SectionLayout {
  /** Bring the right pane into view: expands it if collapsed, or switches to its tab on a phone. */
  showPane: () => void
  /** Bring the centre into view: switches to its tab on a phone (a no-op on wider screens). */
  showCentre: () => void
}

const noop = () => {}

export const SectionLayoutContext = createContext<SectionLayout>({ showPane: noop, showCentre: noop })

/** For a section to move the reader to where its result appears, e.g. after a run. */
export const useSectionLayout = () => useContext(SectionLayoutContext)
