import { ArrowRight, LoaderCircle } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { useSaveMission } from '@/lib/mission/save'
import { useMissionStore } from '@/stores/mission'
import { cn } from '@/lib/utils'
import { useTour } from '@/stores/tour'
import { startDemo } from './demo'
import { TOUR_STEPS } from './steps'

interface Box {
  x: number
  y: number
  w: number
  h: number
}

/** Room around the cut-out, and between it (or the screen edge) and the card. */
const PAD = 6
const GAP = 16

/** The visible element a step points at, padded, or null for a centred card. */
function measure(target: string | undefined): Box | null {
  if (!target) return null
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)) {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0) {
      const x = Math.max(r.left - PAD, 0)
      const y = Math.max(r.top - PAD, 0)
      return {
        x,
        y,
        w: Math.min(r.right + PAD, window.innerWidth) - x,
        h: Math.min(r.bottom + PAD, window.innerHeight) - y,
      }
    }
  }
  return null
}

const same = (a: Box | null, b: Box | null) =>
  a === b || (a !== null && b !== null && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h)

/** Beside the hole if there is room (right, left, below, above), else inside its lower right. */
function place(hole: Box | null, card: { w: number; h: number }): { left: number; top: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const clamp = (v: number, size: number, max: number) => Math.min(Math.max(v, GAP), max - size - GAP)
  if (!hole) return { left: (vw - card.w) / 2, top: (vh - card.h) / 2 }
  const midY = clamp(hole.y + hole.h / 2 - card.h / 2, card.h, vh)
  const midX = clamp(hole.x + hole.w / 2 - card.w / 2, card.w, vw)
  if (hole.x + hole.w + GAP + card.w + GAP <= vw) return { left: hole.x + hole.w + GAP, top: midY }
  if (hole.x - GAP - card.w >= GAP) return { left: hole.x - GAP - card.w, top: midY }
  if (hole.y + hole.h + GAP + card.h + GAP <= vh) return { left: midX, top: hole.y + hole.h + GAP }
  if (hole.y - GAP - card.h >= GAP) return { left: midX, top: hole.y - GAP - card.h }
  return {
    left: clamp(hole.x + hole.w - card.w - 2 * GAP, card.w, vw),
    top: clamp(hole.y + hole.h - card.h - 2 * GAP, card.h, vh),
  }
}

/**
 * The guided tour: the app dimmed, the part a step explains cut out of the dimming,
 * and a card beside it. Started from Help in the rail.
 */
export function Tour() {
  const active = useTour((s) => s.active)
  return active ? <TourOverlay /> : null
}

