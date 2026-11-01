import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="Histograms of apogee, rail exit velocity, max Mach and descent time, with percentiles and a tornado chart."
      explainer="Summaries of the last Monte Carlo campaign. Percentiles are taken over all samples; P(apogee > ceiling) and P(outside boundary) are counted directly, not assumed normal."
      methodsHref="/docs/methods/monte-carlo"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Inspect"
      fields={["Variable","Filter samples","Export CSV"]}
    />
  )
}
