import { BookOpen, CircleHelp, FilePlus2, FolderOpen, Rocket, Upload, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import logoUrl from '@/assets/apogee-logo.svg'
import { ProblemNotice } from '@/components/ProblemNotice'
import { useCompact } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'
import { useCreateMission, useImportMission, useMissionList } from '@/sections/missions/queries'
import { useMissionStore } from '@/stores/mission'
import { useTour } from '@/stores/tour'
import { NavDrawer } from './NavDrawer'
import { StatusBar } from './StatusBar'

const RECENT = 4
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

/** The launch screen: the wordmark, then the few things people open the app to do. */
export function Home() {
  const compact = useCompact()
  const navigate = useNavigate()
  const missions = useMissionList()
  const create = useCreateMission()
  const importMission = useImportMission()
  const openName = useMissionStore((s) => s.draft?.meta.name)
  const fileInput = useRef<HTMLInputElement>(null)
  const startTour = useTour((s) => s.start)

  // New and imported missions land selected in Missions, where opening one checks for unsaved changes.
  const showMission = (id: string) => navigate(`/missions?id=${id}`)
  const recent = [...(missions.data ?? [])]
    .sort((a, b) => b.updated_utc.localeCompare(a.updated_utc))
    .slice(0, RECENT)

  return (
    <div className="flex h-full flex-col">
      {compact && (
        <header className="flex h-12 shrink-0 items-center border-b border-border px-3">
          <NavDrawer />
        </header>
      )}
      <motion.div
        className="min-h-0 flex-1 overflow-auto"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center gap-10 px-4 py-10 sm:px-6">
          <div className="flex flex-col items-center gap-4 text-center">
            <h1 className="w-full max-w-xl">
              <img src={logoUrl} alt="Apogee" className="w-full" />
            </h1>
            <p className="font-display text-lg text-muted-foreground sm:text-xl">
              Flight simulation and analysis for high-power rocketry.
            </p>
          </div>

          <ProblemNotice error={create.error ?? importMission.error} />

          <div className="grid gap-3 sm:grid-cols-2">
            <Action
              icon={CircleHelp}
              title="New to Apogee?"
              detail="Take the tour, with Calisto flying"
              onClick={startTour}
              variant="brand"
            />
            {/* Always six tiles: what's open, or the way to open something. */}
            {openName !== undefined ? (
              <Action
                icon={FolderOpen}
                title="Continue editing"
                detail={openName}
                onClick={() => navigate('/site')}
                primary
              />
            ) : (
              <Action
                icon={FolderOpen}
                title="Open a mission"
                detail="Every mission saved here"
                onClick={() => navigate('/missions')}
              />
            )}
            <Action
              icon={FilePlus2}
              title="New mission"
              detail="Start from an empty mission config."
              disabled={create.isPending}
              onClick={() => create.mutate('Untitled mission', { onSuccess: (doc) => showMission(doc.mission.meta.id!) })}
              primary={openName === undefined}
            />
            <Action
              icon={Upload}
              title="Import mission file"
              detail=".apg bundle or mission.yaml"
              disabled={importMission.isPending}
              onClick={() => fileInput.current?.click()}
            />
            <Action
              icon={Rocket}
              title="Import from OpenRocket"
              detail="Bring in an .ork design"
              onClick={() => navigate('/rocket')}
            />
            <Action
              icon={BookOpen}
              title="First flight guide"
              detail="From an empty mission to a simulated flight"
              onClick={() => navigate('/docs/guides/first-flight')}
            />
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".apg,.yaml,.yml,.json,.zip"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) importMission.mutate(file, { onSuccess: (doc) => showMission(doc.mission.meta.id!) })
              e.target.value = ''
            }}
          />

          {recent.length > 0 && (
            <section aria-labelledby="home-recent" className="space-y-2">
              <div className="flex items-baseline justify-between">
                <h2 id="home-recent" className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Recent missions
                </h2>
                <Link to="/missions" className="text-sm text-primary underline-offset-4 hover:underline">
                  All missions
                </Link>
              </div>
              <ul className="divide-y divide-border rounded-md border border-border bg-surface">
                {recent.map((m) => (
                  <li key={m.id}>
                    <Link
                      to={`/missions?id=${m.id}`}
                      className="flex items-baseline justify-between gap-4 px-4 py-2.5 hover:bg-surface-2"
                    >
                      <span className="truncate">{m.name}</span>
                      <span className="shrink-0 text-sm text-muted-foreground">
                        {dateFormat.format(new Date(m.updated_utc))}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </motion.div>
      <StatusBar />
    </div>
  )
}

function Action({
  icon: Icon,
  title,
  detail,
  onClick,
  disabled,
  primary = false,
  variant,
}: {
  icon: LucideIcon
  title: ReactNode
  detail: ReactNode
  onClick: () => void
  disabled?: boolean
  primary?: boolean
  /** brand: the gradient fill, for the one action that should stand out. */
  variant?: 'brand'
}) {
  const brand = variant === 'brand'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex items-start gap-3 rounded-md border p-4 text-left transition disabled:opacity-50',
        brand
          ? 'border-transparent bg-brand text-primary-foreground hover:brightness-110'
          : primary
            ? 'border-primary bg-surface hover:bg-primary/10'
            : 'border-border bg-surface hover:border-muted-foreground',
      )}
    >
      <Icon className={cn('mt-0.5 size-5 shrink-0', !brand && 'text-primary')} strokeWidth={1.75} aria-hidden />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="font-display text-lg leading-tight font-semibold">{title}</span>
        <span className={cn('truncate text-sm', brand ? 'opacity-90' : 'text-muted-foreground')}>{detail}</span>
      </span>
    </button>
  )
}
