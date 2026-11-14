import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { Button } from '@/components/ui/button'
import { api, type BayCheck, type EjectionBay } from '@/lib/api'
import { formatSI } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useFlightRuns } from '@/sections/flight/run'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** Typical nylon pin strengths in shear (35 and 55 lbf). Batches vary: test yours. */
const PINS = [
  { label: 'Nylon 2-56', n: 156 },
  { label: 'Nylon 4-40', n: 245 },
]

/** Black powder per bay, and whether the joint holds while the rocket coasts. */
export function EjectionCharges() {
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const units = usePrefs((s) => s.display)
  const runId = useFlightRuns((s) => s.byMission[draft.meta.id!]?.resultId)
  const bays = draft.ejection?.bays ?? []
  const devices = draft.recovery?.devices ?? []
  const checks = useQuery({
    queryKey: ['recovery', 'ejection', draft, runId],
    queryFn: () => api.ejectionCharges(draft),
    enabled: bays.length > 0,
    placeholderData: keepPreviousData,
  })
  const editBay = (i: number, recipe: (b: EjectionBay) => void) =>
    edit((m) => {
      const b = m.ejection?.bays?.[i]
      if (b) recipe(b)
    })
  const add = () =>
    edit((m) => {
      const taken = new Set((m.ejection?.bays ?? []).map((b) => b.device))
      const device = devices.find((d) => !taken.has(d.name))?.name ?? null
      const tube = (m.rocket?.radius_m ?? 0.05) * 2
      m.ejection ??= {}
      ;(m.ejection.bays ??= []).push({
        name: device ? `${device} bay` : `Bay ${(m.ejection.bays?.length ?? 0) + 1}`,
        device,
        // A thin-walled tube's inside: a start for the team to measure.
        inner_diameter_m: Number((tube * 0.96).toFixed(4)),
        free_length_m: 0.25,
        shear_pins: 0,
        pin_strength_n: 0,
        separation_pressure_pa: 103421,
        backup_factor: 1.25,
      })
    })

  return (
    <section aria-label="Ejection charges" className="max-w-5xl space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">Ejection charges</h2>
        <p className="text-sm text-muted-foreground">
          {checks.data?.coast_drag_deceleration_ms2 != null
            ? `Drag decelerates the rocket by up to ${formatSI(checks.data.coast_drag_deceleration_ms2, 'acceleration', units, 1)} in coast, from the single flight.`
            : 'Run the single flight to check each joint holds during coast.'}
        </p>
      </header>
      <ProblemNotice error={checks.error} />
      {bays.map((b, i) => (
        <BayRow
          key={i}
          index={i}
          bay={b}
          devices={devices.map((d) => d.name)}
          check={checks.data?.bays[i]}
          onEdit={(r) => editBay(i, r)}
          onRemove={() => edit((m) => void m.ejection?.bays?.splice(i, 1))}
        />
      ))}
      <Button size="sm" onClick={add}>
        <Plus /> {bays.length ? 'Another bay' : 'Add a bay'}
      </Button>
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/ejection">
          Black powder from the ideal gas law for its combustion gas (R = 22.16 ft·lbf/lbm·°R, T = 3307 °R), filling the
          bay's free volume to the pressure that breaks the pins plus a separation pressure. During coast the section
          beyond the joint is pulled away by up to its mass times the rocket's drag deceleration, which the pins or a
          friction fit must hold. These are starting points: ground test every charge.
        </Explainer>
      </div>
    </section>
  )
}

