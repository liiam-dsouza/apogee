import { useState } from 'react'
import { Link } from 'react-router'
import type { Mission } from '@/lib/api'
import { fromSI, toSI, unitFor, type Quantity } from '@/lib/units'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

type LaunchConditions = NonNullable<Mission['launch_conditions']>
type NumberKey = 'cloud_cover_pct' | 'cloud_base_m' | 'visibility_m' | 'wind_speed_ms' | 'wind_gust_ms'

/** `YYYY-MM-DDTHH:mm` in the user's time zone, for a datetime-local input. */
function toLocalInput(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** The sky at launch, for the launch-condition rules on the go/no-go board. Filled from a forecast hour, or by hand. */
export function LaunchConditionsEditor() {
  const lc: Partial<LaunchConditions> = useMissionStore((s) => s.draft?.launch_conditions) ?? {}
  const rules = useMissionStore((s) => s.draft?.constraints?.launch_rules)
  const forecastHour = useMissionStore((s) =>
    s.draft?.environment?.atmosphere?.kind === 'profile' ? s.draft.environment.atmosphere.valid_utc : null,
  )
  const edit = useMissionStore((s) => s.edit)
  const set = (recipe: (c: LaunchConditions) => void) => edit((d) => recipe((d.launch_conditions ??= { source: '' })))
  const number = (key: NumberKey) => (v: number | null) =>
    set((c) => {
      c[key] = v
    })

  return (
    <section className="space-y-3" aria-label="Launch conditions">
      <h2 className="text-sm font-semibold">Launch conditions</h2>
      <p className="text-xs text-muted-foreground">
        For the launch rules on the{' '}
        <Link to="/go-no-go" className="text-primary underline-offset-4 hover:underline">
          go/no-go board
        </Link>
        {rules ? '' : ' (choose them there)'}. Using a forecast hour fills these in; the range's briefing on the day
        beats it.
      </p>
      <label className="block space-y-1 text-sm">
        <span>Launch time (your time zone)</span>
        <input
          type="datetime-local"
          value={lc.launch_utc ? toLocalInput(lc.launch_utc) : ''}
          onChange={(e) =>
            set((c) => {
              c.launch_utc = e.target.value ? new Date(e.target.value).toISOString() : null
            })
          }
          className="h-9 w-full rounded-md border border-border bg-background px-2 tabular-nums"
        />
        {!lc.launch_utc && (
          <span className="block text-xs text-muted-foreground">
            {forecastHour ? 'Unset: the forecast hour in use.' : 'Unset: the daylight rule has no time to check.'}
          </span>
        )}
      </label>
      <div className="grid grid-cols-2 gap-3">
        <OptionalField label="Cloud cover" quantity={null} symbol="%" max={100} value={lc.cloud_cover_pct} onChange={number('cloud_cover_pct')} />
        <OptionalField label="Cloud base" quantity="altitude" value={lc.cloud_base_m} onChange={number('cloud_base_m')} />
      </div>
      <OptionalField label="Visibility" quantity="distance" value={lc.visibility_m} onChange={number('visibility_m')} />
      <div className="grid grid-cols-2 gap-3">
        <OptionalField
          label="Surface wind"
          quantity="speed"
          value={lc.wind_speed_ms}
          placeholder="flight's"
          onChange={number('wind_speed_ms')}
        />
        <OptionalField label="Gusts" quantity="speed" value={lc.wind_gust_ms} onChange={number('wind_gust_ms')} />
      </div>
      {lc.source && <p className="text-xs text-muted-foreground">From {lc.source}.</p>}
    </section>
  )
}

/** A number that may be left blank: unknown, so a rule on it has nothing to judge. */
function OptionalField({
  label,
  quantity,
  symbol,
  value,
  placeholder = 'unknown',
  max = Infinity,
  onChange,
}: {
  label: string
  quantity: Quantity | null
  symbol?: string
  value: number | null | undefined
  placeholder?: string
  max?: number
  onChange: (si: number | null) => void
}) {
  const units = usePrefs((s) => s.display)
  const [editing, setEditing] = useState<string | null>(null)
  const shown = (si: number) => (quantity ? fromSI(si, quantity, units) : si)
  const text = editing ?? (value == null ? '' : String(Number(shown(value).toPrecision(4))))
  return (
    <label className="block space-y-1 text-sm">
      <span>{label}</span>
      <span className="flex h-9 items-center rounded-md border border-border bg-background focus-within:border-primary">
        <input
          inputMode="decimal"
          value={text}
          placeholder={placeholder}
          onFocus={() => setEditing(text)}
          onBlur={() => setEditing(null)}
          onChange={(e) => {
            setEditing(e.target.value)
            const raw = e.target.value.trim()
            const n = Number(raw)
            if (raw === '') onChange(null)
            else if (Number.isFinite(n) && n >= 0 && n <= max) onChange(quantity ? toSI(n, quantity, units) : n)
          }}
          className="h-full min-w-0 flex-1 bg-transparent px-3 tabular-nums outline-none"
        />
        <span className="pr-3 text-muted-foreground">{symbol ?? (quantity ? unitFor(quantity, units).symbol : '')}</span>
      </span>
    </label>
  )
}
