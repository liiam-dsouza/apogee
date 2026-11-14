import { CircleAlert, FileCode2, Plus, Save, TriangleAlert, X } from 'lucide-react'
import { Dialog, DropdownMenu } from 'radix-ui'
import { useEffect, useRef, useState } from 'react'
import { ProblemNotice } from '@/components/ProblemNotice'
import { Button } from '@/components/ui/button'
import { ApiProblem } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useMissionYaml, useSaveMissionYaml } from '../queries'
import { issueRange } from './issueRanges'
import { applyTheme, modelUri, monaco } from './monaco'
import { SNIPPET_GROUPS, SNIPPETS, type MissionSnippet } from './snippets'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const mod = isMac ? '⌘' : 'Ctrl+'

/** Markers the server's save checks set; the YAML worker owns 'yaml'. */
const SERVER_OWNER = 'apogee'

interface Problem {
  severity: 'error' | 'warning'
  message: string
  line: number
  column: number
}

/**
 * The stored mission file in a full-screen code editor. Saving replaces the
 * mission with the YAML as written (the API checks it like an import).
 */
export default function YamlEditor({ missionId, name, onClose }: { missionId: string; name: string; onClose: () => void }) {
  const yaml = useMissionYaml(missionId)
  const save = useSaveMissionYaml(missionId)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const [dirty, setDirty] = useState(false)
  const [problems, setProblems] = useState<Problem[]>([])
  const [confirmClose, setConfirmClose] = useState(false)

  const submit = () => {
    const model = editorRef.current?.getModel()
    if (!model || save.isPending) return
    const text = model.getValue()
    save.mutate(text, {
      onSuccess: onClose,
      onError: (error) => {
        // Point each issue at its line, so the fix is one click away.
        if (!(error instanceof ApiProblem) || model.isDisposed()) return
        monaco.editor.setModelMarkers(
          model,
          SERVER_OWNER,
          (error.problem.issues ?? []).map((i) => ({
            ...issueRange(text, i.path),
            severity: i.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
            message: i.message,
            source: i.path,
          })),
        )
        const first = error.problem.issues?.[0]
        if (first) {
          const at = issueRange(text, first.path)
          jumpTo({ severity: 'error', message: first.message, line: at.startLineNumber, column: at.startColumn })
        }
      },
    })
  }

  const requestClose = () => (dirty ? setConfirmClose(true) : onClose())

  const insert = (snippet: MissionSnippet) => {
    const editor = editorRef.current
    if (!editor) return
    editor.focus()
    editor.getContribution<monaco.editor.IEditorContribution & { insert(template: string): void }>('snippetController2')?.insert(snippet.body)
  }

  const jumpTo = (p: Problem) => {
    const editor = editorRef.current
    if (!editor) return
    editor.revealLineInCenter(p.line)
    editor.setPosition({ lineNumber: p.line, column: p.column })
    editor.focus()
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && requestClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content
          aria-describedby={undefined}
          // Escape inside the editor closes its own widgets (suggestions, find), not the dialog.
          onEscapeKeyDown={(e) => {
            if (e.target instanceof Element && e.target.closest('.monaco-editor')) e.preventDefault()
          }}
          onKeyDown={(e) => {
            if ((isMac ? e.metaKey : e.ctrlKey) && e.key.toLowerCase() === 's') {
              e.preventDefault()
              if (dirty) submit()
            }
          }}
          className="fixed inset-0 z-50 flex flex-col bg-background outline-none md:inset-6 md:overflow-hidden md:rounded-lg md:border md:border-border md:shadow-2xl"
        >
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
            <FileCode2 className="size-5 shrink-0 text-primary" strokeWidth={1.75} aria-hidden />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="font-display text-lg leading-tight font-semibold tracking-wide">Edit as YAML</Dialog.Title>
              <p className="truncate text-xs text-muted-foreground">
                {name}
                {dirty && <span className="text-caution"> · Unsaved changes</span>}
              </p>
            </div>

            {confirmClose ? (
              <div className="flex items-center gap-1 text-sm">
                <span className="mr-1 max-sm:hidden">Discard your changes?</span>
                <Button variant="ghost" size="sm" className="text-nogo" onClick={onClose}>
                  Discard
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirmClose(false)}>
                  Keep editing
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <SnippetMenu onInsert={insert} onClose={() => editorRef.current?.focus()} disabled={!yaml.data} />
                <Button size="sm" variant={dirty ? 'primary' : 'secondary'} onClick={submit} disabled={!dirty || save.isPending}>
                  <Save />
                  {save.isPending ? 'Saving' : 'Save'}
                  <kbd className="ml-1 text-xs opacity-70 max-sm:hidden">{mod}S</kbd>
                </Button>
                <Button variant="ghost" size="icon" className="-mr-2" aria-label="Close" onClick={requestClose}>
                  <X className="size-5!" />
                </Button>
              </div>
            )}
          </header>

          <div className="relative min-h-0 flex-1">
            {yaml.error ? (
              <div className="p-4">
                <ProblemNotice error={yaml.error} />
              </div>
            ) : yaml.data === undefined ? (
              <p className="p-4 text-sm text-muted-foreground">Loading the mission file…</p>
            ) : (
              <CodePane
                missionId={missionId}
                initial={yaml.data}
                editorRef={editorRef}
                onDirty={setDirty}
                onProblems={setProblems}
              />
            )}
          </div>

          <ProblemsBar problems={problems} onJump={jumpTo} saveError={save.error} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function CodePane({
  missionId,
  initial,
  editorRef,
  onDirty,
  onProblems,
}: {
  missionId: string
  initial: string
  editorRef: React.RefObject<monaco.editor.IStandaloneCodeEditor | null>
  onDirty: (dirty: boolean) => void
  onProblems: (problems: Problem[]) => void
}) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    applyTheme()
    const uri = modelUri(missionId)
    monaco.editor.getModel(uri)?.dispose()
    const model = monaco.editor.createModel(initial, 'yaml', uri)
    model.updateOptions({ tabSize: 2, insertSpaces: true })
    const savedVersion = model.getAlternativeVersionId()

    const editor = monaco.editor.create(host.current!, {
      model,
      theme: 'apogee',
      automaticLayout: true,
      fontFamily: "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace",
      fontSize: 13,
      lineHeight: 20,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      padding: { top: 12, bottom: 12 },
      renderLineHighlight: 'all',
      smoothScrolling: true,
      stickyScroll: { enabled: true },
      quickSuggestions: { other: true, comments: false, strings: true },
      tabCompletion: 'on',
      suggest: { showWords: false },
      fixedOverflowWidgets: true,
    })
    editorRef.current = editor
    editor.focus()

    const changes = model.onDidChangeContent(() => {
      onDirty(model.getAlternativeVersionId() !== savedVersion)
      // The server's verdict was on the old text; the YAML worker re-checks live.
      monaco.editor.setModelMarkers(model, SERVER_OWNER, [])
    })
    const markers = monaco.editor.onDidChangeMarkers((uris) => {
      if (!uris.some((u) => u.toString() === uri.toString())) return
      onProblems(
        monaco.editor
          .getModelMarkers({ resource: uri })
          .filter((m) => m.severity >= monaco.MarkerSeverity.Warning)
          .sort((a, b) => b.severity - a.severity || a.startLineNumber - b.startLineNumber)
          .map((m) => ({
            severity: m.severity === monaco.MarkerSeverity.Error ? 'error' : 'warning',
            message: m.message,
            line: m.startLineNumber,
            column: m.startColumn,
          })),
      )
    })
    // Follow the app's theme toggle (dark, light, pink).
    const themeWatch = new MutationObserver(applyTheme)
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-pink'] })

    return () => {
      themeWatch.disconnect()
      markers.dispose()
      changes.dispose()
      // Detach first, so in-flight requests (word highlights) cancel instead of hitting a disposed model.
      editor.setModel(null)
      editor.dispose()
      model.dispose()
      editorRef.current = null
    }
    // The editor is created once per opened file; the callbacks are stable setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionId, initial])

  return <div ref={host} className="absolute inset-0" />
}

