"""One Monte Carlo sample as a mission: the nominal mission with its inputs moved.

A sample is ordinary mission data (plus a motor scale the mission has no field
for), flown by the same deterministic engine as a single flight.
"""

from typing import Any

from simcore.engine.build import MotorScale
from simcore.mission.models import Environment, Mission, ResolvedProfile
from simcore.montecarlo.sampling import Draw, layer_rng, perturb_wind
from simcore.weather.blend import effective_levels

#: Floors that keep a far-tail draw physical (a 6-sigma burn time is not negative).
_MIN_SCALE = 0.2


def sample_mission(mission: Mission, draw: Draw) -> tuple[Mission, MotorScale, dict[str, Any]]:
    """The mission for one sample, its motor scale, and the inputs actually used."""
    p = mission.monte_carlo.parameters
    z = draw.scalars

    def dev(name: str) -> float:
        spread = getattr(p, name)
        return spread.sigma * z[name] if spread.enabled else 0.0

    m = mission.model_copy(deep=True)
    assert m.rocket is not None and m.site is not None
    inputs: dict[str, Any] = {}

    scale = MotorScale(
        impulse=max(_MIN_SCALE, 1 + dev("total_impulse")),
        burn_time=max(_MIN_SCALE, 1 + dev("burn_time")),
    )
    inputs["impulse_scale"] = scale.impulse
    inputs["burn_time_scale"] = scale.burn_time

    m.rocket.dry_mass_kg *= max(_MIN_SCALE, 1 + dev("dry_mass"))
    m.rocket.dry_cg_m += dev("dry_cg")
    m.rocket.drag.multiplier *= max(_MIN_SCALE, 1 + dev("drag"))
    inputs |= {
        "dry_mass_kg": m.rocket.dry_mass_kg,
        "dry_cg_m": m.rocket.dry_cg_m,
        "drag_multiplier": m.rocket.drag.multiplier,
    }

    m.site.inclination_deg = min(90.0, max(0.0, m.site.inclination_deg + dev("rail_inclination")))
    m.site.heading_deg = (m.site.heading_deg + dev("rail_heading")) % 360
    inputs |= {"inclination_deg": m.site.inclination_deg, "heading_deg": m.site.heading_deg}

    for i, device in enumerate(m.recovery.devices):
        if p.parachute_cd_s.enabled:
            device.cd_s_m2 *= max(_MIN_SCALE, 1 + p.parachute_cd_s.sigma * draw.cd_s[i])
        if p.deployment_lag.enabled:
            device.lag_s = max(0.0, device.lag_s + p.deployment_lag.sigma * draw.lag[i])
        if p.deploy_altitude.enabled and device.trigger.kind == "altitude_agl":
            device.trigger.altitude_m = max(
                1.0, device.trigger.altitude_m + p.deploy_altitude.sigma * draw.deploy_altitude[i]
            )
        inputs[f"{device.name}_cd_s_m2"] = device.cd_s_m2
        inputs[f"{device.name}_lag_s"] = device.lag_s
        if device.trigger.kind == "altitude_agl":
            inputs[f"{device.name}_deploy_altitude_m"] = device.trigger.altitude_m

    # The wind: the profile actually flown (any surface blend applied), moved coherently.
    # The standard atmosphere has no wind and no forecast error to sample.
    levels = effective_levels(mission.environment, m.site.elevation_m)
    speed_scale = max(0.0, 1 + dev("wind_speed"))
    direction_offset = dev("wind_direction")
    if levels is not None:
        flown = perturb_wind(
            levels,
            m.site.elevation_m,
            speed_scale=speed_scale,
            direction_offset_deg=direction_offset,
            layer_sigma_ms=p.wind_layers.sigma if p.wind_layers.enabled else 0.0,
            correlation_m=mission.monte_carlo.wind_correlation_m,
            rng=layer_rng(mission.monte_carlo, draw.index),
        )
        m.environment = Environment(
            atmosphere=ResolvedProfile(
                kind="profile", source=f"Monte Carlo sample {draw.index}", levels=flown
            )
        )
        inputs |= {"wind_speed_scale": speed_scale, "wind_direction_offset_deg": direction_offset}
    return m, scale, inputs
