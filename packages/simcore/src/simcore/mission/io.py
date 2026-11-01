"""Reading and writing mission files."""

import io
from typing import Any

from ruamel.yaml import YAML

from simcore.mission.migrations import migrate
from simcore.mission.models import Mission


def _yaml() -> YAML:
    y = YAML(typ="safe", pure=True)
    y.default_flow_style = False
    y.sort_base_mapping_type_on_output = False  # type: ignore[assignment]
    return y


def parse_yaml(text: str) -> dict[str, Any]:
    """Parse YAML (or JSON, a subset) into a raw dict. Does not validate."""
    data = _yaml().load(text)
    if not isinstance(data, dict):
        raise ValueError("a mission file must be a mapping at the top level")
    return data


def load_mission(data: dict[str, Any]) -> Mission:
    """Migrate a raw config dict to the current schema and validate it."""
    return Mission.model_validate(migrate(dict(data)))


def dump_yaml(mission: Mission) -> str:
    """Serialise a mission as YAML, in schema field order."""
    buf = io.StringIO()
    _yaml().dump(mission.model_dump(mode="json", exclude_none=True), buf)
    return buf.getvalue()
