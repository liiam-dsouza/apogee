from pathlib import Path

import numpy as np
import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import FlightResult, run_flight
from simcore.mission import Mission
from simcore.postflight import LogError, launch_time, preview, read_log
from simcore.postflight.fit import fit
from simcore.postflight.log import G0, pad_zero, read_columns
from simcore.postflight.report import Metric, PostflightReport, report

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"
FT = 0.3048


def _store() -> MemoryAssetStore:
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    return store


def _log_csv(mission: Mission, drag: float) -> bytes:
    """A barometric log of the mission flown with ``drag``.

    Feet above sea level, 20 Hz, noisy, starting 5 s before launch.
    """
    m = mission.model_copy(deep=True)
    assert m.rocket is not None and m.site is not None
    m.rocket.drag.multiplier = drag
    r = run_flight(m, _store(), terminate_on_apogee=True)
    t_flight, alt = np.asarray(r.trajectory["time_s"]), np.asarray(r.trajectory["altitude_agl_m"])
    rng = np.random.default_rng(3)
    t = np.arange(0, 5 + t_flight[-1] + 3, 0.05)
    agl = np.interp(t - 5, t_flight, alt, left=0.0, right=alt[-1])
    asl_ft = (agl + m.site.elevation_m) / FT + rng.normal(0, 3, len(t))
    rows = "\n".join(f"{1000 + ti:.2f},{a:.1f},21.5" for ti, a in zip(t, asl_ft, strict=True))
    return f"Time (s),Altitude (ft),Temp (C)\n{rows}\n".encode()


def test_preview_guesses_the_columns(calisto_run: tuple[Mission, FlightResult]) -> None:
    p = preview(_log_csv(calisto_run[0], 1.0))
    assert (p.time_column, p.altitude_column, p.altitude_units) == (
        "Time (s)",
        "Altitude (ft)",
        "ft",
    )
    assert len(p.rows) == 8


def test_log_is_read_above_the_pad_and_launch_found(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    t, alt = read_log(_log_csv(calisto_run[0], 1.0), "Time (s)", "Altitude (ft)", "ft")
    assert abs(alt[:50].mean()) < 2  # on the pad
    assert alt.max() == pytest.approx(calisto_run[1].summary.apogee_agl_m, abs=10)
    assert launch_time(t, alt) == pytest.approx(1005, abs=0.3)


def test_fit_recovers_the_drag_it_was_flown_with(calisto_run: tuple[Mission, FlightResult]) -> None:
    mission = calisto_run[0]
    t, alt = read_log(_log_csv(mission, 1.15), "Time (s)", "Altitude (ft)", "ft")
    result = fit(mission, _store(), t, alt)
    assert result.drag_multiplier == pytest.approx(1.15, rel=0.03)
    assert result.rms_after_m < result.rms_before_m / 3
    assert result.fitted_apogee_m == pytest.approx(result.measured_apogee_m, abs=15)
    assert result.impulse_scale == 1.0 and not result.fitted_impulse


def test_bad_logs_are_refused() -> None:
    with pytest.raises(LogError, match="name the columns"):
        preview(b"1,2\n3,4\n5,6\n")
    with pytest.raises(LogError, match="never climbs"):
        launch_time(np.arange(10.0), np.zeros(10))


def _full_log(mission: Mission, drag: float, *, channels: bool) -> bytes:
    """A whole flight of the mission flown with ``drag``, as an altimeter would log it.

    Feet above sea level at 20 Hz, starting 5 s before launch; with ``channels``,
    also vertical velocity (ft/s) and an accelerometer reading in g (1 g on the pad).
    """
    m = mission.model_copy(deep=True)
    assert m.rocket is not None and m.site is not None
    m.rocket.drag.multiplier = drag
    r = run_flight(m, _store())
    tf = np.asarray(r.trajectory["time_s"])
    alt, vz = (
        np.asarray(r.trajectory["altitude_agl_m"]),
        np.asarray(r.trajectory["vertical_velocity_ms"]),
    )
    rng = np.random.default_rng(5)
    t = np.arange(0, 5 + tf[-1] + 3, 0.05)
    agl = np.interp(t - 5, tf, alt, left=0.0, right=0.0)
    asl_ft = (agl + m.site.elevation_m) / FT + rng.normal(0, 2, len(t))
    if not channels:
        rows = (f"{ti:.2f},{a:.1f}" for ti, a in zip(t, asl_ft, strict=True))
        return ("Time (s),Altitude (ft)\n" + "\n".join(rows) + "\n").encode()
    v = np.interp(t - 5, tf, vz, left=0.0, right=0.0)
    a_g = 1 + np.gradient(v, t) / 9.80665 + rng.normal(0, 0.05, len(t))
    rows = (
        f"{ti:.2f},{a:.1f},{vi / FT:.2f},{ai:.3f}"
        for ti, a, vi, ai in zip(t, asl_ft, v, a_g, strict=True)
    )
    return ("Time (s),Altitude (ft),Velocity (ft/s),Accel (g)\n" + "\n".join(rows) + "\n").encode()


def _metrics(r: PostflightReport) -> dict[str, Metric]:
    return {m.key: m for m in r.metrics}


def test_report_of_the_flight_it_was_flown_from_agrees(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission, flight = calisto_run
    data = _full_log(mission, 1.0, channels=True)
    p = preview(data)
    assert (p.velocity_column, p.velocity_units) == ("Velocity (ft/s)", "ft/s")
    assert (p.acceleration_column, p.acceleration_units) == ("Accel (g)", "g")
    t, (alt, vel, acc) = read_columns(
        data, "Time (s)", ["Altitude (ft)", "Velocity (ft/s)", "Accel (g)"]
    )
    r = report(
        mission, _store(), t, pad_zero(alt * FT), log_velocity=vel * FT, log_acceleration=acc * G0
    )
    m = _metrics(r)
    assert abs(m["apogee"].error_pct or 0) < 0.5
    assert abs(m["max_vertical_velocity"].error_pct or 0) < 2
    assert abs(m["max_acceleration"].error_pct or 0) < 10
    assert abs(m["flight_time"].error or 0) < 1
    assert m["burnout"].error is not None and abs(m["burnout"].error) < 0.3
    assert not any(c.derived for c in r.channels)
    alt_channel = next(c for c in r.channels if c.name == "altitude_agl_m")
    assert alt_channel.rms_error < 5
    # Calisto's main opens at 800 m on the way down: found by the drop in descent rate.
    main = r.events[-2]
    assert main.measured_s == pytest.approx(main.simulated_s, abs=1.0)
    assert flight.summary.parachute_events[-1].name in main.name


def test_report_shows_the_extra_drag_and_derives_missing_channels(
    calisto_run: tuple[Mission, FlightResult],
) -> None:
    mission = calisto_run[0]
    t, alt = read_log(_full_log(mission, 1.15, channels=False), "Time (s)", "Altitude (ft)", "ft")
    r = report(mission, _store(), t, alt)
    m = _metrics(r)
    # Less drag in the simulation than in the flight: it overshoots.
    assert (m["apogee"].error or 0) > 20
    assert m["max_vertical_velocity"].derived and m["max_vertical_velocity"].error_pct is not None
    assert abs(m["max_vertical_velocity"].error_pct) < 10
    assert {c.name for c in r.channels if c.derived} == {"vertical_velocity_ms", "acceleration_ms2"}
    assert any("derived" in w for w in r.warnings)
