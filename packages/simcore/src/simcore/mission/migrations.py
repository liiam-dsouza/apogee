"""Schema migrations, applied on load. Never break an old config.

To change the schema: bump CURRENT_SCHEMA_VERSION, add ``v{n}_to_v{n+1}`` and
register it in MIGRATIONS. Each migration takes and returns a plain dict.
"""

from collections.abc import Callable
from typing import Any, Final

CURRENT_SCHEMA_VERSION: Final = 1

Migration = Callable[[dict[str, Any]], dict[str, Any]]

#: from-version -> function producing the next version
MIGRATIONS: dict[int, Migration] = {}


class MigrationError(ValueError):
    """The config's schema_version cannot be brought up to date."""


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Bring a raw config dict up to CURRENT_SCHEMA_VERSION. Idempotent."""
    version = data.get("schema_version", CURRENT_SCHEMA_VERSION)
    if not isinstance(version, int):
        raise MigrationError("schema_version must be an integer")
    if version > CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            f"schema_version {version} is newer than this software supports "
            f"({CURRENT_SCHEMA_VERSION}); upgrade Apogee to open it"
        )
    while version < CURRENT_SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise MigrationError(f"no migration from schema_version {version}")
        data = step(data)
        version += 1
        data["schema_version"] = version
    return data
