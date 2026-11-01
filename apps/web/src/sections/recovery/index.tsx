import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="A descent profile showing where each device deploys and the descent rate it gives."
      explainer="Each recovery device fires on a trigger (apogee, an altitude above ground, or an expression) after a lag. Descent rate under canopy follows from the device CdS and the mass it carries."
      methodsHref="/docs/methods/recovery"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Devices"
      fields={["Drogue","Main","Add a device","Trigger","CdS","Deployment lag","Mass"]}
    />
  )
}
