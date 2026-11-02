import itertools
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import FlightResult, run_flight
from simcore.mission import Mission
from simcore.mission.models import (
    Environment,
    ManualProfile,
    ProfileLevel,
    ResolvedProfile,
    SurfaceWind,
)
from simcore.weather import (
    ForecastCache,
    ForecastError,
    ForecastNotFound,
    blend_surface_wind,
    effective_levels,
    forecast_params,
    isa_levels,
    isa_pressure_temperature,
    manual_levels,
    profile_at,
    wind_components,
)
from simcore.weather.openmeteo import geometric_altitude


def test_isa_sea_level_and_tropopause() -> None:
    assert isa_pressure_temperature(0) == pytest.approx((101_325.0, 288.15))
    p, t = isa_pressure_temperature(11_000)
    assert t == pytest.approx(216.65)
    assert p == pytest.approx(22_632, rel=1e-3)


def test_isa_levels_carry_the_wind() -> None:
    levels = isa_levels(wind_u_ms=-2.0, top_m=1000, step_m=500)
    assert [lv.altitude_m for lv in levels] == [0, 500, 1000]
    assert {lv.wind_u_ms for lv in levels} == {-2.0}


# --- Open-Meteo -----------------------------------------------------------------

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures"
CALISTO = FIXTURES / "calisto"
WEATHER = FIXTURES / "weather"
#: A real response for White Cliffs, trimmed to three hours.
RESPONSE = json.loads((WEATHER / "openmeteo-white-cliffs.json").read_text())
PAD_M = 220.0


def test_forecast_params_ask_for_si_and_every_level() -> None:
    params = forecast_params(-30.66481, 143.196302)
    assert params["wind_speed_unit"] == "ms"
    assert "geopotential_height_50hPa" in params["hourly"].split(",")


def test_profile_starts_at_the_pad_and_climbs() -> None:
    profile = profile_at(RESPONSE, datetime(2026, 11, 2, 0, 20, tzinfo=UTC), PAD_M)
    assert profile.valid_utc == datetime.fromtimestamp(RESPONSE["hourly"]["time"][0], UTC)
    first, *rest = profile.levels
    assert first.altitude_m == PAD_M
    # The 1000 hPa surface (110 m) is underground at a 220 m pad.
    assert all(lv.altitude_m >= PAD_M + 50 for lv in rest)
    assert rest[-1].altitude_m > 20_000
    pressures = [lv.pressure_pa for lv in profile.levels]
    assert pressures == sorted(pressures, reverse=True)
    assert "Open-Meteo" in profile.source


def test_profile_surface_level_is_the_model_surface() -> None:
    hourly = RESPONSE["hourly"]
    first = profile_at(RESPONSE, datetime.fromtimestamp(hourly["time"][0], UTC), PAD_M).levels[0]
    # The pad is at the model's terrain height here, so nothing is moved.
    assert first.pressure_pa == pytest.approx(hourly["surface_pressure"][0] * 100)
    assert first.temperature_k == pytest.approx(hourly["temperature_2m"][0] + 273.15)
    speed = math.hypot(first.wind_u_ms, first.wind_v_ms)
    assert speed == pytest.approx(hourly["wind_speed_10m"][0])


def test_profile_moves_surface_pressure_to_a_lower_pad() -> None:
    t = datetime.fromtimestamp(RESPONSE["hourly"]["time"][0], UTC)
    lower = profile_at(RESPONSE, t, PAD_M - 70).levels[0]
    # About 8 hPa per 70 m near the ground.
    assert lower.pressure_pa - RESPONSE["hourly"]["surface_pressure"][0] * 100 == pytest.approx(
        800, rel=0.1
    )


def test_wind_direction_is_where_it_blows_from() -> None:
    # A northerly blows towards the south: v negative.
    u, v = wind_components(10, 0)
    assert (u, v) == pytest.approx((0, -10))
    u, v = wind_components(10, 270)  # westerly, towards the east
    assert (u, v) == pytest.approx((10, 0))


def test_profile_outside_the_forecast_says_what_it_covers() -> None:
    with pytest.raises(ForecastError, match="This forecast covers"):
        profile_at(RESPONSE, datetime(2030, 1, 1, tzinfo=UTC), PAD_M)


def test_geometric_altitude_is_slightly_above_geopotential() -> None:
    assert geometric_altitude(0) == 0
    assert geometric_altitude(20_000) - 20_000 == pytest.approx(63, abs=1)


# --- Blending -------------------------------------------------------------------


def _forecast_profile() -> ResolvedProfile:
    return profile_at(RESPONSE, datetime.fromtimestamp(RESPONSE["hourly"]["time"][0], UTC), PAD_M)


