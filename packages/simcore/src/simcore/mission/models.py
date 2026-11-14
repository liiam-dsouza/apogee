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


#: A point on a fin outline: [x aft of the root leading edge, y outward from the body tube], m.
FinPoint = tuple[float, float]


FinCrossSection = Literal["square", "rounded", "airfoil"]

#: OpenRocket's surface finishes, smoothest first (roughness heights in simcore.aero.drag).
SurfaceFinish = Literal[
    "mirror",
    "polished",
    "sheet_metal",
    "optimum",
    "smooth",
    "normal",
    "unfinished",
    "rough_unfinished",
    "rough",
]


class FinMaterial(_Strict):
    """What the fins are made of, as far as flutter cares: the shear modulus."""

    name: str = Field(min_length=1, description="Material name, for display.")
    shear_modulus_pa: float = quantity(
        "Pa",
        "Shear modulus G of the fin as built. Composite layups vary a lot: use a measured "
        "or supplier value where there is one.",
        gt=0,
    )


class TrapezoidalFins(_Strict):
    kind: Literal["trapezoidal"] = Field(description="Fin set defined by chords, span and sweep.")
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
        "Unset means the trailing edge is square: the tip ends level with the root "
        "(sweep = root chord - tip chord), as RocketPy flies it.",
        default=None,
    )
    cant_angle_deg: float = quantity("deg", "Fin cant angle.", default=0.0, ge=-10, le=10)
    thickness_m: float | None = quantity(
        "m", "Fin thickness. With a material, every flight checks fin flutter.", default=None, gt=0
    )
    cross_section: FinCrossSection = Field(
        default="square",
        description="Shape of the fin edges, for the drag estimate: square, rounded or airfoil.",
    )
    material: FinMaterial | None = Field(
        default=None, description="Fin material, for the flutter check. Unset: not checked."
    )

    def outline(self) -> list[FinPoint]:
        """One fin's outline, from the root leading edge: x aft, y outward."""
        sweep = (
            self.sweep_length_m
            if self.sweep_length_m is not None
            else self.root_chord_m - self.tip_chord_m
        )
        return [
            (0.0, 0.0),
            (sweep, self.span_m),
            (sweep + self.tip_chord_m, self.span_m),
            (self.root_chord_m, 0.0),
        ]


class FreeFormFins(_Strict):
    kind: Literal["free_form"] = Field(description="Fin set with an arbitrary outline.")
    count: int = Field(ge=2, le=8, description="Number of fins in the set.")
    points: list[FinPoint] = Field(
        min_length=3,
        description=(
            "One fin's outline as [x, y] in metres: x aft of the root leading edge, "
            "y outward from the body tube. Starts at [0, 0] (root leading edge) and ends "
            "on the body tube at the root trailing edge, [root chord, 0]."
        ),
        json_schema_extra={"units": "m"},
    )
    position_m: float = quantity(
        "m", "Position of the root chord's leading edge, aft of the nose tip.", ge=0
    )
    cant_angle_deg: float = quantity("deg", "Fin cant angle.", default=0.0, ge=-10, le=10)
    thickness_m: float | None = quantity(
        "m", "Fin thickness. With a material, every flight checks fin flutter.", default=None, gt=0
    )
    cross_section: FinCrossSection = Field(
        default="square",
        description="Shape of the fin edges, for the drag estimate: square, rounded or airfoil.",
    )
    material: FinMaterial | None = Field(
        default=None, description="Fin material, for the flutter check. Unset: not checked."
    )

    @field_validator("points")
    @classmethod
    def _outline_sits_on_the_body(cls, v: list[FinPoint]) -> list[FinPoint]:
        if v[0] != (0.0, 0.0):
            raise ValueError("the outline must start at the root leading edge, [0, 0]")
        if v[-1][1] != 0 or v[-1][0] <= 0:
            raise ValueError("the outline must end on the body tube, at [root chord, 0]")
        if any(y < 0 for _, y in v):
            raise ValueError("no point may be inside the body tube (y < 0)")
        if max(y for _, y in v) <= 0:
            raise ValueError("the fin needs some span: at least one point with y > 0")
        return v

    @property
    def root_chord_m(self) -> float:
        return self.points[-1][0]

    @property
    def span_m(self) -> float:
        return max(y for _, y in self.points)

    def outline(self) -> list[FinPoint]:
        """One fin's outline, from the root leading edge: x aft, y outward."""
        return list(self.points)


