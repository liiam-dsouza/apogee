"""Weather: fetch and cache forecasts, resolve one hour into a profile, preview the flown profile.

Fetching needs internet; everything else works from the cache, so the field
laptop flies the last forecast it fetched.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from apogee_api.deps import SettingsDep
from apogee_api.problems import ApiProblem, Problem
from simcore.mission.models import Environment, ProfileLevel, ResolvedProfile
from simcore.weather import (
    CachedForecast,
    ForecastCache,
    ForecastError,
    ForecastNotFound,
    effective_levels,
    forecast_hours,
    forecast_params,
    profile_at,
)
from simcore.weather.openmeteo import FORECAST_URL

router = APIRouter(prefix="/api/weather", tags=["weather"])

USER_AGENT = "Apogee/0.1 (rocketry flight simulation; launch-site forecast)"
SOURCE = "Open-Meteo forecast (best match)"

Latitude = Annotated[float, Field(ge=-90, le=90, description="WGS84 latitude, degrees.")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="WGS84 longitude, degrees.")]


def _cache(settings: Any) -> ForecastCache:
    return ForecastCache(settings.data_dir / "weather")


class ForecastInfo(BaseModel):
    """A cached forecast: when it was fetched, where for, and which hours it covers."""

    id: str = Field(description="Cache id.")
    fetched_utc: datetime = Field(description="When it was downloaded, UTC.")
    source: str = Field(description="Provider and model.")
    latitude: float = Field(description="Where it was requested for, degrees.")
    longitude: float = Field(description="Where it was requested for, degrees.")
    grid_latitude: float = Field(description="The model grid point used, degrees.")
    grid_longitude: float = Field(description="The model grid point used, degrees.")
    grid_elevation_m: float = Field(description="Model terrain height at the grid point.")
    hours: list[datetime] = Field(description="Times it has a forecast for, UTC, hourly.")


def _info(entry: CachedForecast) -> ForecastInfo:
    r = entry.response
    return ForecastInfo(
        id=entry.id,
        fetched_utc=entry.fetched_utc,
        source=entry.source,
        latitude=entry.latitude,
        longitude=entry.longitude,
        grid_latitude=r["latitude"],
        grid_longitude=r["longitude"],
        grid_elevation_m=r.get("elevation", 0.0),
        hours=forecast_hours(r),
    )


class ForecastRequest(BaseModel):
    latitude: Latitude
    longitude: Longitude


def _open_meteo(latitude: float, longitude: float) -> dict[str, Any]:
    query = urllib.parse.urlencode(forecast_params(latitude, longitude))
    req = urllib.request.Request(f"{FORECAST_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        parsed: dict[str, Any] = json.loads(resp.read())
        return parsed


@router.post(
    "/forecasts",
    operation_id="fetchForecast",
    responses={
        502: {"model": Problem, "description": "Open-Meteo refused the request."},
        503: {"model": Problem, "description": "Open-Meteo is not reachable (offline?)."},
    },
)
def fetch_forecast(body: ForecastRequest, settings: SettingsDep) -> ForecastInfo:
    """Fetch a seven-day hourly forecast for a point from Open-Meteo, and cache it."""
    try:
        response = _open_meteo(body.latitude, body.longitude)
    except urllib.error.HTTPError as e:
        raise ApiProblem(
            502,
            "forecast_refused",
            f"Open-Meteo refused the request (HTTP {e.code})",
            "Try again later. Cached forecasts for this site still work.",
        ) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ApiProblem(
            503,
            "forecast_unreachable",
            "Open-Meteo could not be reached",
            "You may be offline. Use a cached forecast for this site, or enter the wind by hand.",
        ) from e
    if "hourly" not in response:
        raise ApiProblem(502, "forecast_unreadable", "Open-Meteo returned no hourly forecast")
    entry = _cache(settings).put(body.latitude, body.longitude, SOURCE, response)
    return _info(entry)


@router.get("/forecasts", operation_id="listForecasts")
def list_forecasts(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    settings: SettingsDep,
) -> list[ForecastInfo]:
    """Cached forecasts for points within 25 km of this one, newest first."""
    return [_info(e) for e in _cache(settings).near(latitude, longitude)]


@router.get(
    "/forecasts/{forecast_id}/profile",
    operation_id="forecastProfile",
    responses={
        404: {"model": Problem, "description": "No such cached forecast."},
        422: {"model": Problem, "description": "The forecast does not cover that time."},
    },
)
def forecast_profile(
    forecast_id: str,
    valid_utc: Annotated[datetime, Query(description="The launch time; the nearest hour is used.")],
    elevation_m: Annotated[float, Query(description="Pad elevation; the profile starts here.")],
    settings: SettingsDep,
) -> ResolvedProfile:
    """One hour of a cached forecast as a profile, ready to put in the mission."""
    try:
        entry = _cache(settings).get(forecast_id)
    except ForecastNotFound as e:
        raise ApiProblem(404, "forecast_not_found", "That forecast is not cached") from e
    if valid_utc.tzinfo is None:
        valid_utc = valid_utc.replace(tzinfo=UTC)
    try:
        return profile_at(entry.response, valid_utc, elevation_m, fetched_utc=entry.fetched_utc)
    except ForecastError as e:
        raise ApiProblem(422, "forecast_out_of_range", str(e)) from e


class EffectiveProfileRequest(BaseModel):
    environment: Environment = Field(description="The mission's environment section.")
    elevation_m: float = Field(description="Pad elevation, metres above sea level.")


class EffectiveProfile(BaseModel):
    levels: list[ProfileLevel] | None = Field(
        description="The profile the flight is simulated in; None for the standard atmosphere."
    )


@router.post("/effective", operation_id="effectiveProfile")
def effective_profile(body: EffectiveProfileRequest) -> EffectiveProfile:
    """The atmosphere a flight would fly in, after blending in the surface wind."""
    return EffectiveProfile(levels=effective_levels(body.environment, body.elevation_m))
