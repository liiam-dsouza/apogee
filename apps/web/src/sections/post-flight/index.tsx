import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="Recorded flight data over the prediction, with residuals and a fitted drag multiplier."
      explainer="Aligns an altimeter or telemetry log with the prediction in time, then fits a drag multiplier and thrust scale that minimise the residual. Fitted values feed the next campaign as priors."
      methodsHref="/docs/methods/calibration"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Flight data"
      fields={["Upload log","Column mapping","Time alignment","Compare against run"]}
    />
  )
}