FinSet = Annotated[TrapezoidalFins | FreeFormFins, Field(discriminator="kind")]


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
    """Drag coefficient: estimated from the rocket's shape, a table asset, or a constant."""

    estimate: bool = Field(
        default=False,
        description=(
            "Estimate drag from the rocket's shape (component build-up, as OpenRocket does). "
            "Depends on Mach, Reynolds number and angle of attack."
        ),
    )

    table: AssetRef | None = Field(
        default=None,
        description="CSV asset of (Mach, CD) rows.",
    )
    constant_cd: float | None = Field(
        default=None, gt=0, description="A constant drag coefficient, if there is no table."
    )

    @model_validator(mode="after")
    def _one_source(self) -> "DragCurve":
        given = [self.estimate, self.table is not None, self.constant_cd is not None]
        if sum(given) != 1:
            raise ValueError("give exactly one of estimate, table or constant_cd")
        return self


# Plain defaults rather than factories, so the schema (and the generated types)
# carry them. Pydantic copies a model default for each instance.
class Drag(_Strict):
    power_off: DragCurve = Field(
        default=DragCurve(estimate=True), description="Drag coefficient after burnout."
    )
    power_on: DragCurve = Field(
        default=DragCurve(estimate=True), description="Drag coefficient while the motor burns."
    )
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
    fins: list[FinSet] = Field(
        min_length=1, description="Fin sets: trapezoidal, or free-form with any outline."
    )
    tail: Tail | None = Field(default=None, description="Boat-tail, if any.")
    rail_buttons: RailButtons | None = Field(
        default=None, description="Rail buttons. Without them the rail is a single point."
    )
    motor_position_m: float = quantity(
        "m", "Position of the motor's nozzle exit, aft of the nose tip.", gt=0
    )
    surface_finish: SurfaceFinish = Field(
        default="normal",
        description="Outside surface finish, for the drag estimate's skin friction. "
        "normal is regular paint.",
    )
    drag: Drag = Field(
        default=Drag(), description="Aerodynamic drag. Unset: estimated from the shape."
    )

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


class SolidMotor(_Strict):
    """A solid motor with known grain geometry (team-built, or a published spec)."""

    kind: Literal["solid"] = Field(description="Solid motor with grain geometry.")
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
    def _throat_inside_nozzle(self) -> "SolidMotor":
        if self.throat_radius_m > self.nozzle_radius_m:
            raise ValueError("throat_radius_m cannot exceed nozzle_radius_m")
        return self


class GenericMotor(_Strict):
    """A motor known only by its thrust curve and masses, e.g. a commercial reload.

    Propellant is a cylinder ("chamber") that loses mass with the impulse
    delivered. Good for trajectory; inertia during the burn is approximate.
    """

    kind: Literal["generic"] = Field(description="Motor from thrust curve and masses only.")
    thrust_curve: AssetRef = Field(description="Thrust curve asset (.eng).")
    burn_time_s: float | None = quantity(
        "s", "Burn time. Unset takes it from the thrust curve.", default=None, gt=0
    )
    propellant_mass_kg: float = quantity("kg", "Propellant mass at ignition.", gt=0)
    dry_mass_kg: float = quantity("kg", "Motor mass without propellant.", gt=0)
    dry_inertia: Inertia
    dry_cg_position_m: float = quantity("m", "Centre of dry mass, forward of the nozzle exit.")
    chamber_radius_m: float = quantity("m", "Radius of the propellant cylinder.", gt=0)
    chamber_height_m: float = quantity("m", "Length of the propellant cylinder.", gt=0)
    chamber_position_m: float = quantity(
        "m", "Centre of the propellant cylinder, forward of the nozzle exit."
    )
    nozzle_radius_m: float = quantity("m", "Nozzle exit radius.", gt=0)


