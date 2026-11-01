import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="Wind speed and direction against altitude, a hodograph and a wind rose."
      explainer="Weather is fetched once, cached and then treated as data, so every run is reproducible offline. A measured surface wind can be blended into a forecast aloft with a power law that fades out over the first few hundred metres."
      methodsHref="/docs/methods/wind"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Wind profile"
      fields={["Source","Fetch forecast","Manual altitude table","Surface measurement","Blend exponent (alpha)","Cache age"]}
    />
  )
}
