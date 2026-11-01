import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { motion } from 'motion/react'
import { lazy, Suspense, useState, type ComponentType, type LazyExoticComponent } from 'react'
import { Group, Panel, Separator, useDefaultLayout, usePanelRef } from 'react-resizable-panels'
import { Button } from '@/components/ui/button'
import { MissionBar } from './MissionBar'
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

/**
 * Centre canvas plus the docked, resizable, collapsible right pane. Pane width
 * and collapsed state persist per section in localStorage.
 */
export function SectionView({ id }: { id: string }) {
  const def = SECTION_BY_ID[id]
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

  return (
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
  )
}
