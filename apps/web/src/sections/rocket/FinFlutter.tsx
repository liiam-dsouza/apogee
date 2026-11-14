import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Play, Plus } from 'lucide-react'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { QuantityField } from '@/components/QuantityField'
import { Button } from '@/components/ui/button'
import { api, type FinMaterialPreset, type FlutterResponse } from '@/lib/api'
import type { FinSet } from '@/lib/rocket'
import { formatSI } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useFlightRuns, useRunFlight } from '@/sections/flight/run'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** A new fin set's starting point: 3 mm G10, the commonest high-power fin. */
const DEFAULT_THICKNESS_M = 0.003
const CUSTOM = 'custom'

/** Fin thickness and material per fin set, and the flutter margin they give on the single flight. */
export function FinFlutter() {
  const draft = useMissionStore((s) => s.draft!)
  const edit = useMissionStore((s) => s.edit)
  const fins = draft.rocket!.fins
  // A new run of this mission changes the answer without changing the draft.
  const runId = useFlightRuns((s) => s.byMission[draft.meta.id!]?.resultId)
  const materials = useQuery({
    queryKey: ['structures', 'fin-materials'],
    queryFn: api.listFinMaterials,
    staleTime: Infinity,
  })
  const flutter = useQuery({
    queryKey: ['structures', 'flutter', draft, runId],
    queryFn: () => api.finFlutter(draft),
    placeholderData: keepPreviousData,
  })
  const run = useRunFlight()
  const ready = Boolean(draft.motor && draft.site)
  const data = flutter.data

  return (
    <section aria-label="Fin flutter" className="max-w-4xl space-y-4">
      <header className="space-y-1">
        <h3 className="font-display text-xl font-semibold">Fin flutter</h3>
        {data && (
          <p className="text-sm text-muted-foreground">
            Asks for flutter speed at least {data.required_margin.toFixed(2)} × the rocket's speed: {data.required_by}
          </p>
        )}
      </header>
      <ProblemNotice error={flutter.error ?? materials.error} />
      <div className="space-y-4">
        {fins.map((f, i) => (
          <FinSetRow
            key={i}
            index={i}
            fins={f}
            presets={materials.data ?? []}
            result={data?.fin_sets.find((r) => r.fin_set === i + 1)}
            required={data?.required_margin}
            onEdit={(recipe) => edit((d) => recipe(d.rocket!.fins[i]))}
          />
        ))}
      </div>
      {data && !data.flight_run && fins.some((f) => f.thickness_m != null && f.material) && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            disabled={!ready || run.isPending}
            onClick={() => run.mutate({ draft, ascentOnly: false })}
          >
            <Play />
            {run.isPending ? 'Flying' : 'Run the flight to check'}
          </Button>
          {!ready && <span className="text-sm text-muted-foreground">The flight needs a motor and a launch site.</span>}
        </div>
      )}
      <ProblemNotice error={run.error} />
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/flutter">
          The flutter boundary of NACA TN 4197 (as in RocketPy and Apogee Components' Peak of Flight #291): flutter speed
          rises with the fin's stiffness and with thickness to the power 1.5, and falls in dense air. It is compared with
          the rocket's speed at every point of the ascent, so the tightest point is usually near burnout, low down. It
          treats the fin as a flat, isotropic plate clamped at the root: composite fins, fillets and tip-to-tip layups
          change the real answer, so keep a margin.
        </Explainer>
      </div>
    </section>
  )
}

