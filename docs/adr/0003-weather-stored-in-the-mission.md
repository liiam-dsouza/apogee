# 0003: The flown atmosphere is stored in the mission

**Status:** accepted, 2026-11-02

## Context

A flight's result depends on the wind. Forecasts change every few hours, and
at the launch site there is often no internet. Results are cached by a hash of
the mission.

## Decision

When the user picks a forecast hour, the resolved profile (every level's
altitude, pressure, temperature and wind, plus its source, valid time and fetch
time) is copied into `environment.atmosphere` in the mission. A measured
surface wind is stored beside it as `environment.surface_wind`, and the blend
is applied when the flight is built, not baked into the stored levels.

Raw forecasts are also cached on the server, as received, so another hour can
be picked offline.

## Consequences

- A mission flies identically anywhere, offline, forever; its hash changes when
  the weather does, so cached results never go stale silently.
- Mission files grow by a few kilobytes per profile.
- The blend settings stay editable and the raw forecast stays visible, because
  the stored levels are the forecast, not the blend.

## Rejected

- **Store a reference to a cached forecast.** Smaller, but the mission would not
  fly on another machine, and deleting the cache would change results.
- **Store the blended levels only.** Loses the forecast and the user's blend settings.
