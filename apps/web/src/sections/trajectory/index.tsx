import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="The flight path in 3D over terrain, with the wind field and the landing point."
      explainer="Draws the trajectory from the most recent flight result. The wind vectors are the resolved profile the flight used, not live data."
      methodsHref="/docs/methods/flight"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="View"
      fields={["Camera presets","Playback","Show wind field","Show terrain"]}
    />
  )
}
