import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="Truth events against what the flight computer detected, its live output, and pass/fail assertions."
      explainer="Replays a simulated flight into a real flight computer as realistic sensor data, with noise, saturation and the barometric Mach dip, then checks its events against the truth. Live charges must never be connected."
      methodsHref="/docs/guides/hil"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Session"
      fields={["Transport and port","Sensor models","Time scale","Trajectory to replay","Test harness acknowledgement","Start and abort"]}
    />
  )
}
