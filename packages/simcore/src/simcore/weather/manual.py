"""A hand-entered wind table resolved into a full profile.

Pressure and temperature come from the standard atmosphere, shifted to match
the pad's measured temperature and station pressure when they are given:
temperature by a constant offset, pressure by a constant ratio. That keeps
the standard lapse rate and is good to about 1% in density through the
troposphere on an ordinary day. Above the top entered level the wind is held
constant, up to 20 km, so a rocket flying higher than the briefing reached
does not meet a calm it was never told about.
"""

from simcore.mission.models import ManualProfile, ProfileLevel
from simcore.weather.isa import isa_pressure_temperature
from simcore.weather.wind import wind_components

#: Highest level written; matches the forecasts' top.
TOP_M = 20_000.0
#: Spacing of the levels added above the top entered height.
STEP_ABOVE_M = 500.0


def manual_levels(profile: ManualProfile, pad_elevation_m: float) -> list[ProfileLevel]:
    """Levels from the pad to 20 km above sea level, for ``profile``."""
    p_isa_pad, t_isa_pad = isa_pressure_temperature(pad_elevation_m)
    dt = (profile.surface_temperature_k - t_isa_pad) if profile.surface_temperature_k else 0.0
    ratio = (profile.surface_pressure_pa / p_isa_pad) if profile.surface_pressure_pa else 1.0

    winds = [
        (pad_elevation_m + lv.height_m, *wind_components(lv.speed_ms, lv.direction_deg))
        for lv in profile.levels
    ]
    # The wind at the pad is the lowest entry's, if none was entered at 0 m.
    if winds[0][0] > pad_elevation_m:
        winds.insert(0, (pad_elevation_m, winds[0][1], winds[0][2]))
    top, u_top, v_top = winds[-1]
    altitude = top + STEP_ABOVE_M
    while altitude < max(TOP_M, top + STEP_ABOVE_M):
        winds.append((altitude, u_top, v_top))
        altitude += STEP_ABOVE_M
    if winds[-1][0] < TOP_M:
        winds.append((TOP_M, u_top, v_top))

    levels = []
    for alt, u, v in winds:
        p, t = isa_pressure_temperature(min(alt, TOP_M))
        levels.append(
            ProfileLevel(
                altitude_m=alt,
                pressure_pa=p * ratio,
                temperature_k=t + dt,
                wind_u_ms=u,
                wind_v_ms=v,
            )
        )
    return levels
