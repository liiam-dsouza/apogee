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

import itertools
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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

AssetRef = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description="sha256 of a file in the mission's assets.",
    ),
]

Inertia = Annotated[
    tuple[float, float, float],
    Field(
        description=(
            "Principal moments of inertia (I11, I22, I33) in kg·m², about the centre of mass, "
            "with e3 along the rocket's axis."
        ),
        json_schema_extra={"units": "kg·m²"},
    ),
]


# --- Rocket (positions: metres aft of the nose tip, ADR 0002) ----------------


class NoseCone(_Strict):
    kind: Literal[
        "von_karman", "conical", "tangent_ogive", "lvhaack", "elliptical", "parabolic"
    ] = Field(description="Nose cone profile.")
    length_m: float = quantity("m", "Nose cone length, tip to shoulder.", gt=0)


class TrapezoidalFins(_Strict):
    count: int = Field(ge=2, le=8, description="Number of fins in the set.")
    root_chord_m: float = quantity("m", "Chord length at the body tube.", gt=0)
    tip_chord_m: float = quantity("m", "Chord length at the fin tip.", ge=0)
    span_m: float = quantity("m", "Distance from body tube to fin tip.", gt=0)
    position_m: float = quantity(
        "m", "Position of the root chord's leading edge, aft of the nose tip.", ge=0
    )
    sweep_length_m: float | None = quantity(
        "m",
        "Axial distance from root leading edge to tip leading edge. "
        "Unset means the tip chord is centred on the root chord.",
        default=None,
    )
    cant_angle_deg: float = quantity("deg", "Fin cant angle.", default=0.0, ge=-10, le=10)


class Tail(_Strict):
    top_radius_m: float = quantity("m", "Radius at the forward end of the tail.", gt=0)
    bottom_radius_m: float = quantity("m", "Radius at the aft end of the tail.", ge=0)
    length_m: float = quantity("m", "Tail (boat-tail) length.", gt=0)
    position_m: float = quantity(
        "m", "Position of the tail's forward end, aft of the nose tip.", ge=0
    )


class RailButtons(_Strict):
    upper_position_m: float = quantity("m", "Forward rail button, aft of the nose tip.", ge=0)
    lower_position_m: float = quantity("m", "Aft rail button, aft of the nose tip.", ge=0)
    angular_position_deg: float = quantity(
        "deg", "Angle of the buttons around the body, relative to the fins.", default=45.0
    )


class DragCurve(_Strict):
    """Drag coefficient against Mach: a table asset, or a constant."""

    table: AssetRef | None = Field(
        default=None,
        description="CSV asset of (Mach, CD) rows. Takes precedence over constant_cd.",
    )
    constant_cd: float | None = Field(
        default=None, gt=0, description="A constant drag coefficient, if there is no table."
    )

    @model_validator(mode="after")
    def _one_source(self) -> "DragCurve":
        if (self.table is None) == (self.constant_cd is None):
            raise ValueError("give exactly one of table or constant_cd")
        return self


class Drag(_Strict):
    power_off: DragCurve = Field(description="Drag coefficient after burnout.")
    power_on: DragCurve = Field(description="Drag coefficient while the motor burns.")
    multiplier: float = Field(
        default=1.0,
        gt=0,
        le=5,
        description=(
            "Scales both curves. 1 uses them as given; post-flight calibration fits this."
        ),
    )


class Rocket(_Strict):
    radius_m: float = quantity("m", "Body tube outer radius.", gt=0, le=1)
    dry_mass_kg: float = quantity("kg", "Mass without the motor.", gt=0)
    dry_inertia: Inertia
    dry_cg_m: float = quantity("m", "Centre of mass without the motor, aft of the nose tip.")
    nose: NoseCone = Field(description="Nose cone.")
    fins: list[TrapezoidalFins] = Field(min_length=1, description="Fin sets.")
    tail: Tail | None = Field(default=None, description="Boat-tail, if any.")
    rail_buttons: RailButtons | None = Field(
        default=None, description="Rail buttons. Without them the rail is a single point."
    )
    motor_position_m: float = quantity(
        "m", "Position of the motor's nozzle exit, aft of the nose tip.", gt=0
    )
    drag: Drag = Field(description="Aerodynamic drag.")

    def length_m(self) -> float:
        """Overall length: the furthest-aft point of any component."""
        ends = [self.nose.length_m, self.motor_position_m]
        ends += [f.position_m + f.root_chord_m for f in self.fins]
        if self.tail:
            ends.append(self.tail.position_m + self.tail.length_m)
        return max(ends)


# --- Motor (positions inside the motor: from the nozzle exit) ----------------


class Grains(_Strict):
    count: int = Field(ge=1, le=20, description="Number of propellant grains.")
    density_kg_m3: float = quantity("kg/m³", "Propellant density.", gt=0)
    outer_radius_m: float = quantity("m", "Grain outer radius.", gt=0)
    initial_inner_radius_m: float = quantity("m", "Grain core radius before burning.", ge=0)
    initial_height_m: float = quantity("m", "Height of one grain before burning.", gt=0)
    separation_m: float = quantity("m", "Gap between adjacent grains.", ge=0)
    cg_position_m: float = quantity(
        "m", "Centre of mass of the grain stack, forward of the nozzle exit."
    )

    @model_validator(mode="after")
    def _has_propellant(self) -> "Grains":
        if self.initial_inner_radius_m >= self.outer_radius_m:
            raise ValueError("initial_inner_radius_m must be smaller than outer_radius_m")
        return self