function FinSetRow({
  index,
  fins,
  presets,
  result,
  required,
  onEdit,
}: {
  index: number
  fins: FinSet
  presets: FinMaterialPreset[]
  result: FlutterResponse['fin_sets'][number] | undefined
  required: number | undefined
  onEdit: (recipe: (f: FinSet) => void) => void
}) {
  const units = usePrefs((s) => s.display)
  const path = `rocket.fins[${index}]`
  const label = `Fin set ${index + 1}`
  const material = fins.material
  const thickness = fins.thickness_m

  if (thickness == null || !material) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-border p-3">
        <span className="text-sm">
          <span className="font-medium">{label}</span>{' '}
          <span className="text-muted-foreground">
            {thickness == null ? 'has no thickness or material' : 'has no material'}, so flutter isn't checked.
          </span>
        </span>
        <Button
          size="sm"
          variant="ghost"
          disabled={presets.length === 0}
          onClick={() =>
            onEdit((f) => {
              const g10 = presets[0]
              f.thickness_m ??= DEFAULT_THICKNESS_M
              f.material ??= { name: g10.name, shear_modulus_pa: g10.shear_modulus_pa }
            })
          }
        >
          <Plus />
          Add thickness and material
        </Button>
      </div>
    )
  }

  const preset = presets.find((p) => p.name === material.name && p.shear_modulus_pa === material.shear_modulus_pa)
  const flutter = result?.flutter
  const tone =
    flutter == null || required == null
      ? ''
      : flutter.min_margin >= required
        ? 'text-go'
        : flutter.min_margin >= 1
          ? 'text-caution'
          : 'text-nogo'

  return (
    <div className="grid gap-4 rounded-md border border-border p-3 md:grid-cols-[minmax(0,18rem)_1fr]">
      <div className="space-y-3">
        <span className="text-sm font-medium">{label}</span>
        <label className="block space-y-1 text-sm">
          <span>Material</span>
          <select
            value={preset?.id ?? CUSTOM}
            onChange={(e) => {
              const p = presets.find((x) => x.id === e.target.value)
              onEdit((f) => {
                f.material = p
                  ? { name: p.name, shear_modulus_pa: p.shear_modulus_pa }
                  : { name: 'Custom', shear_modulus_pa: f.material?.shear_modulus_pa ?? presets[0].shear_modulus_pa }
              })
            }}
            className="h-9 w-full rounded-md border border-border bg-background px-2"
          >
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
            <option value={CUSTOM}>{preset ? 'Custom' : `${material.name} (own value)`}</option>
          </select>
          {preset?.note && <span className="block text-xs text-muted-foreground">{preset.note}</span>}
        </label>
        <QuantityField
          schema="FinMaterial"
          name="shear_modulus_pa"
          path={`${path}.material.shear_modulus_pa`}
          label="Shear modulus"
          quantity="modulus"
          decimals={2}
          value={material.shear_modulus_pa}
          onChange={(v) =>
            onEdit((f) => {
              // A changed number is the team's own value, not the preset's.
              f.material = { name: preset ? 'Custom' : (f.material?.name ?? 'Custom'), shear_modulus_pa: v }
            })
          }
        />
        <QuantityField
          schema="TrapezoidalFins"
          name="thickness_m"
          path={`${path}.thickness_m`}
          label="Thickness"
          quantity="thickness"
          decimals={2}
          value={thickness}
          onChange={(v) => onEdit((f) => void (f.thickness_m = v))}
        />
        <Button
          size="sm"
          variant="ghost"
          onClick={() =>
            onEdit((f) => {
              f.material = null
            })
          }
        >
          Stop checking this fin set
        </Button>
      </div>
      <div className="space-y-3">
        {flutter ? (
          <>
            <p className={cn('font-display text-3xl font-semibold tabular-nums', tone)}>
              {flutter.min_margin.toFixed(2)} ×
              <span className="ml-2 align-middle text-sm font-normal text-muted-foreground">
                lowest flutter margin in the ascent
              </span>
            </p>
            <dl className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-6 gap-y-3 text-sm">
              <Fact k="Where" v={`${formatSI(flutter.altitude_agl_m, 'altitude', units)} up, ${flutter.time_s.toFixed(1)} s`} />
              <Fact k="Rocket speed there" v={formatSI(flutter.speed_ms, 'speed', units)} />
              <Fact k="Flutter speed there" v={formatSI(flutter.flutter_speed_ms, 'speed', units)} />
              {result?.thinnest_m != null && required != null && (
                <Fact
                  k={`Thinnest fin for ${required.toFixed(2)} ×`}
                  v={formatSI(result.thinnest_m, 'thickness', units, 2)}
                />
              )}
            </dl>
            {result?.thinnest_m != null && Math.abs(result.thinnest_m - thickness) > 1e-5 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onEdit((f) => void (f.thickness_m = Number(result.thinnest_m!.toFixed(5))))}
              >
                Use the thinnest thickness
              </Button>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Run the single flight with these fins to see the margin.
          </p>
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
