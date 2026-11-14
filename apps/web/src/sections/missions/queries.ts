import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Mission } from '@/lib/api'
import { useMissionStore } from '@/stores/mission'

export const missionKeys = {
  all: ['missions'] as const,
  one: (id: string) => ['missions', id] as const,
  yaml: (id: string) => ['missions', id, 'yaml'] as const,
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

/** The stored YAML, fetched fresh each time the editor opens. */
export function useMissionYaml(id: string) {
  return useQuery({ queryKey: missionKeys.yaml(id), queryFn: () => api.getMissionYaml(id), staleTime: 0, gcTime: 0 })
}

export function useSaveMissionYaml(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (yaml: string) => api.updateMissionYaml(id, yaml),
    onSuccess: (doc) => {
      qc.setQueryData(missionKeys.one(id), doc)
      qc.invalidateQueries({ queryKey: missionKeys.all, exact: true })
      // The pane only opens the YAML editor on an open mission once it is saved,
      // so reloading the draft here never throws away edits.
      const { draft, load } = useMissionStore.getState()
      if (draft?.meta.id === id) load(doc.mission)
    },
  })
}
