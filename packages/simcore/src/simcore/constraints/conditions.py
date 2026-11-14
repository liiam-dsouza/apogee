"""Launch conditions as metrics: the sky at launch, judged like a flight's results.

Most are the same for every flight (cloud cover, visibility, wind, the sun),
so a rule on one is judged once, whatever its ``evaluate_on``. Cloud base
above apogee depends on the flight, so it is worked out per flight.
"""

import math
from datetime import datetime

from pydantic import BaseModel, Field

from simcore.mission.models import Mission
from simcore.weather.sun import horizon_crossings, sun_elevation_deg

#: Metrics that come from the launch conditions, not from a flight.
CONDITION_METRICS = frozenset(
    {"cloud_cover_pct", "visibility_m", "surface_wind_ms", "sun_elevation_deg"}
)

#: Cloud cover below this is a clear sky: nothing to fly into.
CLEAR_SKY_PCT = 1.0

#: What to set when a condition metric is missing.
CONDITION_HINT: dict[str, str] = {
    "cloud_cover_pct": "Set the cloud cover in the Weather section.",
    "visibility_m": "Set the visibility in the Weather section.",
    "surface_wind_ms": "Set the surface wind in the Weather section.",
    "sun_elevation_deg": "Set the launch time in the Weather section.",
    "cloud_clearance_m": "Set the cloud base in the Weather section.",
}


class LaunchSummary(BaseModel):
    """The launch conditions the board judged, with the daylight around the launch."""

    launch_utc: datetime | None = Field(description="Launch time used, UTC.")
    values: dict[str, float] = Field(description="Each condition metric there is a value for.")
    previous_crossing_utc: datetime | None = Field(
        description="The sunrise (in daylight) or sunset (at night) before launch, within a day."
    )
    next_crossing_utc: datetime | None = Field(
        description="The sunset (in daylight) or sunrise (at night) after launch, within a day."
    )


def launch_time(mission: Mission) -> datetime | None:
    """The planned launch time, else the forecast hour the atmosphere is from."""
    if mission.launch_conditions.launch_utc is not None:
        return mission.launch_conditions.launch_utc
    atmosphere = mission.environment.atmosphere
    return atmosphere.valid_utc if atmosphere.kind == "profile" else None


def _flight_surface_wind(mission: Mission) -> float | None:
    """The wind the flight is simulated in at the surface, if it has any."""
    env = mission.environment
    if env.surface_wind is not None:
        return env.surface_wind.speed_ms
    if env.atmosphere.kind == "profile":
        lv = env.atmosphere.levels[0]
        return math.hypot(lv.wind_u_ms, lv.wind_v_ms)
    if env.atmosphere.kind == "manual":
        return env.atmosphere.levels[0].speed_ms
    return None


def condition_values(mission: Mission) -> dict[str, float]:
    """Every condition metric the mission gives a value for."""
    lc = mission.launch_conditions
    out: dict[str, float] = {}
    if lc.cloud_cover_pct is not None:
        out["cloud_cover_pct"] = lc.cloud_cover_pct
    if lc.visibility_m is not None:
        out["visibility_m"] = lc.visibility_m
    sustained = lc.wind_speed_ms if lc.wind_speed_ms is not None else _flight_surface_wind(mission)
    winds = [w for w in (sustained, lc.wind_gust_ms) if w is not None]
    if winds:
        out["surface_wind_ms"] = max(winds)
    when = launch_time(mission)
    if when is not None and mission.site is not None:
        out["sun_elevation_deg"] = sun_elevation_deg(
            mission.site.latitude_deg, mission.site.longitude_deg, when
        )
    return out


def with_conditions(
    flight: dict[str, float], conditions: dict[str, float], cloud_base_m: float | None
) -> dict[str, float]:
    """A flight's metrics with the conditions added, and its apogee's clearance below cloud."""
    out = flight | conditions
    if cloud_base_m is not None and "apogee_agl_m" in flight:
        out["cloud_clearance_m"] = cloud_base_m - flight["apogee_agl_m"]
    return out


def launch_summary(mission: Mission) -> LaunchSummary:
    when = launch_time(mission)
    before = after = None
    if when is not None and mission.site is not None:
        before, after = horizon_crossings(
            mission.site.latitude_deg, mission.site.longitude_deg, when
        )
    return LaunchSummary(
        launch_utc=when,
        values=condition_values(mission),
        previous_crossing_utc=before,
        next_crossing_utc=after,
    )
