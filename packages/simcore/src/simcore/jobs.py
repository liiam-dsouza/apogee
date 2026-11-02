"""Job bodies: plain functions the worker runs (in a process pool) and tests call.

They take and return plain data so they pickle cheaply across processes.
"""

from pathlib import Path
from typing import Any


def simulate_flight(
    mission_data: dict[str, Any],
    *,
    ascent_only: bool,
    result_id: str,
    data_dir: str,
    git_sha: str,
) -> str:
    """Run one flight and store it under ``data_dir/results``. Returns the result id."""
    from simcore.assets import DirectoryAssetStore
    from simcore.engine import run_flight
    from simcore.mission import load_mission
    from simcore.results import write_flight

    root = Path(data_dir)
    mission = load_mission(mission_data)
    result = run_flight(
        mission, DirectoryAssetStore(root / "assets"), terminate_on_apogee=ascent_only
    )
    write_flight(root / "results", result_id, mission, result, git_sha=git_sha)
    return result_id


def openrocket_cross_check(
    mission_data: dict[str, Any], *, reference: dict[str, float], data_dir: str
) -> list[dict[str, Any]]:
    """Fly an imported rocket under OpenRocket's own conditions and compare.

    Returns CrossCheck rows (as dicts) for apogee, max Mach, rail exit and CP.
    """
    from simcore.assets import DirectoryAssetStore
    from simcore.engine import center_of_pressure_m, run_flight
    from simcore.importers.openrocket import CrossCheck
    from simcore.mission import load_mission

    mission = load_mission(mission_data)
    store = DirectoryAssetStore(Path(data_dir) / "assets")
    s = run_flight(mission, store).summary
    rows: list[CrossCheck] = []

    def pct(ours: float, theirs: float) -> float:
        return abs(ours - theirs) / abs(theirs)

    if "apogee_m" in reference:
        rows.append(
            CrossCheck(
                quantity="Apogee",
                units="m",
                ours=s.apogee_agl_m,
                openrocket=reference["apogee_m"],
                tolerance="3%",
                status="ok" if pct(s.apogee_agl_m, reference["apogee_m"]) <= 0.03 else "flag",
                note="Both flown in ISA with OpenRocket's average wind, from its site and rod. "
                "A large difference usually means something was mapped wrongly.",
            )
        )
    if "max_mach" in reference:
        rows.append(
            CrossCheck(
                quantity="Max Mach",
                units="1",
                ours=s.max_mach,
                openrocket=reference["max_mach"],
                tolerance="3%",
                status="ok" if pct(s.max_mach, reference["max_mach"]) <= 0.03 else "flag",
                note="Same conditions as the apogee comparison.",
            )
        )
    if "rail_exit_velocity_ms" in reference:
        rows.append(
            CrossCheck(
                quantity="Rail exit velocity",
                units="m/s",
                ours=s.rail_exit_velocity_ms,
                openrocket=reference["rail_exit_velocity_ms"],
                tolerance="by definition",
                status="explained",
                note=(
                    "Defined differently. RocketPy: when the upper rail button leaves the rail, "
                    "starting with the motor at the rail's base. OpenRocket: when the rocket has "
                    "travelled the full rod length. RocketPy's is the physical one for rail "
                    "buttons, and lower."
                ),
            )
        )
    if "cp_m" in reference and "cp_mach" in reference:
        cp = center_of_pressure_m(mission, store, reference["cp_mach"])
        rows.append(
            CrossCheck(
                quantity=f"Centre of pressure at Mach {reference['cp_mach']:.2f}",
                units="m from nose tip",
                ours=cp,
                openrocket=reference["cp_m"],
                tolerance="3 cm",
                status="ok" if abs(cp - reference["cp_m"]) <= 0.03 else "flag",
                note=(
                    f"OpenRocket's value at {reference.get('cp_aoa_deg', 0):.2f}° angle of attack. "
                    "Near zero angle of attack, because OpenRocket adds body lift at angle of "
                    "attack and RocketPy does not."
                ),
            )
        )
    return [r.model_dump() for r in rows]
