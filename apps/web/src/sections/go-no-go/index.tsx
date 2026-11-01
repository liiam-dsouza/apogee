import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="One row per constraint, large enough to read at arm’s length in sunlight."
      explainer="Each constraint is a rule from the competition profile or the team, checked against the Monte Carlo distribution (P95 by default) rather than one nominal flight. Each row cites the rule it comes from."
      methodsHref="/docs/methods/constraints"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Constraint set"
      fields={["Competition profile","Category","Team overrides","Additional rules"]}
    />
  )
}
