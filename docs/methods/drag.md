# Drag: method

How Apogee estimates a rocket's drag from its shape, without OpenRocket,
RASAero or a wind tunnel. The **Rocket** section shows the result and what
makes it up; `simcore.aero.drag` computes it.

## What it needs

Only what the mission already describes: the body radius, nose shape and
length, boat-tail, fin outlines and thickness, and the motor's nozzle exit
radius. Two settings are the estimate's own:

- `rocket.surface_finish`: OpenRocket's finishes, from *mirror* to *rough*,
  each a roughness height (regular paint is 60 µm). The default is `normal`.
- `rocket.fins[].cross_section`: `square`, `rounded` or `airfoil` edges.
  The default is `square`, OpenRocket's default and the cautious choice.

A fin set with no `thickness_m` is estimated at 3 mm, and the mission shows a
warning until it has one.

Each of `rocket.drag.power_off` and `power_on` is `estimate: true` (the
default for a new rocket), a `table` of CD against Mach, or a `constant_cd`.
`drag.multiplier` scales whichever is used; the Monte Carlo spread and the
post-flight fit both act on it.

## The method

A component build-up, as OpenRocket does it: Niskanen, *Development of an Open
Source model rocket simulation software* (2009), section 3.4, and OpenRocket's
`BarrowmanDragCalculator`, `SymmetricComponentCalc` and `FinSetCalc`. Every CD
is referenced to the body tube's frontal area, as RocketPy's is.

| Part | What it is | Depends on |
| --- | --- | --- |
| Friction | Turbulent flat-plate skin friction, `1 / (1.50 ln Re − 5.6)²`, never below the roughness limit `0.032 (k/L)^0.2`, with a compressibility correction. Over the wetted area of nose, body and tail (times `1 + 1/(2·fineness)`) and both sides of every fin (times `1 + 2t/c`). | Mach, **Reynolds number**, finish |
| Nose | Wave drag from DATCOM tables for each shape, scaled for fineness; cones and ogives from a closed form above Mach 1. Zero below about Mach 0.9 for the tangent shapes. | Mach |
| Tail | A boat-tail's pressure drag from its fineness: none at 3 or more. | Mach |
| Fins | Leading-edge pressure (stagnation pressure for square edges, a fit for rounded), times cos² of the sweep; trailing-edge base drag (full for square, half for rounded, none for airfoil). | Mach |
| Base | `0.12 + 0.13 M²` (subsonic) over the aft end. **While the motor burns, the nozzle exit area is taken off**: the only difference between the power-on and power-off curves. | Mach |

The Reynolds number is on the rocket's length. In flight RocketPy passes it at
every step, from the air's density and viscosity where the rocket is, so the
friction term changes with speed and altitude, not just Mach. The Rocket
section and the motor finder, which need a curve against Mach alone, take
Reynolds number along the standard atmosphere at the site.

### Angle of attack

RocketPy applies drag along the rocket's axis, so the estimate uses
OpenRocket's axial correction: a smooth polynomial from 1 at 0° to 1.3 at 17°,
back to 0 at 90°, and negative beyond (flow from behind pushes the rocket
forward). The angle is the total of RocketPy's pitch and yaw angles of the
flow. The side force at an angle of attack is RocketPy's own (Barrowman
normal force), so nothing is counted twice.

### How it reaches RocketPy

`rocketpy.Rocket(power_off_drag=…, power_on_drag=…)` takes a function of
seven arguments: angle of attack (pitch and yaw), Mach, Reynolds number and
the three rotation rates. Everything but friction is tabulated against Mach
once, when the rocket is built (every 0.005 Mach to Mach 4); friction is
computed directly. A flight takes no longer than with a table.

## How good it is

The only independent drag curve in the repository is RocketPy's for its
Calisto rocket (`tests/fixtures/calisto/`). With a smooth finish and rounded
fins, the estimate is:

| Mach | 0.2 | 0.4 | 0.6 | 0.8 | 1.0 | 1.2 | 1.5 | 2.0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Estimate ÷ RocketPy's curve | 0.94 | 1.01 | 1.06 | 1.16 | 0.84 | 0.74 | 0.78 | 0.78 |

So: within about 15% below Mach 0.8, and **16–26% low from Mach 1 to 2**.
Component build-ups are known to underestimate the transonic drag rise; for a
rocket that goes supersonic, expect the estimate to be optimistic about apogee.
With the defaults (regular paint, square fins) Calisto's estimate is about 30%
above its curve subsonic, and it flies to 2,982 m against 3,305 m on the curve.
That spread is the honest size of the uncertainty from finish and fin edges
alone: set them to match the rocket as built.

`packages/simcore/tests/test_drag.py` checks these numbers, and
`tests/golden/` pins Calisto's flight on the estimate, so a change to the
method moves a test.

### Against a real flight

Luke on a K940 (`data/luke-k940-qrs.apg`, barometric log
`data/Flight Data/Luke-K940-LR.csv`), flown in the mission's stored weather:

| Drag | Predicted apogee | Fitted multiplier |
| --- | --- | --- |
| OpenRocket's table, from its saved simulation | 1,331 m | 1.40 |
| Estimate, as in `Luke.ork` (regular paint, airfoil fins) | 1,330 m | 1.40 |
| Estimate, defaults (regular paint, square fins) | 1,282 m | 1.28 |

Measured: 1,168 m. The estimate reproduces OpenRocket's drag for the same
rocket to within 1 m of apogee, which checks the port. Both overpredict this
flight by 14%: the fit puts all of that on drag, though the mass, motor and
weather can share it. One flight is not enough to say which; a multiplier
near 1.4 again on the next flight would say the method underestimates this
rocket's drag. The J760 log has no altitude channel, so it can't be fitted.

The real check is always a flown rocket: fit the drag multiplier in
**Post-flight**. A multiplier near 1 means the estimate is right for that
rocket; anything else is the correction to carry forward. Record it in
[the validation record](../validation/index.md).

## Not modelled

- Rail buttons and launch lugs (the mission has no sizes for them; usually
  under 2% of CD).
- Fin-body interference, fin cant, and fin tabs.
- Mach above 4: CD is held at its Mach 4 value.
- A finish per part: one finish covers the whole rocket. An OpenRocket import
  takes the finish most of its parts have.
