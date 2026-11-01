import { useQuery } from '@tanstack/react-query'
import { Moon, Sun, WifiOff } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { Tooltip } from '@/components/ui/tooltip'
import { api } from '@/lib/api'
import { useDraftValidation } from '@/lib/mission/validation'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** Bottom of the centre column: job, mission state, connectivity, versions. */
export function StatusBar() {
  return (
    <footer className="flex h-8 shrink-0 items-center gap-5 border-t border-border bg-surface px-3 text-xs text-muted-foreground">
      <span>No job running</span>
      <MissionState />
      <span className="ml-auto" />
      <Connectivity />
      <Versions />
      <ThemeToggle />
    </footer>
  )
}

function MissionState() {
  const hasDraft = useMissionStore((s) => s.draft !== null)
  const isDirty = useMissionStore((s) => s.isDirty)
  if (!hasDraft) return <span>No mission open</span>
  return (
    <>
      <span className="flex items-center gap-1.5">
        <span className={cn('size-2 rounded-full', isDirty ? 'bg-caution' : 'bg-go')} aria-hidden />
        {isDirty ? 'Unsaved changes' : 'Saved'}
      </span>
      <IssueCount />
    </>
  )
}

function IssueCount() {
  const { data } = useDraftValidation()
  if (!data) return null
  const issues = data.issues ?? []
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  if (errors === 0 && warnings === 0) return <span>No problems</span>
  const parts = [
    errors && `${errors} ${errors === 1 ? 'error' : 'errors'}`,
    warnings && `${warnings} ${warnings === 1 ? 'warning' : 'warnings'}`,
  ].filter(Boolean)
  return <span className={errors ? 'text-nogo' : 'text-caution'}>{parts.join(', ')}</span>
}

function subscribeOnline(cb: () => void) {
  window.addEventListener('online', cb)
  window.addEventListener('offline', cb)
  return () => {
    window.removeEventListener('online', cb)
    window.removeEventListener('offline', cb)
  }
}

function Connectivity() {
  const online = useSyncExternalStore(subscribeOnline, () => navigator.onLine)
  if (online) return null
  return (
    <Tooltip content="No network. Simulations still run; weather fetches use the cache.">
      <span className="flex items-center gap-1.5 font-medium text-caution">
        <WifiOff className="size-3.5" aria-hidden />
        Offline
      </span>
    </Tooltip>
  )
}

function Versions() {
  const { data, isError } = useQuery({ queryKey: ['system', 'info'], queryFn: api.systemInfo })
  if (isError) return <span className="text-nogo">API not reachable</span>
  if (!data) return <span>Connecting to API</span>
  return (
    <Tooltip content={`simcore ${data.simcore_version} · ${data.git_sha.slice(0, 8)} · ${data.worker_count} workers`}>
      <span>RocketPy {data.rocketpy_version}</span>
    </Tooltip>
  )
}

function ThemeToggle() {
  const theme = usePrefs((s) => s.theme)
  const setTheme = usePrefs((s) => s.setTheme)
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={next === 'light' ? 'Switch to high-contrast light theme' : 'Switch to dark theme'}
      className="rounded p-1 hover:bg-surface-2 hover:text-foreground"
    >
      {theme === 'dark' ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
    </button>
  )
}
