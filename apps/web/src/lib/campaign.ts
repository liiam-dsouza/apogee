import { useMutation, useQuery } from '@tanstack/react-query'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, type Mission } from '@/lib/api'

/**
 * The latest Monte Carlo campaign per mission. The id is remembered across
 * reloads; the draft it was started from only for this session (to say when
 * the mission has changed since).
 */
interface Campaigns {
  byMission: Record<string, string>
  startedFrom: Record<string, Mission>
  record: (draft: Mission, campaignId: string) => void
}

export const useCampaigns = create<Campaigns>()(
  persist(
    (set) => ({
      byMission: {},
      startedFrom: {},
      record: (draft, campaignId) =>
        set((s) => ({
          byMission: { ...s.byMission, [draft.meta.id!]: campaignId },
          startedFrom: { ...s.startedFrom, [draft.meta.id!]: draft },
        })),
    }),
    { name: 'apogee.campaigns', partialize: (s) => ({ byMission: s.byMission }) },
  ),
)

export function useRunCampaign() {
  const record = useCampaigns((s) => s.record)
  return useMutation({
    mutationFn: (draft: Mission) => api.runMonteCarlo(draft).then((state) => ({ draft, state })),
    onSuccess: ({ draft, state }) => record(draft, state.id),
  })
}

/** The open mission's latest campaign, polled while it runs. */
export function useCampaign(missionId: string | undefined) {
  const id = useCampaigns((s) => (missionId ? s.byMission[missionId] : undefined))
  const startedFrom = useCampaigns((s) => (missionId ? s.startedFrom[missionId] : undefined))
  const query = useQuery({
    queryKey: ['campaigns', id],
    queryFn: () => api.getCampaign(id!),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data?.state.status === 'running' ? 1000 : false),
  })
  return { id, startedFrom, ...query }
}
