"""arq worker: ``arq apogee_worker.main.WorkerSettings``.

Consumes jobs from Redis and runs them through simcore in a process pool, so
CPU-bound simulations never block the event loop (and its heartbeat).
"""

import asyncio
import contextlib
import os
import socket
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, ClassVar

from arq.connections import RedisSettings
from pydantic_settings import BaseSettings, SettingsConfigDict

from simcore import jobs
from simcore.versions import rocketpy_version, simcore_version

# Shared with apogee_api.queue; the worker must not import the API package.
WORKER_HEARTBEAT_PREFIX = "apogee:worker:"
HEARTBEAT_INTERVAL_S = 10
HEARTBEAT_TTL_S = 30


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APOGEE_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    max_jobs: int = 4
    data_dir: str = ".data"
    git_sha: str = "dev"


settings = Settings()


async def ping(_: dict[str, Any]) -> dict[str, str]:
    """Round-trip check for the queue; returns the versions a job would run with."""
    return {"simcore_version": simcore_version(), "rocketpy_version": rocketpy_version()}


async def simulate_flight(ctx: dict[str, Any], **kwargs: Any) -> str:
    """One deterministic flight; returns the stored result id."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(ctx["pool"], partial(jobs.simulate_flight, **kwargs))


async def openrocket_cross_check(ctx: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
    """Fly an imported design under OpenRocket's conditions; returns report rows."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(ctx["pool"], partial(jobs.openrocket_cross_check, **kwargs))


async def monte_carlo_chunk(ctx: dict[str, Any], **kwargs: Any) -> str:
    """One chunk of a Monte Carlo campaign; returns the campaign id."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(ctx["pool"], partial(jobs.monte_carlo_chunk, **kwargs))


async def _heartbeat(ctx: dict[str, Any]) -> None:
    key = ctx["heartbeat_key"]
    while True:
        await ctx["redis"].set(key, "1", ex=HEARTBEAT_TTL_S)
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["pool"] = ProcessPoolExecutor(max_workers=settings.max_jobs)
    ctx["heartbeat_key"] = f"{WORKER_HEARTBEAT_PREFIX}{socket.gethostname()}:{os.getpid()}"
    ctx["heartbeat"] = asyncio.create_task(_heartbeat(ctx))


async def shutdown(ctx: dict[str, Any]) -> None:
    ctx["heartbeat"].cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await ctx["heartbeat"]
    await ctx["redis"].delete(ctx["heartbeat_key"])
    ctx["pool"].shutdown(cancel_futures=True)


class WorkerSettings:
    functions: ClassVar = [ping, simulate_flight, openrocket_cross_check, monte_carlo_chunk]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.max_jobs
    # A full flight is ~300 ms; anything near this is stuck, not slow.
    job_timeout = 300
