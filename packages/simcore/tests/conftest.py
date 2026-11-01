from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.engine import FlightResult, run_flight
from simcore.mission import Mission, load_mission, parse_yaml

CALISTO = Path(__file__).parents[3] / "tests" / "fixtures" / "calisto"


@pytest.fixture(scope="session")
def calisto_run() -> tuple[Mission, FlightResult]:
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((CALISTO / name).read_bytes())
    mission = load_mission(parse_yaml((CALISTO / "calisto.mission.yaml").read_text()))
    return mission, run_flight(mission, store)