def _speed_dir(lv: ProfileLevel) -> tuple[float, float]:
    return math.hypot(lv.wind_u_ms, lv.wind_v_ms), math.degrees(
        math.atan2(-lv.wind_u_ms, -lv.wind_v_ms)
    ) % 360


def test_blend_matches_the_measurement_at_the_anemometer() -> None:
    wind = SurfaceWind(speed_ms=4.0, direction_deg=200, height_m=2)
    blended = blend_surface_wind(_forecast_profile().levels, wind, PAD_M)
    at_anemometer = next(lv for lv in blended if lv.altitude_m == PAD_M + 2)
    assert _speed_dir(at_anemometer) == pytest.approx((4.0, 200))


def test_blend_follows_the_power_law_and_hands_over_to_the_profile() -> None:
    profile = _forecast_profile()
    wind = SurfaceWind(speed_ms=4.0, direction_deg=200, height_m=2, alpha=0.14, blend_depth_m=300)
    blended = blend_surface_wind(profile.levels, wind, PAD_M)
    by_alt = {lv.altitude_m: lv for lv in blended}
    # At the anemometer height and below, the power law alone.
    assert by_alt[PAD_M].wind_u_ms == pytest.approx(wind_components(4.0 * (1 / 2) ** 0.14, 200)[0])
    # At and above the blend depth, the profile untouched.
    for lv in profile.levels:
        if lv.altitude_m >= PAD_M + 300:
            assert by_alt[lv.altitude_m] == lv
    # Pressure and temperature are never changed, only interpolated.
    assert by_alt[PAD_M].pressure_pa == pytest.approx(profile.levels[0].pressure_pa)


def test_blend_has_no_jumps() -> None:
    wind = SurfaceWind(speed_ms=12.0, direction_deg=90, height_m=10, blend_depth_m=400)
    blended = blend_surface_wind(_forecast_profile().levels, wind, PAD_M)
    # Above the anemometer, where the power law meets the forecast (below it the
    # power law itself is steep, as real wind near the ground is).
    low = [lv for lv in blended if PAD_M + 10 <= lv.altitude_m <= PAD_M + 600]
    for a, b in itertools.pairwise(low):
        du = math.hypot(b.wind_u_ms - a.wind_u_ms, b.wind_v_ms - a.wind_v_ms)
        assert du / (b.altitude_m - a.altitude_m) < 0.15  # m/s per m


def test_surface_wind_rejects_a_blend_below_the_anemometer() -> None:
    with pytest.raises(ValueError, match="blend_depth_m"):
        SurfaceWind(speed_ms=1, direction_deg=0, height_m=10, blend_depth_m=5)


def test_effective_levels() -> None:
    assert effective_levels(Environment(), PAD_M) is None  # RocketPy's own standard atmosphere
    wind = SurfaceWind(speed_ms=5, direction_deg=0)
    calm_aloft = effective_levels(Environment(surface_wind=wind), PAD_M)
    assert calm_aloft is not None
    assert calm_aloft[-1].wind_u_ms == 0 and calm_aloft[-1].wind_v_ms == 0
    profile = _forecast_profile()
    assert effective_levels(Environment(atmosphere=profile), PAD_M) == profile.levels


# --- Cache ----------------------------------------------------------------------


def test_cache_round_trips_and_finds_by_place(tmp_path: Path) -> None:
    cache = ForecastCache(tmp_path)
    a = cache.put(-30.66, 143.19, "Open-Meteo", RESPONSE)
    b = cache.put(-30.70, 143.20, "Open-Meteo", RESPONSE)  # ~4 km away
    cache.put(-33.87, 151.21, "Open-Meteo", RESPONSE)  # Sydney
    assert cache.get(a.id) == a
    assert [e.id for e in cache.near(-30.66, 143.19)] == [b.id, a.id]
    with pytest.raises(ForecastNotFound):
        cache.get("../etc/passwd")


# --- Flight ---------------------------------------------------------------------


