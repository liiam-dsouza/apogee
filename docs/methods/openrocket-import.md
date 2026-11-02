# OpenRocket import: method

How an `.ork` file becomes a mission's `rocket` and `recovery` sections, what
is approximated, and how the result is checked against OpenRocket itself.

## What comes across

| OpenRocket | Mission |
| --- | --- |
| Nose cone shape, length | `rocket.nose` (tangent ogive, conical, elliptical, parabolic, Von Kármán, LV-Haack) |
| Body tubes | `rocket.radius_m` (the largest) |
| Trapezoidal fin sets | `rocket.fins[]`; elliptical fins become a trapezoid of equal area |
| Aftmost transition | `rocket.tail` |
| Rail buttons | `rocket.rail_buttons` (first and last) |
| Motor mount | `rocket.motor_position_m` (aft end of the mount, plus overhang) |
| Every part's mass | `rocket.dry_mass_kg`, `dry_cg_m`, `dry_inertia` |
| Parachutes, streamers | `recovery.devices[]` (CdS from Cd and size; deploy event and delay) |
| Up-to-date simulation data | `rocket.drag` (CD against Mach, power on and off) |

Positions are metres aft of the nose tip in both tools ([ADR 0002](../adr/0002-positions-from-nose-tip.md)).

## Masses

A part with a **measured** override mass in OpenRocket keeps it exactly. Other
parts get the mass OpenRocket would compute: tubes, couplers, bulkheads and
rings from geometry and material density; the nose as a shell following its
exact profile; parachutes from canopy area and shroud lines; mass components
as entered. Moments of inertia are summed from simple shapes and are good to a
few percent.

## Drag

OpenRocket does not store a drag curve, but a saved simulation records CD and
Mach at every step. The importer takes the **up-to-date** simulation's ascent,
splits it at burnout into power-on and power-off, and averages CD in 0.01 Mach
bins. Beyond the Mach range flown, RocketPy holds CD constant. OpenRocket's
drag is reasonable subsonic and shaky transonic.

## Cross-checks

| Check | Against | Tolerance |
| --- | --- | --- |
| Dry mass | Liftoff mass minus motor mass | 2% |
| CG at liftoff | OpenRocket's CG at t = 0 | 1 cm |
| Pitch and roll inertia | OpenRocket's at t = 0 | 10%, 20% |
| Apogee, max Mach | Its saved results, flown here in ISA with its wind, site and rod | 3% |
| Centre of pressure | Its CP at the first sample with angle of attack under 1° and Mach ≥ 0.2 | 3 cm |
| Rail exit velocity | Reported, not judged: defined differently | — |

**Why CP is compared at near-zero angle of attack.** OpenRocket adds body lift
at angle of attack, which moves its CP forward; RocketPy's Barrowman CP does
not. For Lanius, OpenRocket's CP leaving the rod (4° angle of attack) is 13 cm
forward of its CP in calm flight. Compared at 0.1°, the two agree to 5 mm.

**Why rail exit velocity differs.** RocketPy counts rail exit when the upper
rail button leaves the rail, starting with the motor at the rail's base.
OpenRocket counts it when the rocket has travelled the whole rod length. For
Lanius that is 3.83 m of travel against 4.89 m: 21.0 against 24.4 m/s. RocketPy's
is the physical value for a rocket on rail buttons.

## Lanius (2026), for the record

| | Apogee import | OpenRocket |
| --- | --- | --- |
| Dry mass | 15.039 kg | 15.039 kg |
| CG at liftoff | 2.122 m | 2.122 m |
| Apogee (its conditions) | 3,128.4 m | 3,128.5 m |
| CP at Mach 0.20 | 2.558 m | 2.553 m |

## Not supported yet

Multi-stage designs (the sustainer is imported), freeform fins (mass counted,
no lift), pods, and more than one transition. Motors are named, not stored, in
`.ork` files: attach the `.eng` or fetch it from ThrustCurve.org.
