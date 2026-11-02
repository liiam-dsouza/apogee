import { Line, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useQuery } from '@tanstack/react-query'
import { Pause, Play, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useRef, type ComponentRef, type RefObject } from 'react'
import { Vector3 } from 'three'
import { Link } from 'react-router'
import { create } from 'zustand'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type FlightPath } from '@/lib/api'
import { formatSI } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

type Preset = '3d' | 'side' | 'top'

/** Playback and camera, shared by the canvas and the pane. */
const useView = create<{
  t: number
  playing: boolean
  preset: Preset
  presetNonce: number
  setT: (t: number) => void
  setPlaying: (p: boolean) => void
  setPreset: (p: Preset) => void
}>()((set) => ({
  t: 0,
  playing: false,
  preset: '3d',
  presetNonce: 0,
  setT: (t) => set({ t }),
  setPlaying: (playing) => set({ playing }),
  setPreset: (preset) => set((s) => ({ preset, presetNonce: s.presetNonce + 1 })),
}))

/** The open mission's own flight, if it has been run: never a stale one. */
function useFlight() {
  const draft = useMissionStore((s) => s.draft)
  const lookup = useQuery({
    queryKey: ['flight-lookup', draft],
    queryFn: () => api.lookupFlight(draft!),
    enabled: Boolean(draft?.rocket && draft.motor && draft.site),
  })
  const id = lookup.data?.available ? lookup.data.result_id : undefined
  const path = useQuery({
    queryKey: ['results', id, 'path'],
    queryFn: () => api.getPath(id!),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
  const result = useQuery({
    queryKey: ['results', id],
    queryFn: () => api.getResult(id!),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
  return { lookup, path, result }
}

/** Index of the last sample at or before t. */
function indexAt(ts: number[], t: number): number {
  let lo = 0
  let hi = ts.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (ts[mid] <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}

/** Linear interpolation of the path at time t. */
function sampleAt(p: FlightPath, t: number) {
  const i = indexAt(p.t, t)
  const j = Math.min(i + 1, p.t.length - 1)
  const f = j === i ? 0 : Math.max(0, Math.min(1, (t - p.t[i]) / (p.t[j] - p.t[i])))
  const lerp = (a: number[]) => a[i] + (a[j] - a[i]) * f
  return {
    east: lerp(p.east_m),
    north: lerp(p.north_m),
    altitude: lerp(p.altitude_agl_m),
    speed: lerp(p.speed_ms),
  }
}

/** Scene position: x east, y up, z south (three.js is right-handed with y up). */
function toScene(east: number, north: number, altitude: number): [number, number, number] {
  return [east, altitude, -north]
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function Centre() {
  return (
    <RequireMission>
      <TrajectoryCentre />
    </RequireMission>
  )
}

function TrajectoryCentre() {
  const { lookup, path, result } = useFlight()
  const draft = useMissionStore((s) => s.draft!)

  if (!draft.rocket || !draft.motor || !draft.site) {
    return <Empty>The 3D view needs a flight, and a flight needs a rocket, a motor and a site.</Empty>
  }
  if (lookup.data && !lookup.data.available) {
    return (
      <Empty>
        No flight for the mission as it is now.{' '}
        <Link to="/flight" className="text-primary underline-offset-4 hover:underline">
          Run it in Single flight.
        </Link>
      </Empty>
    )
  }
  return (
    <div className="relative h-full">
      <ProblemNotice error={lookup.error ?? path.error} />
      {path.data && <Scene path={path.data} events={result.data?.summary.parachute_events ?? []} />}
      <div className="pointer-events-none absolute right-4 bottom-4 left-4 max-w-md">
        <div className="pointer-events-auto">
          <Explainer methodsHref="/docs/methods/flight">
            The single flight's path, east and north of the pad and height above it, to scale. The dashed line on the
            ground is its track. Drag to orbit, scroll to zoom, right-drag to pan.
          </Explainer>
        </div>
      </div>
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
      <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
        {children}
      </p>
    </div>
  )
}

interface SceneLabel {
  key: string
  at: [number, number, number]
  text: string
  muted?: boolean
}

function Scene({ path, events }: { path: FlightPath; events: { name: string; triggered_s: number }[] }) {
  const theme = usePrefs((s) => s.theme)
  // Canvas colours come from the theme tokens; re-read them when the theme changes.
  const colors = useMemo(
    () => ({
      line: token('--chart-1'),
      ink: token('--muted-foreground'),
      grid: token('--chart-grid'),
      fg: token('--foreground'),
      bg: token('--background'),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme],
  )
  const points = useMemo(
    () => path.t.map((_, i) => toScene(path.east_m[i], path.north_m[i], path.altitude_agl_m[i])),
    [path],
  )
  const ground = useMemo(() => points.map(([x, , z]) => [x, 0.5, z] as [number, number, number]), [points])
  const extent = useMemo(() => {
    const horizontal = Math.max(...path.east_m.map(Math.abs), ...path.north_m.map(Math.abs), 200)
    return { horizontal, height: Math.max(...path.altitude_agl_m) }
  }, [path])
  const apogee = useMemo(() => {
    const i = path.altitude_agl_m.indexOf(Math.max(...path.altitude_agl_m))
    return { i, p: points[i] }
  }, [path, points])
  const span = Math.max(extent.horizontal, extent.height)
  const gridSize = Math.ceil((extent.horizontal * 2.4) / 500) * 500
  // In priority order: a label that would overlap an earlier one is hidden.
  const labels = useMemo<SceneLabel[]>(() => {
    const out: SceneLabel[] = [
      { key: 'apogee', at: apogee.p, text: `Apogee ${Math.round(path.altitude_agl_m[apogee.i]).toLocaleString()} m` },
      { key: 'pad', at: [0, 0, 0], text: 'Pad' },
      { key: 'landing', at: points[points.length - 1], text: 'Landing' },
    ]
    for (const e of events) {
      const s = sampleAt(path, e.triggered_s)
      out.push({ key: `event-${e.name}`, at: toScene(s.east, s.north, s.altitude), text: `${e.name} opens`, muted: true })
    }
    out.push({ key: 'north', at: [0, 0, -gridSize / 2], text: 'N', muted: true })
    return out
  }, [apogee, path, points, events, gridSize])
  const labelEls = useRef(new Map<string, HTMLSpanElement>())

  return (
    <>
      <Canvas
        className="absolute! inset-0"
        camera={{ position: [span * 0.9, span * 0.6, span * 1.1], near: 1, far: span * 20, fov: 45 }}
        style={{ background: colors.bg }}
      >
        <gridHelper args={[gridSize, gridSize / 250, colors.grid, colors.grid]} />
        <Line points={ground} color={colors.ink} lineWidth={1} dashed dashSize={span / 80} gapSize={span / 120} />
        <Line points={[apogee.p, [apogee.p[0], 0, apogee.p[2]]]} color={colors.ink} lineWidth={1} transparent opacity={0.6} />
        <Line points={points} color={colors.line} lineWidth={2.5} />
        <Line points={[[0, 0.5, 0], [0, 0.5, -gridSize / 2]]} color={colors.ink} lineWidth={1} transparent opacity={0.5} />
        <Marker path={path} color={colors.fg} />
        <CameraRig span={span} height={extent.height} />
        <LabelProjector labels={labels} elements={labelEls} />
      </Canvas>
      {/* Labels are plain DOM over the canvas, placed each frame by LabelProjector. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        {labels.map((l) => (
          <span
            key={l.key}
            ref={(el) => {
              if (el) labelEls.current.set(l.key, el)
              else labelEls.current.delete(l.key)
            }}
            className={cn(
              'absolute top-0 left-0 rounded bg-background/80 px-1.5 py-0.5 text-xs whitespace-nowrap',
              l.muted ? 'text-muted-foreground' : 'text-foreground',
            )}
            style={{ visibility: 'hidden' }}
          >
            {l.text}
          </span>
        ))}
      </div>
    </>
  )
}

/** Projects each label's point to the screen every frame, hiding any that would overlap an earlier one. */
function LabelProjector({
  labels,
  elements,
}: {
  labels: SceneLabel[]
  elements: RefObject<Map<string, HTMLSpanElement>>
}) {
  const v = useMemo(() => new Vector3(), [])
  useFrame(({ camera, size }) => {
    const placed: { x0: number; x1: number; y0: number; y1: number }[] = []
    for (const l of labels) {
      const el = elements.current.get(l.key)
      if (!el) continue
      v.set(...l.at).project(camera)
      const x = ((v.x + 1) / 2) * size.width + 8
      const y = ((1 - v.y) / 2) * size.height - 10
      const box = { x0: x, x1: x + el.offsetWidth, y0: y, y1: y + el.offsetHeight }
      const visible =
        v.z < 1 && placed.every((o) => box.x1 <= o.x0 || box.x0 >= o.x1 || box.y1 <= o.y0 || box.y0 >= o.y1)
      el.style.visibility = visible ? 'visible' : 'hidden'
      if (visible) {
        el.style.transform = `translate(${x}px, ${y}px)`
        placed.push(box)
      }
    }
  })
  return null
}

/** The rocket's position at the playback time. */
function Marker({ path, color }: { path: FlightPath; color: string }) {
  const t = useView((s) => s.t)
  const s = sampleAt(path, t)
  return (
    <mesh position={toScene(s.east, s.north, s.altitude)}>
      <sphereGeometry args={[Math.max(...path.altitude_agl_m) / 120, 16, 16]} />
      <meshBasicMaterial color={color} />
    </mesh>
  )
}

/** Orbit controls, plus the camera presets the pane asks for. */
function CameraRig({ span, height }: { span: number; height: number }) {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null)
  const camera = useThree((s) => s.camera)
  const preset = useView((s) => s.preset)
  const nonce = useView((s) => s.presetNonce)
  useEffect(() => {
    const target: [number, number, number] = [0, height / 2, 0]
    const positions: Record<Preset, [number, number, number]> = {
      '3d': [span * 0.9, span * 0.6, span * 1.1],
      side: [0, height / 2, span * 2.2], // from the south, looking north
      top: [0, span * 2.4, 0.01],
    }
    camera.position.set(...positions[preset])
    controls.current?.target.set(...(preset === 'top' ? [0, 0, 0] : target) as [number, number, number])
    controls.current?.update()
  }, [preset, nonce, camera, span, height])
  return <OrbitControls ref={controls} makeDefault enableDamping />
}

export function Pane() {
  return (
    <RequireMission compact>
      <PlaybackPane />
    </RequireMission>
  )
}

function PlaybackPane() {
  const { path } = useFlight()
  const { t, setT, playing, setPlaying, preset, setPreset } = useView()
  const units = usePrefs((s) => s.display)
  const p = path.data
  const end = p ? p.t[p.t.length - 1] : 0

  // Real-time playback, sped up 4x after apogee so the descent doesn't take minutes.
  useEffect(() => {
    if (!playing || !p) return
    let last = performance.now()
    let frame = requestAnimationFrame(function step(now) {
      const dt = (now - last) / 1000
      last = now
      const { t: current } = useView.getState()
      const apogeeTime = p.t[p.altitude_agl_m.indexOf(Math.max(...p.altitude_agl_m))]
      const next = current + dt * (current > apogeeTime ? 8 : 1)
      if (next >= end) {
        useView.getState().setT(end)
        useView.getState().setPlaying(false)
        return
      }
      useView.getState().setT(next)
      frame = requestAnimationFrame(step)
    })
    return () => cancelAnimationFrame(frame)
  }, [playing, p, end])

  if (!p) return <p className="p-4 text-sm text-muted-foreground">Run the single flight to see it in 3D.</p>
  const s = sampleAt(p, t)
  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Playback</h2>
        <div className="flex items-center gap-2">
          <Button
            size="icon"
            className="size-9"
            aria-label={playing ? 'Pause' : 'Play'}
            onClick={() => {
              if (!playing && t >= end) setT(0)
              setPlaying(!playing)
            }}
          >
            {playing ? <Pause /> : <Play />}
          </Button>
          <Button size="icon" variant="ghost" className="size-9" aria-label="Back to launch" onClick={() => setT(0)}>
            <RotateCcw />
          </Button>
          <input
            type="range"
            aria-label="Time"
            min={0}
            max={end}
            step={0.1}
            value={t}
            onChange={(e) => {
              setPlaying(false)
              setT(Number(e.target.value))
            }}
            className="min-w-0 flex-1"
          />
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm tabular-nums">
          <Readout label="Time" value={`${t.toFixed(1)} s`} />
          <Readout label="Altitude" value={formatSI(s.altitude, 'altitude', units)} />
          <Readout label="Speed" value={formatSI(s.speed, 'speed', units, 0)} />
          <Readout label="From the pad" value={formatSI(Math.hypot(s.east, s.north), 'distance', units)} />
        </dl>
        <p className="text-xs text-muted-foreground">Plays in real time to apogee, then 8× for the descent.</p>
      </section>
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Camera</h2>
        <div role="radiogroup" aria-label="Camera" className="flex rounded-md border border-border p-0.5">
          {(
            [
              ['3d', '3D'],
              ['side', 'From the south'],
              ['top', 'From above'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={preset === id}
              onClick={() => setPreset(id)}
              className={cn(
                'flex-1 rounded px-2 py-1 text-sm',
                preset === id ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
