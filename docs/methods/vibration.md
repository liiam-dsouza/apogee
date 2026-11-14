# Airframe vibration: method

How Apogee predicts the vibration a payload or flight computer feels during a
flight that hasn't happened yet: which frequencies, how strong, and when. It is
for tuning or isolating a payload, not for structural sizing.

The short version: **the frequencies are good to a few percent for the first
bending mode and about ±15% for the next two. The levels are good to a factor
of 2 or so on a rocket like the one the excitation was fitted to, and worse when
extrapolated to much higher dynamic pressure or a different motor.** Confirm the
frequencies with a tap test once the airframe exists (below).

## What it needs

The mission's `structure`, which an OpenRocket import fills in:

- **Shells**: every body tube, coupler, motor tube, transition and nose cone,
  with its radius, wall, Young's modulus and shear modulus. Nose cones and
  transitions are cut into eight straight pieces. Overlapping shells add their
  stiffness, so a coupler stiffens the tubes it sits in. Stiffness comes from
  the material's name (`structures.materials.TUBE_MATERIALS`): typical values,
  and wound composites vary a lot with the wind angle.
- **Masses**: every part's mass, spread over its length about its CG (the
  tubes' own included). They add up to the rocket's dry mass and CG.
- **Joints**: one where each airframe section meets the next. A joint bends
  more than solid tube: `flexibility_cal` calibers of the tube beside it
  (default 1.25, fitted below). A switch band makes two joints a band's width
  apart, which the default allows for.
- **Stations**: where vibration is predicted. The import adds one for each mass
  component named like a payload, avionics bay, sled or altimeter, or the dry CG
  if there is none. Add your payload's position.
- **Damping** (4% of critical) and the **excitation** coefficients.

The motor's mass is added from the mission's motor as it burns: the case over
its length, the propellant over the grains, burning off with the impulse.

## The beam

The airframe is a free beam (nothing holds a rocket in flight), cut into 160
finite elements from nose tip to tail:

- **Bending**: cubic Hermite elements with Przemieniecki's shear term (a
  Timoshenko stiffness) and consistent mass. A thin tube's shear area is half
  its wall area. Wound fiberglass is about four times softer in shear than in
  tension, which lowers the third mode by about 7% and the first by 1-2%.
- **Axial**: linear bar elements; joints are rigid axially.
- **Joints**: a hinge with a rotational spring, k = EI / (flexibility × D).

The modes are solved at each moment of the burn (about 5 ms each). The first
two bending modes and the first axial mode are rigid-body modes at 0 Hz; they
are kept, since they carry the whole rocket's response to a load.

## What shakes it

Three random loads, each sized by the flight at that moment:

| Source | Where | RMS | Spectrum |
|---|---|---|---|
| `motor_roughness` | axial, at the motor's forward end | fraction of thrust | flat to `band_hz` (2 kHz) |
| `motor_side_load` | lateral, at the nozzle | fraction of thrust | flat to `band_hz` |
| `aero_load` | lateral, along the airframe, per metre | fraction of q × projected width | flat to U/D, falling above |

The aerodynamic load is turbulent pressure on the airframe and fins (fins add
their projected width over the root chord). It falls with Mach as
attached-flow pressure fluctuations do (Lowson: 1 / (1 + 0.14 M²)) and rises
around Mach 1, `transonic_factor` times at its peak, where shocks move along
the airframe. It is correlated over one body diameter along the axis.

Thrust comes from the thrust curve; dynamic pressure, speed and Mach from the
flight.

## The response

Modal superposition with every mode up to three times the highest frequency
asked for. At a station, the acceleration PSD is h(f)ᴴ P h(f) g(f): h is each
mode's acceleration per unit modal force at the station, P is the load's modal
cross-spectrum and g its spectrum. The lateral loads are the same in every
plane, so a sensor's two lateral axes get the same PSD.

Results come in windows (0.25 s by default), each with its own modes and
loads. From the PSDs:

- **band RMS**: the square root of the PSD's integral over a band;
- **persistence**: the share of windows a band's RMS is over a threshold;
- **expected FFT amplitude**: what a single-sided amplitude spectrum of a
  record T seconds long shows on average, sqrt(2 × PSD / T). A flight-log FFT
  depends on its record length in this way, so compare like with like.

