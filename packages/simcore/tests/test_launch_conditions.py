from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from simcore.constraints import ProfileError, board, condition_values, launch_summary, load_profiles
from simcore.mission import Mission
from simcore.mission.models import ConstraintSettings, SurfaceWind
from simcore.weather import conditions_at, horizon_crossings, sun_elevation_deg

SPACEPORT = (32.99, -106.97)  # Spaceport America, New Mexico
LAUNCH = datetime(2024, 6, 21, 18, 0, tzinfo=UTC)  # noon local (MDT)


def _mission(**conditions: Any) -> Mission:
    return Mission.model_validate(
        {
            "meta": {"name": "x"},
            "site": {
                "latitude_deg": SPACEPORT[0],
                "longitude_deg": SPACEPORT[1],
                "elevation_m": 1400,
                "rail_length_m": 5.2,
                "inclination_deg": 85,
                "heading_deg": 0,
            },
            "launch_conditions": conditions,
            "constraints": {"launch_rules": "faa-101"},
        }
    )


def _board(m: Mission, apogees: list[float] | None = None) -> dict[str, Any]:
    samples = [{"apogee_agl_m": a} for a in apogees] if apogees else None
    nominal = {"apogee_agl_m": apogees[0]} if apogees else None
    b = board(
        m.constraints, nominal, samples, condition_values(m), m.launch_conditions.cloud_base_m
    )
    return {r.id: r for r in b.rows} | {"verdict": b.verdict}


def test_sunrise_and_sunset_match_the_almanac() -> None:
    # USNO: Spaceport America, 2024-06-21: sunrise 05:59, sunset 20:19 MDT (UTC-6).
    rise, set_ = horizon_crossings(*SPACEPORT, LAUNCH)
    assert rise is not None and set_ is not None
    assert abs(rise - datetime(2024, 6, 21, 11, 59, tzinfo=UTC)) < timedelta(minutes=2)
    assert abs(set_ - datetime(2024, 6, 22, 2, 19, tzinfo=UTC)) < timedelta(minutes=2)
    # At night the crossings are the sunset before and the sunrise after.
    before, after = horizon_crossings(*SPACEPORT, datetime(2024, 6, 22, 6, 0, tzinfo=UTC))
    assert before is not None and after is not None
    assert abs(before - set_) < timedelta(minutes=1)


def test_sun_elevation_at_solar_noon_and_midnight_sun() -> None:
    # Solstice noon on the tropic of Cancer at Greenwich: sun overhead.
    assert sun_elevation_deg(23.44, 0, datetime(2024, 6, 20, 12, 2, tzinfo=UTC)) > 89
    assert horizon_crossings(78.2, 15.6, datetime(2024, 6, 21, 12, tzinfo=UTC)) == (None, None)


def test_launch_rules_judge_the_conditions_once() -> None:
    clear = _board(
        _mission(
            launch_utc=LAUNCH,
            cloud_cover_pct=30,
            cloud_base_m=4000,
            visibility_m=16_000,
            wind_speed_ms=5,
            wind_gust_ms=8,
        ),
        [3000, 3200, 3400],
    )
    for rid in ("faa_cloud_cover", "faa_visibility", "faa_daylight", "safety_code_wind"):
        assert clear[rid].status == "pass", rid
        assert clear[rid].evaluate_on == "conditions"
        assert clear[rid].source == "launch"
    assert clear["faa_into_cloud"].status == "pass"
    assert clear["faa_into_cloud"].value_low == pytest.approx(600)  # the highest flight
    assert clear["verdict"] == "go"


def test_each_launch_rule_can_fail() -> None:
    bad = _board(
        _mission(
            launch_utc=LAUNCH + timedelta(hours=10),  # 22:00 local, after sunset
            cloud_cover_pct=70,
            cloud_base_m=3100,
            visibility_m=5000,
            wind_speed_ms=6,
            wind_gust_ms=10,  # 22 mph
        ),
        [3000, 3200],
    )
    for rid in ("faa_cloud_cover", "faa_visibility", "faa_into_cloud", "faa_daylight"):
        assert bad[rid].status == "fail", rid
    assert bad["safety_code_wind"].value_high == 10
    assert bad["verdict"] == "no_go"


