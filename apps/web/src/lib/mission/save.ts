import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Mission } from '@/lib/api'
import { useMissionStore } from '@/stores/mission'

export function useSaveMission() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const sent = useMissionStore.getState().draft
      if (!sent) throw new Error('No mission is open')
      return { sent, doc: await api.updateMission(sent) }
    },
    onSuccess: ({ sent, doc }: { sent: Mission; doc: Awaited<ReturnType<typeof api.updateMission>> }) => {
      // Immer gives every edit a new object, so reference equality says whether
      // anything changed while the request was in flight.
      const { draft, markSaved } = useMissionStore.getState()
      if (draft === sent) markSaved()
      qc.setQueryData(['missions', doc.mission.meta.id], doc)
      qc.invalidateQueries({ queryKey: ['missions'], exact: true })
    },
  })
}
