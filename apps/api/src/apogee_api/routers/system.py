from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api import queue
from apogee_api.settings import get_settings
from simcore.versions import rocketpy_version, simcore_version

router = APIRouter(prefix="/api", tags=["system"])


class SystemInfo(BaseModel):
    rocketpy_version: str = Field(description="RocketPy version the workers simulate with.")
    simcore_version: str = Field(description="simcore package version.")
    git_sha: str = Field(description="Commit the running build was made from.")
    worker_count: int = Field(description="Workers currently sending heartbeats.")
    queue_available: bool = Field(description="Whether the job queue (Redis) is reachable.")
    field_mode: bool = Field(description="Whether the deployment is in field mode.")


class Health(BaseModel):
    status: str = Field(description="'ok' when the API process is serving.")


@router.get("/health", operation_id="getHealth")
async def health() -> Health:
    return Health(status="ok")


@router.get("/system/info", operation_id="getSystemInfo")
async def system_info() -> SystemInfo:
    settings = get_settings()
    workers = await queue.worker_count()
    return SystemInfo(
        rocketpy_version=rocketpy_version(),
        simcore_version=simcore_version(),
        git_sha=settings.git_sha,
        worker_count=workers or 0,
        queue_available=workers is not None,
        field_mode=settings.field_mode,
    )
