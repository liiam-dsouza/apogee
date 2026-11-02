import { useMutation } from '@tanstack/react-query'
import { Check, Download, FileUp, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { create } from 'zustand'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { RequireMission } from '@/components/RequireMission'
import { RocketSideView } from '@/components/RocketSideView'
import { Button } from '@/components/ui/button'
import { api, type CrossCheck, type ImportReport, type OpenRocketImport } from '@/lib/api'
import { formatSI, systemOf } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** An import awaiting review. Nothing touches the mission until it is applied. */
interface PendingImport {
  result: OpenRocketImport | null
  ork: File | null
  set: (ork: File, result: OpenRocketImport) => void
  clear: () => void
}

const usePending = create<PendingImport>()((set) => ({
  result: null,
  ork: null,
  set: (ork, result) => set({ ork, result }),
  clear: () => set({ ork: null, result: null }),
}))

export function Centre() {
  return (
    <RequireMission>
      <RocketCentre />
    </RequireMission>
  )
}

function RocketCentre() {
  const pending = usePending((s) => s.result)
  const rocket = useMissionStore((s) => s.draft?.rocket ?? null)
  if (pending) return <ImportReview result={pending} />
  if (!rocket) {
    return (
      <div className="flex h-full flex-col justify-end gap-4 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          This mission has no rocket yet. Import one from OpenRocket.
        </p>
      </div>
    )
  }
  return <RocketSummary />
}

function RocketSummary() {
  const rocket = useMissionStore((s) => s.draft!.rocket!)
  const units = usePrefs((s) => s.display)
  const length = Math.max(
    rocket.nose.length_m,
    rocket.motor_position_m,
    ...rocket.fins.map((f) => f.position_m + f.root_chord_m),
    rocket.tail ? rocket.tail.position_m + rocket.tail.length_m : 0,
  )
  const facts: [string, string][] = [
    ['Length', formatSI(length, 'distance', units, 2)],
    ['Diameter', formatSI(rocket.radius_m * 2, 'length', units, systemOf(units) === 'metric' ? 3 : 2)],
    ['Dry mass', formatSI(rocket.dry_mass_kg, 'mass', units, 2)],
    ['Dry centre of mass', `${formatSI(rocket.dry_cg_m, 'distance', units, 3)} from the tip`],
    ['Nose', `${rocket.nose.kind.replace('_', ' ')}, ${formatSI(rocket.nose.length_m, 'distance', units, 2)}`],
    ['Fins', rocket.fins.map((f) => `${f.count} × ${(f.root_chord_m * 1000).toFixed(0)}/${(f.tip_chord_m * 1000).toFixed(0)} mm`).join(', ')],
  ]
  return (
    <div className="space-y-6 p-6">
      <RocketSideView rocket={rocket} />
      <dl className="grid max-w-3xl grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-x-6 gap-y-3">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="text-sm">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/openrocket-import">
          The rocket is stored as RocketPy needs it: outer geometry for the aerodynamics, and the dry mass, centre of mass
          and inertia of everything except the motor. Positions are measured aft of the nose tip. The centre of pressure
          and stability margin depend on Mach and the motor, so they are shown with each flight.
        </Explainer>
      </div>
    </div>
  )
}

const STATUS: Record<CrossCheck['status'], { label: string; className: string }> = {
  ok: { label: 'Agrees', className: 'text-go' },
  flag: { label: 'Check this', className: 'text-nogo' },
  explained: { label: 'Defined differently', className: 'text-caution' },
  unavailable: { label: 'Not compared', className: 'text-muted-foreground' },
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return Math.abs(v) >= 100 ? v.toLocaleString(undefined, { maximumFractionDigits: 1 }) : v.toLocaleString(undefined, { maximumFractionDigits: 3 })
}

function ImportReview({ result }: { result: OpenRocketImport }) {
  const report = result.report
  const fileName = usePending((s) => s.ork?.name.replace(/\.ork$/i, ''))
  // OpenRocket names every new design "Rocket"; the file name says more.
  const title = report.rocket_name === 'Rocket' && fileName ? fileName : report.rocket_name
  const flagged = report.cross_checks.filter((c) => c.status === 'flag').length
  return (
    <div className="space-y-8 p-6">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">Review the import: {title}</h2>
        <p className="text-sm text-muted-foreground">
          From {report.openrocket_version}. Nothing changes in the mission until you choose Use this rocket.
          {report.reference_simulation && ` Compared against OpenRocket's simulation '${report.reference_simulation}'.`}
        </p>
      </header>

      {report.warnings.length > 0 && (
        <section aria-label="Check before trusting" className="space-y-2">
          <h3 className="text-sm font-semibold">Check before trusting this</h3>
          <ul className="max-w-3xl list-disc space-y-1 pl-5 text-sm">
            {report.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Comparison with OpenRocket" className="space-y-2">
        <h3 className="text-sm font-semibold">
          Against OpenRocket{flagged > 0 && <span className="ml-2 text-nogo">{flagged} to check</span>}
        </h3>
        <div className="max-w-4xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 font-normal">Quantity</th>
                <th className="py-1 text-right font-normal">Apogee</th>
                <th className="py-1 text-right font-normal">OpenRocket</th>
                <th className="py-1 pl-4 font-normal">Tolerance</th>
                <th className="py-1 font-normal">Result</th>
              </tr>
            </thead>
            <tbody>
              {report.cross_checks.map((c) => (
                <tr key={c.quantity} className="border-t border-border align-top">
                  <td className="py-2 pr-4">
                    {c.quantity}
                    {c.units && c.units !== '1' && <span className="text-muted-foreground"> ({c.units})</span>}
                    <p className="max-w-md text-xs text-muted-foreground">{c.note}</p>
                  </td>
                  <td className="py-2 text-right tabular-nums">{fmt(c.ours)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(c.openrocket)}</td>
                  <td className="py-2 pl-4 text-muted-foreground">{c.tolerance}</td>
                  <td className={cn('py-2 font-medium', STATUS[c.status].className)}>{STATUS[c.status].label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <RocketSideView rocket={result.rocket} />

      <ReportList title="Came across as-is" items={report.mapped} />
      <ReportList title="Approximated" items={report.approximated} open />
      <ReportList title="Not supported (mass still counted)" items={report.unsupported} open />
      <SimulationList report={report} />
    </div>
  )
}

function ReportList({ title, items, open = false }: { title: string; items: ImportReport['mapped']; open?: boolean }) {
  if (items.length === 0) return null
  return (
    <details open={open} className="max-w-3xl">
      <summary className="cursor-pointer text-sm font-semibold">
        {title} <span className="font-normal text-muted-foreground">({items.length})</span>
      </summary>
      <ul className="mt-2 divide-y divide-border text-sm">
        {items.map((i, n) => (
          <li key={`${i.component}-${n}`} className="py-1.5">
            <span className="font-medium">{i.component}</span>
            {i.target && <code className="ml-2 text-xs text-muted-foreground">{i.target}</code>}
            <p className="text-muted-foreground">{i.detail}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}

function SimulationList({ report }: { report: ImportReport }) {
  if (report.simulations.length === 0) return null
  return (
    <details className="max-w-3xl">
      <summary className="cursor-pointer text-sm font-semibold">
        Simulations saved in the file <span className="font-normal text-muted-foreground">({report.simulations.length})</span>
      </summary>
      <table className="mt-2 w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-1 font-normal">Name</th>
            <th className="py-1 font-normal">State</th>
            <th className="py-1 text-right font-normal">Apogee (m)</th>
            <th className="py-1 text-right font-normal">Wind (m/s)</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {report.simulations.map((s) => (
            <tr key={s.name} className="border-t border-border">
              <td className="py-1">{s.name}</td>
              <td className={cn('py-1', s.up_to_date ? '' : 'text-caution')}>{s.up_to_date ? 'Up to date' : 'Out of date'}</td>
              <td className="py-1 text-right">{fmt(s.apogee_m)}</td>
              <td className="py-1 text-right">{fmt(s.wind_average_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <ImportPane />
    </RequireMission>
  )
}

function ImportPane() {
  const pending = usePending()
  const edit = useMissionStore((s) => s.edit)
  const hasSite = useMissionStore((s) => Boolean(s.draft?.site))
  const [ork, setOrk] = useState<File | null>(null)
  const [eng, setEng] = useState<File | null>(null)
  const [applyRail, setApplyRail] = useState(false)
  const orkInput = useRef<HTMLInputElement>(null)
  const engInput = useRef<HTMLInputElement>(null)

  const runImport = useMutation({
    mutationFn: (args: { ork: File; thrust?: { file?: File; sha?: string } }) => api.importOpenRocket(args.ork, args.thrust),
    onSuccess: (result, args) => pending.set(args.ork, result),
  })
  const fetchMotor = useMutation({
    mutationFn: async () => {
      const ref = pending.result!.motor_reference!
      const fetched = await api.fetchThrustCurve(ref.manufacturer, ref.designation)
      return api.importOpenRocket(pending.ork!, { sha: fetched.asset.sha256 })
    },
    onSuccess: (result) => pending.set(pending.ork!, result),
  })

  const apply = () => {
    const r = pending.result!
    edit((d) => {
      d.rocket = r.rocket
      d.recovery = r.recovery
      if (r.motor) d.motor = r.motor
      d.assets = { ...d.assets, ...r.assets }
      if (applyRail && r.rail && d.site) {
        d.site.rail_length_m = r.rail.rail_length_m
        d.site.inclination_deg = r.rail.inclination_deg
        d.site.heading_deg = r.rail.heading_deg
      }
    })
    pending.clear()
    setOrk(null)
    setEng(null)
  }

  if (pending.result) {
    const r = pending.result
    const ref = r.motor_reference
    return (
      <div className="space-y-5 p-4">
        <h2 className="text-sm font-semibold">Use this import?</h2>
        <ul className="space-y-1 text-sm">
          <li>Rocket and recovery replace the mission's.</li>
          <li>
            {r.motor
              ? `Motor: ${ref ? `${ref.manufacturer} ${ref.designation}` : 'from the thrust curve'}.`
              : 'No motor: the thrust curve is missing.'}
          </li>
        </ul>
        {!r.motor && ref && (
          <div className="space-y-2 rounded-md border border-border p-3">
            <p className="text-sm">
              OpenRocket names the {ref.manufacturer} {ref.designation} but doesn't store its thrust curve.
            </p>
            <Button className="w-full" onClick={() => fetchMotor.mutate()} disabled={fetchMotor.isPending}>
              <Download />
              {fetchMotor.isPending ? 'Fetching' : `Fetch ${ref.designation} from ThrustCurve.org`}
            </Button>
            <p className="text-xs text-muted-foreground">Needs internet. Offline, attach the .eng file and import again.</p>
            <ProblemNotice error={fetchMotor.error} />
          </div>
        )}
        {r.rail && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={applyRail} disabled={!hasSite} onChange={(e) => setApplyRail(e.target.checked)} />
            <span>
              Also set the rail from OpenRocket: {r.rail.rail_length_m} m at {r.rail.inclination_deg}°
              <span className="block text-xs text-muted-foreground">
                {hasSite ? "OpenRocket's rod was set for its own launch site; keep yours unless they match." : 'Add a site first to apply rail settings.'}
              </span>
            </span>
          </label>
        )}
        <div className="flex flex-col gap-2">
          <Button variant="primary" onClick={apply}>
            <Check />
            Use this rocket
          </Button>
          <Button variant="ghost" onClick={() => pending.clear()}>
            <X />
            Discard the import
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Import from OpenRocket</h2>
        <FilePick label="Design (.ork)" file={ork} onPick={() => orkInput.current?.click()} />
        <FilePick label="Motor thrust curve (.eng), optional" file={eng} onPick={() => engInput.current?.click()} />
        <input ref={orkInput} type="file" accept=".ork" className="hidden" onChange={(e) => setOrk(e.target.files?.[0] ?? null)} />
        <input ref={engInput} type="file" accept=".eng" className="hidden" onChange={(e) => setEng(e.target.files?.[0] ?? null)} />
        <Button
          variant="primary"
          className="w-full"
          disabled={!ork || runImport.isPending}
          onClick={() => ork && runImport.mutate({ ork, thrust: eng ? { file: eng } : undefined })}
        >
          <FileUp />
          {runImport.isPending ? 'Reading the design' : 'Import and review'}
        </Button>
        <p className="text-xs text-muted-foreground">
          With the motor's thrust curve, the review also flies the rocket under OpenRocket's own conditions and compares
          apogee, Mach and centre of pressure.
        </p>
        <ProblemNotice error={runImport.error} />
      </section>
    </div>
  )
}

function FilePick({ label, file, onPick }: { label: string; file: File | null; onPick: () => void }) {
  return (
    <div className="space-y-1">
      <span className="text-sm">{label}</span>
      <button
        type="button"
        onClick={onPick}
        className="flex h-9 w-full items-center rounded-md border border-border bg-background px-3 text-left text-sm hover:border-muted-foreground"
      >
        {file ? file.name : <span className="text-muted-foreground">Choose a file</span>}
      </button>
    </div>
  )
}
