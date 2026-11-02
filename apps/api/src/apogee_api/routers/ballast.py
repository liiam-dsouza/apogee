"""Ballast: solve for the mass that trims apogee to target, with its checks.

A solve flies about 110 flights (the root find, a full flight and a small
Monte Carlo at the answer), so it runs as a job. Solutions are cached by the
mission's hash: the same mission is never solved twice.
"""

import hashlib
import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.queue import BALLAST_TASK, QueueUnavailable
from apogee_api.routers.sim import _runnable_issues
from simcore.ballast.solve import BallastSolution, target_for
from simcore.mission import Mission, canonical_json
from simcore.versions import rocketpy_version, simcore_version

router = APIRouter(prefix="/api/ballast", tags=["ballast"])


def ballast_key(mission: Mission) -> str:
    """Installed ballast is replaced by the solve, so it doesn't change the answer."""
    data = mission.model_dump(mode="json")
    data["ballast"]["installed_kg"] = 0.0
    payload = "\n".join([canonical_json(data), rocketpy_version(), simcore_version()])
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


class BallastRequest(BaseModel):
    mission: Mission = Field(description="The mission, with its ballast settings.")


class BallastRun(BaseModel):
    status: Literal["queued", "running", "done", "failed"] = Field(description="Solve status.")
    result_id: str = Field(description="Where the solution is (or will be) stored.")
    job_id: str | None = Field(description="Job to poll while not done.")
    error: str | None = Field(default=None, description="Why it failed.")


@router.post(
    "/solve",
    operation_id="solveBallast",
    responses={
        422: {"model": Problem, "description": "The mission can't be solved for yet."},
        503: {"model": Problem, "description": "No job queue."},
    },
)
async def solve_ballast(
    body: BallastRequest, queue: QueueDep, assets: AssetStoreDep, settings: SettingsDep
) -> BallastRun:
    """Start a solve, or return the stored solution for this exact mission."""
    mission = body.mission
    issues = _runnable_issues(mission, assets)
    if issues:
        raise ApiProblem(422, "not_runnable", "This mission cannot be flown yet", None, issues)
    try:
        target_for(mission)
    except ValueError as e:
        raise ApiProblem(422, "no_target", "No apogee target", str(e)) from e
    if mission.ballast.position_m is None:
        raise ApiProblem(422, "no_bay", "Where is the ballast bay?", "Set the bay position.")
    rid = ballast_key(mission)
    if (settings.data_dir / "ballast" / f"{rid}.json").exists():
        return BallastRun(status="done", result_id=rid, job_id=None)
    try:
        job_id = await queue.submit(
            BALLAST_TASK,
            f"ballast:{rid}",
            mission_data=mission.model_dump(mode="json"),
            result_id=rid,
            data_dir=str(settings.data_dir),
        )
        state = await queue.state(job_id)
    except QueueUnavailable as e:
        raise ApiProblem(503, "queue_unavailable", "Simulations are unavailable") from e
    status = "failed" if state.status in ("failed", "not_found") else state.status
    return BallastRun(status=status, result_id=rid, job_id=job_id, error=state.error)


@router.get(
    "/{result_id}",
    operation_id="getBallast",
    responses={404: {"model": Problem, "description": "Not solved (yet)."}},
)
def get_ballast(result_id: str, settings: SettingsDep) -> BallastSolution:
    if not result_id.isalnum():
        raise ApiProblem(404, "ballast_not_found", "No such solution")
    path = settings.data_dir / "ballast" / f"{result_id}.json"
    if not path.exists():
        raise ApiProblem(404, "ballast_not_found", "Not solved yet")
    return BallastSolution.model_validate(json.loads(path.read_text()))
