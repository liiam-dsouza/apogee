import { ChevronLeft, ChevronRight, CircleHelp } from 'lucide-react'
import { motion } from 'motion/react'
import { Fragment, type ReactElement, type ReactNode } from 'react'
import { NavLink } from 'react-router'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { usePrefs } from '@/stores/prefs'
import { useTour } from '@/stores/tour'
import { RAIL_GROUP_LABEL, SECTIONS, type RailGroup, type SectionDef } from './sections'

const MAIN_GROUPS: RailGroup[] = ['setup', 'analysis', 'field', 'hardware']

/**
 * The icon rail: 64 px collapsed, or wide with each section's name when expanded.
 * Items never move vertically; the active indicator slides between them.
 */
export function Rail() {
  const expanded = usePrefs((s) => s.railExpanded)
  const setExpanded = usePrefs((s) => s.setRailExpanded)
  return (
    <div className="relative h-full shrink-0">
      {/* Compacts on short screens, and scrolls as a last resort, so no section is ever out of reach. */}
      <nav
        aria-label="Sections"
        className={cn(
          'flex h-full shrink-0 flex-col overflow-x-hidden overflow-y-auto border-r border-border bg-surface py-3 scrollbar-thin transition-[width] duration-200 ease-out shorter:py-2 motion-reduce:transition-none',
          expanded ? 'w-52 items-stretch px-3' : 'w-16 items-center',
        )}
      >
        <ApogeeMark expanded={expanded} />
        <div data-tour="rail-sections" className="mt-4 flex flex-col gap-1 short:mt-2 short:gap-0.5">
          {MAIN_GROUPS.map((group, i) => (
            <Fragment key={group}>
              {i > 0 && <div role="separator" className="my-2 h-px w-8 shrink-0 self-center bg-border short:my-1" />}
              {SECTIONS.filter((s) => s.group === group).map((s) => (
                <RailItem key={s.id} section={s} expanded={expanded} />
              ))}
            </Fragment>
          ))}
        </div>
        <div data-tour="rail-footer" className="mt-auto flex flex-col gap-1 pt-2 short:gap-0.5">
          {SECTIONS.filter((s) => s.group === 'footer').map((s) => (
            <RailItem key={s.id} section={s} expanded={expanded} />
          ))}
          <HelpItem expanded={expanded} />
        </div>
      </nav>
      {/* On the rail's edge, level with the section headers, so it costs the rail no height. */}
      <Tooltip side="right" content={expanded ? 'Collapse sections' : 'Expand sections'}>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? 'Collapse sections' : 'Expand sections'}
          aria-expanded={expanded}
          className="absolute top-3 -right-3 z-10 flex size-6 items-center justify-center rounded-full border border-border bg-surface text-muted-foreground shadow-sm transition-colors hover:border-muted-foreground hover:text-foreground"
        >
          {expanded ? <ChevronLeft className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        </button>
      </Tooltip>
    </div>
  )
}

/** Square icon buttons when collapsed; full-width rows with a label when expanded. */
function itemClass(expanded: boolean) {
  return cn(
    'relative flex shrink-0 items-center rounded-md transition-colors',
    expanded
      ? 'h-10 w-full gap-3 px-2.5 short:h-9 shorter:h-8'
      : 'size-10 justify-center short:size-9 shorter:size-8',
  )
}

/** Names the icon on hover, only while the rail is too narrow to show it. */
function CollapsedTooltip({
  expanded,
  content,
  children,
}: {
  expanded: boolean
  content: ReactNode
  children: ReactElement
}) {
  if (expanded) return children
  return (
    <Tooltip side="right" content={content}>
      {children}
    </Tooltip>
  )
}

function RailItem({ section, expanded }: { section: SectionDef; expanded: boolean }) {
  const Icon = section.icon
  const groupLabel = RAIL_GROUP_LABEL[section.group]
  return (
    <CollapsedTooltip
      expanded={expanded}
      content={
        <span className="flex flex-col">
          <span>{section.label}</span>
          {groupLabel && <span className="text-xs text-muted-foreground">{groupLabel}</span>}
        </span>
      }
    >
      {/*
        className must be a string here: Tooltip's trigger is a Radix Slot,
        which merges className by string-joining, so a NavLink className
        function would be stringified. Active styling keys off the
        aria-current="page" that NavLink sets instead.
      */}
      <NavLink
        to={`/${section.id}`}
        aria-label={section.label}
        className={cn(
          itemClass(expanded),
          'text-muted-foreground hover:bg-surface-2 hover:text-foreground aria-[current=page]:text-primary aria-[current=page]:hover:bg-transparent aria-[current=page]:hover:text-primary',
        )}
      >
        {({ isActive }) => (
          <>
            {isActive && (
              <motion.span
                layoutId="rail-indicator"
                // Decorative: must never take the pointer from the buttons around it.
                className="pointer-events-none absolute inset-0 rounded-md bg-primary/15"
                transition={{ type: 'spring', stiffness: 500, damping: 38 }}
              >
                <span className="absolute top-2 bottom-2 -left-3 w-0.75 rounded-r bg-brand" />
              </motion.span>
            )}
            <Icon className="relative size-5 shrink-0" strokeWidth={1.75} aria-hidden />
            {expanded && <span className="relative truncate text-sm">{section.label}</span>}
          </>
        )}
      </NavLink>
    </CollapsedTooltip>
  )
}

/** Starts the guided tour. A button, not a section: it has no page of its own. */
function HelpItem({ expanded }: { expanded: boolean }) {
  const start = useTour((s) => s.start)
  return (
    <CollapsedTooltip expanded={expanded} content="Help: take the tour">
      <button
        type="button"
        onClick={start}
        aria-label="Help: take the tour"
        className={cn(itemClass(expanded), 'text-muted-foreground hover:bg-surface-2 hover:text-foreground')}
      >
        <CircleHelp className="relative size-5 shrink-0" strokeWidth={1.75} aria-hidden />
        {expanded && <span className="relative truncate text-sm">Help</span>}
      </button>
    </CollapsedTooltip>
  )
}

/** The app mark; opens the home screen. */
function ApogeeMark({ expanded }: { expanded: boolean }) {
  return (
    <CollapsedTooltip expanded={expanded} content="Home">
      <NavLink
        to="/"
        end
        aria-label="Home"
        className={cn(
          'flex shrink-0 items-center gap-3 rounded-md p-2 transition-colors hover:bg-surface-2',
          expanded ? 'my-2' : 'm-2',
        )}
      >
        <img src="/favicon.svg" alt="" className="size-8 shrink-0" />
        {expanded && <span className="font-display text-xl font-semibold tracking-wide">Apogee</span>}
      </NavLink>
    </CollapsedTooltip>
  )
}
