import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark, Download, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { ProblemNotice } from '@/components/ProblemNotice'
import { Button } from '@/components/ui/button'
import { api, type Site, type SitePreset } from '@/lib/api'
import { useMissionStore } from '@/stores/mission'

const presetKeys = { all: ['site-presets'] as const }

function useSitePresets() {
  return useQuery({ queryKey: presetKeys.all, queryFn: api.listSitePresets })
}

/** Copies a preset into the draft. Undoable; the mission keeps no link to the preset. */
function applyPreset(preset: SitePreset) {
  useMissionStore.getState().edit((d) => {
    d.site = structuredClone(preset.site)
  })
}

/** For a mission with no site yet: start from a saved one. Renders nothing when there are none. */
export function UseSavedSite() {
  const presets = useSitePresets()
  if (!presets.data?.length) return null
  return (
    <section className="space-y-2 border-b border-border p-4">
      <h2 className="text-sm font-semibold">Use a saved site</h2>
      <div className="flex flex-wrap gap-2">
        {presets.data.map((p) => (
          <Button key={p.id} size="sm" onClick={() => applyPreset(p)}>
            <Bookmark /> {p.name}
          </Button>
        ))}
      </div>
    </section>
  )
}

/** Load a saved site over this mission's, or save this one for next time. */
export function SavedSites({ site }: { site: Site }) {
  const qc = useQueryClient()
  const presets = useSitePresets()
  const [name, setName] = useState('')
  const invalidate = () => qc.invalidateQueries({ queryKey: presetKeys.all })
  const trimmed = name.trim()
  const existing = presets.data?.find((p) => p.name === trimmed)

  const save = useMutation({
    mutationFn: () =>
      existing
        ? api.updateSitePreset(existing.id, { name: trimmed, site })
        : api.createSitePreset({ name: trimmed, site }),
    onSuccess: () => {
      setName('')
      return invalidate()
    },
  })
  const remove = useMutation({ mutationFn: api.deleteSitePreset, onSuccess: invalidate })

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Saved sites</h2>
      {presets.data?.map((p) => (
        <div key={p.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
          <span className="truncate text-sm">{p.name}</span>
          <span className="ml-auto flex items-center gap-1">
            <Button size="sm" onClick={() => applyPreset(p)}>
              <Download /> Load
            </Button>
            <Button size="sm" variant="ghost" aria-label={`Delete saved site ${p.name}`} disabled={remove.isPending}
              onClick={() => remove.mutate(p.id)}>
              <Trash2 />
            </Button>
          </span>
        </div>
      ))}
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (trimmed) save.mutate()
        }}
      >
        <label className="flex-1 space-y-1 text-sm">
          <span>Save this site as</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Club launch field"
            className="h-9 w-full rounded-md border border-border bg-background px-3" />
        </label>
        <Button type="submit" disabled={!trimmed || save.isPending}>
          <Bookmark /> {existing ? 'Replace' : 'Save'}
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        Loading a saved site copies it into this mission. Changing a saved site later doesn't change missions that
        already use it.
      </p>
      <ProblemNotice error={presets.error ?? save.error ?? remove.error} />
    </section>
  )
}
