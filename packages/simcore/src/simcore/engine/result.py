"""What a flight produces. Plain data: no RocketPy objects, ever."""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pydantic import BaseModel, Field

from simcore.mission.models import quantity


class Landing(BaseModel):
    east_m: float = quantity("m", "Landing point east of the pad.")
    north_m: float = quantity("m", "Landing point north of the pad.")
    latitude_deg: float = quantity("deg", "Landing point latitude, WGS84.")
    longitude_deg: float = quantity("deg", "Landing point longitude, WGS84.")
    drift_distance_m: float = quantity("m", "Horizontal distance from pad to landing point.")
    speed_ms: float = quantity("m/s", "Speed at touchdown.")
    kinetic_energy_j: float = quantity(
        "J", "Kinetic energy at touchdown, whole rocket as one body."
    )
    flight_time_s: float = quantity("s", "Time from ignition to touchdown.")


class ParachuteEvent(BaseModel):
    name: str = Field(description="Recovery device name, from the mission.")
    triggered_s: float = quantity("s", "Time the trigger fired.")
    triggered_agl_m: float = quantity("m", "Altitude above ground when the trigger fired.")


class FlightSummary(BaseModel):
    """Summary scalars of one flight. Every constraint metric comes from here."""

    apogee_agl_m: float = quantity("m", "Highest altitude above the pad.")
    apogee_time_s: float = quantity("s", "Time from ignition to apogee.")
    rail_exit_velocity_ms: float = quantity("m/s", "Speed when the last rail button leaves.")
    stability_margin_at_rail_exit_cal: float = quantity(
        "cal", "Static stability margin at rail exit, in body calibers."
    )
    min_stability_margin_cal: float = quantity(
        "cal", "Lowest static stability margin during powered and coasting flight."
    )
    max_stability_margin_cal: float = quantity(
        "cal", "Highest static stability margin during powered and coasting flight."
    )
    max_mach: float = quantity("1", "Highest Mach number.")
    max_speed_ms: float = quantity("m/s", "Highest speed.")
    max_dynamic_pressure_pa: float = quantity("Pa", "Highest dynamic pressure (max q).")
    max_acceleration_ms2: float = quantity("m/s²", "Highest acceleration magnitude.")
    burnout_time_s: float = quantity("s", "Motor burnout time.")
    landing: Landing | None = Field(
        description="Touchdown. None for an ascent-only flight, which stops at apogee."
    )
    parachute_events: list[ParachuteEvent] = Field(
        description="Recovery devices that deployed, in order."
    )


#: Trajectory channels: name -> (units, description). Arrays share the time base.
TRAJECTORY_CHANNELS: dict[str, tuple[str, str]] = {
    "time_s": ("s", "Time since ignition"),
    "altitude_agl_m": ("m", "Altitude above the pad"),
    "vertical_velocity_ms": ("m/s", "Vertical velocity, up positive"),
    "speed_ms": ("m/s", "Speed"),
    "acceleration_ms2": ("m/s²", "Acceleration magnitude"),
    "mach": ("1", "Mach number"),
    "dynamic_pressure_pa": ("Pa", "Dynamic pressure"),
    "stability_margin_cal": ("cal", "Static stability margin"),
    "east_m": ("m", "Position east of the pad"),
    "north_m": ("m", "Position north of the pad"),
}


@dataclass(frozen=True)
class FlightResult:
    """One simulated flight: summary scalars plus the trajectory.

    Attributes:
        summary: Scalars every downstream feature uses.
        trajectory: Channel name -> array, all on ``trajectory["time_s"]``.
        ascent_only: True if the flight stopped at apogee.
        computed_utc: When the simulation ran.
    """

    summary: FlightSummary
    trajectory: dict[str, np.ndarray]
    ascent_only: bool
    computed_utc: datetime
    warnings: list[str] = field(default_factory=list)
