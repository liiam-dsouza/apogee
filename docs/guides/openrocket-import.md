# Import a rocket from OpenRocket

About five minutes. You need the team's `.ork` file and, ideally, the motor's
`.eng` thrust curve. For what is mapped and approximated, see
[the method](../methods/openrocket-import.md).

1. **Save the design in OpenRocket with an up-to-date simulation.** Run at least
   one simulation and save the file afterwards. Apogee takes the drag curves
   from that simulation's data, and compares its own flight against it.
2. **Open a mission.** In **Missions**, create one with **New mission** (or open
   an existing one) and choose **Open in editor**.
3. **Import.** Go to **Rocket**. In the pane, choose the design under **Design
   (.ork)** and, if you have it, the motor under **Motor thrust curve (.eng)**.
   Choose **Import and review**. Nothing changes in the mission yet.
4. **Read the review.** It shows:
   - **Comparison with OpenRocket.** Dry mass, centre of mass and inertia always;
     apogee, max Mach, rail exit and centre of pressure when there is a thrust
     curve. *Agrees* is within tolerance. *Check this* means the two tools disagree
     by more than the tolerance; find out why before trusting either.
     *Defined differently* means the tools measure the quantity differently
     (rail exit is the usual one).
   - **Warnings**, and parts that were approximated or are unsupported.
     Unsupported parts keep their mass, so the total still balances.
5. **No thrust curve?** If OpenRocket names a motor but doesn't store its
   curve, the review offers **Fetch … from ThrustCurve.org** (needs internet).
   Offline, download the `.eng` elsewhere, attach it and import again.
6. **Use it.** Choose **Use this rocket**. Rocket and recovery replace the
   mission's; the motor too if there was a curve. OpenRocket's launch-rod settings
   are only applied if you tick the box. They were set for OpenRocket's own
   launch site, so keep your site's rail unless they match.
7. **Save**, then fly it in **Single flight**.

## When the comparison disagrees

- **Mass or centre of mass.** Usually a part with an overridden mass in
  OpenRocket that isn't marked as an override, or a mass component placed
  relative to the wrong parent. Check the part list in the review.
- **Apogee by a few percent.** Expected if the drag curves differ. Apogee uses
  the curves from OpenRocket's own saved simulation, so re-run and re-save it
  after changing the design.
- **Rail exit.** Defined differently: OpenRocket reports the speed after the
  rocket has travelled the whole rod length, Apogee (RocketPy) when the upper
  rail button leaves the rail, which is sooner and slower.
