"""Free-form fins fly through RocketPy's FreeFormFins, not an approximation."""

from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import FlightResult, run_flight
from simcore.engine.build import center_of_pressure_m, rocket_length_m
from simcore.mission import Mission
from simcore.mission.models import FreeFormFins, TrapezoidalFins

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


def _as_free_form(mission: Mission) -> Mission:
    """Calisto with its trapezoidal fins redrawn as the same free-form outline."""
    assert mission.rocket is not None
    [fins] = mission.rocket.fins
    assert isinstance(fins, TrapezoidalFins)
    free = FreeFormFins(
        kind="free_form",
        count=fins.count,
        points=fins.outline(),
        position_m=fins.position_m,
        cant_angle_deg=fins.cant_angle_deg,
    )
    rocket = mission.rocket.model_copy(update={"fins": [free]})
    return mission.model_copy(update={"rocket": rocket})


@pytest.fixture(scope="module")
def store() -> MemoryAssetStore:
    s = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        s.put((CALISTO / name).read_bytes())
    return s


def test_same_outline_same_centre_of_pressure(
    calisto_run: tuple[Mission, FlightResult], store: MemoryAssetStore
) -> None:
    mission, _ = calisto_run
    free = _as_free_form(mission)
    for mach in (0.1, 0.5):
        assert center_of_pressure_m(free, store, mach) == pytest.approx(
            center_of_pressure_m(mission, store, mach), abs=0.005
        )
    assert rocket_length_m(free) == pytest.approx(rocket_length_m(mission))


def test_same_outline_flies_the_same(
    calisto_run: tuple[Mission, FlightResult], store: MemoryAssetStore
) -> None:
    mission, trapezoid = calisto_run
    free = run_flight(_as_free_form(mission), store)
    assert free.summary.apogee_agl_m == pytest.approx(trapezoid.summary.apogee_agl_m, rel=0.01)
