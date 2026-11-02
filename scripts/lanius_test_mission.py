"""Build the Lanius test mission: the team's rocket at White Cliffs.

    uv run python scripts/lanius_test_mission.py

Reads data/Lanius.ork (the team's design; not in git) and writes
data/lanius-white-cliffs.mission.zip, ready to import in Missions.

What is real and what is not:
- Rocket, recovery: imported from the .ork (see the import report in the app).
- Motor: AeroTech M1340W, the design's default, from ThrustCurve.org cert data.
- Pad: White Cliffs, -30.664810, 143.196302 (Endeavour Aerospace launch site).
- Elevation: 220 m from Open-Meteo's 90 m elevation model. CONFIRM on site;
  the .ork's simulations used 150.9 m.
- Rail: 4.89 m, vertical, from the .ork's up-to-date simulation.
- Boundary: an ILLUSTRATIVE 3 km square centred on the pad, for testing the
  map. Not the real range boundary.
- Atmosphere: standard, no wind (no weather has been fetched).
"""

import math
from pathlib import Path

from simcore.assets import MemoryAssetStore
from simcore.bundle import write_bundle
from simcore.importers.openrocket import import_openrocket
from simcore.importers.thrust import generic_motor_estimate, parse_eng
from simcore.mission import load_mission, validate_mission

ROOT = Path(__file__).parents[1]
ORK = ROOT / "data" / "Lanius.ork"
ENG = ROOT / "tests" / "fixtures" / "motors" / "AeroTech_M1340W.eng"
OUT = ROOT / "data" / "lanius-white-cliffs.mission.zip"

PAD_LAT = -(30 + 39 / 60 + 53.316 / 3600)  # 30°39'53.316" S
PAD_LON = 143 + 11 / 60 + 46.686 / 3600  # 143°11'46.686" E
ELEVATION_M = 220.0
HALF_SIDE_M = 1500.0


def square(lat: float, lon: float, half_m: float) -> list[tuple[float, float]]:
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    return [
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon + dlon, lat + dlat),
        (lon - dlon, lat + dlat),
    ]


def main() -> None:
    imported = import_openrocket(ORK.read_bytes())
    store = MemoryAssetStore()
    assets = {}
    for sha, (name, data) in imported.assets.items():
        store.put(data)
        assets[sha] = {"kind": "drag_table", "filename": name, "size": len(data)}
    eng = ENG.read_bytes()
    thrust_sha = store.put(eng)
    assets[thrust_sha] = {"kind": "thrust_curve", "filename": ENG.name, "size": len(eng)}

    rail = imported.rail
    mission_data = {
        "meta": {
            "name": "Lanius at White Cliffs (test)",
            "id": "01JLANIUSWHITECLIFFS000000",
            "authors": ["Apogee test fixture"],
            "notes": (
                "Test mission. Rocket and recovery imported from Lanius.ork; motor M1340W. "
                "Elevation 220 m is from an elevation model: confirm on site. "
                "The range boundary is an illustrative 3 km square, not the real one."
            ),
        },
        "rocket": imported.rocket.model_dump(mode="json"),
        "motor": {
            "kind": "generic",
            "thrust_curve": thrust_sha,
            **generic_motor_estimate(parse_eng(eng.decode())),
        },
        "recovery": imported.recovery.model_dump(mode="json"),
        "site": {
            "latitude_deg": PAD_LAT,
            "longitude_deg": PAD_LON,
            "elevation_m": ELEVATION_M,
            "rail_length_m": rail.rail_length_m if rail else 4.89,
            "inclination_deg": rail.inclination_deg if rail else 90.0,
            "heading_deg": 0.0,
            "boundary": square(PAD_LAT, PAD_LON, HALF_SIDE_M),
        },
        "environment": {"atmosphere": {"kind": "standard"}},
        "assets": assets,
    }
    mission, report = validate_mission(mission_data)
    for issue in report.issues:
        print(f"{issue.severity}: {issue.path}: {issue.message}")
    assert mission is not None and report.valid
    OUT.write_bytes(write_bundle(load_mission(mission.model_dump(mode="json")), store))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
