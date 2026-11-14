"""Motor finder: which commercial motors fit the mount, and which come nearest a target apogee.

Two stages, so a search over every motor of a diameter stays quick:

1. **Screen.** Each motor that fits is flown as a point mass in the plane of
   the rail, from the catalogue's numbers alone: total impulse, burn time and
   masses, thrust held at its average, the rocket's own drag curves and an ISA
   atmosphere above the pad. A few milliseconds a motor; good for ranking, not
   for the final number (it ignores the thrust curve's shape, wind and
   weathercocking).
2. **Fly.** The best-screened motors get their real thrust curves and full
   flights, which the board judges like any other.
"""

import math
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from simcore.aero.drag import model_for, reference_curve
from simcore.assets import AssetError, AssetStore
from simcore.constraints.evaluate import evaluate, resolve
from simcore.constraints.profiles import LAUNCH_METRICS, get_profile
from simcore.importers.drag import parse_drag_csv
from simcore.importers.thrust import (
    ThrustCurve,
    ThrustCurveError,
    generic_motor_estimate,
    parse_eng,
)
from simcore.mission.models import (
    Asset,
    ConstraintSettings,
    DragCurve,
    GenericMotor,
    Mission,
    quantity,
)
from simcore.weather.isa import isa_pressure_temperature

#: Standard motor-mount diameters, in mm.
MOUNT_DIAMETERS_MM = (13, 18, 24, 29, 38, 54, 75, 98, 152)

_G = 9.80665
_R_AIR = 287.05287
_GAMMA = 1.4


class Candidate(BaseModel):
    """A motor from the ThrustCurve.org catalogue."""

    motor_id: str = Field(description="ThrustCurve.org motor id.")
    manufacturer: str = Field(description="Manufacturer, e.g. 'AeroTech'.")
    designation: str = Field(description="Designation, e.g. 'M1340W'.")
    common_name: str = Field(description="Class and average thrust, e.g. 'M1340'.")
    impulse_class: str = Field(description="Impulse class letter.")
    type: str = Field(description="SU (single use), reload or hybrid.")
    diameter_mm: float = quantity("mm", "Case diameter.")
    length_mm: float = quantity("mm", "Case length.")
    total_impulse_ns: float = quantity("N·s", "Total impulse.")
    average_thrust_n: float = quantity("N", "Average thrust.")
    burn_time_s: float = quantity("s", "Burn time.")
    total_mass_kg: float = quantity("kg", "Loaded motor mass.")
    propellant_mass_kg: float = quantity("kg", "Propellant mass.")
    case_info: str = Field(default="", description="Case or hardware it needs.")
    propellant: str = Field(default="", description="Propellant name.")
    availability: str = Field(default="", description="regular, occasional or OOP.")


