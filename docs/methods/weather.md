# Weather and wind: method

Where a flight's atmosphere comes from, how a measured surface wind is blended
into a forecast, and what that assumes.

## What a flight flies in

The mission's `environment` has two parts:

| Field | What it is |
| --- | --- |
| `atmosphere` | `standard` (ISA, no wind); a `profile`: a table of altitude, pressure, temperature and wind (u east, v north), with its `source`, `valid_utc` and `fetched_utc`; or `manual`: wind typed in by hand |
| `surface_wind` | Optional. A measured wind (speed, direction it blows **from**, anemometer height) with a blend exponent `alpha` and `blend_depth_m` |

The profile is stored **in the mission**, not looked up at run time, so a run
is reproducible offline and its result hash changes when the weather does.
`simcore.weather.effective_levels` turns the two into the table RocketPy flies
(as `custom_atmosphere`). `POST /api/weather/effective` returns the same table,
which is what the Weather section draws.

## Forecasts (Open-Meteo)

`POST /api/weather/forecasts` fetches a seven-day hourly forecast from
[Open-Meteo](https://open-meteo.com) (free, no key) for the pad: its
`best_match` model on every pressure level from 1000 to 50 hPa (about 20 km),
plus surface fields. Every fetch is cached as received in
`<data dir>/weather/`. Offline, the cache is what you fly with. The UI lists the
forecasts cached within 25 km of the site and shows the age of the one in use,
amber after 6 hours and red after 24.

Picking an hour (`GET /api/weather/forecasts/{id}/profile`) resolves it into a profile:

- **The lowest level is the pad.** The model's surface pressure and 2 m
  temperature are moved from the model's terrain height to the pad's
  elevation hydrostatically (standard lapse rate), with the 10 m wind. The
  model's terrain is a ~10 km average, so it can be tens of metres off the pad.
- **Pressure levels follow** from 50 m above the pad. Levels below the pad (the
  1000 hPa surface is often underground inland) are dropped.
- **Heights are converted** from geopotential to geometric altitude (about
  60 m apart at 20 km).
- **Direction is meteorological:** where the wind blows from, degrees true.
  u = −speed·sin(direction), v = −speed·cos(direction).
- The nearest forecast hour is used. A time more than an hour outside the
  forecast is refused.

## Wind entered by hand

For a range safety officer's briefing, or any table of wind against height.
The mission stores what was typed: heights above the pad, speed and the
direction the wind blows from, plus a free-text note of where it came from.
It is resolved when the flight is built (`simcore.weather.manual`):

- **Between entered heights** the wind is interpolated linearly in u and v (as
  RocketPy does for every profile). Below the lowest entry, its wind reaches
  down to the pad.
- **Above the top entry** the wind is held constant up to 20 km. A rocket
  that flies above the briefing's top does not meet an invented calm.
- **Temperature and pressure** follow the standard atmosphere. If the pad's
  temperature and **station** pressure (not the sea-level QNH a forecast quotes)
  are entered, the whole column is shifted to match: temperature by a constant
  offset, pressure by a constant ratio. On a hot day this matters: air at 40 °C
  is about 8% thinner than at 15 °C, which raises apogee noticeably.

A measured surface wind blends into a hand-entered profile exactly as it does
into a forecast.

## Surface-wind blending

Forecast models do not resolve the bottom few hundred metres well, and the
rail-exit phase is where wind matters most for weathercocking. The team
measures the wind at the pad; the blend makes the profile agree with it near
the ground and with the forecast aloft.

With h the height above the pad, h_ref the anemometer height and D the blend depth:

- **Power law near the ground:** v(h) = v_ref · (h / h_ref)^alpha, in the measured
  direction. alpha defaults to 0.14 (open, flat ground); rougher terrain is
  0.2 or more. Below 1 m the law is held constant (it goes to zero at the ground).
- **Weight:** w = 1 at and below h_ref, falling as a half cosine to 0 at D.
- **Speed** = w · v(h) + (1 − w) · forecast speed.
- **Direction** = measured + (1 − w) · turn, where turn is the angle from the
  measured direction to the forecast's at the same height. It turns the short way
  round to the forecast direction at D, and the same way round at every height below.
- Above D, the forecast is untouched. Pressure and temperature are never changed.

Speed and direction are blended rather than u and v. Blending components of a
measured wind that opposes the forecast passes through an invented calm layer.
Fixing the turn direction by the top of the layer stops a forecast that lies
nearly opposite the measurement from swinging the wind back and forth.

A surface wind over the **standard atmosphere** blends into calm air above D.
Validation warns about this: it is only right on a genuinely calm day aloft.

## Assumptions and weak spots

- **One forecast hour, frozen.** The flight lasts minutes; the atmosphere does
  not change during it. Wind does not vary horizontally along the drift.
- **Forecast error is not modelled here.** That is the Monte Carlo's job:
  coherent perturbations of the whole profile, not independent per-level noise.
- **The power law is an engineering fit,** not boundary-layer physics. It is
  poor in strongly stable (night) or convective conditions, and in gusts.
- **The surface level uses the 10 m wind** at the pad when there is no
  measurement, so the bottom 10 m is slightly windy rather than tending to zero.
- **Open-Meteo's `best_match`** picks the model per location and can change
  which model it uses. The source and grid point are recorded with every profile.

## Validation

- `packages/simcore/tests/test_weather.py`: a real Open-Meteo response for White
  Cliffs (`tests/fixtures/weather/`) parsed into a profile; hydrostatic
  correction; geometric altitude; blend properties (matches the measurement,
  hands over to the forecast at D, no jumps, no invented calm, turns one way);
  the cache; and a Calisto flight that a westerly carries east.
- Against measured soundings or flights: none yet.

## Not built yet

Radiosonde soundings (University of Wyoming), and RocketPy's own forecast models.
