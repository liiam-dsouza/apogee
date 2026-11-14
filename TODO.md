# To do

Features queued after reviewing StratoForge (sim.strato-forge-nv.com), plus our own ideas.
Done items move to [`PROGRESS.md`](PROGRESS.md).

## From StratoForge

1. [x] **Fin flutter check.** Flutter speed vs. max speed, the margin, and the thinnest
   safe fin. A board rule for it.
2. [x] **Ejection charges and shear pins.** Black powder grams from bay volume and target
   pressure (with a +25% backup); does the drag-separation force during coast stay under
   the pins' strength.
3. [x] **Recovery-failure outcomes.** Drogue fails / main fails / nothing opens: landing
   speed, energy and drift, as single flights and as Monte Carlo landing zones.
4. [x] **Launch-condition rules on the go/no-go board.** FAA Part 101.25 from the
   mission's weather: cloud cover over half the sky, cloud base vs. apogee, visibility,
   gusts over 20 mph, launching after sunset.
5. [x] **Motor finder.** Rank ThrustCurve motors that fit the mount for a target apogee,
   with rail exit speed, stability and thrust-to-weight, judged against the profile.
6. [ ] **Printable reports.** A mission report (geometry, stability, motor, aero, flight,
   recovery, dispersion, board) and a printable field checklist.
7. [ ] **Smaller items.** Cd-vs-Mach chart and drag breakdown; `.rse` and RockSim `.rkt`
   import; deploy settings per altimeter model.

## Our own

- [x] **Help tour.** A Help button in the rail (with Docs and Settings) that starts a
  guided tour: dimmed app, the explained part cut out, a description, a docs link, and
  Skip / Previous / Next. (Asked for 2026-11-11; done before #3.)

8. [ ] **What drives the spread.** Rank Monte Carlo inputs by how much of the apogee and
   drift variance each explains.
9. [ ] **Launch-day wind envelope.** Sweep wind against rail heading and tilt: the highest
   wind that's still GO, and the heading that keeps the 95% ellipse inside the boundary.
10. [ ] **Mission version history.** Keep every save, diff versions, and link each run to
    the version it flew.
11. [ ] **Known gaps.** Post-flight fits the descent and GPS track and feeds the
    validation record; static-fire data for team-built motors.
