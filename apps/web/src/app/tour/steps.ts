/** One stop on the guided tour. */
export interface TourStep {
  title: string
  body: string
  /** Section to open first, e.g. '/rocket'. Unset: stay where the tour is. */
  route?: string
  /** `data-tour` value of the element to cut out. Unset, or not on screen: a centred card. */
  target?: string
  /** Docs page to read more, e.g. '/docs/methods/flight'. */
  docs?: string
}

export const TOUR_STEPS: TourStep[] = [
  {
    title: 'Welcome to Apogee',
    body: "Apogee takes a team from an OpenRocket design to a launch-day go/no-go, all on this laptop with no internet. The tour opens its own copy of Calisto, RocketPy's reference rocket, and flies it, so every section shows real numbers. Your own missions aren't touched.",
    docs: '/docs/start-here',
  },
  {
    title: 'Sections',
    body: 'Every part of the work is a section. They run top to bottom in the order you need them: mission setup, then analysis, then the field. Expand the rail with the arrow on its edge to see their names.',
    target: 'rail-sections',
  },
  {
    title: 'Missions',
    body: "A mission is everything about one flight: rocket, motor, recovery, site, weather and rules. Create one, import an .apg bundle from another machine, or export yours to share. Calisto (tour) is open now; taking the tour again resets it.",
    route: '/missions',
    target: 'centre',
    docs: '/docs/guides/first-flight',
  },
  {
    title: 'The open mission',
    body: 'The mission you are editing, with undo, redo and save. Edits are kept as a draft that survives a reload; save to keep them in the mission.',
    route: '/missions',
    target: 'mission-bar',
  },
  {
    title: 'Rocket',
    body: "Calisto's airframe, drawn to scale. Import your own design from OpenRocket in the pane on the right. Further down, the fin flutter check compares Calisto's 4 mm G10 fins' flutter speed with the flight's speed at every point of the ascent, and gives the thinnest safe fin.",
    route: '/rocket',
    target: 'centre',
    docs: '/docs/methods/flutter',
  },
  {
    title: 'Editing panes',
    body: 'Most sections have a pane on the right for editing, and the centre for results. Drag its edge to resize it, or hide it with the button at the top right.',
    route: '/rocket',
    target: 'pane',
    docs: '/docs/guides/openrocket-import',
  },
  {
    title: 'Motor',
    body: "Calisto's Cesaroni M1670: its thrust curve, impulse class and masses. Replace a motor by uploading an .eng file or fetching one from ThrustCurve.org.",
    route: '/motor',
    target: 'centre',
    docs: '/docs/methods/flight',
  },
  {
    title: 'Recovery',
    body: "Steady descent rates under Calisto's drogue and main, and the CdS for the rate you want. Below them, the flights with each part of the recovery failed, and the black powder for each bay, with whether its shear pins hold while the rocket coasts.",
    route: '/recovery',
    target: 'centre',
    docs: '/docs/methods/ejection',
  },
  {
    title: 'Site and weather',
    body: "Calisto's pad at Spaceport America, with its rail. Set the range boundary on the map, then fetch a forecast for launch day or enter the wind by hand. The forecast is copied into the mission, so it still flies offline.",
    route: '/site',
    target: 'centre',
    docs: '/docs/guides/launch-day-weather',
  },
  {
    title: 'Single flight',
    body: "Calisto has just been flown: apogee, rail exit, stability and the trajectory charts. Run your own mission from the pane. The same mission always gives the same result, so a re-run comes straight from the cache.",
    route: '/flight',
    target: 'pane',
    docs: '/docs/methods/flight',
  },
  {
    title: 'Dispersion',
    body: "A 60-flight Monte Carlo campaign of Calisto is running now: landing points appear as each batch lands, with the ellipses that hold 68, 95 and 99.7% of them. Tune each input's spread, or fly every sample with a recovery failure, in the pane.",
    route: '/dispersion',
    target: 'centre',
    docs: '/docs/methods/monte-carlo',
  },
  {
    title: 'Ballast',
    body: 'Solves for the ballast that puts apogee on target, rounded to the plates you have, with the 90% band and every rule checked at that mass.',
    route: '/ballast',
    target: 'centre',
    docs: '/docs/methods/ballast',
  },
  {
    title: 'Post-flight',
    body: 'Load the altimeter log after flying. Apogee overlays it on the prediction and fits the drag so the next prediction is better.',
    route: '/post-flight',
    target: 'centre',
    docs: '/docs/methods/post-flight',
  },
  {
    title: 'Go / no-go',
    body: "Calisto judged against AURC 2026's 10,000 ft category: every rule on the single flight and the campaign, with the clause it comes from and the expected score. GO only when every hard rule has been judged and passes.",
    route: '/go-no-go',
    target: 'centre',
    docs: '/docs/methods/constraints',
  },
  {
    title: 'Status',
    body: 'The open mission\'s state, whether the browser is online, and the job queue. At the field, this is where you see that Apogee is working offline.',
    target: 'status-bar',
    docs: '/docs/architecture/overview',
  },
  {
    title: 'Docs, settings and help',
    body: "The docs explain what every calculation assumes and where it is weak, offline. Settings holds the theme and units. Calisto (tour) stays open for you to explore; your own missions are in Missions. Press Help to take this tour again.",
    target: 'rail-footer',
    docs: '/docs/start-here',
  },
]
