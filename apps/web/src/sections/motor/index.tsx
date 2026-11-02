import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, FileUp } from 'lucide-react'
import { useRef, useState } from 'react'
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type ThrustCurveImport } from '@/lib/api'
import { formatSI, type Quantity } from '@/lib/units'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

function useMotor() {
  return useMissionStore((s) => s.draft?.motor ?? null)
}

function useThrustCurve(sha: string | undefined) {
  return useQuery({
    queryKey: ['assets', sha, 'thrust-curve'],
    queryFn: () => api.thrustCurve(sha!),
    enabled: Boolean(sha),
    staleTime: Infinity, // assets never change
  })
}

/** Puts an imported motor in the mission, with its curve in the assets, dropping the old curve. */
function useApplyMotor() {
  const edit = useMissionStore((s) => s.edit)
  return (imported: ThrustCurveImport) =>
    edit((d) => {
      const old = d.motor?.thrust_curve
      const { sha256, filename, size } = imported.asset
      d.motor = imported.motor
      d.assets = { ...d.assets, [sha256]: { kind: 'thrust_curve', filename, size } }
      const drag = [d.rocket?.drag.power_off.table, d.rocket?.drag.power_on.table]
      if (old && old !== sha256 && !drag.includes(old) && d.assets) delete d.assets[old]
    })
}

export function Centre() {
  return (
    <RequireMission>
      <MotorCentre />
    </RequireMission>
  )
}

