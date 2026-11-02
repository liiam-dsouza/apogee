"""Post-flight: upload a flight log, preview it, and fit the mission to it."""

import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, UploadFile
from fastapi import File as FileParam
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.queue import POSTFLIGHT_TASK, QueueUnavailable
from apogee_api.routers.sim import _runnable_issues
from simcore.mission import Mission, canonical_json
from simcore.postflight import LogError, preview
from simcore.postflight.fit import PostflightFit
from simcore.postflight.log import MAX_LOG_BYTES
from simcore.versions import rocketpy_version, simcore_version

router = APIRouter(prefix="/api/postflight", tags=["post-flight"])


class LogPreview(BaseModel):
    sha256: str = Field(description="The stored log; pass it to the fit.")
    filename: str = Field(description="Original filename.")
    columns: list[str] = Field(description="Column names from the header.")
    rows: list[list[str]] = Field(description="The first rows, as text.")
    time_column: str | None = Field(description="Guessed time column.")
    altitude_column: str | None = Field(description="Guessed altitude column.")
    altitude_units: Literal["m", "ft"] = Field(description="Guessed altitude units.")


@router.post(
    "/logs",
    operation_id="uploadFlightLog",
    responses={422: {"model": Problem, "description": "Not a readable log."}},
)
async def upload_log(
    store: AssetStoreDep, file: Annotated[UploadFile, FileParam(description="CSV log.")]
) -> LogPreview:
    """Store a flight log and show its columns, with a guess at time and altitude."""
    data = await file.read(MAX_LOG_BYTES + 1)
    if len(data) > MAX_LOG_BYTES:
        raise ApiProblem(413, "file_too_large", "The log is larger than 20 MB")
    try:
        p = preview(data)
    except (LogError, UnicodeDecodeError) as e:
        raise ApiProblem(422, "unreadable_log", "This log can't be read", str(e)) from e
    return LogPreview(
        sha256=store.put(data),
        filename=file.filename or "log.csv",
        columns=p.columns,
        rows=p.rows,
        time_column=p.time_column,
        altitude_column=p.altitude_column,
        altitude_units=p.altitude_units,
    )


class FitRequest(BaseModel):
    mission: Mission = Field(description="The mission as flown.")
    log_sha256: str = Field(description="The uploaded log.")
    time_column: str = Field(description="Column holding time, in seconds.")
    altitude_column: str = Field(description="Column holding altitude.")
    altitude_units: Literal["m", "ft"] = Field(description="Units of the altitude column.")
    fit_impulse: bool = Field(default=False, description="Also fit the total-impulse scale.")


class FitRun(BaseModel):
    status: Literal["queued", "running", "done", "failed"] = Field(description="Fit status.")
    result_id: str = Field(description="Where the fit is (or will be) stored.")
    job_id: str | None = Field(description="Job to poll while not done.")
    error: str | None = Field(default=None, description="Why it failed.")


@router.post(
    "/fit",
    operation_id="fitPostflight",
    responses={
        422: {"model": Problem, "description": "The mission can't be flown, or no such log."},
        503: {"model": Problem, "description": "No job queue."},
    },
)
async def start_fit(
    body: FitRequest, queue: QueueDep, assets: AssetStoreDep, settings: SettingsDep
) -> FitRun:
    """Fit the drag multiplier (and impulse) to the log, or return the stored fit."""
    issues = _runnable_issues(body.mission, assets)
    if issues:
        raise ApiProblem(422, "not_runnable", "This mission cannot be flown yet", None, issues)
    if not assets.has(body.log_sha256):
        raise ApiProblem(422, "no_log", "That log is not stored; upload it again")
    payload = "\n".join(
        [
            canonical_json(body.model_dump(mode="json", exclude={"mission"})),
            canonical_json(
                body.mission.model_dump(mode="json", exclude={"monte_carlo", "constraints"})
            ),
            rocketpy_version(),
            simcore_version(),
        ]
    )
    rid = hashlib.sha256(payload.encode()).hexdigest()[:32]
    if (settings.data_dir / "postflight" / f"{rid}.json").exists():
        return FitRun(status="done", result_id=rid, job_id=None)
    try:
        job_id = await queue.submit(
            POSTFLIGHT_TASK,
            f"postflight:{rid}",
            mission_data=body.mission.model_dump(mode="json"),
            log_sha=body.log_sha256,
            time_column=body.time_column,
            altitude_column=body.altitude_column,
            altitude_units=body.altitude_units,
            fit_impulse=body.fit_impulse,
            result_id=rid,
            data_dir=str(settings.data_dir),
        )
        state = await queue.state(job_id)
    except QueueUnavailable as e:
        raise ApiProblem(503, "queue_unavailable", "Simulations are unavailable") from e
    status = "failed" if state.status in ("failed", "not_found") else state.status
    return FitRun(status=status, result_id=rid, job_id=job_id, error=state.error)


@router.get(
    "/fits/{result_id}",
    operation_id="getPostflightFit",
    responses={404: {"model": Problem, "description": "Not fitted (yet)."}},
)
def get_fit(result_id: str, settings: SettingsDep) -> PostflightFit:
    path = settings.data_dir / "postflight" / f"{result_id}.json"
    if not result_id.isalnum() or not path.exists():
        raise ApiProblem(404, "fit_not_found", "Not fitted yet")
    return PostflightFit.model_validate(json.loads(path.read_text()))
