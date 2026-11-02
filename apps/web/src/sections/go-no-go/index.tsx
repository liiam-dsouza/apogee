import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { CircleAlert, CircleCheck, CircleHelp, CircleMinus, CircleX, Plus, ShieldAlert, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Explainer } from '@/components/Explainer'
import { ProblemNotice } from '@/components/ProblemNotice'
import { RequireMission } from '@/components/RequireMission'
import { Button } from '@/components/ui/button'
import { api, type ConstraintSettings, type RuleResult } from '@/lib/api'
import { useCampaign } from '@/lib/campaign'
import { fromSI, toSI, unitFor, type Quantity } from '@/lib/units'
import { cn } from '@/lib/utils'
import { useMissionStore } from '@/stores/mission'
import { usePrefs } from '@/stores/prefs'

/** A team rule as the mission stores it. */
type Constraint = NonNullable<ConstraintSettings['additional']>[number]

/** How each metric converts to the user's units; null shows it as stored. */
const METRIC_QUANTITY: Record<string, Quantity | null> = {
  apogee_agl_m: 'altitude',
  main_deploy_agl_m: 'altitude',
  drift_m: 'distance',
  rail_exit_velocity_ms: 'speed',
  landing_speed_ms: 'speed',
  drogue_descent_rate_ms: 'speed',
  max_acceleration_ms2: 'acceleration',
  max_dynamic_pressure_pa: 'dynamic_pressure',
  landing_kinetic_energy_j: 'energy',
}

const METRIC_LABEL: Record<string, string> = {
  apogee_agl_m: 'Apogee above the pad',
  rail_exit_velocity_ms: 'Rail exit velocity',
  stability_margin_at_rail_exit_cal: 'Stability at rail exit (cal)',
  min_stability_margin_cal: 'Lowest stability margin (cal)',
  max_stability_margin_cal: 'Highest stability margin (cal)',
  stability_margin_at_launch_pct_length: 'Stability at launch (% of length)',
  min_stability_margin_pct_length: 'Lowest stability (% of length)',
  max_stability_margin_pct_length: 'Highest stability (% of length)',
  thrust_to_weight: 'Thrust to weight',
  max_mach: 'Max Mach',
  max_acceleration_ms2: 'Max acceleration',
  max_dynamic_pressure_pa: 'Max dynamic pressure',
  landing_speed_ms: 'Touchdown speed',
  landing_kinetic_energy_j: 'Landing kinetic energy',
  main_deploy_agl_m: 'Main deployment altitude',
  drogue_descent_rate_ms: 'Descent rate under drogue',
  descent_time_s: 'Descent time',
  drift_m: 'Drift from the pad',
  flight_time_s: 'Flight time',
}

/** Where a new team rule starts (SI), to be edited: typical competition limits. */
const STARTING_LIMIT: Record<string, { min?: number; max?: number }> = {
  apogee_agl_m: { max: 3048 },
  rail_exit_velocity_ms: { min: 15 },
  stability_margin_at_rail_exit_cal: { min: 1.5 },
  min_stability_margin_cal: { min: 1.5 },
  max_stability_margin_cal: { max: 6 },
  stability_margin_at_launch_pct_length: { max: 18 },
  min_stability_margin_pct_length: { min: 7.5 },
  max_stability_margin_pct_length: { max: 25 },
  thrust_to_weight: { min: 5 },
  max_mach: { max: 1 },
  max_acceleration_ms2: { max: 200 },
  max_dynamic_pressure_pa: { max: 100_000 },
  landing_speed_ms: { max: 11 },
  landing_kinetic_energy_j: { max: 100 },
  main_deploy_agl_m: { max: 457.2 },
  drogue_descent_rate_ms: { min: 20, max: 40 },
  descent_time_s: { max: 180 },
  drift_m: { max: 1500 },
  flight_time_s: { max: 300 },
}

const JUDGED: Record<string, string> = {
  nominal: 'Single flight',
  p50: 'Half of flights',
  p95: '95% of flights',
  p99: '99% of flights',
  worst: 'Every flight',
}

function useMetricFormat() {
  const units = usePrefs((s) => s.units)
  return (metric: string, si: number, storedUnits = '') => {
    const q = METRIC_QUANTITY[metric]
    const shown = q ? fromSI(si, q, units) : si
    const symbol = q ? unitFor(q, units).symbol : storedUnits === '1' ? '' : storedUnits
    const digits = Math.abs(shown) >= 100 ? 0 : Math.abs(shown) >= 10 ? 1 : 2
    return `${shown.toLocaleString(undefined, { maximumFractionDigits: digits })}${symbol ? ` ${symbol}` : ''}`
  }
}