function TourOverlay() {
  const { step, go, stop } = useTour()
  const current = TOUR_STEPS[step]
  const last = step === TOUR_STEPS.length - 1
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [hole, setHole] = useState<Box | null>(null)
  const [cardSize, setCardSize] = useState({ w: 352, h: 240 })
  const card = useRef<HTMLDivElement>(null)
  const next = useRef<HTMLButtonElement>(null)
  const maskId = useId()
  const titleId = useId()

  // Open and fly the example once, as the tour starts.
  useEffect(() => {
    if (useTour.getState().demo === 'idle') void startDemo()
  }, [])

  // Open the step's section; its content loads lazily, so the hole is found below.
  useEffect(() => {
    if (current.route && !pathname.startsWith(current.route)) navigate(current.route)
  }, [current.route, pathname, navigate])

  // Follow the target every frame: sections load, panes resize, the window changes.
  useEffect(() => {
    let frame = 0
    let prev: Box | null = null
    const tick = () => {
      const box = measure(current.target)
      if (!same(box, prev)) {
        prev = box
        setHole(box)
      }
      frame = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(frame)
  }, [current.target])

  useLayoutEffect(() => {
    const el = card.current
    if (el) setCardSize({ w: el.offsetWidth, h: el.offsetHeight })
  }, [step, hole])

  useEffect(() => next.current?.focus(), [step])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') stop()
      else if (e.key === 'ArrowRight' && last) stop()
      else if (e.key === 'ArrowRight') go(step + 1)
      else if (e.key === 'ArrowLeft' && step > 0) go(step - 1)
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, last, go, stop])

  const pos = place(hole, cardSize)
  // With nothing to point at, the hole closes to a point in the middle.
  const h = hole ?? { x: window.innerWidth / 2, y: window.innerHeight / 2, w: 0, h: 0 }
  const spring = { type: 'spring', stiffness: 380, damping: 36 } as const

  return createPortal(
    <div className="fixed inset-0 z-[100]">
      {/* The dimming takes every click, so the app can't change under the tour. */}
      <svg className="absolute inset-0 size-full" aria-hidden>
        <defs>
          <mask id={maskId}>
            <rect width="100%" height="100%" fill="white" />
            <motion.rect
              initial={false}
              animate={{ x: h.x, y: h.y, width: h.w, height: h.h }}
              transition={spring}
              rx={8}
              fill="black"
            />
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="black" fillOpacity={0.62} mask={`url(#${maskId})`} />
      </svg>
      {hole && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute rounded-lg ring-2 ring-primary"
          initial={false}
          animate={{ left: hole.x, top: hole.y, width: hole.w, height: hole.h }}
          transition={spring}
        />
      )}
      <motion.div
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="absolute w-[22rem] max-w-[calc(100vw-2rem)] space-y-3 rounded-lg border border-border bg-surface p-4 shadow-2xl"
        initial={false}
        animate={{ left: pos.left, top: pos.top }}
        transition={spring}
      >
        <p className="text-xs text-muted-foreground tabular-nums">
          {step + 1} of {TOUR_STEPS.length}
        </p>
        <h2 id={titleId} className="font-display text-xl font-semibold">
          {current.title}
        </h2>
        <p className="text-sm leading-relaxed">{current.body}</p>
        <DemoStatusLine />
        {current.docs && (
          <Link
            to={current.docs}
            onClick={stop}
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
          >
            Read more in the docs <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        )}
        <div className="flex items-center gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={stop}>
            Skip
          </Button>
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" size="sm" disabled={step === 0} onClick={() => go(step - 1)}>
              Previous
            </Button>
            <Button ref={next} variant="primary" size="sm" onClick={() => (last ? stop() : go(step + 1))}>
              {last ? 'Finish' : 'Next'}
            </Button>
          </div>
        </div>
      </motion.div>
    </div>,
    document.body,
  )
}

/** What the tour's example is doing, and the choice to make if unsaved changes are in the way. */
function DemoStatusLine() {
  const demo = useTour((s) => s.demo)
  const error = useTour((s) => s.demoError)
  const setDemo = useTour((s) => s.setDemo)
  const openName = useMissionStore((s) => s.draft?.meta.name)
  const save = useSaveMission()

  if (demo === 'conflict') {
    return (
      <div className="space-y-2 rounded-md border border-caution/50 p-3 text-sm">
        <p>
          The tour opens its own copy of Calisto to show the app working, but <strong>{openName}</strong> has unsaved
          changes.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={save.isPending}
            onClick={() => save.mutate(undefined, { onSuccess: () => void startDemo() })}
          >
            {save.isPending ? 'Saving' : 'Save and continue'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDemo('skipped')}>
            Tour without the example
          </Button>
        </div>
        {save.error && <p className="text-nogo">Couldn't save: {save.error.message}</p>}
      </div>
    )
  }
  const busy = demo === 'loading' || demo === 'flying'
  const text = {
    idle: null,
    loading: 'Opening the Calisto example',
    flying: 'Flying Calisto',
    ready: 'Calisto is open and flown; its campaign keeps running in the background.',
    skipped: null,
    failed: `Couldn't open the example (${error ?? 'unknown error'}). The tour carries on without it.`,
  }[demo]
  if (!text) return null
  return (
    <p className={cn('flex items-center gap-1.5 text-xs', demo === 'failed' ? 'text-caution' : 'text-muted-foreground')}>
      {busy && <LoaderCircle className="size-3.5 animate-spin" aria-hidden />}
      {text}
    </p>
  )
}
