import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="The thrust curve, annotated with total impulse, motor class and burn time."
      explainer="The motor is a thrust curve (.eng, .rse or a static-fire log) plus propellant and grain geometry. Total impulse is the area under the curve; mass flow follows from the propellant mass over the burn."
      methodsHref="/docs/methods/motor"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Motor"
      fields={["Library search","Upload .eng / .rse","Propellant mass","Grain geometry","Nozzle radius","Dry mass","Ignition delay"]}
    />
  )
}
