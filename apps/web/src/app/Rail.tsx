import { motion } from 'motion/react'
import { Fragment } from 'react'
import { NavLink } from 'react-router'
import { Tooltip } from '@/components/ui/tooltip'
import { RAIL_GROUP_LABEL, SECTIONS, type RailGroup, type SectionDef } from './sections'

const MAIN_GROUPS: RailGroup[] = ['setup', 'analysis', 'field', 'hardware']

/** The 64 px icon rail. It never moves; the active indicator slides between items. */
export function Rail() {
  return (
    <nav aria-label="Sections" className="flex w-16 shrink-0 flex-col items-center border-r border-border bg-surface py-3">
      <ApogeeMark />
      <div className="mt-4 flex flex-col items-center gap-1">
        {MAIN_GROUPS.map((group, i) => (
          <Fragment key={group}>
            {i > 0 && <div role="separator" className="my-2 h-px w-8 bg-border" />}
            {SECTIONS.filter((s) => s.group === group).map((s) => (
              <RailItem key={s.id} section={s} />
            ))}
          </Fragment>
        ))}
      </div>
      <div className="mt-auto flex flex-col items-center gap-1">
        {SECTIONS.filter((s) => s.group === 'footer').map((s) => (
          <RailItem key={s.id} section={s} />
        ))}
      </div>
    </nav>
  )
}

function RailItem({ section }: { section: SectionDef }) {
  const Icon = section.icon
  const groupLabel = RAIL_GROUP_LABEL[section.group]
  return (
    <Tooltip
      side="right"
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
        className="relative flex size-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground aria-[current=page]:text-primary aria-[current=page]:hover:bg-transparent aria-[current=page]:hover:text-primary"
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
                <span className="absolute top-2 bottom-2 -left-3 w-[3px] rounded-r bg-primary" />
              </motion.span>
            )}
            <Icon className="relative size-5" strokeWidth={1.75} aria-hidden />
          </>
        )}
      </NavLink>
    </Tooltip>
  )
}

/** A ballistic arc with its apex marked. */
function ApogeeMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-8 text-foreground" role="img" aria-label="Apogee">
      <path d="M4 27 Q16 -3 28 27" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="16" cy="12" r="2.75" className="fill-primary" />
    </svg>
  )
}
