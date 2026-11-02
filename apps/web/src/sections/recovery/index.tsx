import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type RecoveryDevice } from '@/lib/api'
import { useIssuesAt } from '@/lib/mission/validation'
import { formatSI, toSI, unitFor } from '@/lib/units'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

type Device = RecoveryDevice

/** Starting points for a new device; the team must size their own. */
const PRESETS: Record<'drogue' | 'main', Device> = {
  drogue: { name: 'Drogue', cd_s_m2: 0.3, trigger: { kind: 'apogee' }, lag_s: 1, sampling_rate_hz: 100 },
  main: { name: 'Main', cd_s_m2: 5, trigger: { kind: 'altitude_agl', altitude_m: 300 }, lag_s: 1, sampling_rate_hz: 100 },
}

export function Centre() {
  return (
    <RequireMission>
      <RecoveryCentre />
    </RequireMission>
  )
}

function RecoveryCentre() {
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const units = usePrefs((s) => s.display)
  // Wanted descent rate per device, in SI; asks the API for the CdS that gives it.
  const [targets, setTargets] = useState<Record<string, number>>({})
  const ready = Boolean(draft.rocket && draft.motor && draft.site)
  const devices = draft.recovery?.devices ?? []
  const descent = useQuery({
    queryKey: ['recovery', 'descent', draft, targets],
    queryFn: () => api.descentRates(draft, targets),
    enabled: ready && devices.length > 0,
    placeholderData: keepPreviousData,
  })

  if (devices.length === 0) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          No recovery devices: the rocket would come down ballistic. Add a drogue and a main in the pane.
        </p>
      </div>
    )
  }
  if (!ready) {
    return (
      <p className="p-6 text-muted-foreground">
        Descent rates need a rocket, a motor and a launch site: the mass under the canopy and the air it falls through.
      </p>
    )
  }

  const data = descent.data
  const speed = (v: number | null | undefined) => (v == null ? '—' : formatSI(v, 'speed', units, 1))
  const height = (v: number | null | undefined) => (v == null ? 'apogee' : formatSI(v, 'altitude', units))
  const speedUnit = unitFor('speed', units).symbol

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-semibold">Descent rates</h2>
        {data && (
          <p className="text-sm text-muted-foreground">
            {formatSI(data.mass_kg, 'mass', units, 2)} under the canopy (rocket and burnt-out motor).
            {data.apogee_agl_m == null
              ? ' Run the single flight to see the rate at apogee.'
              : ` Apogee ${formatSI(data.apogee_agl_m, 'altitude', units)} from the single flight.`}
          </p>
        )}
      </header>
      <ProblemNotice error={descent.error} />
      {data && (
        <div className="max-w-5xl overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="pb-2 font-normal">Device</th>
                <th className="pb-2 font-normal">Governs</th>
                <th className="pb-2 font-normal">CdS</th>
                <th className="pb-2 font-normal">Rate at the top</th>
                <th className="pb-2 font-normal">Rate at the bottom</th>
                <th className="pb-2 font-normal">Want at the bottom</th>
                <th className="pb-2 font-normal">CdS for that</th>
              </tr>
            </thead>
            <tbody>
              {data.devices.map((d) => (
                <tr key={d.name} className="border-t border-border align-top">
                  <td className="py-3 pr-4 font-medium">{d.name}</td>
                  <td className="py-3 pr-4">
                    {height(d.top_agl_m)} to {d.bottom_agl_m === 0 ? 'the ground' : height(d.bottom_agl_m)}
                  </td>
                  <td className="py-3 pr-4">{formatSI(d.cd_s_m2, 'area', units, 2)}</td>
                  <td className="py-3 pr-4">{speed(d.rate_top_ms)}</td>
                  <td className="py-3 pr-4 font-medium">{speed(d.rate_bottom_ms)}</td>
                  <td className="py-3 pr-4">
                    <TargetInput
                      label={`Wanted descent rate under ${d.name}`}
                      unit={speedUnit}
                      onChange={(si) =>
                        setTargets((t) => {
                          const next = { ...t }
                          if (si == null) delete next[d.name]
                          else next[d.name] = si
                          return next
                        })
                      }
                    />
                  </td>
                  <td className="py-3">
                    {d.cd_s_for_target_m2 != null && (
                      <span className="flex flex-wrap items-center gap-2">
                        {formatSI(d.cd_s_for_target_m2, 'area', units, 2)}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            edit((m) => {
                              const device = m.recovery?.devices?.find((x) => x.name === d.name)
                              if (device) device.cd_s_m2 = Number(d.cd_s_for_target_m2!.toFixed(4))
                            })
                          }
                        >
                          Use this CdS
                        </Button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/flight">
          The steady rate where drag balances weight, v = √(2mg / ρCdS), in the mission's atmosphere. Each device governs
          the descent from where it opens down to where the next one takes over; it is slowest at the bottom, in denser
          air, which is where IREC measures the drogue. A deploying device replaces the one before, as in the flight
          simulation. These are sizing estimates: the single flight, with deployment lag, is the answer.
        </Explainer>
      </div>
    </div>
  )
}

function TargetInput({ label, unit, onChange }: { label: string; unit: string; onChange: (si: number | null) => void }) {
  const units = usePrefs((s) => s.display)
  const [text, setText] = useState('')
  return (
    <span className="flex h-8 w-28 items-center rounded-md border border-border bg-background">
      <input
        aria-label={label}
        inputMode="decimal"
        value={text}
        placeholder="—"
        onChange={(e) => {
          setText(e.target.value)
          const n = Number(e.target.value)
          onChange(e.target.value.trim() !== '' && Number.isFinite(n) && n > 0 ? toSI(n, 'speed', units) : null)
        }}
        className="h-full min-w-0 flex-1 bg-transparent px-2 text-right tabular-nums outline-none"
      />
      <span className="pr-2 text-xs text-muted-foreground">{unit}</span>
    </span>
  )
}

export function Pane() {
  return (
    <RequireMission compact>
      <DevicesPane />
    </RequireMission>
  )
}

function DevicesPane() {
  const devices = useMissionStore((s) => s.draft?.recovery?.devices ?? [])
  const edit = useMissionStore((s) => s.edit)
  const editDevice = (i: number, recipe: (d: Device) => void) =>
    edit((m) => {
      const d = m.recovery?.devices?.[i]
      if (d) recipe(d)
    })
  const add = (preset: Device) =>
    edit((m) => {
      m.recovery ??= {}
      ;(m.recovery.devices ??= []).push(structuredClone(preset))
    })

  return (
    <div className="space-y-4 p-4">
      {devices.map((d, i) => (
        <DeviceEditor key={i} index={i} device={d} onEdit={(r) => editDevice(i, r)} onRemove={() => edit((m) => void m.recovery?.devices?.splice(i, 1))} />
      ))}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => add(PRESETS.drogue)}>
          <Plus /> Drogue
        </Button>
        <Button size="sm" onClick={() => add(PRESETS.main)}>
          <Plus /> Main
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        New devices start at placeholder sizes. Size them from the descent table, or from the canopy's Cd and area.
      </p>
    </div>
  )
}

function DeviceEditor({
  index,
  device,
  onEdit,
  onRemove,
}: {
  index: number
  device: Device
  onEdit: (recipe: (d: Device) => void) => void
  onRemove: () => void
}) {
  const path = `recovery.devices[${index}]`
  const nameIssues = useIssuesAt(`${path}.name`)
  return (
    <section className="space-y-3 rounded-md border border-border p-3">
      <div className="flex items-end gap-2">
        <label className="block flex-1 space-y-1 text-sm">
          <span>Name</span>
          <input
            value={device.name}
            onChange={(e) => onEdit((d) => void (d.name = e.target.value))}
            className="h-9 w-full rounded-md border border-border bg-background px-3"
          />
        </label>
        <Button size="sm" variant="ghost" aria-label={`Remove ${device.name || `device ${index + 1}`}`} onClick={onRemove}>
          <Trash2 />
        </Button>
      </div>
      {nameIssues.map((i) => (
        <p key={i.code} className="text-xs text-nogo">
          {i.message}
        </p>
      ))}
      <QuantityField
        schema="RecoveryDevice"
        name="cd_s_m2"
        path={`${path}.cd_s_m2`}
        label="CdS"
        quantity="area"
        decimals={3}
        value={device.cd_s_m2}
        onChange={(v) => onEdit((d) => void (d.cd_s_m2 = v))}
      />
      <label className="block space-y-1 text-sm">
        <span>Deploys</span>
        <select
          value={device.trigger.kind}
          onChange={(e) =>
            onEdit((d) => {
              d.trigger = e.target.value === 'apogee' ? { kind: 'apogee' } : { kind: 'altitude_agl', altitude_m: 300 }
            })
          }
          className="h-9 w-full rounded-md border border-border bg-background px-2"
        >
          <option value="apogee">At apogee</option>
          <option value="altitude_agl">At an altitude, descending</option>
        </select>
      </label>
      {device.trigger.kind === 'altitude_agl' && (
        <QuantityField
          schema="AtAltitude"
          name="altitude_m"
          path={`${path}.trigger.altitude_m`}
          label="Deployment altitude"
          quantity="altitude"
          decimals={0}
          value={device.trigger.altitude_m}
          onChange={(v) =>
            onEdit((d) => {
              if (d.trigger.kind === 'altitude_agl') d.trigger.altitude_m = v
            })
          }
        />
      )}
      <QuantityField
        schema="RecoveryDevice"
        name="lag_s"
        path={`${path}.lag_s`}
        label="Deployment lag"
        quantity="time"
        decimals={2}
        value={device.lag_s ?? 0}
        onChange={(v) => onEdit((d) => void (d.lag_s = v))}
      />
    </section>
  )
}
