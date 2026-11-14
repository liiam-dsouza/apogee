"""Example missions shipped with the library, for the guided tour.

``calisto.apg`` is a copy of missions/examples/calisto.apg (``make example``
writes both): RocketPy's Calisto, the golden reference flight.
"""

from pathlib import Path

from simcore.bundle import read_bundle
from simcore.mission import Mission, load_mission
from simcore.mission.models import EjectionBay
from simcore.structures.materials import FIN_MATERIALS

CALISTO_BUNDLE = Path(__file__).with_name("calisto.apg")

#: The tour's own copy of Calisto, so it never touches a team's missions.
TOUR_MISSION_ID = "01JCALISTOTOUR000000000000"


def tour_mission() -> tuple[Mission, dict[str, bytes]]:
    """Calisto with everything the tour shows filled in, and its assets by hash.

    On top of the reference: 4 mm G10 fins (fin flutter), a drogue and a main
    bay (ejection charges), AURC 2026's 10,000 ft category (the go/no-go board)
    and a 60-sample campaign, small enough to finish while the tour runs.
    """
    data, assets = read_bundle(CALISTO_BUNDLE.read_bytes())
    data["meta"] = {
        **data["meta"],
        "id": TOUR_MISSION_ID,
        "name": "Calisto (tour)",
        "notes": "Made by the guided tour from the Calisto reference. Taking the tour again "
        "resets it.",
    }
    mission = load_mission(data)
    assert mission.rocket is not None
    g10 = next(m for m in FIN_MATERIALS if m.id == "g10")
    mission.rocket.fins = [
        f.model_copy(update={"thickness_m": 0.004, "material": g10.material()})
        for f in mission.rocket.fins
    ]
    inside = round(2 * mission.rocket.radius_m * 0.96, 4)
    mission.ejection.bays = [
        EjectionBay(
            name="Drogue bay",
            device="Drogue",
            inner_diameter_m=inside,
            free_length_m=0.3,
            forward_mass_kg=2.5,
            shear_pins=2,
            pin_strength_n=156,
        ),
        EjectionBay(
            name="Main bay",
            device="Main",
            inner_diameter_m=inside,
            free_length_m=0.4,
            forward_mass_kg=6.0,
            shear_pins=3,
            pin_strength_n=156,
        ),
    ]
    mission.constraints.profile = "aurc-2026"
    mission.constraints.category = "10k-cots"
    mission.monte_carlo.samples = 60
    return mission, assets