function useBoard() {
  const draft = useMissionStore((s) => s.draft)
  // Refetch as the campaign fills in; the server finds the flight and campaign by the mission's hash.
  const campaign = useCampaign(draft?.meta.id)
  return useQuery({
    queryKey: ['go-no-go', draft, campaign.data?.state.samples_done],
    queryFn: () => api.goNoGoBoard(draft!),
    enabled: Boolean(draft),
    placeholderData: keepPreviousData,
  })
}

export function Centre() {
  return (
    <RequireMission>
      <BoardCentre />
    </RequireMission>
  )
}

const VERDICT = {
  go: { label: 'GO', className: 'text-go', icon: CircleCheck, detail: 'Every hard rule passes.' },
  no_go: { label: 'NO-GO', className: 'text-nogo', icon: CircleX, detail: 'A hard rule fails.' },
  incomplete: {
    label: 'NOT JUDGED',
    className: 'text-caution',
    icon: CircleHelp,
    detail: 'A hard rule has no result to judge yet.',
  },
} as const

function BoardCentre() {
  const board = useBoard()
  const settings = useMissionStore((s) => s.draft?.constraints)
  const formatMetric = useMetricFormat()
  const data = board.data
  const noRules = !settings?.profile && !(settings?.additional ?? []).length

  if (noRules) {
    return (
      <div className="flex h-full flex-col justify-end gap-3 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          No rules yet. Choose a competition profile in the pane, or add the team's own.
        </p>
      </div>
    )
  }

  const v = data ? VERDICT[data.board.verdict] : null
  return (
    <div className="h-full space-y-6 overflow-y-auto p-6">
      <ProblemNotice error={board.error} />
      {data && v && (
        <>
          <header className="flex flex-wrap items-end gap-x-8 gap-y-3">
            <div>
              <p className={cn('flex items-center gap-3 font-display text-6xl font-bold tracking-tight', v.className)}>
                <v.icon className="size-12" aria-hidden />
                {v.label}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{v.detail}</p>
            </div>
            <Basis data={data} />
          </header>

          {data.board.profile && !data.board.profile.verified && (
            <p className="flex items-start gap-2 rounded-md border border-caution/50 bg-caution/10 p-3 text-sm">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
              <span>
                <strong>{data.board.profile.name}</strong> was transcribed from the rules documents but has not been
                checked by the team. Check each rule against its reference before relying on this board.
              </span>
            </p>
          )}

          {data.board.score && <ScoreCard score={data.board.score} formatMetric={formatMetric} />}

          <table className="w-full max-w-6xl text-base">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="pb-2 font-normal">Status</th>
                <th className="pb-2 font-normal">Rule</th>
                <th className="pb-2 font-normal">Value</th>
                <th className="pb-2 font-normal">Limit</th>
                <th className="pb-2 font-normal">Judged on</th>
                <th className="pb-2 font-normal">Reference</th>
              </tr>
            </thead>
            <tbody>
              {data.board.rows.map((r) => (
                <BoardRow key={r.id} row={r} formatMetric={formatMetric} />
              ))}
            </tbody>
          </table>
        </>
      )}
      <div className="max-w-xl">
        <Explainer methodsHref="/docs/methods/constraints">
          Each rule is checked against the Monte Carlo campaign (95% of flights by default) rather than one flight:
          drift and landing limits are about what will happen, not what one simulation did. A rule with no result to
          judge is never counted as passing. Hard rules decide GO or NO-GO; scoring and advisory rules only warn.
        </Explainer>
      </div>
    </div>
  )
}

function Basis({ data }: { data: NonNullable<ReturnType<typeof useBoard>['data']> }) {
  const { flight, campaign } = data
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Single flight</dt>
      <dd>
        {flight.available ? (
          'Run for this mission'
        ) : (
          <Link to="/flight" className="text-primary underline-offset-4 hover:underline">
            Not run for this mission
          </Link>
        )}
      </dd>
      <dt className="text-muted-foreground">Campaign</dt>
      <dd>
        {campaign.samples_done > 0 ? (
          `${campaign.samples_done} of ${campaign.samples} flights`
        ) : (
          <Link to="/dispersion" className="text-primary underline-offset-4 hover:underline">
            Not run for this mission
          </Link>
        )}
      </dd>
    </dl>
  )
}