function SnippetMenu({
  onInsert,
  onClose,
  disabled,
}: {
  onInsert: (s: MissionSnippet) => void
  onClose: () => void
  disabled: boolean
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="sm" disabled={disabled}>
          <Plus />
          Insert
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          // Hand focus back to the editor (where an inserted snippet's first field is waiting).
          onCloseAutoFocus={(e) => {
            e.preventDefault()
            onClose()
          }}
          className="z-50 max-h-[min(32rem,var(--radix-dropdown-menu-content-available-height))] w-80 overflow-y-auto rounded-md border border-border bg-surface-2 p-1 shadow-xl"
        >
          {SNIPPET_GROUPS.map((group, i) => (
            <DropdownMenu.Group key={group}>
              {i > 0 && <DropdownMenu.Separator className="mx-1 my-1 h-px bg-border" />}
              <DropdownMenu.Label className="px-2 pt-1.5 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {group}
              </DropdownMenu.Label>
              {SNIPPETS.filter((s) => s.group === group).map((s) => (
                <DropdownMenu.Item
                  key={s.prefix}
                  onSelect={() => onInsert(s)}
                  className="flex cursor-default items-baseline gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-primary/15 data-highlighted:text-foreground"
                >
                  <span className="min-w-0 flex-1 truncate">{s.label}</span>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">{s.detail}</span>
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Group>
          ))}
          <p className="border-t border-border px-2 pt-2 pb-1 text-xs text-muted-foreground">
            Or type a snippet's name in the editor, e.g. <span className="font-mono">fin-set</span>, and press Tab.
          </p>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

function ProblemsBar({ problems, onJump, saveError }: { problems: Problem[]; onJump: (p: Problem) => void; saveError: Error | null }) {
  const [expanded, setExpanded] = useState(true)
  const errors = problems.filter((p) => p.severity === 'error').length
  const warnings = problems.length - errors
  // Line-level issues are shown in the list; only a problem without lines gets the notice.
  const showNotice = saveError && !(saveError instanceof ApiProblem && (saveError.problem.issues?.length ?? 0) > 0)

  return (
    <footer className="shrink-0 border-t border-border bg-surface text-sm">
      {showNotice && (
        <div className="border-b border-border p-2">
          <ProblemNotice error={saveError} />
        </div>
      )}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        disabled={problems.length === 0}
        aria-expanded={expanded}
        className="flex h-9 w-full items-center gap-4 px-4 text-left text-muted-foreground enabled:hover:text-foreground"
      >
        {problems.length === 0 ? (
          <span>No problems</span>
        ) : (
          <>
            <span className={cn('flex items-center gap-1.5', errors > 0 && 'text-nogo')}>
              <CircleAlert className="size-4" aria-hidden />
              {errors} {errors === 1 ? 'error' : 'errors'}
            </span>
            <span className={cn('flex items-center gap-1.5', warnings > 0 && 'text-caution')}>
              <TriangleAlert className="size-4" aria-hidden />
              {warnings} {warnings === 1 ? 'warning' : 'warnings'}
            </span>
          </>
        )}
        <span className="ml-auto text-xs max-sm:hidden">Ctrl+Space for suggestions</span>
      </button>
      {expanded && problems.length > 0 && (
        <ul className="max-h-40 overflow-y-auto border-t border-border py-1">
          {problems.map((p, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => onJump(p)}
                className="flex w-full items-baseline gap-2 px-4 py-1 text-left hover:bg-surface-2"
              >
                {p.severity === 'error' ? (
                  <CircleAlert className="size-3.5 shrink-0 translate-y-0.5 text-nogo" aria-label="Error" />
                ) : (
                  <TriangleAlert className="size-3.5 shrink-0 translate-y-0.5 text-caution" aria-label="Warning" />
                )}
                <span className="min-w-0 flex-1">{p.message}</span>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">Ln {p.line}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </footer>
  )
}
