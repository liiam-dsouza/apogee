from pathlib import Path

import numpy as np
import pytest

from simcore.engine import FlightResult
from simcore.mission import Mission
from simcore.results import lttb

CalistoRun = tuple[Mission, FlightResult]


def test_lttb_keeps_ends_and_peaks() -> None:
    x = np.linspace(0, 60, 60_000)
    y = np.sin(x)
    y[31_337] = 50.0  # a one-sample spike, like max q
    xs, ys = lttb(x, y, 2000)
    assert len(xs) == 2000
    assert xs[0] == x[0] and xs[-1] == x[-1]
    assert 50.0 in ys
    assert np.all(np.diff(xs) > 0)


def test_lttb_passes_short_series_through() -> None:
    x = np.arange(10.0)
    xs, ys = lttb(x, x * 2, 2000)
    assert xs.tolist() == x.tolist()
    assert ys.tolist() == (x * 2).tolist()


def test_flight_round_trips_through_storage(tmp_path: Path, calisto_run: CalistoRun) -> None:
    from simcore.results import read_record, read_series, result_key, write_flight

    mission, result = calisto_run
    rid = result_key(mission, ascent_only=False)
    record = write_flight(tmp_path, rid, mission, result, git_sha="test")
    again = read_record(tmp_path, rid)
    assert again == record
    assert again.summary == result.summary
    assert again.provenance.rocketpy_version == "1.13.0"
    [alt] = read_series(tmp_path, rid, ["altitude_agl_m"], max_points=500)
    assert len(alt.t) == 500
    assert max(alt.y) == pytest.approx(result.summary.apogee_agl_m, rel=1e-6)


def test_result_key_depends_on_mode_and_content(calisto_run: CalistoRun) -> None:
    from simcore.results import result_key

    mission, _ = calisto_run
    assert result_key(mission, ascent_only=True) != result_key(mission, ascent_only=False)
    changed = mission.model_copy(deep=True)
    assert changed.rocket is not None
    changed.rocket.dry_mass_kg += 0.001
    assert result_key(changed, ascent_only=False) != result_key(mission, ascent_only=False)


def test_concurrent_writers_leave_one_result_and_no_temp_dirs(
    tmp_path: Path, calisto_run: CalistoRun
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from simcore.results import read_record, result_key, write_flight

    mission, result = calisto_run
    rid = result_key(mission, ascent_only=False)
    with ThreadPoolExecutor(8) as pool:
        list(
            pool.map(lambda _: write_flight(tmp_path, rid, mission, result, git_sha="t"), range(8))
        )
    assert [p.name for p in tmp_path.iterdir()] == [rid]
    assert read_record(tmp_path, rid).summary == result.summary
