# Monte Carlo: method

A single flight answers "what does this design do?". A campaign answers
"what will happen on the day, given what we don't know?": it flies the
mission hundreds of times, each with its uncertain inputs drawn from their
distributions, and reports the spread.

## What varies

Every input is normal about its nominal value, with one standard deviation
set per mission (`monte_carlo.parameters`). Each can be switched off.

| Input | Default spread | How it is applied |
| --- | --- | --- |
| Total impulse | 3% | Thrust curve scaled. Use 5% for student-made motors. |
| Burn time | 5% | Thrust curve stretched in time with impulse held, so thrust divides by the same factor. |
| Dry mass | 0.5% | 0.5% if weighed, 2% if estimated. |
| Dry centre of mass | 5 mm | Along the axis. |
| Drag coefficient | 10% | Multiplies both drag curves. More if there is no wind-tunnel or flight data. |
| Rail inclination | 0.5° | |
| Rail heading | 2° | |
| Parachute CdS | 10% | Each device independently. |
| Deployment lag | 0.3 s | Added to each device's lag; the total is held at zero or above. |
| Deploy altitude | 10 m | Altitude-triggered devices only (altimeter error). |
| Wind speed | 15% | One multiplier for the whole profile. |
| Wind direction | 10° | One offset for the whole profile. |
| Wind noise between heights | 1 m/s | Per component, correlated over `wind_correlation_m` (750 m). |

Draws far in a tail are kept physical: scale factors never go below 0.2, and
inclination stays between 0° and 90°.

## Sampling

**Latin Hypercube** (`scipy.stats.qmc.LatinHypercube`): for *n* samples, each
input's range is split into *n* equally likely slices and every slice is used
exactly once. For the same number of flights this covers the inputs far more
evenly than independent draws, which matters when each flight costs a second.

The hypercube depends only on the seed, the sample count and which inputs are
switched on. Any worker can rebuild it and take its own rows, so a campaign
gives the same samples however it is split across workers, and the same
mission with the same seed gives the same campaign. A finished campaign is
reused rather than re-run.

## The wind

The wind is the input most implementations get wrong. Perturbing each altitude
layer independently makes physically absurd profiles (20 m/s of shear across
50 m), and the errors cancel on the way up, which shrinks the landing ellipse.
Instead, applied to the profile the flight actually flies (forecast or
hand-entered, with any surface wind blended in):

1. **Coherent error:** one speed multiplier and one direction offset for every
   height. This is the forecast being wrong overall. Both are drawn in the
   hypercube like every other input.
2. **Correlated noise:** a smaller perturbation per component, as an AR(1)
   process in height: neighbouring levels a distance *dz* apart are correlated
   by exp(−*dz*/*L*), with *L* = `wind_correlation_m`.

With the standard atmosphere there is no wind, and no forecast error to sample.

## Outputs

Every sample records its inputs and its outputs: apogee, rail exit velocity,
stability margins, max Mach, max q, max acceleration, landing point, drift,
touchdown speed and flight time. **Every sample as CSV** downloads all of it.

- **Percentiles** (5%, median, 95%) are counted from the samples, not assumed normal.
- **Landing ellipses** are fitted from the covariance of the landing points,
  scaled to hold 68%, 95% and 99.7% of landings (the 1σ, 2σ and 3σ shares of
  a one-dimensional normal). For a two-dimensional normal that needs a radius
  of √χ²₂(p) standard deviations: 1.52, 2.49 and 3.44. Note that some tools
  draw "1σ" at a radius of 1, which holds only 39%.
- **P(lands outside the boundary)** and **P(lands in a hazard zone)** are
  counted directly from the landing points. Each comes with the upper end of
  its 95% Wilson confidence interval: 0 out of 100 landings outside does not
  mean zero risk; it means less than about 3.7% at 95% confidence. Compare
  the upper bound, not the estimate, against a limit.
- **Convergence:** the standard error of the mean apogee is shown. When it is
  small against what you care about, more samples will not change the answer.

A sample whose simulation fails is recorded with its error and left out of
the statistics. The map says how many failed.

## How it runs

A campaign is split into chunks of 20 samples, one job each, so every worker
shares it (`simcore.montecarlo`, `apps/api/.../routers/montecarlo.py`).
Results are read from the chunks that have finished, so the map fills in while
the campaign runs. If the stack restarts mid-campaign, running it again
resumes: only the missing chunks are queued.

Campaign settings are not part of a single flight's cache key, so changing
them never re-runs the single flight.

## Not built yet

- Early stopping when the campaign has converged.
- Failure-mode campaigns (drogue only, main only, ballistic).
- Spreads derived from a forecast ensemble, and sampling among several
  candidate profiles (forecast hours, a morning sounding).
- Ignition delay; parachute trigger noise.
- P(apogee above a ceiling): needs the constraints section.
