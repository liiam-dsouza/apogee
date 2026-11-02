"""Steady (terminal) descent under each recovery device.

Under a canopy the rocket soon falls at the speed where drag balances weight:
v = sqrt(2 m g / (rho CdS)). That is a sizing estimate; the flight simulation,
with deployment lag and the approach to terminal speed, is the real answer.

As in RocketPy, a device that deploys replaces the one before it: the rate
under the main uses the main's CdS alone. Each device governs the descent from
its own deployment height down to the next device's (or the ground), and is
reported at both ends: the bottom is where it is slowest, and where IREC's
DTEG 6.3.3 measures the drogue.
"""

import math

import numpy as np
from pydantic import BaseModel, Field

from simcore.mission.models import Mission, RecoveryDevice, quantity
from simcore.weather.blend import effective_levels
from simcore.weather.isa import isa_pressure_temperature

G0 = 9.80665
R_AIR = 287.05287


def descent_rate(mass_kg: float, cd_s_m2: float, density_kg_m3: float) -> float:
    """Terminal descent rate, m/s."""
    return math.sqrt(2 * mass_kg * G0 / (density_kg_m3 * cd_s_m2))


def cd_s_for_rate(mass_kg: float, rate_ms: float, density_kg_m3: float) -> float:
    """The CdS (m²) that gives this terminal descent rate."""
    return 2 * mass_kg * G0 / (density_kg_m3 * rate_ms**2)


class DeviceDescent(BaseModel):
    name: str = Field(description="Device name.")
    cd_s_m2: float = quantity("m²", "The device's CdS.")
    top_agl_m: float | None = quantity(
        "m", "Where it takes over: its deployment height. None for apogee without a flight."
    )
    bottom_agl_m: float = quantity("m", "Where it hands over: the next device's height, or 0.")
    rate_top_ms: float | None = quantity("m/s", "Steady descent rate at the top.")
    rate_bottom_ms: float = quantity("m/s", "Steady descent rate at the bottom.")
    target_rate_ms: float | None = quantity("m/s", "The rate asked for at the bottom, if any.")
    cd_s_for_target_m2: float | None = quantity("m²", "CdS that gives the target rate there.")


def _density(mission: Mission, altitude_msl_m: float) -> float:
    assert mission.site is not None
    levels = effective_levels(mission.environment, mission.site.elevation_m)
    if levels is None:
        p, t = isa_pressure_temperature(altitude_msl_m)
    else:
        alts = [lv.altitude_m for lv in levels]
        p = float(
            np.exp(np.interp(altitude_msl_m, alts, [math.log(lv.pressure_pa) for lv in levels]))
        )
        t = float(np.interp(altitude_msl_m, alts, [lv.temperature_k for lv in levels]))
    return p / (R_AIR * t)


def descent_mass_kg(mission: Mission) -> float:
    """Rocket plus burnt-out motor: what hangs under the canopy."""
    assert mission.rocket is not None and mission.motor is not None
    return mission.rocket.dry_mass_kg + mission.motor.dry_mass_kg


def descent_table(
    mission: Mission,
    apogee_agl_m: float | None = None,
    target_rates_ms: dict[str, float] | None = None,
) -> list[DeviceDescent]:
    """Each device's steady descent rate, in deployment order (highest first)."""
    assert mission.site is not None
    mass = descent_mass_kg(mission)
    pad = mission.site.elevation_m
    targets = target_rates_ms or {}

    def top_of(d: RecoveryDevice) -> float | None:
        return apogee_agl_m if d.trigger.kind == "apogee" else d.trigger.altitude_m

    # Highest first; an apogee device with no flight to say how high opens first anyway.
    devices = sorted(
        mission.recovery.devices,
        key=lambda d: (top_of(d) is not None, -(top_of(d) or 0.0)),
    )
    out = []
    for i, d in enumerate(devices):
        top = top_of(d)
        nxt = top_of(devices[i + 1]) if i + 1 < len(devices) else None
        bottom = nxt if nxt is not None else 0.0
        rho_bottom = _density(mission, pad + bottom)
        target = targets.get(d.name)
        out.append(
            DeviceDescent(
                name=d.name,
                cd_s_m2=d.cd_s_m2,
                top_agl_m=top,
                bottom_agl_m=bottom,
                rate_top_ms=None
                if top is None
                else descent_rate(mass, d.cd_s_m2, _density(mission, pad + top)),
                rate_bottom_ms=descent_rate(mass, d.cd_s_m2, rho_bottom),
                target_rate_ms=target,
                cd_s_for_target_m2=cd_s_for_rate(mass, target, rho_bottom) if target else None,
            )
        )
    return out