function BayRow({
  index,
  bay,
  devices,
  check,
  onEdit,
  onRemove,
}: {
  index: number
  bay: EjectionBay
  devices: string[]
  check: BayCheck | undefined
  onEdit: (recipe: (b: EjectionBay) => void) => void
  onRemove: () => void
}) {
  const units = usePrefs((s) => s.display)
  const path = `ejection.bays[${index}]`
  const pins = bay.shear_pins ?? 0
  const preset = PINS.find((p) => p.n === bay.pin_strength_n)
  const holds = check?.hold_margin
  const tone = holds == null ? '' : holds >= 2 ? 'text-go' : holds >= 1 ? 'text-caution' : 'text-nogo'

  return (
    <div className="grid gap-4 rounded-md border border-border p-3 lg:grid-cols-[minmax(0,20rem)_1fr]">
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <input
            aria-label="Bay name"
            value={bay.name}
            onChange={(e) => onEdit((b) => void (b.name = e.target.value || 'Bay'))}
            className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-sm font-medium"
          />
          <Button size="sm" variant="ghost" aria-label={`Remove ${bay.name}`} onClick={onRemove}>
            <Trash2 />
          </Button>
        </div>
        <label className="block space-y-1 text-sm">
          <span>Releases</span>
          <select
            value={bay.device ?? ''}
            onChange={(e) => onEdit((b) => void (b.device = e.target.value || null))}
            className="h-9 w-full rounded-md border border-border bg-background px-2"
          >
            <option value="">Nothing named</option>
            {devices.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <QuantityField
          schema="EjectionBay"
          name="inner_diameter_m"
          path={`${path}.inner_diameter_m`}
          label="Inside diameter"
          quantity="length"
          decimals={3}
          value={bay.inner_diameter_m}
          onChange={(v) => onEdit((b) => void (b.inner_diameter_m = v))}
        />
        <QuantityField
          schema="EjectionBay"
          name="free_length_m"
          path={`${path}.free_length_m`}
          label="Free length"
          quantity="length"
          decimals={3}
          value={bay.free_length_m}
          onChange={(v) => onEdit((b) => void (b.free_length_m = v))}
        />
        {bay.forward_mass_kg == null ? (
          <Button size="sm" variant="ghost" onClick={() => onEdit((b) => void (b.forward_mass_kg = 1))}>
            <Plus /> Mass beyond the joint
          </Button>
        ) : (
          <QuantityField
            schema="EjectionBay"
            name="forward_mass_kg"
            path={`${path}.forward_mass_kg`}
            label="Mass beyond the joint"
            quantity="mass"
            decimals={3}
            value={bay.forward_mass_kg}
            onChange={(v) => onEdit((b) => void (b.forward_mass_kg = v))}
          />
        )}
        <label className="block space-y-1 text-sm">
          <span>Shear pins</span>
          <input
            type="number"
            min={0}
            max={24}
            value={pins}
            onChange={(e) =>
              onEdit((b) => {
                const n = Math.max(0, Math.min(24, Math.round(Number(e.target.value) || 0)))
                b.shear_pins = n
                if (n > 0 && !b.pin_strength_n) b.pin_strength_n = PINS[0].n
              })
            }
            className="h-9 w-full rounded-md border border-border bg-background px-2 tabular-nums"
          />
        </label>
        {pins > 0 && (
          <>
            <label className="block space-y-1 text-sm">
              <span>Pin type</span>
              <select
                value={preset?.label ?? 'own'}
                onChange={(e) => {
                  const p = PINS.find((x) => x.label === e.target.value)
                  if (p) onEdit((b) => void (b.pin_strength_n = p.n))
                }}
                className="h-9 w-full rounded-md border border-border bg-background px-2"
              >
                {PINS.map((p) => (
                  <option key={p.label} value={p.label}>
                    {p.label}
                  </option>
                ))}
                <option value="own">Own value</option>
              </select>
            </label>
            <QuantityField
              schema="EjectionBay"
              name="pin_strength_n"
              path={`${path}.pin_strength_n`}
              label="Strength per pin"
              quantity="force"
              decimals={0}
              value={bay.pin_strength_n ?? 0}
              onChange={(v) => onEdit((b) => void (b.pin_strength_n = v))}
            />
          </>
        )}
        <QuantityField
          schema="EjectionBay"
          name="separation_pressure_pa"
          path={`${path}.separation_pressure_pa`}
          label="Separation pressure"
          quantity="pressure"
          decimals={1}
          value={bay.separation_pressure_pa ?? 103421}
          onChange={(v) => onEdit((b) => void (b.separation_pressure_pa = v))}
        />
      </div>
      <div className="space-y-3">
        {check ? (
          <>
            <p className="font-display text-3xl font-semibold tabular-nums">
              {formatSI(check.primary_charge_kg, 'charge', units, 2)}
              <span className="ml-2 align-middle text-sm font-normal text-muted-foreground">
                black powder, {formatSI(check.backup_charge_kg, 'charge', units, 2)} backup
              </span>
            </p>
            <dl className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-6 gap-y-3 text-sm">
              <Fact k="Bay pressure" v={formatSI(check.design_pressure_pa, 'pressure', units, 1)} />
              {pins > 0 && <Fact k="Breaks the pins at" v={formatSI(check.pin_break_pressure_pa, 'pressure', units, 1)} />}
              <Fact k="Force on the bulkhead" v={formatSI(check.ejection_force_n, 'force', units)} />
              {check.drag_separation_n != null && (
                <Fact k="Coast pulls the joint" v={formatSI(check.drag_separation_n, 'force', units)} />
              )}
              {pins > 0 && <Fact k="Pins hold" v={formatSI(check.pins_hold_n, 'force', units)} />}
              {holds != null && (
                <div>
                  <dt className="text-xs text-muted-foreground">Hold margin</dt>
                  <dd className={cn('font-medium tabular-nums', tone)}>{holds.toFixed(1)} ×</dd>
                </div>
              )}
            </dl>
            {check.notes.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {check.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Working it out.</p>
        )}
      </div>
    </div>
  )
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="tabular-nums">{v}</dd>
    </div>
  )
}
