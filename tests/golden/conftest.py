from pathlib import Path

import pytest

from simcore.assets import MemoryAssetStore
from simcore.mission import Mission, load_mission, parse_yaml

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def calisto() -> tuple[Mission, MemoryAssetStore]:
    root = FIXTURES / "calisto"
    store = MemoryAssetStore()
    for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
        store.put((root / name).read_bytes())
    return load_mission(parse_yaml((root / "calisto.mission.yaml").read_text())), store
