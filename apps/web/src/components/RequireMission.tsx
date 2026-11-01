import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useMissionStore } from '@/stores/mission'

/** Renders children only when a mission is open in the editor. */
export function RequireMission({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  const hasDraft = useMissionStore((s) => s.draft !== null)
  if (hasDraft) return <>{children}</>
  if (compact) return <p className="p-4 text-sm text-muted-foreground">No mission open.</p>
  return (
    <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
      <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
        Open a mission to edit it here.
      </p>
      <Link to="/missions" className="text-primary underline-offset-4 hover:underline">
        Go to missions
      </Link>
    </div>
  )
}
