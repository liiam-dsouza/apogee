import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="The recommended ballast, the apogee-against-mass curve with the target marked, and the constraint report."
      explainer="Finds the ballast mass that puts the nominal apogee on target (Brent’s method, ascent-only flights), rounds it to the plates you actually have, then re-checks every constraint at that mass. A small Monte Carlo gives the confidence band."
      methodsHref="/docs/methods/ballast"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Solve"
      fields={["Target apogee","Bay position","Increment","Minimum and maximum","Solve"]}
    />
  )
}
