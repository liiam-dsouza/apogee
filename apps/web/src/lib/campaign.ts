import { useMutation, useQuery } from '@tanstack/react-query'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, type FailureMode, type Mission } from '@/lib/api'

/**
 * The latest Monte Carlo campaign per mission. The id is remembered across
 * reloads; the draft it was started from only for this session (to say when
 * the mission has changed since), with the recovery failure it flew, if any.
 */
interface Campaigns {
  byMission: Record<string, string>
  startedFrom: Record<string, Mission>
  failure: Record<string, FailureMode | null>
  record: (draft: Mission, campaignId: string, failure: FailureMode | null) => void
}

/** How each recovery failure is named next to a campaign. */
export const FAILURE_LABEL: Record<FailureMode, string> = {
  drogue_fails: 'Drogue fails',
  main_fails: 'Main fails',
  nothing_opens: 'Nothing opens',
}

export const useCampaigns = create<Campaigns>()(
  persist(
    (set) => ({
      byMission: {},
      startedFrom: {},
      failure: {},
      record: (draft, campaignId, failure) =>
        set((s) => ({
          byMission: { ...s.byMission, [draft.meta.id!]: campaignId },
          startedFrom: { ...s.startedFrom, [draft.meta.id!]: draft },
          failure: { ...s.failure, [draft.meta.id!]: failure },
        })),
    }),
    { name: 'apogee.campaigns', partialize: (s) => ({ byMission: s.byMission, failure: s.failure }) },
  ),
)

export function useRunCampaign() {
  const record = useCampaigns((s) => s.record)
  return useMutation({
    mutationFn: ({ draft, failure = null }: { draft: Mission; failure?: FailureMode | null }) =>
      api.runMonteCarlo(draft, failure).then((state) => ({ draft, failure, state })),
    onSuccess: ({ draft, failure, state }) => record(draft, state.id, failure),
  })
}

/** The open mission's latest campaign, polled while it runs. */
export function useCampaign(missionId: string | undefined) {
  const id = useCampaigns((s) => (missionId ? s.byMission[missionId] : undefined))
  const startedFrom = useCampaigns((s) => (missionId ? s.startedFrom[missionId] : undefined))
  const failure = useCampaigns((s) => (missionId ? (s.failure[missionId] ?? null) : null))
  const query = useQuery({
    queryKey: ['campaigns', id],
    queryFn: () => api.getCampaign(id!),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data?.state.status === 'running' ? 1000 : false),
  })
  return { id, startedFrom, failure, ...query }
}
