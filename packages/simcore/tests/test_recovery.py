from pathlib import Path

import pytest

from simcore.engine import FlightResult
from simcore.importers.thrust import motor_class, parse_eng
from simcore.mission import Mission
from simcore.recovery import cd_s_for_rate, descent_rate, descent_table

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


def test_rate_and_cd_s_are_inverses() -> None:
    v = descent_rate(20.0, 1.0, 1.2)
    assert v == pytest.approx((2 * 20 * 9.80665 / 1.2) ** 0.5)
    assert cd_s_for_rate(20.0, v, 1.2) == pytest.approx(1.0)


def test_steady_rate_matches_the_simulated_flight(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission, flight = calisto_run
    s = flight.summary
    table = descent_table(mission, apogee_agl_m=s.apogee_agl_m)
    assert [d.name for d in table] == ["Drogue", "Main"]
    drogue, main = table
    assert drogue.top_agl_m == pytest.approx(s.apogee_agl_m)
    assert drogue.bottom_agl_m == main.top_agl_m == pytest.approx(800)
    # The drogue has long reached terminal speed by the main's height.
    assert drogue.rate_bottom_ms == pytest.approx(s.drogue_descent_rate_ms, rel=0.03)
    assert s.landing is not None
    assert main.rate_bottom_ms == pytest.approx(s.landing.speed_ms, rel=0.05)
    # Thinner air higher up: faster.
    assert drogue.rate_top_ms is not None and drogue.rate_top_ms > drogue.rate_bottom_ms


def test_cd_s_for_a_target_rate(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission, _ = calisto_run
    drogue = descent_table(mission, target_rates_ms={"Drogue": 25.0})[0]
    assert drogue.top_agl_m is None  # apogee, no flight given
    assert drogue.cd_s_for_target_m2 is not None
    assert drogue.cd_s_for_target_m2 < drogue.cd_s_m2  # faster needs a smaller canopy
    resized = mission.model_copy(deep=True)
    next(
        d for d in resized.recovery.devices if d.name == "Drogue"
    ).cd_s_m2 = drogue.cd_s_for_target_m2
    assert descent_table(resized)[0].rate_bottom_ms == pytest.approx(25.0)


def test_motor_class() -> None:
    curve = parse_eng((CALISTO / "Cesaroni_M1670.eng").read_text())
    letter, pct = motor_class(curve.total_impulse_ns)
    assert letter == "M" and 0 < pct < 100
    assert motor_class(200)[0] == "H"
    assert motor_class(160)[0] == "G"  # G tops out at 160 N·s
    assert curve.max_thrust_n >= curve.average_thrust_n > 0
