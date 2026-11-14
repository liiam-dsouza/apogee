"""Open-Meteo forecasts: the request, and turning one hour of the response into a profile.

Open-Meteo (https://open-meteo.com) is free and needs no key. Its ``best_match``
model gives wind, temperature and geopotential height on pressure levels, plus
surface fields. Fetching is the caller's job (simcore never touches the
network); this module only builds the query and reads the JSON.

Past days come from its historical forecast archive: what the models had for
that day, the same variables in the same shape. Upper-air history starts in
2021; before that the archive has surface fields only.
"""

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from simcore.mission.models import LaunchConditions, ProfileLevel, ResolvedProfile
from simcore.weather.wind import wind_components

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
FORECAST_SOURCE = "Open-Meteo forecast (best match)"
HISTORY_SOURCE = "Open-Meteo historical forecast (best match)"

#: Every level Open-Meteo offers from the ground to about 20 km.
PRESSURE_LEVELS_HPA = (
    1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50,
)  # fmt: skip
_SURFACE = ("temperature_2m", "surface_pressure", "wind_speed_10m", "wind_direction_10m")
_PER_LEVEL = ("temperature", "wind_speed", "wind_direction", "geopotential_height")
#: For launch-condition rules. Forecasts cached before these were asked for lack them.
_CONDITIONS = ("cloud_cover", "visibility", "wind_gusts_10m", "dew_point_2m")
#: Height of a convective cloud base per degree of dew-point spread (Espy), m/K.
_CLOUD_BASE_M_PER_K = 125.0

#: Pressure levels this close above the pad are dropped: the surface level covers them,
#: and a level a few metres above another makes a spurious shear.
_MIN_LEVEL_ABOVE_PAD_M = 50.0
#: An hour more than this far from the requested time is not "the forecast for then".
_MAX_HOUR_GAP_S = 3600

_EARTH_RADIUS_M = 6_356_766.0  # the radius geopotential height is defined against
_G0 = 9.80665
_R = 287.05287
_LAPSE = 0.0065


class ForecastError(ValueError):
    """The response cannot give a profile for the time asked."""


def forecast_params(latitude: float, longitude: float, days: int = 7) -> dict[str, str]:
    """Query parameters for a forecast at a point: hourly, SI units, times as Unix seconds."""
    hourly = (
        list(_SURFACE)
        + list(_CONDITIONS)
        + [f"{var}_{p}hPa" for p in PRESSURE_LEVELS_HPA for var in _PER_LEVEL]
    )
    return {
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "hourly": ",".join(hourly),
        "wind_speed_unit": "ms",
        "timeformat": "unixtime",
        "timezone": "GMT",
        "forecast_days": str(days),
    }


def history_params(latitude: float, longitude: float, day: date, today: date) -> dict[str, str]:
    """Query parameters for a past day from the historical archive.

    The UTC day either side is included, so every hour of ``day`` in any time
    zone is covered; nothing after ``today`` (UTC) is asked for.
    """
    params = forecast_params(latitude, longitude)
    del params["forecast_days"]
    params["start_date"] = min(day - timedelta(days=1), today).isoformat()
    params["end_date"] = min(day + timedelta(days=1), today).isoformat()
    return params


def has_upper_air(response: dict[str, Any]) -> bool:
    """Whether any hour has any pressure level (old archive days are surface only)."""
    hourly = response.get("hourly", {})
    return any(
        v is not None for p in PRESSURE_LEVELS_HPA for v in hourly.get(f"temperature_{p}hPa", [])
    )


def forecast_hours(response: dict[str, Any]) -> list[datetime]:
    """The times (UTC) the response has a forecast for."""
    return [datetime.fromtimestamp(t, UTC) for t in response["hourly"]["time"]]


def geometric_altitude(geopotential_height_m: float) -> float:
    """Geometric altitude for a geopotential height (about 60 m apart at 20 km)."""
    return _EARTH_RADIUS_M * geopotential_height_m / (_EARTH_RADIUS_M - geopotential_height_m)


def _nearest_hour(response: dict[str, Any], valid_utc: datetime) -> int:
    times = response["hourly"]["time"]
    target = valid_utc.timestamp()
    i = min(range(len(times)), key=lambda k: abs(times[k] - target))
    if abs(times[i] - target) > _MAX_HOUR_GAP_S:
        first, last = forecast_hours(response)[0], forecast_hours(response)[-1]
        raise ForecastError(
            f"This forecast covers {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} UTC, "
            f"not {valid_utc:%Y-%m-%d %H:%M} UTC"
        )
    return i


