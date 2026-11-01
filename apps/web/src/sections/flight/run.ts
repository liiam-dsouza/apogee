import { useMutation, useQuery } from '@tanstack/react-query'
import { create } from 'zustand'
import { api, type Mission, type RunState } from '@/lib/api'

/** The latest flight per mission, and the exact draft it was run from. */
interface FlightRuns {
  byMission: Record<string, { resultId: string; draft: Mission; cached: boolean }>
  record: (draft: Mission, run: RunState) => void
}

export const useFlightRuns = create<FlightRuns>()((set) => ({
  byMission: {},
  record: (draft, run) =>
    set((s) => ({
      byMission: { ...s.byMission, [draft.meta.id!]: { resultId: run.result_id, draft, cached: run.cached } },
    })),
}))

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * Runs the draft as it is now (saved or not). Waits up to 30 s server-side,
 * then polls the job, so a ~300 ms flight returns in one request.
 */
export function useRunFlight() {
  const record = useFlightRuns((s) => s.record)
  return useMutation({
    mutationFn: async ({ draft, ascentOnly }: { draft: Mission; ascentOnly: boolean }) => {
      let run = await api.runFlight(draft, { ascentOnly, waitS: 30 })
      while (run.status === 'queued' || run.status === 'running') {
        await sleep(500)
        const job = await api.getJob(run.job_id!)
        if (job.status === 'done') run = { ...run, status: 'done' }
        else if (job.status === 'failed' || job.status === 'not_found')
          run = { ...run, status: 'failed', error: job.error ?? 'The job was lost.' }
      }
      if (run.status === 'failed') throw new Error(`The simulation failed: ${run.error}`)
      return { draft, run }
    },
    onSuccess: ({ draft, run }) => record(draft, run),
  })
}

export function useResult(id: string | undefined) {
  return useQuery({
    queryKey: ['results', id],
    queryFn: () => api.getResult(id!),
    enabled: Boolean(id),
    staleTime: Infinity, // results never change
  })
}

export function useSeries(id: string | undefined, channels: string[]) {
  return useQuery({
    queryKey: ['results', id, 'series', channels],
    queryFn: () => api.getSeries(id!, channels, 1500),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}