function MotorCentre() {
  const motor = useMotor()
  const curve = useThrustCurve(motor?.thrust_curve)
  const units = usePrefs((s) => s.units)

  if (!motor) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          This mission has no motor yet. Upload a thrust curve or fetch one from ThrustCurve.org in the pane.
        </p>
      </div>
    )
  }
  const c = curve.data
  const facts: [string, string][] = c
    ? [
        ['Total impulse', `${c.total_impulse_ns.toLocaleString(undefined, { maximumFractionDigits: 0 })} N·s`],
        ['Average thrust', formatSI(c.average_thrust_n, 'force', units, 0)],
        ['Peak thrust', formatSI(c.max_thrust_n, 'force', units, 0)],
        ['Burn time', `${c.burn_time_s.toFixed(2)} s`],
        ['Propellant', formatSI(c.propellant_mass_kg, 'mass', units, 2)],
        ['Loaded motor', formatSI(c.total_mass_kg, 'mass', units, 2)],
      ]
    : []

  return (
    <div className="space-y-6 p-6">
      <ProblemNotice error={curve.error} />
      {c && (
        <>
          <header className="space-y-1">
            <h2 className="font-display text-2xl font-semibold">
              {c.manufacturer} {c.designation}
            </h2>
            <p className="text-sm text-muted-foreground">
              {c.impulse_class} class, {Math.round(c.class_percent)}% of the way through it.{' '}
              {motor.kind === 'generic'
                ? 'Modelled from its thrust curve and masses.'
                : 'Modelled from its grain geometry.'}
            </p>
          </header>
          <div className="max-w-3xl">
            <TimeSeriesChart
              title="Thrust"
              unit="N"
              t={c.points.map((p) => p[0])}
              y={c.points.map((p) => p[1])}
              markPeak
              syncKey="motor"
            />
          </div>
          <dl className="grid max-w-3xl grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-6 gap-y-3">
            {facts.map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted-foreground">{k}</dt>
                <dd className="text-sm tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/flight">
          The thrust curve is flown as given, after a zero point at ignition. A generic motor is a cylinder of propellant
          that loses mass in step with the impulse delivered; its masses and geometry are first estimated from the
          file's header, so check them against the motor's data sheet. Monte Carlo varies the total impulse and burn
          time around this curve.
        </Explainer>
      </div>
    </div>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <MotorPane />
    </RequireMission>
  )
}

type Field = { name: string; label: string; quantity: Quantity; decimals: number }

const GENERIC_FIELDS: Field[] = [
  { name: 'propellant_mass_kg', label: 'Propellant mass', quantity: 'mass', decimals: 3 },
  { name: 'dry_mass_kg', label: 'Dry mass', quantity: 'mass', decimals: 3 },
  { name: 'dry_cg_position_m', label: 'Dry centre of mass', quantity: 'length', decimals: 3 },
  { name: 'chamber_radius_m', label: 'Propellant radius', quantity: 'length', decimals: 4 },
  { name: 'chamber_height_m', label: 'Propellant length', quantity: 'length', decimals: 3 },
  { name: 'chamber_position_m', label: 'Propellant centre', quantity: 'length', decimals: 3 },
  { name: 'nozzle_radius_m', label: 'Nozzle exit radius', quantity: 'length', decimals: 4 },
]

const SOLID_FIELDS: Field[] = [
  { name: 'dry_mass_kg', label: 'Dry mass', quantity: 'mass', decimals: 3 },
  { name: 'dry_cg_position_m', label: 'Dry centre of mass', quantity: 'length', decimals: 3 },
  { name: 'nozzle_radius_m', label: 'Nozzle exit radius', quantity: 'length', decimals: 4 },
  { name: 'throat_radius_m', label: 'Throat radius', quantity: 'length', decimals: 4 },
]

const GRAIN_FIELDS: Field[] = [
  { name: 'density_kg_m3', label: 'Propellant density', quantity: 'density', decimals: 0 },
  { name: 'outer_radius_m', label: 'Grain outer radius', quantity: 'length', decimals: 4 },
  { name: 'initial_inner_radius_m', label: 'Core radius', quantity: 'length', decimals: 4 },
  { name: 'initial_height_m', label: 'Grain height', quantity: 'length', decimals: 4 },
  { name: 'separation_m', label: 'Grain separation', quantity: 'length', decimals: 4 },
  { name: 'cg_position_m', label: 'Grain stack centre', quantity: 'length', decimals: 3 },
]

function MotorPane() {
  const motor = useMotor()
  const edit = useMissionStore((s) => s.edit)

  const field = (f: Field) => {
    if (!motor) return null
    const value = (motor as Record<string, unknown>)[f.name]
    if (typeof value !== 'number') return null
    return (
      <QuantityField
        key={f.name}
        schema={motor.kind === 'generic' ? 'GenericMotor' : 'SolidMotor'}
        name={f.name}
        path={`motor.${f.name}`}
        label={f.label}
        quantity={f.quantity}
        decimals={f.decimals}
        value={value}
        onChange={(v) =>
          edit((d) => {
            if (d.motor) (d.motor as Record<string, unknown>)[f.name] = v
          })
        }
      />
    )
  }

  return (
    <div className="space-y-6 p-4">
      {motor && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">{motor.kind === 'generic' ? 'Generic motor' : 'Solid motor'}</h2>
          {(motor.kind === 'generic' ? GENERIC_FIELDS : SOLID_FIELDS).map(field)}
          {motor.kind === 'solid' && (
            <>
              <h3 className="pt-2 text-sm font-semibold">Grains ({motor.grains.count})</h3>
              {GRAIN_FIELDS.map((f) => (
                <QuantityField
                  key={f.name}
                  schema="Grains"
                  name={f.name}
                  path={`motor.grains.${f.name}`}
                  label={f.label}
                  quantity={f.quantity}
                  decimals={f.decimals}
                  value={(motor.grains as Record<string, number>)[f.name]}
                  onChange={(v) =>
                    edit((d) => {
                      if (d.motor?.kind === 'solid') (d.motor.grains as Record<string, number>)[f.name] = v
                    })
                  }
                />
              ))}
            </>
          )}
          <p className="text-xs text-muted-foreground">
            Positions are measured forward of the nozzle exit. Check estimated values against the motor's data sheet.
          </p>
        </section>
      )}
      <ReplaceMotor hasMotor={Boolean(motor)} />
    </div>
  )
}

function ReplaceMotor({ hasMotor }: { hasMotor: boolean }) {
  const apply = useApplyMotor()
  const fileInput = useRef<HTMLInputElement>(null)
  const [manufacturer, setManufacturer] = useState('')
  const [designation, setDesignation] = useState('')
  const upload = useMutation({ mutationFn: api.importMotor, onSuccess: apply })
  const fetchCurve = useMutation({
    mutationFn: () => api.fetchThrustCurve(manufacturer.trim(), designation.trim()),
    onSuccess: apply,
  })

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">{hasMotor ? 'Replace the motor' : 'Add a motor'}</h2>
      <input
        ref={fileInput}
        type="file"
        accept=".eng"
        className="hidden"
        aria-label="Thrust curve file"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload.mutate(file)
          e.target.value = ''
        }}
      />
      <Button className="w-full" onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
        <FileUp /> {upload.isPending ? 'Reading' : 'Upload a thrust curve (.eng)'}
      </Button>
      <ProblemNotice error={upload.error} />

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (manufacturer.trim() && designation.trim()) fetchCurve.mutate()
        }}
      >
        <p className="text-xs text-muted-foreground">Or fetch it from ThrustCurve.org (needs internet):</p>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1 text-sm">
            <span>Manufacturer</span>
            <input
              value={manufacturer}
              onChange={(e) => setManufacturer(e.target.value)}
              placeholder="AeroTech"
              className="h-9 w-full rounded-md border border-border bg-background px-3"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>Designation</span>
            <input
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              placeholder="M1340W"
              className="h-9 w-full rounded-md border border-border bg-background px-3"
            />
          </label>
        </div>
        <Button
          type="submit"
          className="w-full"
          disabled={fetchCurve.isPending || !manufacturer.trim() || !designation.trim()}
        >
          <Download /> {fetchCurve.isPending ? 'Fetching' : 'Fetch from ThrustCurve.org'}
        </Button>
        <ProblemNotice error={fetchCurve.error} />
      </form>
      {hasMotor && (
        <p className="text-xs text-muted-foreground">
          A new motor replaces this one, with its masses estimated from the new file. Undo puts the old one back.
        </p>
      )}
    </section>
  )
}
