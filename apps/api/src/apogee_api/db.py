"""SQLite metadata store. Result payloads will live beside it as Parquet."""

import fcntl
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Field, Session, SQLModel, create_engine


class MissionRecord(SQLModel, table=True):
    __tablename__ = "missions"

    id: str = Field(primary_key=True, description="The mission's meta.id (ULID).")
    name: str = Field(index=True)
    yaml: str = Field(description="The mission config exactly as exported.")
    config_hash: str = Field(index=True)
    created_utc: datetime
    updated_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


_engine: Engine | None = None


def _sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
    # Several uvicorn processes share the file: WAL lets readers proceed during
    # a write, and the busy timeout waits out a lock instead of erroring.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_engine(data_dir: Path) -> Engine:
    """Open the database in data_dir, creating tables if needed.

    Safe to call from several processes at once (uvicorn --workers): table
    creation is serialised with a file lock.
    """
    global _engine
    _engine = create_engine(
        f"sqlite:///{data_dir / 'apogee.db'}", connect_args={"check_same_thread": False}
    )
    event.listen(_engine, "connect", _sqlite_pragmas)
    with open(data_dir / ".init.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        SQLModel.metadata.create_all(_engine)
    return _engine


def get_session() -> Iterator[Session]:
    assert _engine is not None, "init_engine() not called"
    with Session(_engine) as session:
        yield session