class Motor(_Strict):
    thrust_curve: AssetRef = Field(description="Thrust curve asset (.eng or .rse).")
    burn_time_s: float | None = quantity(
        "s", "Burn time. Unset takes it from the thrust curve.", default=None, gt=0
    )
    dry_mass_kg: float = quantity("kg", "Motor mass without propellant.", gt=0)
    dry_inertia: Inertia
    dry_cg_position_m: float = quantity("m", "Centre of dry mass, forward of the nozzle exit.")
    nozzle_radius_m: float = quantity("m", "Nozzle exit radius.", gt=0)
    throat_radius_m: float = quantity("m", "Nozzle throat radius.", gt=0)
    grains: Grains = Field(description="Propellant grain geometry.")

    @model_validator(mode="after")
    def _throat_inside_nozzle(self) -> "Motor":
        if self.throat_radius_m > self.nozzle_radius_m:
            raise ValueError("throat_radius_m cannot exceed nozzle_radius_m")
        return self


# --- Recovery -----------------------------------------------------------------


class AtApogee(_Strict):
    kind: Literal["apogee"] = Field(description="Deploy at apogee.")


class AtAltitude(_Strict):
    kind: Literal["altitude_agl"] = Field(description="Deploy at an altitude while descending.")
    altitude_m: float = quantity("m", "Deployment altitude above ground level.", gt=0)


class RecoveryDevice(_Strict):
    name: str = Field(min_length=1, description="Device name, e.g. 'Drogue' or 'Main'.")
    cd_s_m2: float = quantity(
        "m²", "Drag coefficient times reference area (CdS) of the open canopy.", gt=0
    )
    trigger: AtApogee | AtAltitude = Field(
        discriminator="kind", description="When the device deploys."
    )
    lag_s: float = quantity("s", "Time from trigger to fully open canopy.", default=0.0, ge=0)
    sampling_rate_hz: float = quantity(
        "Hz", "Rate the flight computer checks the trigger.", default=100.0, gt=0
    )


class Recovery(_Strict):
    devices: list[RecoveryDevice] = Field(
        default_factory=list,
        description="Recovery devices. None means a ballistic descent.",
    )


# --- Environment ----------------------------------------------------------------


class StandardAtmosphere(_Strict):
    kind: Literal["standard"] = Field(
        description="International Standard Atmosphere, no wind. For sanity runs."
    )


class ProfileLevel(_Strict):
    altitude_m: float = quantity("m", "Geometric altitude above mean sea level.")
    pressure_pa: float = quantity("Pa", "Static pressure.", gt=0)
    temperature_k: float = quantity("K", "Air temperature.", gt=0)
    wind_u_ms: float = quantity("m/s", "Wind component towards east.")
    wind_v_ms: float = quantity("m/s", "Wind component towards north.")


class ResolvedProfile(_Strict):
    kind: Literal["profile"] = Field(
        description="A resolved atmosphere table, stored so runs are reproducible offline."
    )
    source: str = Field(description="Where the profile came from, e.g. 'manual' or a model.")
    valid_utc: datetime | None = Field(default=None, description="Time the profile describes, UTC.")
    levels: list[ProfileLevel] = Field(
        min_length=2, description="Levels, ordered by increasing altitude."
    )

    @field_validator("levels")
    @classmethod
    def _ascending(cls, v: list[ProfileLevel]) -> list[ProfileLevel]:
        if any(b.altitude_m <= a.altitude_m for a, b in itertools.pairwise(v)):
            raise ValueError("levels must be in strictly increasing altitude")
        return v


class Environment(_Strict):
    atmosphere: StandardAtmosphere | ResolvedProfile = Field(
        default_factory=lambda: StandardAtmosphere(kind="standard"),
        discriminator="kind",
        description="Atmosphere and wind the flight is simulated in.",
    )


class Mission(_Strict):
    """A complete mission config. Serialised as YAML (or JSON)."""

    schema_version: Literal[2] = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Config schema version. Older configs are migrated on load.",
    )
    extends: str | None = Field(
        default=None,
        description="Path of a base config this one overrides (not yet supported).",
    )
    meta: MissionMeta = Field(description="Name, id, authorship.")
    rocket: Rocket | None = Field(default=None, description="Airframe, without the motor.")
    motor: Motor | None = Field(default=None, description="Solid rocket motor.")
    recovery: Recovery = Field(
        default_factory=Recovery, description="Parachutes and other recovery devices."
    )
    ballast: OpenSection
    site: Site | None = Field(default=None, description="Launch site and range geometry.")
    environment: Environment = Field(
        default_factory=Environment, description="Atmosphere and wind."
    )
    monte_carlo: OpenSection
    constraints: OpenSection
    solver: OpenSection
    assets: dict[str, Asset] = Field(
        default_factory=dict,
        description=(
            "Content-addressed files, keyed by sha256: thrust curves, drag tables, .ork originals."
        ),
    )

    def referenced_assets(self) -> set[str]:
        """sha256 of every asset the config points at."""
        refs: set[str] = set()
        if self.motor:
            refs.add(self.motor.thrust_curve)
        if self.rocket:
            for curve in (self.rocket.drag.power_off, self.rocket.drag.power_on):
                if curve.table:
                    refs.add(curve.table)
        return refs
