import { TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'
import { ApiProblem } from '@/lib/api'

/** Inline error for a failed request: what went wrong, and which fields. */
export function ProblemNotice({
  error,
  fixLink,
}: {
  error: unknown
  /** Turns an issue path into a link to the section that fixes it. */
  fixLink?: (path: string) => { href: string; label: string } | null
}) {
  if (!error) return null
  const problem = error instanceof ApiProblem ? error.problem : null
  // fetch() rejects with a TypeError when the server can't be reached at all.
  const title =
    problem?.title ??
    (error instanceof TypeError
      ? 'Could not reach the API. Check that the stack is running.'
      : error instanceof Error
        ? error.message
        : String(error))
  return (
    <div role="alert" className="space-y-1 rounded-md border border-nogo/50 bg-nogo/10 p-3 text-sm">
      <p className="flex items-center gap-2 font-medium text-foreground">
        <TriangleAlert className="size-4 text-nogo" aria-hidden />
        {title}
      </p>
      {problem?.detail && <p className="text-muted-foreground">{problem.detail}</p>}
      {problem?.issues && problem.issues.length > 0 && (
        <ul className="list-inside list-disc text-muted-foreground">
          {problem.issues.map((i) => (
            <li key={`${i.path}:${i.code}`}>
              <code className="text-foreground">{i.path}</code> {i.message}
              {fixLink?.(i.path) && (
                <>
                  {' '}
                  {/* Client-side navigation: a full page load would drop the unsaved draft. */}
                  <Link className="text-primary underline-offset-4 hover:underline" to={fixLink(i.path)!.href}>
                    {fixLink(i.path)!.label}
                  </Link>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
