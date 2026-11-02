import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { motion } from 'motion/react'
import { lazy, Suspense, useMemo, useState, type ComponentType, type LazyExoticComponent, type ReactNode } from 'react'
import { Group, Panel, Separator, useDefaultLayout, usePanelRef } from 'react-resizable-panels'
import { Button } from '@/components/ui/button'
import { useCompact } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'
import { MissionBar } from './MissionBar'
import { NavDrawer } from './NavDrawer'
import { SectionLayoutContext, type SectionLayout } from './sectionLayout'
import { SECTION_BY_ID, type SectionDef } from './sections'
import { StatusBar } from './StatusBar'

type Lazy = LazyExoticComponent<ComponentType>
const lazyCache = new Map<string, { Centre: Lazy; Pane: Lazy }>()

/** Sections are code-split so MapLibre, three.js and friends stay off first paint. */
function lazySection(def: SectionDef) {
  let entry = lazyCache.get(def.id)
  if (!entry) {
    entry = {
      Centre: lazy(() => def.load().then((m) => ({ default: m.Centre }))),
      Pane: lazy(() => def.load().then((m) => ({ default: m.Pane ?? (() => null) }))),
    }
    lazyCache.set(def.id, entry)
  }
  return entry
}

export function SectionView({ id }: { id: string }) {
  const def = SECTION_BY_ID[id]
  return useCompact() ? <CompactSectionView def={def} /> : <WideSectionView def={def} />
}

function SectionContent({ Centre }: { Centre: Lazy }) {
  return (
    <motion.div
      className="relative min-h-0 flex-1 overflow-auto"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15 }}
    >
      <Suspense fallback={null}>
        <Centre />
      </Suspense>
    </motion.div>
  )
}

/**
 * Centre canvas plus the docked, resizable, collapsible right pane. Pane width
 * and collapsed state persist per section in localStorage.
 */
function WideSectionView({ def }: { def: SectionDef }) {
  const id = def.id
  const { Centre, Pane } = lazySection(def)
  const paneRef = usePanelRef()
  const [paneOpen, setPaneOpen] = useState(true)
  const layout = useDefaultLayout({
    id: `apogee.layout.${id}`,
    panelIds: def.hasPane ? ['centre', 'pane'] : ['centre'],
    storage: localStorage,
  })

  const togglePane = () => {
    const pane = paneRef.current
    if (!pane) return
    if (pane.isCollapsed()) pane.expand()
    else pane.collapse()
  }
  const sectionLayout = useMemo<SectionLayout>(
    () => ({ showPane: () => paneRef.current?.expand(), showCentre: () => {} }),
    [paneRef],
  )

  return (
    <SectionLayoutContext value={sectionLayout}>
    <Group orientation="horizontal" className="h-full" {...layout}>
      <Panel id="centre" minSize="40%">
        <div className="flex h-full flex-col">
          <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4">
            <h1 className="font-display text-xl font-semibold tracking-wide">{def.label}</h1>
            <div className="ml-auto flex min-w-0 items-center gap-2">
              <MissionBar />
            {def.hasPane && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={togglePane}
                aria-label={paneOpen ? 'Hide editing pane' : 'Show editing pane'}
                aria-expanded={paneOpen}
              >
                {paneOpen ? <PanelRightClose /> : <PanelRightOpen />}
              </Button>
            )}
            </div>
          </header>
          <SectionContent Centre={Centre} />
          <StatusBar />
        </div>
      </Panel>
      {def.hasPane && (
        <>
          <Separator className="w-px bg-border transition-colors hover:bg-primary data-[separator-state=drag]:bg-primary" />
          <Panel
            id="pane"
            panelRef={paneRef}
            collapsible
            collapsedSize={0}
            defaultSize="400px"
            minSize="360px"
            maxSize="480px"
            onResize={(size) => setPaneOpen(size.inPixels > 0)}
          >
            <aside aria-label={`${def.label} settings`} className="h-full overflow-auto bg-surface">
              <Suspense fallback={null}>
                <Pane />
              </Suspense>
            </aside>
          </Panel>
        </>
      )}
    </Group>
    </SectionLayoutContext>
  )
}

/**
 * Phones and small tablets: no rail and no docked pane. The sections menu sits
 * in the header, and the centre and pane are tabs. Both stay mounted, so a map
 * or a half-typed field survives switching between them.
 */
function CompactSectionView({ def }: { def: SectionDef }) {
  const { Centre, Pane } = lazySection(def)
  const [tab, setTab] = useState<'centre' | 'pane'>('centre')
  const sectionLayout = useMemo<SectionLayout>(
    () => ({ showPane: () => setTab('pane'), showCentre: () => setTab('centre') }),
    [],
  )

  return (
    <SectionLayoutContext value={sectionLayout}>
      <div className="flex h-full flex-col">
        <header className="flex min-h-12 shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-border px-3 py-1.5">
          <NavDrawer />
          <h1 className="min-w-0 truncate font-display text-xl font-semibold tracking-wide">{def.label}</h1>
          <div className="ml-auto flex min-w-0 items-center">
            <MissionBar />
          </div>
        </header>
        {def.hasPane && (
          <div role="tablist" aria-label={def.label} className="flex shrink-0 border-b border-border bg-surface">
            <TabButton selected={tab === 'centre'} onSelect={() => setTab('centre')} controls="section-centre">
              {def.centreLabel ?? 'Overview'}
            </TabButton>
            <TabButton selected={tab === 'pane'} onSelect={() => setTab('pane')} controls="section-pane">
              {def.paneLabel ?? 'Settings'}
            </TabButton>
          </div>
        )}
        <div id="section-centre" role={def.hasPane ? 'tabpanel' : undefined} className={cn('flex min-h-0 flex-1 flex-col', tab !== 'centre' && 'hidden')}>
          <SectionContent Centre={Centre} />
        </div>
        {def.hasPane && (
          <aside
            id="section-pane"
            role="tabpanel"
            aria-label={`${def.label} settings`}
            className={cn('min-h-0 flex-1 overflow-auto bg-surface', tab !== 'pane' && 'hidden')}
          >
            <Suspense fallback={null}>
              <Pane />
            </Suspense>
          </aside>
        )}
        <StatusBar />
      </div>
    </SectionLayoutContext>
  )
}

function TabButton({
  selected,
  onSelect,
  controls,
  children,
}: {
  selected: boolean
  onSelect: () => void
  controls: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      aria-controls={controls}
      onClick={onSelect}
      className={cn(
        'relative h-10 flex-1 text-sm font-medium transition-colors',
        selected ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
      {selected && <span className="absolute inset-x-4 bottom-0 h-0.5 rounded-t bg-brand" />}
    </button>
  )
}
