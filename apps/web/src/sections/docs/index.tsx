import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="The documentation site, served from this machine so it works offline."
      explainer="Methods, the mission config reference, the system map and a fully worked example."
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Contents"
      fields={["Search","Start here","Methods","Config reference","Guides"]}
    />
  )
}