Motor = Annotated[SolidMotor | GenericMotor, Field(discriminator="kind")]


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


#: A common starting point for the pressure that pushes a section off, over what
#: breaks the pins: 15 psi. Ground testing sets the real charge.
DEFAULT_SEPARATION_PRESSURE_PA = 103_421.0


class EjectionBay(_Strict):
    """A compartment a black-powder charge pressurises to separate the rocket."""

    name: str = Field(min_length=1, description="Bay name, e.g. 'Drogue bay'.")
    device: str | None = Field(
        default=None, description="The recovery device it releases, by name. For display."
    )
    inner_diameter_m: float = quantity(
        "m", "Inside diameter of the bay: the bulkhead the gas pushes on.", gt=0, le=1
    )
    free_length_m: float = quantity(
        "m",
        "Length of the empty space the gas fills: the bay's length less what is packed in it.",
        gt=0,
        le=5,
    )
    forward_mass_kg: float | None = quantity(
        "kg",
        "Mass the joint holds on to during coast: everything on the far side from the motor, "
        "e.g. the nose and payload for a forward bay. Unset: drag separation isn't checked.",
        default=None,
        gt=0,
    )
    shear_pins: int = Field(default=0, ge=0, le=24, description="Shear pins across the joint.")
    pin_strength_n: float = quantity(
        "N", "Shear strength of one pin. Use a tested or de-rated value.", default=0.0, ge=0
    )
    separation_pressure_pa: float = quantity(
        "Pa",
        "Pressure the charge must reach over what breaks the pins, to push the section off "
        "against friction and the packed recovery gear. 15 psi is a common start.",
        default=DEFAULT_SEPARATION_PRESSURE_PA,
        gt=0,
    )
    backup_factor: float = quantity(
        "1", "Backup charge as a multiple of the primary.", default=1.25, ge=1, le=3
    )

    @model_validator(mode="after")
    def _pins_have_a_strength(self) -> "EjectionBay":
        if self.shear_pins > 0 and self.pin_strength_n <= 0:
            raise ValueError("shear pins need a pin_strength_n")
        return self


class Ejection(_Strict):
    bays: list[EjectionBay] = Field(
        default_factory=list, description="Separation joints and their charges."
    )


# --- Structure (airframe vibration) ----------------------------------------------


class AirframeShell(_Strict):
    """A length of tube that carries bending: body tube, coupler, motor tube, piece of nose.

    Shells that overlap (a coupler inside two body tubes) add their stiffness.
    The outer radius goes linearly from the forward end to the aft end.
    """

    name: str = Field(min_length=1, description="Part name, for display.")
    position_m: float = quantity("m", "Forward end, aft of the nose tip.", ge=0)
    length_m: float = quantity("m", "Length along the axis.", gt=0)
    forward_radius_m: float = quantity("m", "Outer radius at the forward end.", ge=0, le=1)
    aft_radius_m: float = quantity("m", "Outer radius at the aft end.", ge=0, le=1)
    wall_thickness_m: float = quantity("m", "Wall thickness.", gt=0, le=0.1)
    material: str = Field(default="", description="Material name, for display.")
    youngs_modulus_pa: float = quantity(
        "Pa", "Young's modulus along the axis. A layup's own or a tap-tested value is best.", gt=0
    )
    shear_modulus_pa: float = quantity(
        "Pa",
        "In-plane shear modulus of the wall. Composite tubes are soft in shear, which lowers "
        "the higher bending modes.",
        gt=0,
    )


