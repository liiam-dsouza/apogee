"""FastAPI app. Thin: validate, enqueue, serialise. All physics lives in simcore."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from apogee_api import problems
from apogee_api.db import init_engine
from apogee_api.queue import ArqQueue, InlineQueue, JobQueue
from apogee_api.routers import (
    assets,
    imports,
    missions,
    montecarlo,
    results,
    sim,
    system,
    weather,
)
from apogee_api.settings import get_settings


def _operation_id(route: APIRoute) -> str:
    # Routes set operation_id explicitly; this keeps generated names stable otherwise.
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_engine(settings.data_dir)
    queue: JobQueue = (
        InlineQueue() if settings.queue == "inline" else await ArqQueue.connect(settings.redis_url)
    )
    app.state.queue = queue
    yield
    await queue.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Apogee API",
        version="0.1.0",
        lifespan=lifespan,
        # /docs on the web origin is the app's own Docs section.
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=_operation_id,
    )
    problems.install(app)
    app.include_router(system.router)
    app.include_router(missions.router)
    app.include_router(assets.router)
    app.include_router(sim.router)
    app.include_router(results.router)
    app.include_router(imports.router)
    app.include_router(weather.router)
    app.include_router(montecarlo.router)
    return app


app = create_app()
