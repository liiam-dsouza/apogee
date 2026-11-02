import { CircleAlert, CircleCheck, CircleHelp, CircleMinus, CircleX } from 'lucide-react'
import type { RuleResult } from '@/lib/api'
import { JUDGED, useMetricFormat } from '@/lib/metrics'
import { cn } from '@/lib/utils'

/**
 * Judged rules, one row each: status (icon and word), rule and source, value, limit, what it was judged on, clause.
 * On a phone each row becomes a card, its cells labelled from `data-label`.
 */
export function RuleTable({ rows }: { rows: RuleResult[] }) {
  const formatMetric = useMetricFormat()
  return (
    <table className="w-full max-w-6xl text-base max-md:block">
      <thead className="text-left text-xs text-muted-foreground max-md:hidden">
        <tr>
          <th className="pb-2 font-normal">Status</th>
          <th className="pb-2 font-normal">Rule</th>
          <th className="pb-2 font-normal">Value</th>
          <th className="pb-2 font-normal">Limit</th>
          <th className="pb-2 font-normal">Judged on</th>
          <th className="pb-2 font-normal">Reference</th>
        </tr>
      </thead>
      <tbody className="max-md:block max-md:space-y-3">
        {rows.map((r) => (
          <RuleRow key={r.id} row={r} formatMetric={formatMetric} />
        ))}
      </tbody>
    </table>
  )
}

const OUTCOME = {
  go: { label: 'Pass', icon: CircleCheck, className: 'text-go' },
  warn: { label: 'Warn', icon: CircleAlert, className: 'text-caution' },
  no_go: { label: 'Fail', icon: CircleX, className: 'text-nogo' },
  missing: { label: 'No result', icon: CircleHelp, className: 'text-muted-foreground' },
} as const

const SOURCE: Record<RuleResult['source'], string> = {
  profile: 'Profile',
  override: 'Team override',
  team: 'Team rule',
}

const CELL = 'py-3 pr-4 max-md:block max-md:p-0'
/** On a phone, the column heading sits above the value. */
const LABELLED = 'max-md:before:block max-md:before:text-xs max-md:before:text-muted-foreground max-md:before:content-[attr(data-label)]'

function RuleRow({ row, formatMetric }: { row: RuleResult; formatMetric: ReturnType<typeof useMetricFormat> }) {
  const o =
    row.status === 'not_applicable'
      ? { label: 'Does not apply', icon: CircleMinus, className: 'text-muted-foreground' }
      : OUTCOME[row.outcome]
  const fmt = (v: number) => formatMetric(row.metric, v, row.units)
  const limit =
    row.lower != null && row.upper != null
      ? `${fmt(row.lower)} to ${fmt(row.upper)}`
      : row.lower != null
        ? `at least ${fmt(row.lower)}`
        : `at most ${fmt(row.upper!)}`
  const values = [row.value_low, row.value_high].filter((x): x is number => x != null)
  const value =
    values.length === 2 && values[0] !== values[1]
      ? `${fmt(values[0])} to ${fmt(values[1])}`
      : values.length
        ? fmt(values[0])
        : '—'
  return (
    <tr className="border-t border-border align-top max-md:grid max-md:grid-cols-2 max-md:gap-x-4 max-md:gap-y-2 max-md:rounded-md max-md:border max-md:bg-surface max-md:p-3">
      <td className={cn(CELL, 'max-md:col-span-2')}>
        <span className={cn('flex items-center gap-1.5 font-medium whitespace-nowrap', o.className)}>
          <o.icon className="size-5" aria-hidden />
          {o.label}
        </span>
      </td>
      <td className={cn(CELL, 'max-md:col-span-2')}>
        <p>{row.label}</p>
        <p className="text-xs text-muted-foreground">
          {SOURCE[row.source]} · {row.severity}
        </p>
        {row.note && <p className="mt-1 text-xs text-muted-foreground">{row.note}</p>}
      </td>
      <td className={cn(CELL, LABELLED, 'tabular-nums')} data-label="Value">
        {value}
        {row.violation_share != null && row.violation_share > 0 && (
          <p className="text-xs text-muted-foreground">
            {(row.violation_share * 100).toFixed(row.violation_share < 0.1 ? 1 : 0)}% of flights outside
          </p>
        )}
      </td>
      <td className={cn(CELL, LABELLED, 'tabular-nums')} data-label="Limit">
        {limit}
      </td>
      <td className={cn(CELL, LABELLED, 'text-sm')} data-label="Judged on">
        {JUDGED[row.evaluate_on] ?? row.evaluate_on}
      </td>
      <td className={cn(CELL, LABELLED, 'text-sm text-muted-foreground md:pr-0')} data-label="Reference">
        {row.reference || '—'}
      </td>
    </tr>
  )
}
