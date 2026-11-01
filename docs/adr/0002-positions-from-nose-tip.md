# 0002: Rocket positions are metres aft of the nose tip

**Status:** accepted, 2026-11-02

## Context

RocketPy places components on an axis with an arbitrary origin and a
configurable direction (`tail_to_nose` or `nose_to_tail`). Its examples put the
origin at the dry centre of mass. That keeps RocketPy flexible, but a mission
file written that way can't be checked by eye: "position −1.04956" means
nothing until you know where zero is. OpenRocket, the team's design tool,
measures from the nose tip.

## Decision

In the mission config every axial position on the rocket (nose, fins, tail,
rail buttons, motor, dry centre of mass, ballast bay) is **metres aft of the
nose tip**, so the nose tip is 0 and every position is positive. The engine
adapter passes these to RocketPy with `coordinate_system_orientation="nose_to_tail"`.

Positions *inside the motor* (grain centre of mass, dry centre of mass) stay
relative to the nozzle exit, as RocketPy and motor datasheets define them.

## Consequences

- Physical checks become plain comparisons: a centre of mass forward of the
  nose tip is negative; fins aft of the tail are beyond the rocket's length.
- OpenRocket import needs no change of origin, only of units.
- RocketPy examples must be converted (`x_ours = x_nose_tip − x_theirs` for a
  `tail_to_nose` example), as was done for the Calisto fixture.

## Rejected

- **RocketPy's centre-of-mass origin.** The origin moves whenever mass changes,
  including with ballast, which is exactly what the solver varies.
