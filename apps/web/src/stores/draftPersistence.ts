import { api, type Mission } from '@/lib/api'
import { useMissionStore } from './mission'

/**
 * Keeps the open mission across a reload: a tablet in the field that sleeps,
 * crashes or refreshes must not lose unsaved edits.
 *
 * Unsaved changes are written to localStorage as they happen and come back
 * flagged as restored (with a way to discard them). A clean mission is only
 * remembered by id and reopened from the server, so it is never stale.
 */
export const DRAFT_KEY = 'apogee.draft'

interface Stored {
  missionId: string
  /** Present only while there are unsaved changes. */
  draft?: Mission
  savedAt: string
}

export function readStored(storage: Storage): Stored | null {
  try {
    const raw = storage.getItem(DRAFT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Stored
    return typeof parsed?.missionId === 'string' ? parsed : null
  } catch {
    return null
  }
}

export function writeStored(storage: Storage, draft: Mission | null, isDirty: boolean, now = new Date()) {
  try {
    if (!draft?.meta.id) {
      storage.removeItem(DRAFT_KEY)
      return
    }
    const stored: Stored = { missionId: draft.meta.id, savedAt: now.toISOString() }
    if (isDirty) stored.draft = draft
    storage.setItem(DRAFT_KEY, JSON.stringify(stored))
  } catch {
    // Storage full or blocked (private mode): editing still works, just without the safety net.
  }
}

/** Reopens whatever was open before the reload. Resolves once done (or given up). */
export async function restoreDraft(storage: Storage): Promise<void> {
  const stored = readStored(storage)
  if (!stored || useMissionStore.getState().draft) return
  if (stored.draft) {
    useMissionStore.getState().restore(stored.draft, stored.savedAt)
    return
  }
  try {
    const doc = await api.getMission(stored.missionId)
    // The user may have opened something else while this was in flight.
    if (!useMissionStore.getState().draft) useMissionStore.getState().load(doc.mission)
  } catch {
    // Deleted, or the API is down: start with nothing open, as before.
  }
}

/** Throws away restored changes and reopens the saved mission. */
export async function discardRestored(): Promise<void> {
  const id = useMissionStore.getState().draft?.meta.id
  if (!id) return
  const doc = await api.getMission(id)
  useMissionStore.getState().load(doc.mission)
}

const WRITE_DELAY_MS = 300

/** Restore, then keep storage in step with the store. Call once at startup. */
export function startDraftPersistence(storage: Storage = window.localStorage): () => void {
  void restoreDraft(storage)
  let timer: ReturnType<typeof setTimeout> | undefined
  const unsubscribe = useMissionStore.subscribe((state, prev) => {
    if (state.draft === prev.draft && state.isDirty === prev.isDirty) return
    clearTimeout(timer)
    // Saving and closing are written at once; typing is batched.
    const delay = state.isDirty ? WRITE_DELAY_MS : 0
    timer = setTimeout(() => {
      const { draft, isDirty } = useMissionStore.getState()
      writeStored(storage, draft, isDirty)
    }, delay)
  })
  const flush = () => {
    clearTimeout(timer)
    const { draft, isDirty } = useMissionStore.getState()
    writeStored(storage, draft, isDirty)
  }
  window.addEventListener('pagehide', flush)
  return () => {
    unsubscribe()
    window.removeEventListener('pagehide', flush)
  }
}
