import { Redo2, Save, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
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
    <div data-tour="mission-bar" className="flex min-w-0 items-center gap-1">
      <MissionName name={name} />
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
        <Tooltip content={<ProblemNotice error={save.error} />} className="max-w-96 p-0" tappable>
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

/** The mission name, edited in place. A rename is an ordinary draft edit: it lands on save, and undo reverts it. */
function MissionName({ name }: { name: string }) {
  const edit = useMissionStore((s) => s.edit)
  const [value, setValue] = useState<string | null>(null)
  const cancelled = useRef(false)
  const shown = value ?? name

  const commit = () => {
    const next = cancelled.current ? undefined : value?.trim()
    cancelled.current = false
    setValue(null)
    // A mission must have a name, so an emptied field falls back to the old one.
    if (next && next !== name) {
      edit((d) => {
        d.meta.name = next
      })
    }
  }

  return (
    <input
      aria-label="Mission name"
      title={shown}
      value={shown}
      size={Math.max(shown.length, 4)}
      spellCheck={false}
      onFocus={(e) => {
        setValue(name)
        e.currentTarget.select()
      }}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        else if (e.key === 'Escape') {
          cancelled.current = true
          e.currentTarget.blur()
        }
      }}
      className="mr-2 max-w-64 min-w-0 truncate rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-sm text-muted-foreground field-sizing-content outline-none hover:border-border focus:border-ring focus:text-foreground max-lg:hidden"
    />
  )
}

/** Unsaved changes came back after a reload: say so, and offer to throw them away (with a confirm). */
function RestoredNotice({ savedAt }: { savedAt: string }) {
  const [confirming, setConfirming] = useState(false)
  if (confirming) {
    return (
      <span className="mr-1 flex flex-wrap items-center gap-1 text-sm">
        <span className="max-sm:hidden">Discard the restored changes?</span>
        <span className="sm:hidden">Discard?</span>
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
      <Tooltip content={`Unsaved changes kept from ${new Date(savedAt).toLocaleString()}, before the page reloaded.`} tappable>
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
