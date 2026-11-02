# Ballast: method

How the **Ballast** section finds the mass that trims apogee to a target, and
what it checks before recommending it.

## Ballast in the mission

`ballast` holds the bay's position (aft of the nose tip), the smallest step the
team can add (`increment_kg`), the most the bay holds, an optional target, and
`installed_kg`: the ballast in the rocket now. **Installed ballast is part of
every flight**, campaign and go/no-go judgement. It is added to the rocket as a
point mass at the bay (`simcore.ballast.with_ballast`):

- dry mass gains the ballast;
- the dry centre of mass moves toward the bay;
- transverse inertia gains the parallel-axis terms of both the ballast and the
  rocket about the new centre of mass;
- roll inertia is unchanged (a point on the axis).

The target is `ballast.target_apogee_m`, or the competition category's target
from **Go / no-go** when that is unset.

## The solve

Apogee falls steadily as mass is added, so the answer is a one-dimensional root:
Brent's method on ascent-only flights, to 5 g. Before searching, the bay's
two ends are flown. If the rocket is already short of the target with no
ballast, or still over it with the bay full, the solve says so (and which) and
shows the curve instead of a number.

The exact mass is rounded to the nearest whole increment, the way ballast is
actually added: *Add 3 × 50 g (150 g)*.

## What comes with the number

The number is never shown without these:

- **The nominal apogee at the rounded mass**, and how far it is from target.
- **A 90% band** from 100 Monte Carlo flights at that mass, so the answer reads
  "3,014 m nominal, 2,890 to 3,140 m for 90% of flights", not a false point.
- **Sensitivity**: the apogee change per 100 g near the answer, from one extra
  flight, so the team can reason about it.
- **The constraint report**: the mission's rules (profile and team) judged on
  the full flight and the campaign at that mass. Ballast moves the centre of
  mass, which changes stability and rail exit; heavier means more landing
  energy. If the mission has no rules, the brief's built-in checks are used:
  stability at rail exit at least 1.5 cal, rail exit at least 20 m/s,
  thrust-to-weight at least 5, touchdown under 11 m/s.

Any failing hard rule is shown above the number as *Do not fly this as it stands*.

A solve flies about 110 flights, so it runs as a job, and its answer is cached
by the mission's hash. `installed_kg` is left out of that hash, so installing
the answer doesn't invalidate it.

## Not built yet

The brief's general solver (any free variable: main deploy altitude for a drift
limit, rail angle for the boundary) is not built; this solves for ballast only.