def profile_at(
    response: dict[str, Any],
    valid_utc: datetime,
    pad_elevation_m: float,
    *,
    fetched_utc: datetime | None = None,
    source: str = FORECAST_SOURCE,
) -> ResolvedProfile:
    """The forecast hour nearest ``valid_utc`` as a profile starting at the pad.

    The lowest level is at the pad: the model's surface pressure and 2 m
    temperature, moved hydrostatically from the model's terrain height to the
    pad's, with the 10 m wind. Pressure levels follow, from 50 m above the pad.
    """
    hourly = response["hourly"]
    i = _nearest_hour(response, valid_utc)

    def at(name: str) -> float | None:
        value = hourly.get(name, [None] * (i + 1))[i]
        return None if value is None else float(value)

    t2, p_sfc, ws10, wd10 = (at(name) for name in _SURFACE)
    if t2 is None or p_sfc is None or ws10 is None or wd10 is None:
        raise ForecastError("The forecast has no surface data for that hour")
    dz = pad_elevation_m - float(response.get("elevation", pad_elevation_m))
    t_pad = t2 + 273.15 - _LAPSE * dz
    p_pad = p_sfc * 100 * math.exp(-_G0 * dz / (_R * (t_pad + _LAPSE * dz / 2)))
    u10, v10 = wind_components(ws10, wd10)
    levels = [
        ProfileLevel(
            altitude_m=pad_elevation_m,
            pressure_pa=p_pad,
            temperature_k=t_pad,
            wind_u_ms=u10,
            wind_v_ms=v10,
        )
    ]

    for p in PRESSURE_LEVELS_HPA:
        t, ws, wd, gh = (at(f"{var}_{p}hPa") for var in _PER_LEVEL)
        if t is None or ws is None or wd is None or gh is None:
            continue  # the model does not reach this level here
        altitude = geometric_altitude(gh)
        if altitude < levels[-1].altitude_m + _MIN_LEVEL_ABOVE_PAD_M:
            continue  # underground, or too close to the level below
        u, v = wind_components(ws, wd)
        levels.append(
            ProfileLevel(
                altitude_m=altitude,
                pressure_pa=p * 100.0,
                temperature_k=t + 273.15,
                wind_u_ms=u,
                wind_v_ms=v,
            )
        )
    if len(levels) < 2:
        raise ForecastError("The forecast has no pressure levels above the pad for that hour")

    return ResolvedProfile(
        kind="profile",
        source=(
            f"{source}, grid point {response['latitude']:.3f}, "
            f"{response['longitude']:.3f} at {response.get('elevation', 0):.0f} m"
        ),
        valid_utc=forecast_hours(response)[i],
        fetched_utc=fetched_utc,
        levels=levels,
    )


def conditions_at(response: dict[str, Any], valid_utc: datetime) -> LaunchConditions:
    """The forecast hour nearest ``valid_utc`` as launch conditions.

    Cloud base is estimated from the dew-point spread at 2 m (125 m per kelvin),
    which is where cumulus forms; layered cloud can sit higher or lower. A value
    the forecast doesn't have (the archive often lacks visibility) is left unset.
    """
    hourly = response["hourly"]
    i = _nearest_hour(response, valid_utc)

    def at(name: str) -> float | None:
        value = hourly.get(name, [None] * (i + 1))[i]
        return None if value is None else float(value)

    cover, visibility, gust, dew = (at(name) for name in _CONDITIONS)
    t2, ws10 = at("temperature_2m"), at("wind_speed_10m")
    base = None
    if cover is not None and cover > 0 and t2 is not None and dew is not None:
        base = _CLOUD_BASE_M_PER_K * max(t2 - dew, 0.0)
    hour = forecast_hours(response)[i]
    return LaunchConditions(
        launch_utc=hour,
        cloud_cover_pct=cover,
        cloud_base_m=base,
        visibility_m=visibility,
        wind_speed_ms=ws10,
        wind_gust_ms=gust,
        source=f"Open-Meteo for {hour:%Y-%m-%d %H:%M} UTC; cloud base from the dew point",
    )
