import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
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
async def system_info(queue: QueueDep, settings: SettingsDep) -> SystemInfo:
    workers = await queue.worker_count()
    return SystemInfo(
        rocketpy_version=rocketpy_version(),
        simcore_version=simcore_version(),
        git_sha=settings.git_sha,
        worker_count=workers or 0,
        queue_available=workers is not None,
        field_mode=settings.field_mode,
    )


#: Parts of the data directory: name -> (path under data_dir, what it holds, recomputable).
_STORES = {
    "results": ("results", "Single-flight results", True),
    "campaigns": ("campaigns", "Monte Carlo campaigns", True),
    "ballast": ("ballast", "Ballast solutions", True),
    "weather": ("weather", "Cached forecasts", False),
    "assets": ("assets", "Thrust curves and drag tables", False),
}


class StoreUsage(BaseModel):
    name: str = Field(description="Store name.")
    label: str = Field(description="What it holds.")
    items: int = Field(description="Entries in it.")
    bytes: int = Field(description="Space used.", json_schema_extra={"units": "bytes"})
    recomputable: bool = Field(
        description="Whether everything in it can be computed again (and so may be cleared)."
    )


def _usage(root: Path) -> tuple[int, int]:
    if not root.is_dir():
        return 0, 0
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    return len(entries), size


@router.get("/system/storage", operation_id="getStorage")
def storage(settings: SettingsDep) -> list[StoreUsage]:
    """What the data directory holds. Missions live in the database and aren't listed."""
    out = []
    for name, (sub, label, recomputable) in _STORES.items():
        items, size = _usage(settings.data_dir / sub)
        out.append(
            StoreUsage(name=name, label=label, items=items, bytes=size, recomputable=recomputable)
        )
    return out


@router.delete(
    "/system/storage/{name}",
    operation_id="clearStore",
    status_code=204,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
def clear_store(name: str, settings: SettingsDep) -> None:
    """Delete a store of computed results. Only stores that can be recomputed may be cleared."""
    if name not in _STORES:
        raise ApiProblem(404, "unknown_store", "No such store")
    sub, _, recomputable = _STORES[name]
    if not recomputable:
        raise ApiProblem(409, "not_recomputable", "This store holds data that cannot be recomputed")
    shutil.rmtree(settings.data_dir / sub, ignore_errors=True)
