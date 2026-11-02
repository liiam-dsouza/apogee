"""Blending a measured surface wind into a profile aloft, and the profile a flight flies.

Near the ground the wind follows a power law from the measurement,
``v(h) = v_ref * (h / h_ref) ** alpha``, in the measured direction. Between the
anemometer height and ``blend_depth_m`` speed and direction fade from the power
law into the profile with a cosine weight, so neither jumps. Direction turns
the short way round to the profile's direction at the top of the layer, and the
same way round at every height below it, so a forecast nearly opposite the
measurement cannot make the wind swing back and forth.

Speed and direction are blended rather than u and v: blending the components of
a measured wind that opposes the forecast passes through an invented calm layer.
"""

import math

import numpy as np

from simcore.mission.models import Environment, ProfileLevel, ResolvedProfile, SurfaceWind
from simcore.weather.isa import isa_levels

#: Heights above the pad (m) added inside the blend layer so it is resolved,
#: whatever the spacing of the profile's own levels.
_BLEND_GRID_M = (0, 5, 10, 20, 30, 50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 1500)
#: The power law is singular at the ground; below this height it is held constant.
_MIN_HEIGHT_M = 1.0


def wind_components(speed_ms: float, from_deg: float) -> tuple[float, float]:
    """(u east, v north) of a wind blowing *from* ``from_deg``."""
    rad = math.radians(from_deg)
    return -speed_ms * math.sin(rad), -speed_ms * math.cos(rad)


def _weight(h: float, wind: SurfaceWind) -> float:
    """1 at and below the anemometer, 0 at and above the blend depth."""
    if h <= wind.height_m:
        return 1.0
    if h >= wind.blend_depth_m:
        return 0.0
    x = (h - wind.height_m) / (wind.blend_depth_m - wind.height_m)
    return 0.5 * (1 + math.cos(math.pi * x))


def blend_surface_wind(
    levels: list[ProfileLevel], wind: SurfaceWind, pad_elevation_m: float
) -> list[ProfileLevel]:
    """``levels`` with ``wind`` blended in near the pad. Levels below the pad are unchanged."""
    alt = np.array([lv.altitude_m for lv in levels])
    ln_p = np.log([lv.pressure_pa for lv in levels])
    temp = np.array([lv.temperature_k for lv in levels])
    u = np.array([lv.wind_u_ms for lv in levels])
    v = np.array([lv.wind_v_ms for lv in levels])

    grid = {float(a) for a in alt}
    grid.update(
        pad_elevation_m + h
        for h in (*_BLEND_GRID_M, wind.height_m, wind.blend_depth_m)
        if h <= wind.blend_depth_m and pad_elevation_m + h <= alt[-1]
    )
    original = {lv.altitude_m: lv for lv in levels}

    def turn_to(u_: float, v_: float) -> float:
        """Degrees from the measured direction to this wind's, in (-180, 180]."""
        return (math.degrees(math.atan2(-u_, -v_)) - wind.direction_deg + 180) % 360 - 180

    top = pad_elevation_m + wind.blend_depth_m
    top_turn = turn_to(float(np.interp(top, alt, u)), float(np.interp(top, alt, v)))

    out = []
    for a in sorted(grid):
        h = a - pad_elevation_m
        if a in original and (h < 0 or _weight(h, wind) == 0):
            out.append(original[a])
            continue
        # Linear in altitude, except pressure, which is exponential in altitude.
        lv_u = float(np.interp(a, alt, u))
        lv_v = float(np.interp(a, alt, v))
        if h >= 0:
            w = _weight(h, wind)
            power_law = wind.speed_ms * (max(h, _MIN_HEIGHT_M) / wind.height_m) ** wind.alpha
            speed = w * power_law + (1 - w) * math.hypot(lv_u, lv_v)
            turn = turn_to(lv_u, lv_v)
            turn -= 360 * round((turn - top_turn) / 360)
            lv_u, lv_v = wind_components(speed, wind.direction_deg + (1 - w) * turn)
        out.append(
            ProfileLevel(
                altitude_m=a,
                pressure_pa=float(np.exp(np.interp(a, alt, ln_p))),
                temperature_k=float(np.interp(a, alt, temp)),
                wind_u_ms=lv_u,
                wind_v_ms=lv_v,
            )
        )
    return out


def effective_levels(environment: Environment, pad_elevation_m: float) -> list[ProfileLevel] | None:
    """The atmosphere a flight is simulated in, or None for RocketPy's own standard atmosphere.

    A surface wind over the standard atmosphere blends into calm air aloft.
    """
    atmosphere = environment.atmosphere
    wind = environment.surface_wind
    if isinstance(atmosphere, ResolvedProfile):
        levels = atmosphere.levels
    elif wind is not None:
        levels = isa_levels()
    else:
        return None
    return blend_surface_wind(levels, wind, pad_elevation_m) if wind else levels
