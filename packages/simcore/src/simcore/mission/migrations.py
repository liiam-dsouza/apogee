"""Schema migrations, applied on load. Never break an old config.

To change the schema: bump CURRENT_SCHEMA_VERSION, add ``v{n}_to_v{n+1}`` and
register it in MIGRATIONS. Each migration takes and returns a plain dict.
"""

from collections.abc import Callable
from typing import Any, Final

CURRENT_SCHEMA_VERSION: Final = 4

Migration = Callable[[dict[str, Any]], dict[str, Any]]


def v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Typed rocket, motor, recovery and environment sections.

    v1 stored these as free-form mappings, always empty in practice. Empty
    ones become "not set" (rocket, motor) or the new defaults (recovery,
    environment). Anything else is left for validation to report with a path.
    """
    for key in ("rocket", "motor", "recovery", "environment"):
        if data.get(key) == {}:
            del data[key]
    return data


def v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Motors become a tagged union; every v2 motor was a solid motor."""
    motor = data.get("motor")
    if isinstance(motor, dict) and "kind" not in motor:
        data["motor"] = {"kind": "solid", **motor}
    return data


def v3_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    """Fin sets become a tagged union; every v3 fin set was trapezoidal."""
    rocket = data.get("rocket")
    if isinstance(rocket, dict) and isinstance(fins := rocket.get("fins"), list):
        rocket["fins"] = [
            {"kind": "trapezoidal", **f} if isinstance(f, dict) and "kind" not in f else f
            for f in fins
        ]
    return data


#: from-version -> function producing the next version
MIGRATIONS: dict[int, Migration] = {1: v1_to_v2, 2: v2_to_v3, 3: v3_to_v4}


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
