import { TriangleAlert } from 'lucide-react'
import { ApiProblem } from '@/lib/api'

/** Inline error for a failed request: what went wrong, and which fields. */
export function ProblemNotice({ error }: { error: unknown }) {
  if (!error) return null
  const problem = error instanceof ApiProblem ? error.problem : null
  const title = problem?.title ?? 'Could not reach the API. Check that the stack is running.'
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
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
