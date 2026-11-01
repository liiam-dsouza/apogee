import type { ReactNode } from 'react'
import { Explainer } from './Explainer'

/**
 * Stand-in for a section that is scaffolded but not built. States what the
 * canvas will show, in the brief's words, so the shell is navigable and
 * reviewable before each section is implemented.
 */
export function CentreStub({
  summary,
  explainer,
  methodsHref,
}: {
  summary: string
  explainer: ReactNode
  methodsHref?: string
}) {
  return (
    <div className="flex h-full flex-col justify-end gap-4 p-6 md:p-10">
      <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
        {summary}
      </p>
      <div className="max-w-xl">
        <Explainer methodsHref={methodsHref}>{explainer}</Explainer>
      </div>
    </div>
  )
}

export function PaneStub({ title, fields }: { title: string; fields: string[] }) {
  return (
    <div className="space-y-3 p-4">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      <ul className="divide-y divide-border rounded-md border border-border">
        {fields.map((f) => (
          <li key={f} className="px-3 py-2 text-sm text-muted-foreground">
            {f}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">Not built yet. These fields will come from the mission schema.</p>
    </div>
  )
}
