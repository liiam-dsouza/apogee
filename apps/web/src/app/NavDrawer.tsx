import { Menu, X } from 'lucide-react'
import { Dialog } from 'radix-ui'
import { Fragment, useState } from 'react'
import { NavLink } from 'react-router'
import { Button } from '@/components/ui/button'
import { useMissionStore } from '@/stores/mission'
import { RAIL_GROUP_LABEL, SECTIONS, type RailGroup } from './sections'

const GROUPS: RailGroup[] = ['setup', 'analysis', 'field', 'hardware', 'footer']

/** The rail, for phones: a menu button that opens every section, labelled, in a drawer. */
export function NavDrawer() {
  const [open, setOpen] = useState(false)
  const missionName = useMissionStore((s) => s.draft?.meta.name)

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" size="icon" className="-ml-2 shrink-0" aria-label="Sections">
          <Menu className="size-5!" />
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-border bg-surface shadow-xl"
        >
          <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
            <img src="/favicon.svg" alt="" className="size-7" />
            <Dialog.Title className="font-display text-xl font-semibold tracking-wide">Apogee</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" className="-mr-2 ml-auto" aria-label="Close">
                <X className="size-5!" />
              </Button>
            </Dialog.Close>
          </div>
          {missionName !== undefined && (
            <p className="truncate border-b border-border px-4 py-2 text-sm text-muted-foreground">
              Open: <span className="text-foreground">{missionName}</span>
            </p>
          )}
          <nav aria-label="Sections" className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
            {GROUPS.map((group) => (
              <Fragment key={group}>
                {RAIL_GROUP_LABEL[group] ? (
                  <h2 className="px-3 pt-3 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    {RAIL_GROUP_LABEL[group]}
                  </h2>
                ) : (
                  <div role="separator" className="mx-3 my-2 h-px bg-border" />
                )}
                <ul>
                  {SECTIONS.filter((s) => s.group === group).map((s) => (
                    <li key={s.id}>
                      <NavLink
                        to={`/${s.id}`}
                        onClick={() => setOpen(false)}
                        className="flex h-11 items-center gap-3 rounded-md px-3 text-sm text-muted-foreground hover:bg-surface-2 hover:text-foreground aria-[current=page]:bg-primary/15 aria-[current=page]:text-primary"
                      >
                        <s.icon className="size-5 shrink-0" strokeWidth={1.75} aria-hidden />
                        {s.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </Fragment>
            ))}
          </nav>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