function ScoreCard({
  score,
  formatMetric,
}: {
  score: NonNullable<NonNullable<ReturnType<typeof useBoard>['data']>['board']['score']>
  formatMetric: ReturnType<typeof useMetricFormat>
}) {
  const pts = (p: number | null | undefined) => (p == null ? '—' : Math.round(p).toString())
  return (
    <section aria-label="Apogee score" className="flex flex-wrap gap-x-10 gap-y-3 rounded-md border border-border p-4">
      <div>
        <p className="text-xs text-muted-foreground">Expected apogee score</p>
        <p className="font-display text-3xl font-semibold tabular-nums">
          {pts(score.expected)} <span className="text-base text-muted-foreground">of {score.max_points}</span>
        </p>
        <p className="text-xs text-muted-foreground">Mean over the campaign</p>
      </div>
      <Stat label="Single flight" value={pts(score.nominal)} />
      <Stat label="95% of flights score at least" value={pts(score.p5)} />
      <Stat label="Target" value={formatMetric('apogee_agl_m', score.target_m)} />
      <p className="basis-full text-xs text-muted-foreground">
        {score.formula}. {score.reference}.
      </p>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-display text-xl font-semibold tabular-nums">{value}</p>
    </div>
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

function BoardRow({ row, formatMetric }: { row: RuleResult; formatMetric: ReturnType<typeof useMetricFormat> }) {
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
    <tr className="border-t border-border align-top">
      <td className="py-3 pr-4">
        <span className={cn('flex items-center gap-1.5 font-medium whitespace-nowrap', o.className)}>
          <o.icon className="size-5" aria-hidden />
          {o.label}
        </span>
      </td>
      <td className="py-3 pr-4">
        <p>{row.label}</p>
        <p className="text-xs text-muted-foreground">
          {SOURCE[row.source]} · {row.severity}
        </p>
        {row.note && <p className="mt-1 text-xs text-muted-foreground">{row.note}</p>}
      </td>
      <td className="py-3 pr-4 tabular-nums">
        {value}
        {row.violation_share != null && row.violation_share > 0 && (
          <p className="text-xs text-muted-foreground">
            {(row.violation_share * 100).toFixed(row.violation_share < 0.1 ? 1 : 0)}% of flights outside
          </p>
        )}
      </td>
      <td className="py-3 pr-4 tabular-nums">{limit}</td>
      <td className="py-3 pr-4 text-sm">{JUDGED[row.evaluate_on] ?? row.evaluate_on}</td>
      <td className="py-3 text-sm text-muted-foreground">{row.reference || '—'}</td>
    </tr>
  )
}

// --- Pane: the rule set -----------------------------------------------------------

export function Pane() {
  return (
    <RequireMission compact>
      <RulesPane />
    </RequireMission>
  )
}

function useEditConstraints() {
  const edit = useMissionStore((s) => s.edit)
  return (recipe: (c: ConstraintSettings) => void) => edit((d) => recipe((d.constraints ??= {})))
}

function RulesPane() {
  const settings = useMissionStore((s) => s.draft?.constraints) ?? {}
  const editConstraints = useEditConstraints()
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.listProfiles, staleTime: Infinity })
  const profile = profiles.data?.find((p) => p.id === settings.profile)

  return (
    <div className="space-y-6 p-4">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Competition</h2>
        <label className="block space-y-1 text-sm">
          <span>Profile</span>
          <select
            value={settings.profile ?? ''}
            onChange={(e) =>
              editConstraints((c) => {
                c.profile = e.target.value || null
                c.category = null
                c.overrides = {}
              })
            }
            className="h-9 w-full rounded-md border border-border bg-background px-2"
          >
            <option value="">None (team rules only)</option>
            {profiles.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {profile && (
          <>
            <label className="block space-y-1 text-sm">
              <span>Category</span>
              <select
                value={settings.category ?? ''}
                onChange={(e) => editConstraints((c) => void (c.category = e.target.value || null))}
                className="h-9 w-full rounded-md border border-border bg-background px-2"
              >
                <option value="">Choose a category</option>
                {profile.categories?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-xs text-muted-foreground">
              {profile.rules_version}. {profile.verified ? 'Checked against the rules.' : 'Not yet checked by the team.'}
            </p>
            {profile.notes && <p className="text-xs text-muted-foreground">{profile.notes}</p>}
          </>
        )}
        <ProblemNotice error={profiles.error} />
      </section>

      {profile && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Profile rules</h2>
          <p className="text-xs text-muted-foreground">Untick a rule to drop it for this mission, or judge it differently.</p>
          <ul className="space-y-2">
            {profile.constraints.map((rule) => {
              const override = settings.overrides?.[rule.id]
              const on = !override?.disabled
              return (
                <li key={rule.id} className="space-y-1">
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={on}
                      onChange={(e) =>
                        editConstraints((c) => {
                          const o = { ...(c.overrides?.[rule.id] ?? {}), disabled: !e.target.checked }
                          c.overrides = { ...c.overrides, [rule.id]: o }
                        })
                      }
                    />
                    <span className={cn(!on && 'text-muted-foreground line-through')}>{rule.label || rule.id}</span>
                  </label>
                  {on && (
                    <JudgedOnSelect
                      label={`Judge ${rule.label || rule.id} on`}
                      value={override?.evaluate_on ?? rule.evaluate_on ?? 'p95'}
                      onChange={(v) =>
                        editConstraints((c) => {
                          c.overrides = {
                            ...c.overrides,
                            [rule.id]: { disabled: false, ...c.overrides?.[rule.id], evaluate_on: v },
                          }
                        })
                      }
                    />
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      <TeamRules settings={settings} />
    </div>
  )
}

function JudgedOnSelect({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: Constraint['evaluate_on']) => void
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value as Constraint['evaluate_on'])}
      className="ml-6 h-8 rounded-md border border-border bg-background px-2 text-sm"
    >
      {Object.entries(JUDGED).map(([k, v]) => (
        <option key={k} value={k}>
          {v}
        </option>
      ))}
    </select>
  )
}

function TeamRules({ settings }: { settings: ConstraintSettings }) {
  const editConstraints = useEditConstraints()
  const units = usePrefs((s) => s.units)
  const rules = settings.additional ?? []
  const [metric, setMetric] = useState('drift_m')

  const setLimit = (i: number, key: 'min' | 'max', text: string) =>
    editConstraints((c) => {
      const rule = c.additional?.[i]
      if (!rule) return
      const q = METRIC_QUANTITY[rule.metric]
      const n = Number(text)
      rule[key] = text.trim() === '' || !Number.isFinite(n) ? null : q ? toSI(n, q, units) : n
    })

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Team rules</h2>
      {rules.map((rule, i) => {
        const q = METRIC_QUANTITY[rule.metric]
        const shown = (si: number | null | undefined) =>
          si == null ? '' : String(Number((q ? fromSI(si, q, units) : si).toPrecision(6)))
        const unit = q ? unitFor(q, units).symbol : ''
        return (
          <div key={i} className="space-y-2 rounded-md border border-border p-2">
            <div className="flex items-center gap-2">
              <span className="flex-1 text-sm">{METRIC_LABEL[rule.metric] ?? rule.metric}</span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Remove team rule ${i + 1}`}
                onClick={() => editConstraints((c) => void c.additional?.splice(i, 1))}
              >
                <Trash2 />
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <LimitField label={`At least${unit ? ` (${unit})` : ''}`} value={shown(rule.min)} onChange={(t) => setLimit(i, 'min', t)} />
              <LimitField label={`At most${unit ? ` (${unit})` : ''}`} value={shown(rule.max)} onChange={(t) => setLimit(i, 'max', t)} />
            </div>
            <JudgedOnSelect
              label={`Judge team rule ${i + 1} on`}
              value={rule.evaluate_on ?? 'p95'}
              onChange={(v) => editConstraints((c) => void (c.additional![i].evaluate_on = v))}
            />
          </div>
        )
      })}
      <div className="flex gap-2">
        <select
          aria-label="Metric for a new team rule"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-sm"
        >
          {Object.entries(METRIC_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          onClick={() =>
            editConstraints((c) => {
              const id = `team_${metric}_${(c.additional?.length ?? 0) + 1}`
              const rule: Constraint = {
                id,
                label: '',
                reference: 'Team rule',
                metric: metric as Constraint['metric'],
                ...STARTING_LIMIT[metric],
                severity: 'hard',
                evaluate_on: 'p95',
              }
              c.additional = [...(c.additional ?? []), rule]
            })
          }
        >
          <Plus /> Add
        </Button>
      </div>
    </section>
  )
}

function LimitField({ label, value, onChange }: { label: string; value: string; onChange: (text: string) => void }) {
  const [editing, setEditing] = useState<string | null>(null)
  return (
    <label className="block space-y-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <input
        inputMode="decimal"
        value={editing ?? value}
        onFocus={() => setEditing(value)}
        onBlur={() => setEditing(null)}
        onChange={(e) => {
          setEditing(e.target.value)
          onChange(e.target.value)
        }}
        className="h-8 w-full rounded-md border border-border bg-background px-2 text-sm tabular-nums"
      />
    </label>
  )
}
