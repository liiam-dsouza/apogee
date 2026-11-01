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
