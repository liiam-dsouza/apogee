# Single flight: method

What the **Single flight** section computes, what it assumes, and where it is
weak. Every result's provenance panel names the inputs that produced it.

## What it is

One deterministic six-degree-of-freedom flight, simulated by
[RocketPy](https://docs.rocketpy.org) 1.13.0, with the **nominal** value of
every input: no wind uncertainty, motor variation or drag error. It answers
"what does this design do?", not "what will happen on the day". The Dispersion
section, which samples uncertain inputs, answers the second.

## How a mission becomes a flight

`simcore.engine` is the only code that talks to RocketPy:

| Mission | RocketPy |
| --- | --- |
| Positions, metres aft of the nose tip ([ADR 0002](../adr/0002-positions-from-nose-tip.md)) | `coordinate_system_orientation="nose_to_tail"` |
| `motor.thrust_curve` (.eng asset) | parsed by simcore, passed as points; a (0, 0) point is prepended, as RocketPy's own reader does |
| `rocket.drag` tables (CD vs Mach) | parsed by simcore, passed as a **linearly** interpolated `Function`, times `drag.multiplier` |
| `recovery.devices` | `add_parachute`, trigger noise **zero** |
| `environment` | standard atmosphere, or a resolved profile (with any measured surface wind blended in) as `custom_atmosphere`; see [weather](weather.md) |
| `site` | `Environment` location and elevation; rail length, inclination, heading |

## Assumptions

- **Rigid body, constant aerodynamics in roll.** RocketPy's standard equations of motion.
- **Drag depends on Mach only.** Two curves: motor burning and motor off.
- **Linear interpolation between drag-table points.** RocketPy builds a
  Python-list drag source with a cubic spline but a CSV path with linear
  interpolation. A spline can overshoot between measured points, so simcore
  always passes an explicit linear `Function`.
- **Parachutes open fully after `lag_s`**; no inflation dynamics or opening shock model.
- **Landing kinetic energy treats the whole rocket as one body.** Competition
  limits are usually per independently descending section; that split is not modelled yet.
- **Standard atmosphere has no wind.** Use it for sanity checks only.

## Determinism, and its limits

The same mission on the same platform gives **byte-identical** results:
solver tolerance (`rtol=1e-6`), time span (`max_time=600 s`) and parachute
trigger noise (zero) are fixed. Results are cached by a hash of the mission,
the RocketPy version and the simcore version.

Across platforms they are not identical. The same NumPy and SciPy on macOS
arm64 and Linux aarch64 differ by up to 6 × 10⁻⁵ relative (12 cm of apogee for
Calisto), because the compiled ODE solver and maths libraries round
differently. That is far below any physical uncertainty, but it means a number
computed on a laptop and one computed on the lab server can differ in the last
digits. The golden-flight tests allow for it (relative 2 × 10⁻⁴ with unit-aware
absolute floors).

Two settings move results at the millimetre level and are pinned for that
reason: the solver time span (LSODA chooses its first step from it) and the
drag interpolation method.

## Validation

- **Adapter equivalence.** `tests/golden/test_calisto.py` builds RocketPy's
  reference rocket, Calisto, directly in RocketPy and through Apogee's
  adapter, and requires identical results (relative 10⁻¹²).
- **Pinned numbers.** The same test pins Calisto's summary (apogee 3,305.4 m
  AGL, rail exit 26.2 m/s, drift 662 m). A RocketPy upgrade that moves them
  fails the build.
- **Against real flights:** none yet. This is the most important gap: see
  `docs/validation/` once the team has flown.

## Known weak spots

- **Transonic and supersonic drag** is only as good as the drag table. OpenRocket's
  estimates are shaky above about Mach 0.8.
- **Stability margin** is static (Barrowman-style centre of pressure); it
  says nothing about dynamic stability.
- **Rail exit** depends on rail-button positions. Without them the rail is
  treated as a single point and exit happens later than in reality.

## Outputs

Summary scalars are defined, with units, in `simcore.engine.result.FlightSummary`.
Trajectory channels are in `TRAJECTORY_CHANNELS` in the same file. Charts are
downsampled to at most 1,500 points per channel with Largest-Triangle-Three-Buckets,
which keeps peaks; full resolution is stored as Parquet.
