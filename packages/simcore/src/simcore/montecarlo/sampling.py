"""Turning a campaign definition into per-sample inputs.

Every scalar input is drawn by Latin Hypercube sampling: for the same number
of flights it covers the input space far more evenly than independent draws.
The LHS matrix depends only on the seed and the campaign's dimensions, so any
worker can rebuild it and take its own rows: samples are reproducible and
independent of how the campaign is split into jobs.

The wind is perturbed coherently, not level by level:

1. a speed multiplier and a direction offset shared by every height (the
   forecast's overall error), drawn in the hypercube like the other inputs;
2. a smaller noise per component that is correlated in height: an AR(1)
   process with correlation length ``wind_correlation_m``, so neighbouring
   layers move together.

Independent per-level noise would make physically absurd shear, and the
errors would cancel on the way up and shrink the landing ellipse.
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm, qmc

from simcore.mission.models import Mission, MonteCarlo, ProfileLevel
from simcore.weather.wind import wind_components


@dataclass(frozen=True)
class Draw:
    """Standard-normal deviates for one sample, keyed by input."""

    index: int
    scalars: dict[str, float]
    #: Per recovery device, in mission order.
    cd_s: list[float]
    lag: list[float]
    deploy_altitude: list[float]


_SCALARS = (
    "total_impulse",
    "burn_time",
    "dry_mass",
    "dry_cg",
    "drag",
    "rail_inclination",
    "rail_heading",
    "wind_speed",
    "wind_direction",
)


def _dimensions(mission: Mission) -> list[str]:
    params = mission.monte_carlo.parameters
    dims = [name for name in _SCALARS if getattr(params, name).enabled]
    for i, _ in enumerate(mission.recovery.devices):
        dims += [f"cd_s:{i}", f"lag:{i}", f"deploy_altitude:{i}"]
    return dims


def draws(mission: Mission, indices: range | list[int]) -> list[Draw]:
    """The deviates for these sample indices (0-based) of the mission's campaign."""
    mc = mission.monte_carlo
    dims = _dimensions(mission)
    if dims:
        unit = qmc.LatinHypercube(d=len(dims), seed=mc.seed).random(mc.samples)
        # Keep away from 0 and 1, where the normal's inverse is infinite.
        z = norm.ppf(np.clip(unit, 1e-9, 1 - 1e-9))
    else:
        z = np.zeros((mc.samples, 0))
    out = []
    n_devices = len(mission.recovery.devices)
    for i in indices:
        row = dict(zip(dims, (float(v) for v in z[i]), strict=True))
        out.append(
            Draw(
                index=i,
                scalars={k: row.get(k, 0.0) for k in _SCALARS},
                cd_s=[row[f"cd_s:{d}"] for d in range(n_devices)],
                lag=[row[f"lag:{d}"] for d in range(n_devices)],
                deploy_altitude=[row[f"deploy_altitude:{d}"] for d in range(n_devices)],
            )
        )
    return out


def perturb_wind(
    levels: list[ProfileLevel],
    pad_elevation_m: float,
    *,
    speed_scale: float,
    direction_offset_deg: float,
    layer_sigma_ms: float,
    correlation_m: float,
    rng: np.random.Generator,
) -> list[ProfileLevel]:
    """``levels`` with a coherent wind error applied. Pressure and temperature are untouched."""
    out = []
    noise_u = noise_v = 0.0
    previous = None
    for lv in levels:
        speed = math.hypot(lv.wind_u_ms, lv.wind_v_ms) * speed_scale
        from_deg = math.degrees(math.atan2(-lv.wind_u_ms, -lv.wind_v_ms)) + direction_offset_deg
        u, v = wind_components(speed, from_deg)
        if layer_sigma_ms > 0 and lv.altitude_m >= pad_elevation_m:
            # AR(1) in height: correlation exp(-dz / L) between neighbouring levels.
            rho = 0.0 if previous is None else math.exp(-(lv.altitude_m - previous) / correlation_m)
            spread = layer_sigma_ms * math.sqrt(1 - rho * rho)
            noise_u = rho * noise_u + spread * rng.standard_normal()
            noise_v = rho * noise_v + spread * rng.standard_normal()
            previous = lv.altitude_m
            u, v = u + noise_u, v + noise_v
        out.append(lv.model_copy(update={"wind_u_ms": u, "wind_v_ms": v}))
    return out


def layer_rng(mc: MonteCarlo, index: int) -> np.random.Generator:
    """The wind-noise generator for one sample, independent of every other sample."""
    return np.random.default_rng([mc.seed, index])
