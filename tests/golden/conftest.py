from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.mission import Mission, load_mission, parse_yaml
from simcore.mission.models import Drag

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def calisto() -> tuple[Mission, MemoryAssetStore]:
    root = FIXTURES / "calisto"
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((root / name).read_bytes())
    return load_mission(parse_yaml((root / "calisto.mission.yaml").read_text())), store


def estimated(mission: Mission) -> Mission:
    """The same rocket on drag estimated from its shape instead of RocketPy's table."""
    m = mission.model_copy(deep=True)
    assert m.rocket is not None
    m.rocket.drag = Drag(multiplier=m.rocket.drag.multiplier)
    return m


@pytest.fixture(scope="session")
def calisto_estimated(
    calisto: tuple[Mission, MemoryAssetStore],
) -> tuple[Mission, MemoryAssetStore]:
    mission, store = calisto
    return estimated(mission), store
