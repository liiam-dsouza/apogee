import { Download, FileCode2, FilePlus2, FolderOpen, Trash2, Upload } from 'lucide-react'
import { lazy, Suspense, useEffect, useEffectEvent, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { Button } from '@/components/ui/button'
import { api, type MissionSummary } from '@/lib/api'
import { useSaveMission } from '@/lib/mission/save'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import {
  useCreateMission,
  useDeleteMission,
  useImportMission,
  useMissionDocument,
  useMissionList,
} from './queries'
import { useSectionLayout } from '@/app/sectionLayout'

// Monaco is large: load it only when someone opens the YAML editor.
const YamlEditor = lazy(() => import('./yaml/YamlEditor'))

/** The selected card lives in the URL (?id=), so a selection is linkable. */
function useSelectedId() {
  const [params, setParams] = useSearchParams()
  const select = (id: string | null) => setParams(id ? { id } : {}, { replace: true })
  return [params.get('id'), select, params.get('yaml') === '1'] as const
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function Centre() {
  const layout = useSectionLayout()
  const missions = useMissionList()
  const create = useCreateMission()
  const importMission = useImportMission()
  const [selectedId, select] = useSelectedId()
  const fileInput = useRef<HTMLInputElement>(null)

  const onImport = (file: File | undefined) => {
    if (file)
      importMission.mutate(file, {
        onSuccess: (doc) => {
          select(doc.mission.meta.id!)
          layout.showPane()
        },
      })
  }

  // An .apg opened from the OS in the installed app arrives here (manifest file_handlers).
  const onLaunch = useEffectEvent(onImport)
  useEffect(() => {
    window.launchQueue?.setConsumer(async ({ files }) => {
      if (files[0]) onLaunch(await files[0].getFile())
    })
  }, [])

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          disabled={create.isPending}
          onClick={() =>
            create.mutate('Untitled mission', {
              onSuccess: (doc) => {
                select(doc.mission.meta.id!)
                layout.showPane()
              },
            })
          }
        >
          <FilePlus2 aria-hidden />
          New mission
        </Button>
        <Button onClick={() => fileInput.current?.click()} disabled={importMission.isPending}>
          <Upload aria-hidden />
          Import mission file
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".apg,.yaml,.yml,.json,.zip"
          className="hidden"
          onChange={(e) => {
            onImport(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </div>

      <ProblemNotice error={create.error ?? importMission.error ?? missions.error} />

      {missions.data && missions.data.length === 0 && (
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground">
          No missions yet. Create one, or import an .apg or mission.yaml from your team's repository.
        </p>
      )}

      {missions.data && missions.data.length > 0 && (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-3">
          {missions.data.map((m) => (
            <li key={m.id}>
              <MissionCard mission={m} selected={m.id === selectedId} onSelect={() => {
                  select(m.id)
                  layout.showPane()
                }} />
            </li>
          ))}
        </ul>
      )}

      <div className="max-w-xl">
        <Explainer methodsHref="/docs/guides/first-flight">
          A mission config is the one file everything else reads: rocket, motor, recovery, site,
          weather, Monte Carlo settings and constraints. Open one to edit it in the other sections.
          Export it as an .apg to hand to another machine with every file it needs, or as YAML to
          keep it in Git alongside your other launches.
        </Explainer>
      </div>
    </div>
  )
}

function MissionCard({
  mission,
  selected,
  onSelect,
}: {
  mission: MissionSummary
  selected: boolean
  onSelect: () => void
}) {
  const openId = useMissionStore((s) => s.draft?.meta.id)
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'flex w-full flex-col gap-1 rounded-md border bg-surface p-4 text-left transition-colors',
        selected ? 'border-primary' : 'border-border hover:border-muted-foreground',
      )}
    >
      <span className="font-display text-lg font-semibold">{mission.name}</span>
      <span className="text-sm text-muted-foreground">
        Saved {dateFormat.format(new Date(mission.updated_utc))}
      </span>
      {openId === mission.id && <span className="text-sm text-primary">Open in editor</span>}
    </button>
  )
}

export function Pane() {
  const [selectedId, select, yamlRequested] = useSelectedId()
  const layout = useSectionLayout()
  const doc = useMissionDocument(selectedId)
  const remove = useDeleteMission()
  const load = useMissionStore((s) => s.load)
  const openId = useMissionStore((s) => s.draft?.meta.id)
  const openName = useMissionStore((s) => s.draft?.meta.name)
  const isDirty = useMissionStore((s) => s.isDirty)
  const navigate = useNavigate()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [editingYaml, setEditingYaml] = useState(false)
  const [confirmSaveFirst, setConfirmSaveFirst] = useState(false)
  const saveDraft = useSaveMission()

  // ?yaml=1 (from a "Fix problem" link) asks for the YAML editor, under the same
  // save-first rule as the button. The pane may be collapsed, so bring it into view.
  const needsSave = openId === selectedId && isDirty
  const yamlOpen = editingYaml || (yamlRequested && !needsSave)
  const saveFirstShown = confirmSaveFirst || (yamlRequested && needsSave)
  const clearYamlRequest = () => yamlRequested && select(selectedId)
  useEffect(() => {
    if (yamlRequested) layout.showPane()
  }, [yamlRequested, layout])

  if (!selectedId) {
    return <p className="p-4 text-sm text-muted-foreground">Select a mission to see its details.</p>
  }
  if (doc.error) {
    return (
      <div className="p-4">
        <ProblemNotice error={doc.error} />
      </div>
    )
  }
  if (!doc.data) return null

  const { mission, config_hash, issues } = doc.data
  const site = mission.site
  const open = () => {
    load(mission)
    setConfirmDiscard(false)
    navigate('/site')
  }
  // The YAML editor works on the stored file, so the open draft's edits must be saved first.
  const editYaml = () => {
    if (openId === mission.meta.id && isDirty) setConfirmSaveFirst(true)
    else setEditingYaml(true)
  }

  return (
    <div className="space-y-5 p-4">
      <div>
        <h2 className="font-display text-xl font-semibold">{mission.meta.name}</h2>
        {mission.meta.notes && <p className="mt-1 text-sm">{mission.meta.notes}</p>}
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Site</dt>
        <dd>
          {site
            ? `${site.latitude_deg.toFixed(4)}, ${site.longitude_deg.toFixed(4)}`
            : 'Not set'}
        </dd>
        <dt className="text-muted-foreground">Authors</dt>
        <dd>{mission.meta.authors?.length ? mission.meta.authors.join(', ') : 'None listed'}</dd>
        <dt className="text-muted-foreground">Config hash</dt>
        <dd className="truncate" title={config_hash}>
          {config_hash.slice(0, 12)}
        </dd>
        <dt className="text-muted-foreground">Mission id</dt>
        <dd className="truncate">{mission.meta.id}</dd>
      </dl>

      {issues.length > 0 && (
        <ul className="space-y-1 text-sm">
          {issues.map((i) => (
            <li key={i.path + i.code} className="text-caution">
              {i.message}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-2">
        {confirmDiscard ? (
          <div className="space-y-2 rounded-md border border-caution/60 p-3">
            <p className="text-sm">“{openName}” has unsaved changes. Opening this mission discards them.</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={open}>
                Discard changes and open
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDiscard(false)}>
                Keep editing “{openName}”
              </Button>
            </div>
          </div>
        ) : openId === mission.meta.id ? (
          <Button variant="primary" onClick={() => navigate('/site')}>
            <FolderOpen aria-hidden />
            Continue editing
          </Button>
        ) : (
          <Button variant="primary" onClick={() => (isDirty ? setConfirmDiscard(true) : open())}>
            <FolderOpen aria-hidden />
            Open in editor
          </Button>
        )}
        {saveFirstShown ? (
          <div className="space-y-2 rounded-md border border-caution/60 p-3">
            <p className="text-sm">“{openName}” has unsaved changes. Save them before editing the file as YAML.</p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                disabled={saveDraft.isPending}
                onClick={() =>
                  saveDraft.mutate(undefined, {
                    onSuccess: () => {
                      setConfirmSaveFirst(false)
                      setEditingYaml(true)
                    },
                  })
                }
              >
                {saveDraft.isPending ? 'Saving' : 'Save and edit as YAML'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setConfirmSaveFirst(false)
                  clearYamlRequest()
                }}
              >
                Not now
              </Button>
            </div>
            <ProblemNotice error={saveDraft.error} />
          </div>
        ) : (
          <Button onClick={editYaml}>
            <FileCode2 aria-hidden />
            Edit as YAML
          </Button>
        )}
        {yamlOpen && (
          <Suspense fallback={null}>
            <YamlEditor
              missionId={mission.meta.id!}
              name={mission.meta.name}
              onClose={() => {
                setEditingYaml(false)
                clearYamlRequest()
              }}
            />
          </Suspense>
        )}
        <Button asChild>
          <a href={api.exportMissionUrl(mission.meta.id!, 'apg')} download>
            <Download aria-hidden />
            Export .apg
          </a>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <a href={api.exportMissionUrl(mission.meta.id!)} download>
            Export as YAML
          </a>
        </Button>
        {confirmDelete ? (
          <div className="space-y-2 rounded-md border border-nogo/50 p-3">
            <p className="text-sm">Delete “{mission.meta.name}”? This can't be undone.</p>
            <div className="flex gap-2">
              <Button
                className="border-nogo text-nogo"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(mission.meta.id!, {
                    onSuccess: () => {
                      setConfirmDelete(false)
                      select(null)
                    },
                  })
                }
              >
                Delete mission
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                Keep it
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
            <Trash2 aria-hidden />
            Delete
          </Button>
        )}
        <ProblemNotice error={remove.error} />
      </div>
    </div>
  )
}
