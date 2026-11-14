import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', cb)
      return () => mql.removeEventListener('change', cb)
    },
    () => window.matchMedia(query).matches,
  )
}

/**
 * Phones and small tablets: below Tailwind's `lg`, the shell swaps the rail for a
 * menu and the docked pane for tabs. Keep in step with the `max-lg:`/`lg:` classes.
 * Screens only: paper is narrow too, and swapping the layout while printing
 * would remount the page being printed.
 */
export const useCompact = () => useMediaQuery('screen and (max-width: 1023.98px)')

/** Touch-first devices, where nothing hovers (tooltips must open on tap instead). */
export const useNoHover = () => useMediaQuery('(hover: none)')