def candidate_from_thrustcurve(row: dict[str, Any]) -> Candidate | None:
    """A catalogue row from ThrustCurve.org's search, or None if it lacks impulse or masses."""
    try:
        total, prop = float(row["totalWeightG"]) / 1000, float(row["propWeightG"]) / 1000
        impulse, burn = float(row["totImpulseNs"]), float(row["burnTimeS"])
        diameter, length = float(row["diameter"]), float(row["length"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(total, prop, impulse, burn, diameter, length) <= 0 or prop >= total:
        return None
    return Candidate(
        motor_id=str(row["motorId"]),
        manufacturer=row.get("manufacturerAbbrev") or row.get("manufacturer", ""),
        designation=row.get("designation", ""),
        common_name=row.get("commonName", ""),
        impulse_class=row.get("impulseClass", ""),
        type=row.get("type", ""),
        diameter_mm=diameter,
        length_mm=length,
        total_impulse_ns=impulse,
        average_thrust_n=float(row.get("avgThrustN") or impulse / burn),
        burn_time_s=burn,
        total_mass_kg=total,
        propellant_mass_kg=prop,
        case_info=row.get("caseInfo") or "",
        propellant=row.get("propInfo") or "",
        availability=row.get("availability") or "",
    )


class Mount(BaseModel):
    diameter_mm: float = quantity("mm", "Motor mount tube inside diameter (nominal).", gt=0)
    max_length_mm: float = quantity("mm", "Longest motor case the mount takes.", gt=0)


def mount_from_motor(mission: Mission, assets: AssetStore) -> Mount | None:
    """The mount the mission's current motor implies: its case diameter and length.

    From the thrust curve's header, or failing that the motor's propellant
    geometry (shorter than the case). The diameter rounds to the nearest
    standard size; the length is the motor's own, so longer motors only show
    up once the mount's real length is set.
    """
    m = mission.motor
    if m is None:
        return None
    try:
        curve = parse_eng(assets.read(m.thrust_curve).decode("utf-8", errors="replace"))
        diameter, length = curve.diameter_m, curve.length_m
    except (AssetError, ThrustCurveError):
        if isinstance(m, GenericMotor):
            diameter, length = 2 * m.chamber_radius_m, m.chamber_height_m
        else:
            g = m.grains
            diameter = 2 * g.outer_radius_m
            length = g.count * g.initial_height_m + (g.count - 1) * g.separation_m
    mm = diameter * 1000
    nearest = min(MOUNT_DIAMETERS_MM, key=lambda d: abs(d - mm))
    return Mount(diameter_mm=nearest, max_length_mm=round(length * 1000))


def fits(c: Candidate, mount: Mount) -> bool:
    """Same nominal diameter, and no longer than the mount."""
    return abs(c.diameter_mm - mount.diameter_mm) < 1 and c.length_mm <= mount.max_length_mm


class Estimate(BaseModel):
    """The screen's point-mass flight. For ranking: the full flight is the number to trust."""

    apogee_agl_m: float = quantity("m", "Estimated apogee above the pad.")
    rail_exit_velocity_ms: float = quantity("m/s", "Estimated speed off the rail.")
    thrust_to_weight: float = quantity("1", "Average thrust over the weight at ignition.")
    max_mach: float = quantity("1", "Estimated highest Mach number.")
    liftoff_mass_kg: float = quantity("kg", "Rocket, ballast and loaded motor.")


CdOfMach = Callable[[float], float]


def drag_functions(mission: Mission, assets: AssetStore) -> tuple[CdOfMach, CdOfMach]:
    """CD against Mach, (power on, power off), with the drag multiplier applied."""
    assert mission.rocket is not None
    drag = mission.rocket.drag

    def one(curve: DragCurve, power_on: bool) -> CdOfMach:
        if curve.estimate:
            elevation = mission.site.elevation_m if mission.site else 0.0
            cd_of = reference_curve(model_for(mission), elevation, power_on=power_on)
            return lambda m: cd_of(m) * drag.multiplier
        if curve.table is None:
            cd = (curve.constant_cd or 0.0) * drag.multiplier
            return lambda _mach: cd
        rows = parse_drag_csv(assets.read(curve.table))
        mach = np.array([r[0] for r in rows])
        cds = np.array([r[1] for r in rows]) * drag.multiplier
        return lambda m: float(np.interp(m, mach, cds))

    return one(drag.power_on, True), one(drag.power_off, False)


def screen(mission: Mission, c: Candidate, cd_on: CdOfMach, cd_off: CdOfMach) -> Estimate:
    """Fly ``c`` as a point mass up the rail and on to apogee (see the module docstring)."""
    assert mission.rocket is not None and mission.site is not None
    rocket, site = mission.rocket, mission.site
    area = math.pi * rocket.radius_m**2
    m0 = rocket.dry_mass_kg + mission.ballast.installed_kg + c.total_mass_kg
    thrust = c.total_impulse_ns / c.burn_time_s
    burn_rate = c.propellant_mass_kg / c.burn_time_s
    elev = math.radians(site.inclination_deg)
    ux, uz = math.cos(elev), math.sin(elev)

    t = x = z = vx = vz = 0.0
    on_rail, rail_exit, max_mach = True, 0.0, 0.0
    while t < 600:
        burning = t < c.burn_time_s
        dt = 0.005 if burning or on_rail else 0.02
        p, temp = isa_pressure_temperature(site.elevation_m + max(z, 0.0))
        rho = p / (_R_AIR * temp)
        speed = math.hypot(vx, vz)
        mach = speed / math.sqrt(_GAMMA * _R_AIR * temp)
        max_mach = max(max_mach, mach)
        mass = m0 - burn_rate * min(t, c.burn_time_s)
        drag = 0.5 * rho * speed**2 * (cd_on if burning else cd_off)(mach) * area
        f = thrust if burning else 0.0
        # Thrust and drag act along the velocity; on the rail (or at rest) along the rail.
        dx, dz = (vx / speed, vz / speed) if speed > 1e-6 and not on_rail else (ux, uz)
        ax = (f - drag) * dx / mass
        az = (f - drag) * dz / mass - _G
        if on_rail:
            along = ax * ux + az * uz
            along = max(along, 0.0)  # held on the pad until thrust beats gravity
            ax, az = along * ux, along * uz
        vx, vz = vx + ax * dt, vz + az * dt
        x, z = x + vx * dt, z + vz * dt
        t += dt
        if on_rail and math.hypot(x, z) >= site.rail_length_m:
            on_rail, rail_exit = False, math.hypot(vx, vz)
        if not burning and not on_rail and vz <= 0:
            break
    return Estimate(
        apogee_agl_m=max(z, 0.0),
        rail_exit_velocity_ms=rail_exit,
        thrust_to_weight=c.average_thrust_n / (m0 * _G),
        max_mach=max_mach,
        liftoff_mass_kg=m0,
    )


def with_motor(mission: Mission, curve: ThrustCurve, sha: str, filename: str, size: int) -> Mission:
    """The mission flying ``curve`` instead of its motor, estimated as on import.

    The old curve leaves the assets unless a drag table shares it.
    """
    motor = GenericMotor(kind="generic", thrust_curve=sha, **generic_motor_estimate(curve))
    assets = dict(mission.assets)
    old = mission.motor.thrust_curve if mission.motor else None
    drag = mission.rocket.drag if mission.rocket else None
    tables = {drag.power_off.table, drag.power_on.table} if drag else set()
    if old and old != sha and old not in tables:
        assets.pop(old, None)
    assets[sha] = Asset(kind="thrust_curve", filename=filename, size=size)
    return mission.model_copy(update={"motor": motor, "assets": assets})


class Judgement(BaseModel):
    """One candidate's flight against the mission's rules."""

    verdict: Literal["go", "no_go", "incomplete"] = Field(
        description="no_go if a hard rule fails; incomplete if one can't be judged."
    )
    failing: list[str] = Field(description="Rules it fails, hard ones first.")
    points: float | None = Field(description="Apogee score, if the profile scores apogee.")


def judge(settings: ConstraintSettings, values: dict[str, float]) -> Judgement:
    """Every rule judged on one flight, whatever it is normally judged on.

    A rule on a Monte Carlo percentile is judged on this flight instead: a
    finder can't fly a campaign per motor, so it says which ones are worth
    one. Launch-condition rules are left out (they don't depend on the motor).
    Raises ValueError if the settings can't be resolved.
    """
    rules, profile = resolve(settings.model_copy(update={"launch_rules": None}))
    on_flight = {"evaluate_on": "nominal"}
    rules = [
        r.model_copy(update={"constraint": r.constraint.model_copy(update=on_flight)})
        for r in rules
        if r.constraint.metric not in LAUNCH_METRICS
    ]
    rows = evaluate(rules, values, None)
    hard = [r for r in rows if r.severity == "hard"]
    verdict: Literal["go", "no_go", "incomplete"] = (
        "no_go"
        if any(r.status == "fail" for r in hard)
        else "incomplete"
        if any(r.status == "missing" for r in hard)
        else "go"
    )
    failed = [r for r in rows if r.status == "fail"]
    failing = [r.label for r in sorted(failed, key=lambda r: r.severity != "hard")]
    points = None
    if profile and profile.scoring and settings.category and "apogee_agl_m" in values:
        category = next(c for c in profile.categories if c.id == settings.category)
        if category.apogee_target_m is not None:
            points = profile.scoring.points(values["apogee_agl_m"], category.apogee_target_m)
    return Judgement(verdict=verdict, failing=failing, points=points)


def category_target_m(settings: ConstraintSettings) -> float | None:
    """The chosen category's target apogee, if the profile has one."""
    if not (settings.profile and settings.category):
        return None
    profile = get_profile(settings.profile)
    category = next((c for c in profile.categories if c.id == settings.category), None)
    return category.apogee_target_m if category else None
