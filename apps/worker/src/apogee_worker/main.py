"""arq worker: ``arq apogee_worker.main.WorkerSettings``.

Consumes jobs from Redis and runs them through simcore. Publishes a heartbeat
so the API can report how many workers are live.
"""

import asyncio
import contextlib
import os
import socket
from typing import Any, ClassVar

from arq.connections import RedisSettings
from pydantic_settings import BaseSettings, SettingsConfigDict

from simcore.versions import rocketpy_version, simcore_version

# Shared with apogee_api.queue; the worker must not import the API package.
WORKER_HEARTBEAT_PREFIX = "apogee:worker:"
HEARTBEAT_INTERVAL_S = 10
HEARTBEAT_TTL_S = 30


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APOGEE_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    max_jobs: int = 4


settings = Settings()


async def ping(_: dict[str, Any]) -> dict[str, str]:
    """Round-trip check for the queue; returns the versions a job would run with."""
    return {"simcore_version": simcore_version(), "rocketpy_version": rocketpy_version()}


async def _heartbeat(ctx: dict[str, Any]) -> None:
    key = ctx["heartbeat_key"]
    while True:
        await ctx["redis"].set(key, "1", ex=HEARTBEAT_TTL_S)
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["heartbeat_key"] = f"{WORKER_HEARTBEAT_PREFIX}{socket.gethostname()}:{os.getpid()}"
    ctx["heartbeat"] = asyncio.create_task(_heartbeat(ctx))


async def shutdown(ctx: dict[str, Any]) -> None:
    ctx["heartbeat"].cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await ctx["heartbeat"]
    await ctx["redis"].delete(ctx["heartbeat_key"])


class WorkerSettings:
    functions: ClassVar = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.max_jobs
