import { beforeEach, describe, expect, it } from 'vitest'
import type { Mission } from '@/lib/api'
import { useMissionStore } from './mission'

const mission: Mission = {
  schema_version: 3,
  meta: { name: 'Lanius', id: '01JC', created_utc: '2026-11-01T09:14:00Z', authors: [], notes: '' },
  rocket: null, motor: null, recovery: { devices: [] }, ballast: { installed_kg: 0, increment_kg: 0.05, max_kg: 2 }, site: null,
  environment: { atmosphere: { kind: 'standard' } },
  monte_carlo: { samples: 200, seed: 1, wind_correlation_m: 750 }, constraints: {}, solver: {}, assets: {},
}

describe('mission store', () => {
  beforeEach(() => {
    useMissionStore.getState().load(structuredClone(mission))
    useMissionStore.temporal.getState().clear()
  })

  it('marks the draft dirty on edit and clean on save', () => {
    const { edit, markSaved } = useMissionStore.getState()
    edit((d) => { d.meta.name = 'Lanius II' })
    expect(useMissionStore.getState().isDirty).toBe(true)
    markSaved()
    expect(useMissionStore.getState().isDirty).toBe(false)
  })

  it('undoes and redoes edits', () => {
    useMissionStore.getState().edit((d) => { d.meta.name = 'Lanius II' })
    useMissionStore.temporal.getState().undo()
    expect(useMissionStore.getState().draft?.meta.name).toBe('Lanius')
    useMissionStore.temporal.getState().redo()
    expect(useMissionStore.getState().draft?.meta.name).toBe('Lanius II')
  })

  it('opening another mission clears undo history', () => {
    useMissionStore.getState().edit((d) => { d.meta.name = 'Lanius II' })
    useMissionStore.getState().load({ ...structuredClone(mission), meta: { ...mission.meta, id: 'other', name: 'Other' } })
    expect(useMissionStore.temporal.getState().pastStates).toHaveLength(0)
    useMissionStore.temporal.getState().undo()
    expect(useMissionStore.getState().draft?.meta.name).toBe('Other')
  })
})
