"""Rewrite the pinned golden numbers: ``uv run python tests/golden/regenerate.py``.

Only after a deliberate, reviewed change (a RocketPy upgrade, a model fix).
The diff of calisto.json is the review: every number that moved, and by how much.
"""

import json
from pathlib import Path

from simcore.assets import MemoryAssetStore
from simcore.engine import run_flight
from simcore.mission import load_mission, parse_yaml
from simcore.versions import rocketpy_version

root = Path(__file__).parent.parent / "fixtures" / "calisto"
store = MemoryAssetStore()
for name in ("Cesaroni_M1670.eng", "powerOffDragCurve.csv"):
    store.put((root / name).read_bytes())
mission = load_mission(parse_yaml((root / "calisto.mission.yaml").read_text()))
summary = run_flight(mission, store).summary.model_dump(mode="json")
out = Path(__file__).parent / "calisto.json"
out.write_text(
    json.dumps({"rocketpy_version": rocketpy_version(), "summary": summary}, indent=2) + "\n"
)
print(f"wrote {out}")
