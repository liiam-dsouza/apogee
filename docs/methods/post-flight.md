# Post-flight calibration: method

After a flight, the altimeter log tells you how wrong the prediction was. The
**Post-flight** section fits the prediction to it, so the next one starts from
what the rocket actually did.

## The log

Any CSV with a header row: a time column in seconds and an altitude column
in metres or feet. Columns are guessed from their names (`time`, `alt`,
`height`…) and can be chosen by hand. Altitude may be above the pad or above
sea level: the median of the first readings, on the pad, is taken as zero.
Rows that aren't numbers (status lines, units rows) are skipped.

## Alignment

Launch is where the log leaves the pad: the last reading under 1 m before it
first passes 10 m. A barometric log can't place liftoff exactly (pad noise and
the sample rate blur it), and during boost a tenth of a second is tens of
metres, so a time offset of up to a second is fitted along with everything
else.

## The fit

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

- Descent (parachute CdS from the descent rate) and GPS tracks.
- Feeding the fitted drag uncertainty into the Monte Carlo drag spread.
- Recording the flight in the [validation record](../validation/index.md).
