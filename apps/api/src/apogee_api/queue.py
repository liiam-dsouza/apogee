"""Redis connection for the job queue and worker heartbeats.

The API must keep serving when Redis is down (editing missions needs no
queue), so connection failures degrade to "queue unavailable".
"""

import dataclasses
import logging

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

#: Workers refresh `{WORKER_HEARTBEAT_PREFIX}{worker id}` with a short TTL.
WORKER_HEARTBEAT_PREFIX = "apogee:worker:"

_pool: ArqRedis | None = None


async def connect(redis_url: str) -> None:
    global _pool
    # Fail fast: the API starts without a queue rather than waiting on one.
    redis_settings = dataclasses.replace(
        RedisSettings.from_dsn(redis_url), conn_timeout=1, conn_retries=0
    )
    try:
        _pool = await create_pool(redis_settings)
    except (TimeoutError, OSError, RedisError) as e:
        log.warning("job queue unavailable: %s", e)
        _pool = None


async def close() -> None:
    if _pool is not None:
        await _pool.aclose()


async def worker_count() -> int | None:
    """Live workers, or None if the queue is unreachable."""
    if _pool is None:
        return None
    try:
        return len([k async for k in _pool.scan_iter(match=f"{WORKER_HEARTBEAT_PREFIX}*")])
    except (TimeoutError, OSError, RedisError):
        return None
