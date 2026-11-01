import { MotionConfig } from 'motion/react'
import { useEffect } from 'react'
import { Outlet } from 'react-router'
import { TooltipProvider } from '@/components/ui/tooltip'
import { usePrefs } from '@/stores/prefs'
import { Rail } from './Rail'

/** Three-zone shell: rail | section (centre + right pane). */
export function Shell() {
  const theme = usePrefs((s) => s.theme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={300}>
        <div className="flex h-full">
          <Rail />
          <main className="min-w-0 flex-1">
            <Outlet />
          </main>
        </div>
      </TooltipProvider>
    </MotionConfig>
  )
}
