import { beforeEach, describe, expect, it } from 'vitest'
import type { Mission } from '@/lib/api'
import { DRAFT_KEY, readStored, restoreDraft, writeStored } from './draftPersistence'
import { useMissionStore } from './mission'

const mission: Mission = {
  schema_version: 3,
  meta: { name: 'Lanius', id: '01JC', created_utc: '2026-11-01T09:14:00Z', authors: [], notes: '' },
  rocket: null, motor: null, recovery: { devices: [] }, ballast: {}, site: null,
  environment: { atmosphere: { kind: 'standard' } },
  monte_carlo: { samples: 200, seed: 1, wind_correlation_m: 750 }, constraints: {}, solver: {}, assets: {},
}

class MemoryStorage implements Storage {
  private data = new Map<string, string>()
  get length() { return this.data.size }
  clear() { this.data.clear() }
  getItem(k: string) { return this.data.get(k) ?? null }
  key(i: number) { return [...this.data.keys()][i] ?? null }
  removeItem(k: string) { this.data.delete(k) }
  setItem(k: string, v: string) { this.data.set(k, v) }
}

describe('draft persistence', () => {
  let storage: MemoryStorage
  beforeEach(() => {
    storage = new MemoryStorage()
    useMissionStore.setState({ draft: null, isDirty: false, restoredFrom: null })
  })

  it('keeps the whole draft only while it has unsaved changes', () => {
    writeStored(storage, mission, true)
    expect(readStored(storage)?.draft?.meta.name).toBe('Lanius')
    writeStored(storage, mission, false)
    expect(readStored(storage)).toMatchObject({ missionId: '01JC' })
    expect(readStored(storage)?.draft).toBeUndefined()
    writeStored(storage, null, false)
    expect(storage.getItem(DRAFT_KEY)).toBeNull()
  })

  it('restores unsaved changes as dirty and flagged', async () => {
    writeStored(storage, { ...mission, meta: { ...mission.meta, name: 'Lanius II' } }, true, new Date('2026-11-02T10:00:00Z'))
    await restoreDraft(storage)
    const s = useMissionStore.getState()
    expect(s.draft?.meta.name).toBe('Lanius II')
    expect(s.isDirty).toBe(true)
    expect(s.restoredFrom).toBe('2026-11-02T10:00:00.000Z')
    s.markSaved()
    expect(useMissionStore.getState().restoredFrom).toBeNull()
  })

  it('never replaces a mission that is already open', async () => {
    useMissionStore.getState().load({ ...mission, meta: { ...mission.meta, id: 'other', name: 'Other' } })
    writeStored(storage, mission, true)
    await restoreDraft(storage)
    expect(useMissionStore.getState().draft?.meta.name).toBe('Other')
  })

  it('ignores garbage in storage', () => {
    storage.setItem(DRAFT_KEY, '{not json')
    expect(readStored(storage)).toBeNull()
  })
})
