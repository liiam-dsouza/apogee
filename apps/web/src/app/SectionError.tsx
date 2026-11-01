import { TriangleAlert } from 'lucide-react'
import { useRouteError } from 'react-router'
import { Button } from '@/components/ui/button'

/**
 * Shown in place of a section that threw while rendering. The rail and the
 * rest of the app keep working, so one broken view never strands the user.
 */
export function SectionError() {
  const error = useRouteError()
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="flex h-full flex-col justify-center gap-4 p-6 md:p-10">
      <p className="flex items-center gap-2 font-display text-2xl font-medium">
        <TriangleAlert className="size-6 text-nogo" aria-hidden />
        This section stopped working.
      </p>
      <p className="max-w-prose text-sm text-muted-foreground">
        Other sections still work, and your open mission is untouched. Reloading the page usually clears this; if it
        keeps happening, report the message below.
      </p>
      <pre className="max-w-prose overflow-auto rounded-md border border-border bg-surface p-3 text-xs">{message}</pre>
      <div>
        <Button onClick={() => window.location.reload()}>Reload the page</Button>
      </div>
    </div>
  )
}
