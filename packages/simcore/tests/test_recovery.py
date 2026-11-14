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


def test_failures_take_away_the_right_device(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    from simcore.recovery import deployment_order, failure_modes, with_failure

    mission, _ = calisto_run
    assert [d.name for d in deployment_order(mission)] == ["Drogue", "Main"]
    assert failure_modes(mission) == ["drogue_fails", "main_fails", "nothing_opens"]
    names = {
        m: [d.name for d in with_failure(mission, m).recovery.devices]
        for m in failure_modes(mission)
    }
    assert names == {"drogue_fails": ["Main"], "main_fails": ["Drogue"], "nothing_opens": []}
    assert len(mission.recovery.devices) == 2  # the mission itself is untouched


def test_failed_recovery_lands_harder(calisto_run: tuple[Mission, FlightResult]) -> None:
    from simcore.assets import MemoryAssetStore
    from simcore.engine import run_flight
    from simcore.recovery import with_failure

    mission, flight = calisto_run
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    nominal = flight.summary.landing
    assert nominal is not None
    landed = {}
    for mode in ("drogue_fails", "main_fails", "nothing_opens"):
        s = run_flight(with_failure(mission, mode), store).summary
        assert s.landing is not None
        landed[mode] = s
    # Under the drogue alone it lands at the drogue's rate; ballistic is far harder still.
    assert landed["main_fails"].landing.speed_ms == pytest.approx(  # type: ignore[union-attr]
        flight.summary.drogue_descent_rate_ms, rel=0.1
    )
    assert landed["nothing_opens"].landing.speed_ms > 3 * landed["main_fails"].landing.speed_ms  # type: ignore[union-attr]
    # Drogue fails: the main opens into a fast fall, then lands like the nominal flight.
    (main,) = landed["drogue_fails"].parachute_events
    assert (
        main.speed_ms is not None
        and main.speed_ms > 2 * flight.summary.parachute_events[-1].speed_ms
    )  # type: ignore[operator]
    assert landed["drogue_fails"].landing.speed_ms == pytest.approx(nominal.speed_ms, rel=0.1)  # type: ignore[union-attr]