def test_unknown_conditions_are_never_a_pass() -> None:
    b = _board(_mission(), [3000])
    assert b["verdict"] == "incomplete"
    assert b["faa_cloud_cover"].status == "missing"
    assert "cloud cover" in b["faa_cloud_cover"].note
    assert "launch time" in b["faa_daylight"].note
    assert "cloud cover" in b["faa_into_cloud"].note


def test_a_clear_sky_has_no_cloud_to_fly_into() -> None:
    b = _board(_mission(cloud_cover_pct=0), [3000])
    assert b["faa_into_cloud"].status == "not_applicable"
    assert b["faa_into_cloud"].outcome == "go"
    cloudy = _board(_mission(cloud_cover_pct=20), [3000])
    assert "cloud base" in cloudy["faa_into_cloud"].note


def test_wind_falls_back_to_the_flights_surface_wind() -> None:
    m = _mission(wind_gust_ms=4)
    m.environment.surface_wind = SurfaceWind(speed_ms=6, direction_deg=90)
    assert condition_values(m)["surface_wind_ms"] == 6  # sustained beats a weaker gust


def test_launch_time_falls_back_to_the_forecast_hour() -> None:
    m = Mission.model_validate(
        _mission().model_dump(mode="json")
        | {
            "environment": {
                "atmosphere": {
                    "kind": "profile",
                    "source": "test",
                    "valid_utc": LAUNCH.isoformat(),
                    "levels": [
                        {"altitude_m": 1400, "pressure_pa": 85000, "temperature_k": 300,
                         "wind_u_ms": 3, "wind_v_ms": 4},
                        {"altitude_m": 3000, "pressure_pa": 70000, "temperature_k": 290,
                         "wind_u_ms": 5, "wind_v_ms": 5},
                    ],
                }
            }
        }
    )  # fmt: skip
    s = launch_summary(m)
    assert s.launch_utc == LAUNCH
    assert s.values["surface_wind_ms"] == pytest.approx(5)
    assert s.values["sun_elevation_deg"] > 60


def test_conditions_are_left_out_of_the_flight_and_campaign_keys() -> None:
    from simcore.montecarlo.store import campaign_key
    from simcore.results import result_key

    a = _mission()
    b = a.model_copy(deep=True)
    b.launch_conditions.cloud_cover_pct = 80
    assert result_key(a, ascent_only=False) == result_key(b, ascent_only=False)
    assert campaign_key(a) == campaign_key(b)


def test_conditions_from_a_forecast_hour() -> None:
    t = int(LAUNCH.timestamp())
    response = {
        "latitude": SPACEPORT[0],
        "longitude": SPACEPORT[1],
        "hourly": {
            "time": [t, t + 3600],
            "temperature_2m": [30.0, 31.0],
            "dew_point_2m": [2.0, 3.0],
            "wind_speed_10m": [4.0, 5.0],
            "cloud_cover": [40.0, 0.0],
            "visibility": [24_000.0, None],
            "wind_gusts_10m": [9.0, 11.0],
        },
    }
    c = conditions_at(response, LAUNCH)
    assert c.launch_utc == LAUNCH
    assert c.cloud_cover_pct == 40
    assert c.cloud_base_m == pytest.approx(125 * 28)
    assert (c.visibility_m, c.wind_speed_ms, c.wind_gust_ms) == (24_000, 4, 9)
    later = conditions_at(response, LAUNCH + timedelta(hours=1))
    assert later.cloud_base_m is None  # clear sky
    assert later.visibility_m is None  # not in the forecast


def test_launch_rules_cannot_be_chosen_as_a_competition() -> None:
    assert load_profiles()["faa-101"].kind == "launch"
    with pytest.raises(ProfileError, match="launch rules"):
        board(ConstraintSettings(profile="faa-101"), None, None)