class StructuralMass(_Strict):
    """Mass the airframe carries, spread evenly over its length (zero length: a point)."""

    name: str = Field(min_length=1, description="Part name, for display.")
    mass_kg: float = quantity("kg", "Mass.", ge=0)
    position_m: float = quantity("m", "Forward end, aft of the nose tip.")
    length_m: float = quantity("m", "Length it is spread over.", default=0.0, ge=0)


#: How far a joint bends compared with the tube either side, in calibers of that
#: tube: a slip-fit or riveted coupler is softer than solid tube. Fitted to the
#: first bending mode of two flown rockets (docs/methods/vibration.md).
DEFAULT_JOINT_FLEXIBILITY_CAL = 1.25


class AirframeJoint(_Strict):
    """Where two airframe sections meet: a coupler, a nose shoulder, a switch band."""

    name: str = Field(min_length=1, description="Joint name, for display.")
    position_m: float = quantity("m", "Where the sections meet, aft of the nose tip.", ge=0)
    flexibility_cal: float = quantity(
        "cal",
        "Extra bending at the joint, as the length of the tube beside it that would bend as "
        "much, in calibers. 0 is as stiff as the tube.",
        default=DEFAULT_JOINT_FLEXIBILITY_CAL,
        ge=0,
        le=20,
    )


class VibrationStation(_Strict):
    """A place on the airframe whose vibration is predicted: a payload, a flight computer."""

    name: str = Field(min_length=1, description="Station name, e.g. 'Payload'.")
    position_m: float = quantity("m", "Position, aft of the nose tip.", ge=0)


class Excitation(_Strict):
    """What shakes the airframe, as fractions of the load that drives each source.

    Defaults are fitted to one flight log (Luke, a 5" rocket on a CTI K940;
    docs/methods/vibration.md). Motor roughness depends on the propellant, so
    fit it to a log of the same motor where there is one.
    """

    motor_roughness: float = quantity(
        "1",
        "Axial thrust fluctuation, RMS over the band, as a fraction of the thrust.",
        default=0.0064,
        ge=0,
        le=0.5,
    )
    motor_side_load: float = quantity(
        "1",
        "Side force at the nozzle, RMS over the band, as a fraction of the thrust.",
        default=0.0016,
        ge=0,
        le=0.5,
    )
    aero_load: float = quantity(
        "1",
        "Random side load along the airframe, RMS per metre, over dynamic pressure times "
        "the projected width.",
        default=0.0031,
        ge=0,
        le=1,
    )
    transonic_factor: float = quantity(
        "1",
        "How much stronger the aerodynamic load is at Mach 1 than either side of it "
        "(shocks moving on the airframe). 0 is no transonic rise.",
        default=2.0,
        ge=0,
        le=20,
    )
    band_hz: float = quantity(
        "Hz", "Motor roughness is spread evenly from 0 to this frequency.", default=2000, gt=0
    )


