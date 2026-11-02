from pathlib import Path

import numpy as np
import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import FlightResult, run_flight
from simcore.mission import Mission
from simcore.postflight import LogError, launch_time, preview, read_log
from simcore.postflight.fit import fit

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
