import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Mission } from '@/lib/api'

export const missionKeys = {
  all: ['missions'] as const,
  one: (id: string) => ['missions', id] as const,
}

export function useMissionList() {
  return useQuery({ queryKey: missionKeys.all, queryFn: api.listMissions })
}

export function useMissionDocument(id: string | null) {
  return useQuery({
    queryKey: missionKeys.one(id ?? ''),
    queryFn: () => api.getMission(id!),
    enabled: id !== null,
  })
}

function useInvalidateMissions() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: missionKeys.all })
}

export function useCreateMission() {
  const invalidate = useInvalidateMissions()
  return useMutation({
    // The server fills meta.id and meta.created_utc; the client never invents ids.
    mutationFn: (name: string) => api.createMission({ meta: { name } } as Mission),
    onSuccess: invalidate,
  })
}

export function useImportMission() {
  const invalidate = useInvalidateMissions()
  return useMutation({ mutationFn: api.importMission, onSuccess: invalidate })
}

export function useDeleteMission() {
  const invalidate = useInvalidateMissions()
  return useMutation({ mutationFn: api.deleteMission, onSuccess: invalidate })
}
