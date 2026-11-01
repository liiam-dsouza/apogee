"""Dependency injection: settings, database session, job queue, stores."""

from typing import Annotated

from fastapi import Depends, Request

from apogee_api.queue import JobQueue
from apogee_api.settings import Settings, get_settings
from simcore.assets import DirectoryAssetStore

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_queue(request: Request) -> JobQueue:
    queue: JobQueue = request.app.state.queue
    return queue


QueueDep = Annotated[JobQueue, Depends(get_queue)]


def get_asset_store(settings: SettingsDep) -> DirectoryAssetStore:
    return DirectoryAssetStore(settings.assets_dir)


AssetStoreDep = Annotated[DirectoryAssetStore, Depends(get_asset_store)]
