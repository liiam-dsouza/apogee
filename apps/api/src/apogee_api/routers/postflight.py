"""Post-flight: upload a flight log, preview it, compare it with the mission, and fit to it."""

import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, UploadFile
from fastapi import File as FileParam
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.queue import POSTFLIGHT_REPORT_TASK, POSTFLIGHT_TASK, QueueUnavailable
from apogee_api.routers.sim import _runnable_issues
from simcore.mission import Mission, canonical_json
from simcore.mission.models import FLIGHT_IRRELEVANT
from simcore.postflight import LogError, preview
from simcore.postflight.fit import PostflightFit
from simcore.postflight.log import MAX_LOG_BYTES
from simcore.postflight.report import PostflightReport
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
    velocity_column: str | None = Field(default=None, description="Guessed velocity column.")
    velocity_units: Literal["m/s", "ft/s"] = Field(
        default="m/s", description="Guessed velocity units."
    )
    acceleration_column: str | None = Field(
        default=None, description="Guessed acceleration column."
    )
    acceleration_units: Literal["m/s2", "ft/s2", "g"] = Field(
        default="m/s2", description="Guessed acceleration units."
    )


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
        velocity_column=p.velocity_column,
        velocity_units=p.velocity_units,
        acceleration_column=p.acceleration_column,
        acceleration_units=p.acceleration_units,
    )


def _result_id(body: BaseModel, mission: Mission, kind: str | None = None) -> str:
    """Same inputs, same id: a stored result is reused."""
    payload = "\n".join(
        [
            *([kind] if kind else []),
            canonical_json(body.model_dump(mode="json", exclude={"mission"})),
            canonical_json(mission.model_dump(mode="json", exclude=set(FLIGHT_IRRELEVANT))),
            rocketpy_version(),
            simcore_version(),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


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
    rid = _result_id(body, body.mission)
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


class ReportRequest(BaseModel):
    mission: Mission = Field(description="The mission as flown.")
    log_sha256: str = Field(description="The uploaded log.")
    time_column: str = Field(description="Column holding time, in seconds.")
    altitude_column: str = Field(description="Column holding altitude.")
    altitude_units: Literal["m", "ft"] = Field(description="Units of the altitude column.")
    velocity_column: str | None = Field(
        default=None, description="Column holding vertical velocity; derived from altitude if none."
    )
    velocity_units: Literal["m/s", "ft/s"] = Field(
        default="m/s", description="Units of the velocity column."
    )
    acceleration_column: str | None = Field(
        default=None, description="Column holding acceleration; derived from altitude if none."
    )
    acceleration_units: Literal["m/s2", "ft/s2", "g"] = Field(
        default="m/s2", description="Units of the acceleration column."
    )


@router.post(
    "/report",
    operation_id="reportPostflight",
    responses={
        422: {"model": Problem, "description": "The mission can't be flown, or no such log."},
        503: {"model": Problem, "description": "No job queue."},
    },
)
async def start_report(
    body: ReportRequest, queue: QueueDep, assets: AssetStoreDep, settings: SettingsDep
) -> FitRun:
    """Compare the log with a full flight of the mission, or return the stored report."""
    issues = _runnable_issues(body.mission, assets)
    if issues:
        raise ApiProblem(422, "not_runnable", "This mission cannot be flown yet", None, issues)
    if not assets.has(body.log_sha256):
        raise ApiProblem(422, "no_log", "That log is not stored; upload it again")
    rid = _result_id(body, body.mission, "report")
    if (settings.data_dir / "postflight" / "reports" / f"{rid}.json").exists():
        return FitRun(status="done", result_id=rid, job_id=None)
    try:
        job_id = await queue.submit(
            POSTFLIGHT_REPORT_TASK,
            f"postflight-report:{rid}",
            mission_data=body.mission.model_dump(mode="json"),
            log_sha=body.log_sha256,
            time_column=body.time_column,
            altitude_column=body.altitude_column,
            altitude_units=body.altitude_units,
            velocity_column=body.velocity_column,
            velocity_units=body.velocity_units,
            acceleration_column=body.acceleration_column,
            acceleration_units=body.acceleration_units,
            result_id=rid,
            data_dir=str(settings.data_dir),
        )
        state = await queue.state(job_id)
    except QueueUnavailable as e:
        raise ApiProblem(503, "queue_unavailable", "Simulations are unavailable") from e
    status = "failed" if state.status in ("failed", "not_found") else state.status
    return FitRun(status=status, result_id=rid, job_id=job_id, error=state.error)


@router.get(
    "/reports/{result_id}",
    operation_id="getPostflightReport",
    responses={404: {"model": Problem, "description": "Not compared (yet)."}},
)
def get_report(result_id: str, settings: SettingsDep) -> PostflightReport:
    path = settings.data_dir / "postflight" / "reports" / f"{result_id}.json"
    if not result_id.isalnum() or not path.exists():
        raise ApiProblem(404, "report_not_found", "No report yet")
    return PostflightReport.model_validate(json.loads(path.read_text()))
