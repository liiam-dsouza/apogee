import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, type Issue } from '@/lib/api'
import { useMissionStore } from '@/stores/mission'
import { useDebounced } from './useDebounced'

/**
 * Server-side validation of the open draft, re-run shortly after each edit.
 * The server is the authority; running it live means the UI shows exactly
 * the issues a save or a run would hit, with paths into the config.
 */
export function useDraftValidation() {
  const draft = useMissionStore((s) => s.draft)
  const debounced = useDebounced(draft, 400)
  return useQuery({
    queryKey: ['validate', debounced],
    queryFn: () => api.validateMission(debounced as unknown as Record<string, unknown>),
    enabled: debounced !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
}

/** Issues at exactly `path` (e.g. 'site.rail_length_m'), or nested under it. */
export function useIssuesAt(path: string, { nested = false } = {}): Issue[] {
  const { data } = useDraftValidation()
  return (data?.issues ?? []).filter(
    (i) => i.path === path || (nested && (i.path.startsWith(`${path}.`) || i.path.startsWith(`${path}[`))),
  )
}
