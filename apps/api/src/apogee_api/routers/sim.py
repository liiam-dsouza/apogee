"""Simulation endpoints. The API validates and enqueues; workers simulate."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.queue import FLIGHT_TASK, JobState, QueueUnavailable
from simcore.mission import Issue, Mission, canonical_json
from simcore.mission.validation import physical_checks
from simcore.results import result_key

router = APIRouter(prefix="/api", tags=["simulation"])

#: Longest a request may wait for its job before returning 202.
MAX_WAIT_S = 60.0


class FlightRequest(BaseModel):
    mission: Mission = Field(description="The mission to fly, saved or not.")
    ascent_only: bool = Field(
        default=False, description="Stop at apogee: about 30% faster, no landing data."
    )


class RunState(BaseModel):
    status: Literal["queued", "running", "done", "failed"] = Field(description="Run status.")
    job_id: str | None = Field(description="Job to poll while not done.")
    result_id: str = Field(description="Where the result is (or will be) stored.")
    cached: bool = Field(description="True if an identical run's result was reused.")
    error: str | None = Field(default=None, description="Why the run failed.")


def _runnable_issues(mission: Mission, store: Any) -> list[Issue]:
    issues = [i for i in physical_checks(mission) if i.severity == "error"]
    for section, label in (("rocket", "a rocket"), ("motor", "a motor"), ("site", "a launch site")):
        if getattr(mission, section) is None:
            issues.append(
                Issue(
                    path=section,
                    message=f"A flight needs {label}.",
                    code="section_missing",
                    severity="error",
                )
            )
    for sha in sorted(mission.referenced_assets()):
        if not store.has(sha):
            issues.append(
                Issue(
                    path="assets",
                    message=f"File {sha[:12]} has not been uploaded.",
                    code="asset_not_uploaded",
                    severity="error",
                )
            )
    return issues


def _from_job(state: JobState, result_id: str) -> RunState:
    if state.status == "done":
        return RunState(status="done", job_id=state.id, result_id=result_id, cached=False)
    if state.status == "failed" or state.status == "not_found":
        return RunState(
            status="failed",
            job_id=state.id,
            result_id=result_id,
            cached=False,
            error=state.error or "the job was lost",
        )
    return RunState(status=state.status, job_id=state.id, result_id=result_id, cached=False)


@router.post(
    "/sim/flight",
    operation_id="runFlight",
    responses={
        202: {"model": RunState, "description": "Queued; poll the job."},
        422: {"model": Problem, "description": "The mission cannot be flown yet."},
        503: {"model": Problem, "description": "No job queue."},
    },
)
async def run_flight(
    body: FlightRequest,
    response: Response,
    queue: QueueDep,
    store: AssetStoreDep,
    settings: SettingsDep,
    wait_s: Annotated[
        float, Query(ge=0, le=MAX_WAIT_S, description="Wait this long for the result.")
    ] = 0,
) -> RunState:
    """Simulate one deterministic flight.

    Identical requests (same mission, versions and mode) reuse the stored
    result. With ``wait_s`` the request waits for the job and usually returns
    it done; otherwise it returns 202 with a job to poll.
    """
    mission = body.mission
    issues = _runnable_issues(mission, store)
    if issues:
        raise ApiProblem(
            422,
            "not_runnable",
            "This mission cannot be flown yet",
            f"{len(issues)} problem(s) found.",
            issues,
        )
    result_id = result_key(mission, ascent_only=body.ascent_only)
    stored = settings.results_dir / result_id
    if (stored / "result.json").exists():
        # Results from before runs kept their mission: the id is the mission's hash, so
        # this request's mission is the one that produced it (for Compare).
        if not (stored / "mission.json").exists():
            (stored / "mission.json").write_text(canonical_json(mission.model_dump(mode="json")))
        return RunState(status="done", job_id=None, result_id=result_id, cached=True)
    try:
        job_id = await queue.submit(
            FLIGHT_TASK,
            f"flight:{result_id}",
            mission_data=mission.model_dump(mode="json"),
            ascent_only=body.ascent_only,
            result_id=result_id,
            data_dir=str(settings.data_dir),
            git_sha=settings.git_sha,
        )
        state = await queue.wait(job_id, wait_s) if wait_s else await queue.state(job_id)
    except QueueUnavailable as e:
        raise ApiProblem(
            503,
            "queue_unavailable",
            "Simulations are unavailable",
            "The job queue is not reachable. Check that Redis and a worker are running.",
        ) from e
    run = _from_job(state, result_id)
    if run.status in ("queued", "running"):
        response.status_code = status.HTTP_202_ACCEPTED
    return run


@router.get(
    "/jobs/{job_id}",
    operation_id="getJob",
    responses={503: {"model": Problem, "description": "No job queue."}},
)
async def get_job(job_id: str, queue: QueueDep) -> JobState:
    try:
        return await queue.state(job_id)
    except QueueUnavailable as e:
        raise ApiProblem(503, "queue_unavailable", "The job queue is not reachable") from e


class FlightLookup(BaseModel):
    result_id: str = Field(description="The mission's single-flight result id.")
    available: bool = Field(description="Whether that flight has been run.")


@router.post("/sim/flight/lookup", operation_id="lookupFlight")
def lookup_flight(body: FlightRequest, settings: SettingsDep) -> FlightLookup:
    """Where this exact mission's flight result is, and whether it exists. Runs nothing."""
    rid = result_key(body.mission, ascent_only=body.ascent_only)
    return FlightLookup(
        result_id=rid, available=(settings.results_dir / rid / "result.json").exists()
    )
