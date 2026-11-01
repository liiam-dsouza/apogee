import { create } from 'zustand'
import type { LonLat } from '@/components/map/geo'

export type DrawTarget = { kind: 'boundary' } | { kind: 'hazard' } | { kind: 'road' }

export const MIN_POINTS: Record<DrawTarget['kind'], number> = { boundary: 3, hazard: 3, road: 2 }

export const DRAW_LABEL: Record<DrawTarget['kind'], string> = {
  boundary: 'range boundary',
  hazard: 'hazard zone',
  road: 'access road',
}

/** In-progress map drawing, shared between the map (clicks) and the pane (start/finish). */
interface DrawingState {
  target: DrawTarget | null
  points: LonLat[]
  start: (target: DrawTarget) => void
  add: (p: LonLat) => void
  removeLast: () => void
  cancel: () => void
}

export const useDrawing = create<DrawingState>()((set) => ({
  target: null,
  points: [],
  start: (target) => set({ target, points: [] }),
  add: (p) => set((s) => ({ points: [...s.points, p] })),
  removeLast: () => set((s) => ({ points: s.points.slice(0, -1) })),
  cancel: () => set({ target: null, points: [] }),
}))
