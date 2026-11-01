import { CentreStub, PaneStub } from '@/components/SectionStub'

export function Centre() {
  return (
    <CentreStub
      summary="Two or more runs overlaid on every chart, with the config differences listed."
      explainer="Answers “why did this change?” by putting runs side by side and diffing the mission configs that produced them."
      methodsHref="/docs/guides/compare"
    />
  )
}

export function Pane() {
  return (
    <PaneStub
      title="Runs"
      fields={["Select runs","Series to show"]}
    />
  )
}