def test_a_forecast_flies_and_the_wind_carries_the_rocket(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission, _ = calisto_run
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    assert mission.site is not None
    still = mission.model_copy(
        update={
            "environment": Environment(
                atmosphere=ResolvedProfile(
                    kind="profile", source="test", levels=isa_levels(top_m=10_000)
                )
            )
        }
    )
    windy = still.model_copy(
        update={
            "environment": still.environment.model_copy(
                update={
                    "surface_wind": SurfaceWind(speed_ms=8, direction_deg=270, blend_depth_m=3000),
                }
            )
        }
    )
    calm = run_flight(still, store).summary
    blown = run_flight(windy, store).summary
    assert calm.landing is not None and blown.landing is not None
    # A westerly carries the descending rocket east.
    assert blown.landing.east_m > calm.landing.east_m + 100


def test_blend_of_opposing_winds_has_no_invented_calm() -> None:
    # The forecast near the ground here is northerly; measure a southerly.
    profile = _forecast_profile()
    wind = SurfaceWind(speed_ms=6.0, direction_deg=200, height_m=2, blend_depth_m=300)
    blended = blend_surface_wind(profile.levels, wind, PAD_M)
    layer = [lv for lv in blended if PAD_M + 2 <= lv.altitude_m <= PAD_M + 300]
    assert min(_speed_dir(lv)[0] for lv in layer) > 5.0


def test_blend_turns_one_way_through_the_layer() -> None:
    profile = _forecast_profile()
    wind = SurfaceWind(speed_ms=6.0, direction_deg=200, height_m=2, blend_depth_m=300)
    blended = blend_surface_wind(profile.levels, wind, PAD_M)
    layer = [lv for lv in blended if PAD_M + 2 <= lv.altitude_m <= PAD_M + 300]
    turns = [(_speed_dir(lv)[1] - 200 + 180) % 360 - 180 for lv in layer]
    steps = [b - a for a, b in itertools.pairwise(turns) if abs(b - a) < 180]
    assert all(st >= -1e-6 for st in steps) or all(st <= 1e-6 for st in steps)


# --- Manual profile -------------------------------------------------------------


def _manual(**kw: object) -> ManualProfile:
    return ManualProfile.model_validate(
        {
            "kind": "manual",
            "levels": [
                {"height_m": 0, "speed_ms": 4, "direction_deg": 180},
                {"height_m": 1000, "speed_ms": 12, "direction_deg": 270},
            ],
            **kw,
        }
    )


def test_manual_profile_puts_the_entries_at_the_pad_and_holds_above() -> None:
    levels = manual_levels(_manual(), PAD_M)
    assert levels[0].altitude_m == PAD_M
    assert _speed_dir(levels[0]) == pytest.approx((4, 180))
    at_1000 = next(lv for lv in levels if lv.altitude_m == PAD_M + 1000)
    assert _speed_dir(at_1000) == pytest.approx((12, 270))
    assert levels[-1].altitude_m == 20_000
    assert _speed_dir(levels[-1]) == pytest.approx((12, 270))  # held constant above the top
    # Standard atmosphere when nothing was measured.
    p, t = isa_pressure_temperature(PAD_M)
    assert (levels[0].pressure_pa, levels[0].temperature_k) == pytest.approx((p, t))


def test_manual_profile_uses_measured_pad_conditions() -> None:
    hot = manual_levels(_manual(surface_temperature_k=313.15, surface_pressure_pa=97_000), PAD_M)
    assert hot[0].temperature_k == pytest.approx(313.15)
    assert hot[0].pressure_pa == pytest.approx(97_000)
    # The offset and ratio carry up the column.
    _, t_isa = isa_pressure_temperature(PAD_M + 1000)
    at_1000 = next(lv for lv in hot if lv.altitude_m == PAD_M + 1000)
    assert at_1000.temperature_k - t_isa == pytest.approx(
        313.15 - isa_pressure_temperature(PAD_M)[1]
    )


def test_manual_profile_lowest_entry_reaches_down_to_the_pad() -> None:
    m = ManualProfile.model_validate(
        {"kind": "manual", "levels": [{"height_m": 300, "speed_ms": 7, "direction_deg": 90}]}
    )
    levels = manual_levels(m, PAD_M)
    assert levels[0].altitude_m == PAD_M
    assert _speed_dir(levels[0]) == pytest.approx((7, 90))


def test_manual_profile_rejects_unsorted_heights() -> None:
    with pytest.raises(ValueError, match="increasing height"):
        ManualProfile.model_validate(
            {
                "kind": "manual",
                "levels": [
                    {"height_m": 500, "speed_ms": 1, "direction_deg": 0},
                    {"height_m": 100, "speed_ms": 1, "direction_deg": 0},
                ],
            }
        )


def test_a_manual_profile_flies(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, _ = calisto_run
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    westerly = ManualProfile.model_validate(
        {"kind": "manual", "levels": [{"height_m": 0, "speed_ms": 8, "direction_deg": 270}]}
    )
    flown = run_flight(
        mission.model_copy(update={"environment": Environment(atmosphere=westerly)}), store
    ).summary
    assert flown.landing is not None and flown.landing.east_m > 500
