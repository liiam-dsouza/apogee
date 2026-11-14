# Post-flight calibration: method

After a flight, the altimeter log tells you how wrong the prediction was. The
**Post-flight** section compares the two in a **flight report**, and can fit the
prediction to the log, so the next one starts from what the rocket actually did.

## The log

Any CSV with a header row: a time column in seconds and an altitude column
in metres or feet, and optionally vertical velocity (m/s or ft/s) and
acceleration (m/s², ft/s² or g). Columns are guessed from their names (`time`,
`alt`, `height`, `vel`, `accel`…) and can be chosen by hand. Altitude may be
above the pad or above sea level: the median of the first readings, on the
pad, is taken as zero. Rows that aren't numbers (status lines, units rows) are
skipped.

## The flight report

One full flight of the mission (with its current drag multiplier) is compared
with the log. The log is aligned at launch (below), then moved by up to a
second to best match the ascent; no extra flights are flown.

- **Channels.** Altitude, vertical velocity and acceleration are compared on a
  common time base, each drawn as the log against the simulation with the
  error (simulated − log) underneath, and summarised by its RMS, its mean
  (bias) and its largest value. A channel the log doesn't have is derived from
  altitude with a Savitzky-Golay filter and marked as derived: a barometric
  derivative is noisy, so its peaks are approximate. An accelerometer reads
  specific force (1 g on the pad); the pad reading is taken as zero, and the
  magnitude is compared with the simulation's up to apogee.
- **Key numbers.** Apogee and its time, max vertical velocity and its time, max
  acceleration, burnout, the descent rate under each device, and flight time,
  each as measured, simulated, error and error as a percentage of the measured
  value. Positive errors mean the simulation overestimated.
- **Events.** Apogee is the highest reading. Burnout needs an accelerometer:
  where its reading turns negative (thrust below drag, on the motor's
  tail-off); the simulated burnout is the same moment, not the end of the
  thrust curve. A canopy opening after apogee is the sharpest drop in descent
  rate; simulated, it is the trigger plus the device's lag. A device deployed
  at apogee can't be told apart from apogee and is not measured. Touchdown is
  the first reading under 3 m after apogee; a log that ends earlier is compared
  up to its end.

**Print or save as PDF** prints the report alone, on light paper, whatever the
theme. Tested by flying Calisto, writing the flight as a noisy feet-ASL log
with velocity and accelerometer columns and comparing it with the same
mission (apogee within 0.5%, the main found within a second), and with 15% more
drag and altitude only (`packages/simcore/tests/test_postflight.py`).

## Alignment

Launch is where the log leaves the pad: the last reading under 1 m before it
first passes 10 m. A barometric log can't place liftoff exactly (pad noise and
the sample rate blur it), and during boost a tenth of a second is tens of
metres, so a time offset of up to a second is fitted along with everything
else.

## The fit (calibration)

The ascent, from launch to the log's apogee, is compared at 60 instants with
ascent-only flights of the mission. Least squares (`scipy.optimize.least_squares`)
adjusts:

- the **drag multiplier**, from 0.3 to 3 times its current value;
- the **time offset**, ±1 s;
- optionally the **impulse scale**, 0.8 to 1.2. Drag and impulse trade
  against each other (more impulse and more drag can give the same apogee),
  so fit impulse only when the boost itself looks wrong.

The result reports the apogee measured, predicted and fitted, the RMS altitude
error over the ascent before and after, and the fitted values. **Use the fitted
drag multiplier** writes it into the mission. The mission has no field for an
impulse scale; a motor that consistently under-performs needs a thrust curve
that matches it.

Tested by flying Calisto with 15% more drag, writing it as a noisy feet-ASL
log that starts 5 s before launch, and fitting the unmodified mission: the fit
recovers 1.15 within 3% (`packages/simcore/tests/test_postflight.py`).

## Not built yet

- Fitting descent (parachute CdS from the descent rate), and GPS tracks
  (drift and landing point in the report).
- Feeding the fitted drag uncertainty into the Monte Carlo drag spread.
- Recording the flight in the [validation record](../validation/index.md).
