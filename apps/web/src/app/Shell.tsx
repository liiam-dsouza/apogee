import { MotionConfig } from 'motion/react'
import { useEffect } from 'react'
import { Outlet } from 'react-router'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useCompact } from '@/lib/useMediaQuery'
import { usePrefs } from '@/stores/prefs'
import { Rail } from './Rail'

/** Three-zone shell: rail | section (centre + right pane). On a phone the rail becomes a menu in the section header. */
export function Shell() {
  const theme = usePrefs((s) => s.theme)
  const compact = useCompact()
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={300}>
        <div className="flex h-full">
          {!compact && <Rail />}
          <main className="min-w-0 flex-1">
            <Outlet />
          </main>
        </div>
      </TooltipProvider>
    </MotionConfig>
  )
}
