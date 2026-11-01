"""The job queue, behind a small interface.

``ArqQueue`` is the real one (Redis + workers). ``InlineQueue`` runs jobs in a
thread inside the API process: for tests, and for local development without
Redis (APOGEE_QUEUE=inline). The API itself never imports RocketPy; inline
jobs call the same simcore job function the worker does.
"""

import asyncio
import dataclasses
import logging
import uuid
from typing import Any, Literal, Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

#: Workers refresh `{WORKER_HEARTBEAT_PREFIX}{worker id}` with a short TTL.
WORKER_HEARTBEAT_PREFIX = "apogee:worker:"

#: Must match the function name registered in apogee_worker.
FLIGHT_TASK = "simulate_flight"


class JobState(BaseModel):
    id: str = Field(description="Job id.")
    status: Literal["queued", "running", "done", "failed", "not_found"] = Field(
        description="Where the job is."
    )
    result_id: str | None = Field(default=None, description="Result id once done.")
    error: str | None = Field(default=None, description="Why it failed, if it did.")


class QueueUnavailable(RuntimeError):
    pass


class JobQueue(Protocol):
    async def submit(self, task: str, job_id: str, **kwargs: Any) -> str: ...
    async def state(self, job_id: str) -> JobState: ...
    async def wait(self, job_id: str, timeout_s: float) -> JobState: ...
    async def worker_count(self) -> int | None: ...
    async def close(self) -> None: ...


class ArqQueue:
    def __init__(self, pool: ArqRedis | None) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, redis_url: str) -> "ArqQueue":
        # Fail fast: the API starts without a queue rather than waiting on one.
        settings = dataclasses.replace(
            RedisSettings.from_dsn(redis_url), conn_timeout=1, conn_retries=0
        )
        try:
            return cls(await create_pool(settings))
        except (TimeoutError, OSError, RedisError) as e:
            log.warning("job queue unavailable: %s", e)
            return cls(None)

    def _require(self) -> ArqRedis:
        if self._pool is None:
            raise QueueUnavailable("the job queue (Redis) is not reachable")
        return self._pool

    async def submit(self, task: str, job_id: str, **kwargs: Any) -> str:
        pool = self._require()
        job = await pool.enqueue_job(task, _job_id=job_id, **kwargs)
        if job is None:
            # arq refuses a job id it still holds. If that run is live, share it;
            # if it finished (e.g. failed), start a fresh one.
            existing = await self.state(job_id)
            if existing.status in ("queued", "running"):
                return job_id
            fresh = f"{job_id}:{uuid.uuid4().hex[:8]}"
            await pool.enqueue_job(task, _job_id=fresh, **kwargs)
            return fresh
        return job_id

    async def state(self, job_id: str) -> JobState:
        job = Job(job_id, self._require())
        status = await job.status()
        if status in (JobStatus.queued, JobStatus.deferred):
            return JobState(id=job_id, status="queued")
        if status == JobStatus.in_progress:
            return JobState(id=job_id, status="running")
        if status == JobStatus.not_found:
            return JobState(id=job_id, status="not_found")
        info = await job.result_info()
        if info is None:
            return JobState(id=job_id, status="not_found")
        if info.success:
            return JobState(id=job_id, status="done", result_id=str(info.result))
        return JobState(id=job_id, status="failed", error=str(info.result))

    async def wait(self, job_id: str, timeout_s: float) -> JobState:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            state = await self.state(job_id)
            if state.status in ("done", "failed", "not_found"):
                return state
            if asyncio.get_running_loop().time() >= deadline:
                return state
            await asyncio.sleep(0.05)

    async def worker_count(self) -> int | None:
        if self._pool is None:
            return None
        try:
            return len([k async for k in self._pool.scan_iter(match=f"{WORKER_HEARTBEAT_PREFIX}*")])
        except (TimeoutError, OSError, RedisError):
            return None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()


class InlineQueue:
    """Runs jobs in threads in this process. Not for production."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    async def submit(self, task: str, job_id: str, **kwargs: Any) -> str:
        from simcore import jobs  # the same body the worker runs

        fn = getattr(jobs, task)
        running = self._tasks.get(job_id)
        if running is not None and not running.done():
            return job_id
        self._tasks[job_id] = asyncio.create_task(asyncio.to_thread(fn, **kwargs))
        return job_id

    async def state(self, job_id: str) -> JobState:
        task = self._tasks.get(job_id)
        if task is None:
            return JobState(id=job_id, status="not_found")
        if not task.done():
            return JobState(id=job_id, status="running")
        if task.exception() is not None:
            return JobState(id=job_id, status="failed", error=str(task.exception()))
        return JobState(id=job_id, status="done", result_id=task.result())

    async def wait(self, job_id: str, timeout_s: float) -> JobState:
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.wait({task}, timeout=timeout_s)
        return await self.state(job_id)

    async def worker_count(self) -> int | None:
        return 1

    async def close(self) -> None:
        for task in self._tasks.values():
            task.cancel()
