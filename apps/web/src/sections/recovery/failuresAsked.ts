import { create } from 'zustand'

/** Missions whose failures have been asked for this session (the tour asks for its own). */
export const useFailuresAsked = create<{ missions: string[]; ask: (id: string) => void }>()((set) => ({
  missions: [],
  ask: (id) => set((s) => ({ missions: s.missions.includes(id) ? s.missions : [...s.missions, id] })),
}))
