import { Info } from 'lucide-react'
import { useId, useState } from 'react'
import { Tooltip } from '@/components/ui/tooltip'
import { fields, type FieldSchema } from '@/lib/api/fields.gen'
import { useIssuesAt } from '@/lib/mission/validation'
import { fromSI, toSI, unitFor, type Quantity } from '@/lib/units'
import { cn } from '@/lib/utils'
import { usePrefs } from '@/stores/prefs'

type FieldMeta = { description?: string; units?: string }

function meta(schema: FieldSchema, name: string): FieldMeta {
  return ((fields[schema] as Record<string, FieldMeta>)[name] ?? {}) as FieldMeta
}

/** Rounds away float noise from unit conversion without hiding real precision. */
function display(value: number, decimals: number): string {
  return Number(value.toFixed(decimals)).toString()
}

/**
 * A numeric mission field. Holds SI (degrees for angles); shows the user's
 * unit system. The tooltip is the schema description, so it can never
 * disagree with the API docs. Server validation issues for `path` show below.
 */
export function QuantityField({
  schema,
  name,
  path,
  label,
  quantity,
  value,
  onChange,
  decimals = 2,
}: {
  schema: FieldSchema
  name: string
  /** Path into the mission config, matching server issue paths. */
  path: string
  label: string
  quantity: Quantity
  value: number
  onChange: (si: number) => void
  decimals?: number
}) {
  const id = useId()
  const system = usePrefs((s) => s.display)
  const unit = unitFor(quantity, system)
  const { description, units } = meta(schema, name)
  const issues = useIssuesAt(path)
  const errorId = `${id}-errors`

  // While focused, the field keeps its own text so partial input ("-", "12.")
  // isn't reformatted mid-typing; otherwise it shows the stored value.
  const [editing, setEditing] = useState<string | null>(null)
  const text = editing ?? display(fromSI(value, quantity, system), decimals)

  const unparseable = text.trim() !== '' && !Number.isFinite(Number(text))

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        <label htmlFor={id} className="text-sm text-foreground">
          {label}
        </label>
        {description && (
          <Tooltip
            tappable
            content={
              <span className="flex flex-col gap-1">
                <span>{description}</span>
                {units && <span className="text-xs text-muted-foreground">Stored in {units}</span>}
              </span>
            }
          >
            <button type="button" aria-label={`About ${label}`} className="text-muted-foreground hover:text-foreground">
              <Info className="size-3.5" />
            </button>
          </Tooltip>
        )}
      </div>
      <div
        className={cn(
          'flex h-9 items-center rounded-md border bg-background focus-within:border-primary',
          issues.length > 0 || unparseable ? 'border-nogo' : 'border-border',
        )}
      >
        <input
          id={id}
          inputMode="decimal"
          value={text}
          aria-invalid={issues.length > 0 || unparseable}
          aria-describedby={issues.length > 0 ? errorId : undefined}
          onFocus={() => setEditing(text)}
          onBlur={() => setEditing(null)}
          onChange={(e) => {
            setEditing(e.target.value)
            const n = Number(e.target.value)
            if (e.target.value.trim() !== '' && Number.isFinite(n)) onChange(toSI(n, quantity, system))
          }}
          className="h-full min-w-0 flex-1 bg-transparent px-3 text-sm tabular-nums outline-none"
        />
        <span className="pr-3 text-sm text-muted-foreground">{unit.symbol}</span>
      </div>
      {(issues.length > 0 || unparseable) && (
        <ul id={errorId} className="text-xs text-nogo">
          {unparseable && <li>Enter a number.</li>}
          {issues.map((i) => (
            <li key={i.code}>{i.message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
