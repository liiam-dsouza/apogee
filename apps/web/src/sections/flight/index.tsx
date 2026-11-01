import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="Altitude, velocity, acceleration, Mach, dynamic pressure and stability margin against time."
      explainer="A single deterministic flight with the nominal value of every input. Useful for checking the design; not a prediction of what will happen on the day. Use Dispersion for that."
      methodsHref="/docs/methods/flight"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Run"
      fields={["Run flight","Ascent only","Ballast override","Overlay variants"]}
    />
  )
}
