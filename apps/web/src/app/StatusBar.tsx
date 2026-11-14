import { useQuery } from '@tanstack/react-query'
import { CircleAlert, Heart, Moon, Sun, TriangleAlert, WifiOff } from 'lucide-react'
import { Popover } from 'radix-ui'
import { useEffect, useSyncExternalStore } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { api } from '@/lib/api'
import { fixLink } from '@/lib/mission/fixLink'
import { useDraftValidation } from '@/lib/mission/validation'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { type Theme, usePrefs } from '@/stores/prefs'

/** Bottom of the centre column: job, mission state, connectivity, versions. */
export function StatusBar() {
  return (
    <footer data-tour="status-bar" className="flex h-8 shrink-0 items-center gap-5 overflow-hidden border-t border-border bg-surface px-3 text-xs whitespace-nowrap text-muted-foreground max-sm:gap-3">
      <span className="max-sm:hidden">No job running</span>
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
  const missionId = useMissionStore((s) => s.draft?.meta.id)
  if (!data) return null
  const issues = data.issues ?? []
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  if (errors === 0 && warnings === 0) return <span>No problems</span>
  const parts = [
    errors && `${errors} ${errors === 1 ? 'error' : 'errors'}`,
    warnings && `${warnings} ${warnings === 1 ? 'warning' : 'warnings'}`,
  ].filter(Boolean)
  // Errors first: they're what blocks a run.
  const sorted = [...issues].sort((a, b) => Number(b.severity === 'error') - Number(a.severity === 'error'))
  return (
    <Popover.Root>
      <Popover.Trigger
        className={cn('-mx-1 rounded px-1 hover:bg-surface-2', errors ? 'text-nogo' : 'text-caution')}
      >
        {parts.join(', ')}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="start"
          sideOffset={8}
          collisionPadding={8}
          className="z-50 w-[28rem] max-w-[calc(100vw-1rem)] rounded-md border border-border bg-surface-2 p-1.5 text-sm text-foreground shadow-lg"
        >
          <ul className="max-h-80 overflow-y-auto">
            {sorted.map((i) => {
              const fix = fixLink(i.path, missionId)
              return (
                <li key={`${i.path}:${i.code}`} className="flex items-start gap-2 rounded px-1.5 py-1.5">
                  {i.severity === 'error' ? (
                    <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-nogo" aria-label="Error" />
                  ) : (
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-caution" aria-label="Warning" />
                  )}
                  <span className="min-w-0 flex-1">
                    <code className="block text-xs break-all text-muted-foreground">{i.path}</code>
                    {i.message}
                  </span>
                  {fix && (
                    <Popover.Close asChild>
                      <Button asChild size="sm" className="shrink-0">
                        {/* Client-side navigation: a full page load would drop the unsaved draft. */}
                        <Link to={fix.href} title={fix.label}>
                          Fix problem
                        </Link>
                      </Button>
                    </Popover.Close>
                  )}
                </li>
              )
            })}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
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
    <Tooltip content="No network. Simulations still run; weather fetches use the cache." tappable>
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
      <span className="max-sm:hidden">RocketPy {data.rocketpy_version}</span>
    </Tooltip>
  )
}

const NEXT_THEME: Record<Theme, Theme> = { dark: 'light', light: 'pink', pink: 'dark' }
const THEME_LABEL: Record<Theme, string> = {
  dark: 'Switch to dark theme',
  light: 'Switch to high-contrast light theme',
  pink: 'Switch to pink theme',
}

// Created lazily, so the song isn't fetched until someone finds the heart.
let song: HTMLAudioElement | null = null

/** Cycles dark → light → pink. Pink plays the song on a loop until the theme changes. */
function ThemeToggle() {
  const theme = usePrefs((s) => s.theme)
  const setTheme = usePrefs((s) => s.setTheme)
  const next = NEXT_THEME[theme]

  // Stops the song however the theme leaves pink (here or in Settings).
  useEffect(() => {
    if (theme === 'pink' || !song) return
    song.pause()
    song.currentTime = 0
  }, [theme])

  return (
    <button
      type="button"
      onClick={() => {
        // Play inside the click: browsers block audio that doesn't start from a user gesture.
        if (next === 'pink') {
          song ??= Object.assign(new Audio('/assets/sexy.mp3'), { loop: true })
          void song.play().catch(() => {})
        }
        setTheme(next)
      }}
      aria-label={THEME_LABEL[next]}
      className="-m-1 rounded p-2 hover:bg-surface-2 hover:text-foreground"
    >
      {next === 'light' && <Sun className="size-3.5" />}
      {next === 'pink' && <Heart className="size-3.5 fill-current" />}
      {next === 'dark' && <Moon className="size-3.5" />}
    </button>
  )
}