class Structure(_Strict):
    """The airframe as a free beam, for its vibration modes and the vibration in flight.

    Imported from OpenRocket. Masses here are everything but the motor, which is
    added from the mission's motor as it burns.
    """

    shells: list[AirframeShell] = Field(
        default_factory=list, description="Tubes that carry bending."
    )
    masses: list[StructuralMass] = Field(
        default_factory=list, description="Every part's mass, the tubes' own included."
    )
    joints: list[AirframeJoint] = Field(
        default_factory=list, description="Where airframe sections meet."
    )
    stations: list[VibrationStation] = Field(
        default_factory=list, description="Where vibration is predicted."
    )
    damping_ratio: float = quantity(
        "1",
        "Damping of every mode, as a fraction of critical. 0.02 to 0.05 for a bonded composite "
        "airframe with joints.",
        default=0.04,
        gt=0,
        le=0.3,
    )
    excitation: Excitation = Field(
        default_factory=Excitation, description="What shakes the airframe."
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
    fetched_utc: datetime | None = Field(
        default=None,
        description="When a forecast was downloaded, UTC. Its age is how stale the forecast is.",
    )
    levels: list[ProfileLevel] = Field(
        min_length=2, description="Levels, ordered by increasing altitude."
    )

    @field_validator("levels")
    @classmethod
    def _ascending(cls, v: list[ProfileLevel]) -> list[ProfileLevel]:
        if any(b.altitude_m <= a.altitude_m for a, b in itertools.pairwise(v)):
            raise ValueError("levels must be in strictly increasing altitude")
        return v


class ManualWindLevel(_Strict):
    height_m: float = quantity("m", "Height above the pad.", ge=0, le=30_000)
    speed_ms: float = quantity("m/s", "Wind speed.", ge=0, le=150)
    direction_deg: float = quantity(
        "deg", "Direction the wind blows from, degrees clockwise from true north.", ge=0, lt=360
    )


class ManualProfile(_Strict):
    kind: Literal["manual"] = Field(
        description="Wind entered by hand, e.g. from a range safety officer's briefing."
    )
    note: str = Field(default="", description="Where the numbers came from, and when.")
    levels: list[ManualWindLevel] = Field(
        min_length=1,
        description=(
            "Wind at heights above the pad, in increasing height. Held constant above the top."
        ),
    )
    surface_temperature_k: float | None = quantity(
        "K",
        "Air temperature at the pad. Unset uses the standard atmosphere.",
        default=None,
        gt=200,
        lt=340,
    )
    surface_pressure_pa: float | None = quantity(
        "Pa",
        "Station pressure at the pad (not sea-level). Unset uses the standard atmosphere.",
        default=None,
        gt=30_000,
        lt=110_000,
    )

    @field_validator("levels")
    @classmethod
    def _ascending(cls, v: list[ManualWindLevel]) -> list[ManualWindLevel]:
        if any(b.height_m <= a.height_m for a, b in itertools.pairwise(v)):
            raise ValueError("levels must be in strictly increasing height")
        return v


class SurfaceWind(_Strict):
    """A measured surface wind, blended into the profile near the ground."""

    speed_ms: float = quantity("m/s", "Measured wind speed.", ge=0, le=60)
    direction_deg: float = quantity(
        "deg", "Direction the wind blows from, degrees clockwise from true north.", ge=0, lt=360
    )
    height_m: float = quantity(
        "m", "Height of the anemometer above the pad.", default=2.0, gt=0, le=100
    )
    alpha: float = Field(
        default=0.14,
        ge=0,
        le=0.6,
        description=(
            "Power-law exponent for speed against height. About 0.14 over open ground, "
            "higher over rough terrain."
        ),
    )
    blend_depth_m: float = quantity(
        "m",
        "Height above the pad by which the profile above has fully taken over.",
        default=300.0,
        gt=0,
        le=3000,
    )
    measured_utc: datetime | None = Field(default=None, description="When it was measured, UTC.")

    @model_validator(mode="after")
    def _depth_above_anemometer(self) -> "SurfaceWind":
        if self.blend_depth_m <= self.height_m:
            raise ValueError("blend_depth_m must be above the anemometer height")
        return self


class LaunchConditions(_Strict):
    """The sky at launch, for launch-condition rules. A flight doesn't depend on it."""

    launch_utc: datetime | None = Field(
        default=None,
        description="Planned launch time, UTC. Unset: the forecast hour the atmosphere is from.",
    )
    cloud_cover_pct: float | None = quantity(
        "%", "Share of the sky covered by cloud.", default=None, ge=0, le=100
    )
    cloud_base_m: float | None = quantity(
        "m", "Height of the lowest cloud base above the pad.", default=None, ge=0, le=30_000
    )
    visibility_m: float | None = quantity(
        "m", "Horizontal visibility.", default=None, ge=0, le=200_000
    )
    wind_speed_ms: float | None = quantity(
        "m/s",
        "Sustained surface wind. Unset: the flight's wind at the surface.",
        default=None,
        ge=0,
        le=80,
    )
    wind_gust_ms: float | None = quantity(
        "m/s", "Strongest surface gust.", default=None, ge=0, le=100
    )
    source: str = Field(
        default="",
        description="Where the numbers came from, e.g. a forecast or the RSO's briefing.",
    )


class Environment(_Strict):
    atmosphere: StandardAtmosphere | ResolvedProfile | ManualProfile = Field(
        default_factory=lambda: StandardAtmosphere(kind="standard"),
        discriminator="kind",
        description="Atmosphere and wind the flight is simulated in.",
    )
    surface_wind: SurfaceWind | None = Field(
        default=None,
        description="A measured surface wind to blend into the atmosphere near the ground.",
    )


# --- Monte Carlo ------------------------------------------------------------------


class Spread(_Strict):
    """One uncertain input: normally distributed about its nominal value."""

    enabled: bool = Field(default=True, description="Vary this input in a campaign.")
    sigma: float = Field(ge=0, description="One standard deviation, in the input's units.")


def _spread(sigma: float, description: str) -> Any:
    return Field(default_factory=lambda: Spread(sigma=sigma), description=description)


class MonteCarloParameters(_Strict):
    """What varies between samples, and by how much. Defaults follow the brief."""

    total_impulse: Spread = _spread(
        0.03, "Total impulse, relative (0.03 = 3%; use 0.05 for student-made motors)."
    )
    burn_time: Spread = _spread(0.05, "Burn time, relative. Impulse is kept, so thrust scales.")
    dry_mass: Spread = _spread(0.005, "Rocket dry mass, relative (0.005 if weighed, 0.02 if not).")
    dry_cg: Spread = _spread(0.005, "Rocket dry centre of mass, metres along the axis.")
    drag: Spread = _spread(0.10, "Drag coefficient multiplier, relative.")
    rail_inclination: Spread = _spread(0.5, "Rail inclination, degrees.")
    rail_heading: Spread = _spread(2.0, "Rail heading, degrees.")
    parachute_cd_s: Spread = _spread(0.10, "Each parachute's CdS, relative, independently.")
    deployment_lag: Spread = _spread(
        0.3, "Added to each device's deployment lag, seconds; the total is truncated at zero."
    )
    deploy_altitude: Spread = _spread(
        10.0, "Altitude-triggered deployments, metres (altimeter error)."
    )
    wind_speed: Spread = _spread(
        0.15, "Whole-profile wind speed multiplier, relative: the forecast's speed error."
    )
    wind_direction: Spread = _spread(
        10.0, "Whole-profile wind direction offset, degrees: the forecast's direction error."
    )
    wind_layers: Spread = _spread(
        1.0, "Smaller, height-correlated wind noise on top, m/s per component."
    )


class MonteCarlo(_Strict):
    samples: int = Field(default=200, ge=10, le=5000, description="Number of flights to run.")
    seed: int = Field(
        default=1, ge=0, description="Sampling seed. The same seed gives the same samples."
    )
    wind_correlation_m: float = quantity(
        "m",
        "Height over which the layer noise stays correlated (500 to 1,000 m is typical).",
        default=750.0,
        gt=0,
        le=5000,
    )
    parameters: MonteCarloParameters = Field(
        default_factory=MonteCarloParameters, description="The uncertain inputs."
    )


# --- Ballast ----------------------------------------------------------------------


class Ballast(_Strict):
    """Ballast to trim apogee: what is installed, and what the solver may use."""

    installed_kg: float = quantity(
        "kg", "Ballast in the rocket now. Every flight includes it.", default=0.0, ge=0
    )
    position_m: float | None = quantity(
        "m",
        "Centre of the ballast bay, aft of the nose tip. Needed for any ballast.",
        default=None,
        ge=0,
    )
    target_apogee_m: float | None = quantity(
        "m",
        "Apogee to trim to, above the pad. Unset: the competition category's target.",
        default=None,
        gt=0,
    )
    increment_kg: float = quantity(
        "kg", "Smallest step you can add: one plate, or a measure of shot.", default=0.05, gt=0
    )
    max_kg: float = quantity("kg", "Most the bay holds.", default=2.0, gt=0)

    @model_validator(mode="after")
    def _position_if_installed(self) -> "Ballast":
        if self.installed_kg > 0 and self.position_m is None:
            raise ValueError("installed ballast needs position_m")
        return self


# --- Constraints ------------------------------------------------------------------

#: Result metrics a constraint can test. Each is computed from a flight summary
#: and recorded for every Monte Carlo sample (see simcore.constraints.metrics).
Metric = Literal[
    "apogee_agl_m",
    "rail_exit_velocity_ms",
    "stability_margin_at_rail_exit_cal",
    "min_stability_margin_cal",
    "max_stability_margin_cal",
    "stability_margin_at_launch_pct_length",
    "min_stability_margin_pct_length",
    "max_stability_margin_pct_length",
    "thrust_to_weight",
    "max_mach",
    "max_acceleration_ms2",
    "max_dynamic_pressure_pa",
    "landing_speed_ms",
    "landing_kinetic_energy_j",
    "main_deploy_agl_m",
    "drogue_descent_rate_ms",
    "descent_time_s",
    "drift_m",
    "flight_time_s",
    "min_fin_flutter_margin",
    "cloud_clearance_m",
    "cloud_cover_pct",
    "visibility_m",
    "surface_wind_ms",
    "sun_elevation_deg",
]

EvaluateOn = Literal["nominal", "p50", "p95", "p99", "worst"]
Severity = Literal["hard", "scoring", "advisory"]


class Condition(_Strict):
    """Limits a rule to the flights it applies to, e.g. only supersonic ones."""

    metric: Metric = Field(description="The metric that decides.")
    min: float | None = Field(default=None, description="Applies when the metric is at least this.")
    max: float | None = Field(default=None, description="Applies when the metric is below this.")


class Constraint(_Strict):
    """A declarative rule over one result metric: a minimum, a maximum, or a target band."""

    id: str = Field(
        pattern=r"^[a-z0-9_]+$", description="Stable id, e.g. 'min_rail_exit_velocity'."
    )
    label: str = Field(default="", description="What it checks, in words.")
    metric: Metric = Field(description="The result metric it tests.")
    min: float | None = Field(
        default=None, description="Lowest allowed value, in the metric's units."
    )
    max: float | None = Field(
        default=None, description="Highest allowed value, in the metric's units."
    )
    target: float | str | None = Field(
        default=None,
        description=(
            "Target value, or '$category.apogee_target_m' to take the profile category's target. "
            "Needs a tolerance."
        ),
    )
    tolerance_pct: float | None = Field(
        default=None, gt=0, description="Allowed distance from the target, percent of it."
    )
    tolerance_m: float | None = Field(
        default=None, gt=0, description="Allowed distance from the target, in the metric's units."
    )
    severity: Severity = Field(
        default="hard",
        description="hard: a fail is a no-go. scoring: costs points. advisory: worth knowing.",
    )
    evaluate_on: EvaluateOn = Field(
        default="p95",
        description=(
            "nominal: the single flight. p50/p95/p99: that share of Monte Carlo flights must "
            "comply. worst: every flight must."
        ),
    )
    reference: str = Field(default="", description="The rule clause this comes from.")
    applies_if: Condition | None = Field(
        default=None, description="Judge only the flights this holds for. Unset: every flight."
    )

    @model_validator(mode="after")
    def _has_a_limit(self) -> "Constraint":
        if self.min is None and self.max is None and self.target is None:
            raise ValueError("a constraint needs a min, a max or a target")
        if self.target is not None and self.tolerance_pct is None and self.tolerance_m is None:
            raise ValueError("a target needs tolerance_pct or tolerance_m")
        return self


class ConstraintOverride(_Strict):
    """A mission's change to one profile rule. Unset fields keep the profile's value."""

    min: float | None = Field(default=None, description="Lowest allowed value.")
    max: float | None = Field(default=None, description="Highest allowed value.")
    target: float | None = Field(default=None, description="Target value.")
    tolerance_pct: float | None = Field(default=None, gt=0, description="Tolerance, percent.")
    tolerance_m: float | None = Field(default=None, gt=0, description="Tolerance, metric units.")
    severity: Severity | None = Field(default=None, description="Severity.")
    evaluate_on: EvaluateOn | None = Field(default=None, description="What it is judged on.")
    disabled: bool = Field(default=False, description="Drop this rule for this mission.")


class ConstraintSettings(_Strict):
    profile: str | None = Field(
        default=None, description="Competition profile id, e.g. 'aurc-2027'. None: team rules only."
    )
    category: str | None = Field(default=None, description="Category within the profile.")
    overrides: dict[str, ConstraintOverride] = Field(
        default_factory=dict, description="Changes to profile rules, by rule id."
    )
    additional: list[Constraint] = Field(
        default_factory=list, description="The team's own rules, on top of the profile's."
    )
    launch_rules: str | None = Field(
        default=None,
        description="Launch-condition rules id, e.g. 'faa-101'. None: conditions not checked.",
    )


#: Mission sections a single flight doesn't depend on: left out of its cache key.
FLIGHT_IRRELEVANT = frozenset(
    {"monte_carlo", "constraints", "ejection", "structure", "launch_conditions"}
)
#: Mission sections a Monte Carlo campaign doesn't depend on.
CAMPAIGN_IRRELEVANT = frozenset({"constraints", "ejection", "structure", "launch_conditions"})


class Mission(_Strict):
    """A complete mission config. Serialised as YAML (or JSON)."""

    schema_version: Literal[4] = Field(
        default=CURRENT_SCHEMA_VERSION,
        description="Config schema version. Older configs are migrated on load.",
    )
    extends: str | None = Field(
        default=None,
        description=(
            "Reserved for config inheritance, which is not supported: must be unset. "
            "To reuse a launch site, save it as a site preset."
        ),
    )
    meta: MissionMeta = Field(description="Name, id, authorship.")
    rocket: Rocket | None = Field(default=None, description="Airframe, without the motor.")
    motor: Motor | None = Field(
        default=None,
        description="The motor: solid (with grain geometry) or generic (thrust curve and masses).",
    )
    recovery: Recovery = Field(
        default_factory=Recovery, description="Parachutes and other recovery devices."
    )
    ballast: Ballast = Field(
        default_factory=Ballast, description="Ballast installed and to solve for."
    )
    ejection: Ejection = Field(
        default_factory=Ejection,
        description="Ejection charges and shear pins. A flight doesn't depend on them.",
    )
    structure: Structure = Field(
        default_factory=Structure,
        description="The airframe as a beam, for vibration. A flight doesn't depend on it.",
    )
    site: Site | None = Field(default=None, description="Launch site and range geometry.")
    environment: Environment = Field(
        default_factory=Environment, description="Atmosphere and wind."
    )
    launch_conditions: LaunchConditions = Field(
        default_factory=LaunchConditions,
        description="Cloud, visibility, gusts and launch time, for launch-condition rules.",
    )
    monte_carlo: MonteCarlo = Field(
        default_factory=MonteCarlo, description="Monte Carlo campaign settings."
    )
    constraints: ConstraintSettings = Field(
        default_factory=ConstraintSettings,
        description="Competition profile and team rules the go/no-go board checks.",
    )
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
