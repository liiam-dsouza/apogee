import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="A to-scale side view of the airframe with CG and CP marked and the stability margin read out."
      explainer="Geometry and mass come from an OpenRocket import or manual entry. CP is computed from the aerodynamic surfaces (Barrowman), CG from the mass components. Stability margin is the distance between them in calibers."
      methodsHref="/docs/methods/stability"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Components"
      fields={["Nose cone","Body tubes and transitions","Fins","Mass components","Rail buttons","Drag curve source","Import from OpenRocket"]}
    />
  )
}
