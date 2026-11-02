"""International Standard Atmosphere (ICAO), troposphere and lower stratosphere."""

import math

from simcore.mission.models import ProfileLevel

_T0 = 288.15  # K, sea level
_P0 = 101_325.0  # Pa
_LAPSE = 0.0065  # K/m, to 11 km
_G0 = 9.80665
_R = 287.05287  # J/(kg·K), dry air


def isa_pressure_temperature(altitude_m: float) -> tuple[float, float]:
    """Pressure (Pa) and temperature (K) at a geopotential altitude, 0 to 20 km."""
    if altitude_m <= 11_000:
        t = _T0 - _LAPSE * altitude_m
        return _P0 * (t / _T0) ** (_G0 / (_LAPSE * _R)), t
    t11 = _T0 - _LAPSE * 11_000
    p11 = _P0 * (t11 / _T0) ** (_G0 / (_LAPSE * _R))
    return p11 * math.exp(-_G0 * (altitude_m - 11_000) / (_R * t11)), t11


def isa_levels(
    *, wind_u_ms: float = 0.0, wind_v_ms: float = 0.0, top_m: float = 20_000, step_m: float = 250
) -> list[ProfileLevel]:
    """ISA levels from sea level to ``top_m`` with a constant wind (u east, v north)."""
    levels = []
    h = 0.0
    while h <= top_m:
        p, t = isa_pressure_temperature(h)
        levels.append(
            ProfileLevel(
                altitude_m=h,
                pressure_pa=p,
                temperature_k=t,
                wind_u_ms=wind_u_ms,
                wind_v_ms=wind_v_ms,
            )
        )
        h += step_m
    return levels
