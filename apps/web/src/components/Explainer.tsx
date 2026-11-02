import { Collapsible } from 'radix-ui'
import { Book, ChevronDown, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

/**
 * The collapsible "what this does" panel every section carries: the
 * calculation behind the view, in plain language, plus a link to its
 * methods page.
 */
export function Explainer({ children, methodsHref }: { children: ReactNode; methodsHref?: string }) {
  return (
    <Collapsible.Root className="rounded-md border border-border bg-surface">
      <Collapsible.Trigger className="group flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted-foreground hover:text-foreground">
        <Info className="size-4" aria-hidden />
        What this does
        <ChevronDown className="ml-auto size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
      </Collapsible.Trigger>
      <Collapsible.Content className="space-y-2 px-3 pb-3 text-sm leading-relaxed text-foreground">
        {children}
        {methodsHref && (
          <Link to={methodsHref} className="flex flex-row gap-x-2 items-center my-1 text-primary underline-offset-4 hover:underline">
            <Book className="size-4" aria-hidden /> Read the method
          </Link>
        )}
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
