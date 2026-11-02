import { Redo2, Save, Undo2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ProblemNotice } from '@/components/ProblemNotice'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { useSaveMission } from '@/lib/mission/save'
import { discardRestored } from '@/stores/draftPersistence'
import { useMissionHistory, useMissionStore } from '@/stores/mission'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const mod = isMac ? '⌘' : 'Ctrl+'

function isTextInput(target: EventTarget | null) {
  return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
}

/** The open mission, with undo, redo and save. Lives in every section header. */
export function MissionBar() {
  const name = useMissionStore((s) => s.draft?.meta.name)
  const isDirty = useMissionStore((s) => s.isDirty)
  const restoredFrom = useMissionStore((s) => s.restoredFrom)
  const canUndo = useMissionHistory((s) => s.pastStates.length > 0)
  const canRedo = useMissionHistory((s) => s.futureStates.length > 0)
  const undo = useMissionHistory((s) => s.undo)
  const redo = useMissionHistory((s) => s.redo)
  const save = useSaveMission()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(isMac ? e.metaKey : e.ctrlKey)) return
      const key = e.key.toLowerCase()
      if (key === 's') {
        e.preventDefault()
        if (useMissionStore.getState().isDirty) save.mutate()
      } else if (key === 'z' && !isTextInput(e.target)) {
        // Inside a text field, leave undo to the field itself.
        e.preventDefault()
        if (e.shiftKey) redo()
        else undo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [save, undo, redo])

  if (name === undefined) return null

  return (
    <div className="flex min-w-0 items-center gap-1">
      <span className="mr-2 truncate text-sm text-muted-foreground" title={name}>
        {name}
      </span>
      {restoredFrom && <RestoredNotice savedAt={restoredFrom} />}
      <Tooltip content={`Undo (${mod}Z)`}>
        <Button variant="ghost" size="icon" className="size-8" onClick={() => undo()} disabled={!canUndo} aria-label="Undo">
          <Undo2 />
        </Button>
      </Tooltip>
      <Tooltip content={`Redo (${mod}Shift+Z)`}>
        <Button variant="ghost" size="icon" className="size-8" onClick={() => redo()} disabled={!canRedo} aria-label="Redo">
          <Redo2 />
        </Button>
      </Tooltip>
      {save.error && (
        <Tooltip content={<ProblemNotice error={save.error} />} className="max-w-96 p-0">
          <button type="button" className="mr-1 text-sm text-nogo underline-offset-4 hover:underline">
            Not saved
          </button>
        </Tooltip>
      )}
      <Tooltip content={`Save (${mod}S)`}>
        <Button
          size="sm"
          variant={isDirty ? 'primary' : 'secondary'}
          onClick={() => save.mutate()}
          disabled={!isDirty || save.isPending}
        >
          <Save />
          {save.isPending ? 'Saving' : isDirty ? 'Save' : 'Saved'}
        </Button>
      </Tooltip>
    </div>
  )
}

/** Unsaved changes came back after a reload: say so, and offer to throw them away (with a confirm). */
function RestoredNotice({ savedAt }: { savedAt: string }) {
  const [confirming, setConfirming] = useState(false)
  if (confirming) {
    return (
      <span className="mr-1 flex items-center gap-1 text-sm">
        Discard the restored changes?
        <Button variant="ghost" size="sm" className="h-7 px-2 text-nogo" onClick={() => void discardRestored()}>
          Discard
        </Button>
        <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setConfirming(false)}>
          Keep
        </Button>
      </span>
    )
  }
  return (
    <span className="mr-1 flex items-center gap-1 text-sm">
      <Tooltip content={`Unsaved changes kept from ${new Date(savedAt).toLocaleString()}, before the page reloaded.`}>
        <span className="text-caution" tabIndex={0}>
          Restored
        </span>
      </Tooltip>
      <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setConfirming(true)}>
        Discard
      </Button>
    </span>
  )
}
