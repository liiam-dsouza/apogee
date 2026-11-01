"""Pydantic models for the mission config.

Every field carries a ``description`` and, where it has a physical quantity,
``json_schema_extra={"units": ...}``. Those two facts feed the OpenAPI schema,
the generated frontend types, the UI tooltips and the config reference page,
so they cannot disagree. A field without a description fails the test suite.

Units: SI throughout, except angles, which are degrees (see
docs/adr/0001-angles-in-degrees.md).

Sections typed as ``OpenSection`` are not modelled yet; they accept any
mapping so configs round-trip while each section is built out.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ulid import ULID

from simcore.mission.migrations import CURRENT_SCHEMA_VERSION


def quantity(units: str, description: str, **kwargs: Any) -> Any:
    """A Field for a physical quantity, with its units recorded in the schema."""
    return Field(description=description, json_schema_extra={"units": units}, **kwargs)


class _Strict(BaseModel):
    # Unknown keys are errors: a typo in a mission file must not be silently ignored.
    model_config = ConfigDict(extra="forbid")


LonLat = Annotated[
    tuple[float, float],
    Field(description="A point as [longitude, latitude], WGS84, in degrees."),
]


class MissionMeta(_Strict):
    name: str = Field(min_length=1, description="Human-readable mission name.")
    id: str = Field(
        default_factory=lambda: str(ULID()),
        description="ULID identifying this mission; stable across edits.",
    )
    created_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the mission was first created, UTC.",
    )
    authors: list[str] = Field(default_factory=list, description="Who wrote this config.")
    notes: str = Field(default="", description="Free-form notes.")


class Site(_Strict):
    latitude_deg: float = quantity("deg", "Launch pad latitude, WGS84.", ge=-90, le=90)
    longitude_deg: float = quantity("deg", "Launch pad longitude, WGS84.", ge=-180, le=180)
    elevation_m: float = quantity("m", "Pad elevation above mean sea level.", ge=-500, le=9000)
    rail_length_m: float = quantity("m", "Usable length of the launch rail.", gt=0, le=30)
    inclination_deg: float = quantity(
        "deg", "Rail angle above the horizontal (90 is vertical).", ge=0, le=90
    )
    heading_deg: float = quantity("deg", "Rail azimuth, clockwise from true north.", ge=0, lt=360)
    boundary: list[LonLat] | None = Field(
        default=None,
        description=(
            "Range boundary polygon. Drives the probability of landing out of bounds. "
            "Open ring: the first point is not repeated."
        ),
    )
    hazards: list[list[LonLat]] = Field(
        default_factory=list, description="Hazard polygons the rocket must not land in."
    )
    access_roads: list[list[LonLat]] = Field(
        default_factory=list, description="Recovery access roads as polylines."
    )

    @field_validator("boundary")
    @classmethod
    def _polygon_has_area(cls, v: list[tuple[float, float]] | None) -> Any:
        if v is not None and len(v) < 3:
            raise ValueError("a boundary polygon needs at least 3 points")
        return v

    @field_validator("hazards")
    @classmethod
    def _hazards_have_area(cls, v: list[list[tuple[float, float]]]) -> Any:
        for i, poly in enumerate(v):
            if len(poly) < 3:
                raise ValueError(f"hazard {i} needs at least 3 points")
        return v


class Asset(_Strict):
    kind: Literal["thrust_curve", "drag_table", "ork", "other"] = Field(
        description="What the file is used for."
    )
    filename: str = Field(description="Original filename, for display.")
    size: int = quantity("bytes", "File size.", ge=0)


OpenSection = Annotated[
    dict[str, Any],
    Field(
        default_factory=dict,
        description="Not modelled yet: accepted as-is so configs round-trip.",
    ),
]


class Mission(_Strict):
    """A complete mission config. Serialised as YAML (or JSON)."""

    schema_version: Literal[1] = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Config schema version. Older configs are migrated on load.",
    )
    extends: str | None = Field(
        default=None,
        description="Path of a base config this one overrides (not yet supported).",
    )
    meta: MissionMeta = Field(description="Name, id, authorship.")
    rocket: OpenSection
    motor: OpenSection
    recovery: OpenSection
    ballast: OpenSection
    site: Site | None = Field(default=None, description="Launch site and range geometry.")
    environment: OpenSection
    monte_carlo: OpenSection
    constraints: OpenSection
    solver: OpenSection
    assets: dict[str, Asset] = Field(
        default_factory=dict,
        description=(
            "Content-addressed files, keyed by sha256: thrust curves, drag tables, .ork originals."
        ),
    )