## Fitting to a flight log

Every PSD is linear in each coefficient squared, so a log fixes them:
`fit_excitation` matches band powers in decibels (robust least squares) with a
noise floor for the logger. Leave out:

- the ignition and burnout windows: their jolts are shocks, not random
  vibration;
- 5-20 Hz laterally: that is mostly the rocket pitching and coning as a rigid
  body, which this model does not try to capture.

`scripts/vibration_report.py MISSION.apg --log LOG.csv --fit` does this and
plots the prediction against the log.

## Validation

Two rockets, one log each. The defaults come from these.

**First bending mode** (`test_first_bending_mode_of_flown_rockets`), with the
joint flexibility fitted to both at 1.25 calibers:

| Rocket | Model, liftoff → burnout | Measured |
|---|---|---|
| Lanius (6", 3.25 m, M1340W) | 33.7 → 34.9 Hz | ~33 Hz (a teammate's analysis of its log) |
| Luke (5", 2.25 m, K940) | 48.1 → 49.5 Hz | 48-50 Hz (`Luke-K940-HR.csv`) |

**Higher modes are less certain.** On Lanius the model puts mode 2 at 85-88 Hz
almost exactly on a node at the flight computer, which agrees with the log
showing nothing there; mode 3 comes out at 137-151 Hz against a measured
hump at 115-130 Hz. On Luke the model's mode 2 (120 Hz, mostly the 3D-printed
nose swinging) doesn't show in the log, which has a peak near 150 Hz instead;
a printed nose stiffer than solid-PETG values would explain it. Treat
predicted modes above the first as ±15-25% until a tap test says otherwise.

**Levels.** Fitted to Luke's log (boost and coast, ignition and burnout left
out, bands from 20 Hz): `motor_roughness` 0.0064, `motor_side_load` 0.0016,
`aero_load` 0.0031, with a median band error of 3.6 dB axial and 3.4 dB lateral.
That is about the scatter of band RMS over 0.25 s windows itself.

Predicting Lanius with Luke's coefficients, against a teammate's band RMS:

- lateral, early boost (q up to 15 kPa): within 1.5-2x;
- lateral, late boost (q 30-41 kPa, Mach 0.8): 2-4x too high. On Luke's
  coast, lateral RMS grew as q^0.77, a little slower than the model's q, and the
  transonic rise may start too early;
- axial: 4-7x too low through the first 2.5 s. Motor roughness is a property of
  the propellant: the M1340W (White Lightning) is much rougher than the K940.

## Where it is weak

- **Motor roughness doesn't carry over between motors.** Fit it to a log or a
  static fire of the same motor; otherwise treat axial levels as a guess.
- **Levels at much higher q or supersonic** (a 30k ft rocket reaches 150 kPa
  and Mach 1.8) are extrapolated from rockets that never got there. Use them to
  compare designs and to find when the worst vibration comes, not as absolute
  levels.
- **No local modes.** A payload or avionics sled on threaded rods has its own
  resonances; the beam doesn't know about them. The payload mount filters what
  the airframe does.
- **No shocks.** Ignition, rail exit, burnout, ejection and landing are
  transients; the model is random vibration only.
- **Damping** is one number for every mode; real joints add more to some.
- **Lateral below 20 Hz** (pitching and coning) isn't modelled.
- **Joints** are springs of one flexibility; a loose coupler or shear-pinned
  joint can be much softer.

## Tap test: measure the modes

Once the airframe exists, measure its modes. It takes ten minutes:

1. Hang the assembled rocket, motor case and payload in, horizontally from two
   bungee cords near the first mode's nodes (about 22% of the length from each
   end).
2. Tape a logging accelerometer (the flight computer, or a phone) where the
   payload goes.
3. Tap the nose with a rubber mallet, sideways. Log at 500 Hz or more.
4. FFT the ring-down: the peaks are the bending modes. Repeat with the motor
   loaded, or ballast standing in for it, to see the shift through the burn.

Then set `flexibility_cal` (or the tubes' moduli) so the model's first modes
match, and the predicted levels are on the right frequencies.
