"""Running samples, and summarising what they did.

A campaign is split into chunks of samples so several workers share it; each
chunk is a list of plain rows (sample inputs and outputs). The summary is
recomputed from whatever rows exist, so a campaign can be read while it runs.
"""

import math
from typing import Any

import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import chi2

from simcore.assets import AssetStore
from simcore.constraints.metrics import from_summary
from simcore.engine import run_flight
from simcore.mission.models import Mission, quantity
from simcore.mission.validation import point_in_polygon
from simcore.montecarlo.perturb import sample_mission
from simcore.montecarlo.sampling import draws

#: Outputs recorded per sample: name -> (units, label).
OUTPUTS: dict[str, tuple[str, str]] = {
    "apogee_agl_m": ("m", "Apogee above the pad"),
    "apogee_time_s": ("s", "Time to apogee"),
    "rail_exit_velocity_ms": ("m/s", "Rail exit velocity"),
    "stability_margin_at_rail_exit_cal": ("cal", "Stability margin at rail exit"),
    "min_stability_margin_cal": ("cal", "Lowest stability margin"),
    "max_mach": ("1", "Max Mach"),
    "max_dynamic_pressure_pa": ("Pa", "Max dynamic pressure"),
    "max_acceleration_ms2": ("m/s²", "Max acceleration"),
    "thrust_to_weight": ("1", "Thrust to weight"),
    "main_deploy_agl_m": ("m", "Main deployment altitude"),
    "drogue_descent_rate_ms": ("m/s", "Descent rate under drogue, at main deployment"),
    "landing_east_m": ("m", "Landing east of the pad"),
    "landing_north_m": ("m", "Landing north of the pad"),
    "landing_latitude_deg": ("deg", "Landing latitude"),
    "landing_longitude_deg": ("deg", "Landing longitude"),
    "drift_m": ("m", "Drift from the pad"),
    "landing_speed_ms": ("m/s", "Touchdown speed"),
    "landing_kinetic_energy_j": ("J", "Landing kinetic energy (whole rocket)"),
    "descent_time_s": ("s", "Descent time, apogee to touchdown"),
    "flight_time_s": ("s", "Flight time"),
}

#: Probability inside each ellipse: the 1, 2 and 3 sigma levels of a 1-D normal.
ELLIPSE_LEVELS = (0.6827, 0.9545, 0.9973)


def run_samples(mission: Mission, assets: AssetStore, indices: list[int]) -> list[dict[str, Any]]:
    """Fly these samples. A sample that fails is recorded with its error, not raised."""
    rows = []
    for draw in draws(mission, indices):
        flown, motor_scale, inputs = sample_mission(mission, draw)
        row: dict[str, Any] = {"index": draw.index, "error": None, **inputs}
        try:
            s = run_flight(flown, assets, motor_scale=motor_scale).summary
        except Exception as e:  # one bad draw must not lose the chunk
            row["error"] = f"{type(e).__name__}: {e}"
            rows.append(row)
            continue
        # Every constraint metric, so any rule can be judged on the campaign.
        row |= from_summary(s)
        if s.landing:
            row |= {
                "landing_east_m": s.landing.east_m,
                "landing_north_m": s.landing.north_m,
                "landing_latitude_deg": s.landing.latitude_deg,
                "landing_longitude_deg": s.landing.longitude_deg,
            }
        rows.append(row)
    return rows


class Stat(BaseModel):
    name: str = Field(description="Output name.")
    label: str = Field(description="What it is.")
    units: str = Field(description="Units.")
    mean: float = Field(description="Mean.")
    std: float = Field(description="Standard deviation.")
    p5: float = Field(description="5th percentile.")
    p50: float = Field(description="Median.")
    p95: float = Field(description="95th percentile.")
    min: float = Field(description="Smallest.")
    max: float = Field(description="Largest.")


class Ellipse(BaseModel):
    probability: float = Field(description="Share of landings expected inside, 0 to 1.")
    semi_major_m: float = quantity("m", "Semi-major axis.")
    semi_minor_m: float = quantity("m", "Semi-minor axis.")
    bearing_deg: float = quantity("deg", "Direction of the major axis, clockwise from north.")
    polygon: list[tuple[float, float]] = Field(
        description="The ellipse as [longitude, latitude] points, for drawing."
    )


class Probability(BaseModel):
    p: float = Field(description="Estimated probability, 0 to 1.")
    count: int = Field(description="Samples where it happened.")
    of: int = Field(description="Samples it was judged over.")
    upper_95: float = Field(
        description="Upper end of the 95% confidence interval (Wilson). With few samples this "
        "is what to compare against a limit, not p."
    )


class CampaignSummary(BaseModel):
    done: int = Field(description="Samples flown successfully.")
    failed: int = Field(description="Samples whose simulation failed.")
    stats: list[Stat] = Field(description="Distribution of each output.")
    landing_center_east_m: float | None = quantity("m", "Mean landing point, east of the pad.")
    landing_center_north_m: float | None = quantity("m", "Mean landing point, north of the pad.")
    ellipses: list[Ellipse] = Field(description="Landing ellipses fitted from the covariance.")
    outside_boundary: Probability | None = Field(
        description="Landing outside the range boundary, if the site has one."
    )
    in_hazard: Probability | None = Field(
        description="Landing inside any hazard zone, if the site has any."
    )
    apogee_mean_standard_error_m: float | None = quantity(
        "m", "Standard error of the mean apogee: how settled the mean is."
    )


def wilson_upper(count: int, n: int, z: float = 1.96) -> float:
    """Upper end of the Wilson score interval for a binomial proportion."""
    if n == 0:
        return 1.0
    p = count / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z * z / n))


def _probability(hits: int, n: int) -> Probability:
    return Probability(p=hits / n if n else 0.0, count=hits, of=n, upper_95=wilson_upper(hits, n))


def _ellipses(
    east: np.ndarray, north: np.ndarray, lat0: float, lon0: float
) -> tuple[float, float, list[Ellipse]]:
    ce, cn = float(east.mean()), float(north.mean())
    if len(east) < 3:
        return ce, cn, []
    cov = np.cov(np.vstack([east, north]))
    values, vectors = np.linalg.eigh(cov)  # ascending
    major = vectors[:, 1]
    bearing = math.degrees(math.atan2(major[0], major[1])) % 180
    out = []
    metres_per_deg_lat = 111_320.0
    metres_per_deg_lon = metres_per_deg_lat * math.cos(math.radians(lat0))
    for p in ELLIPSE_LEVELS:
        k = math.sqrt(chi2.ppf(p, 2))
        a, b = k * math.sqrt(max(values[1], 0)), k * math.sqrt(max(values[0], 0))
        polygon = []
        for t in np.linspace(0, 2 * math.pi, 73)[:-1]:
            offset = a * math.cos(t) * vectors[:, 1] + b * math.sin(t) * vectors[:, 0]
            e, n = ce + offset[0], cn + offset[1]
            polygon.append((lon0 + e / metres_per_deg_lon, lat0 + n / metres_per_deg_lat))
        out.append(
            Ellipse(
                probability=p, semi_major_m=a, semi_minor_m=b, bearing_deg=bearing, polygon=polygon
            )
        )
    return ce, cn, out


def summarize(mission: Mission, rows: list[dict[str, Any]]) -> CampaignSummary:
    """Statistics over the rows so far."""
    ok = [r for r in rows if r.get("error") is None]
    stats = []
    for name, (units, label) in OUTPUTS.items():
        values = np.array([r[name] for r in ok if r.get(name) is not None], dtype=float)
        if len(values) == 0:
            continue
        p5, p50, p95 = np.percentile(values, [5, 50, 95])
        stats.append(
            Stat(
                name=name,
                label=label,
                units=units,
                mean=float(values.mean()),
                std=float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                p5=float(p5),
                p50=float(p50),
                p95=float(p95),
                min=float(values.min()),
                max=float(values.max()),
            )
        )

    landed = [r for r in ok if r.get("landing_east_m") is not None]
    site = mission.site
    ce = cn = None
    ellipses: list[Ellipse] = []
    outside = hazard = None
    if landed and site:
        east = np.array([r["landing_east_m"] for r in landed])
        north = np.array([r["landing_north_m"] for r in landed])
        ce, cn, ellipses = _ellipses(east, north, site.latitude_deg, site.longitude_deg)
        points = [(r["landing_longitude_deg"], r["landing_latitude_deg"]) for r in landed]
        if site.boundary:
            boundary = site.boundary
            out_count = sum(not point_in_polygon(lon, lat, boundary) for lon, lat in points)
            outside = _probability(out_count, len(points))
        if site.hazards:
            hazards = site.hazards
            in_count = sum(
                any(point_in_polygon(lon, lat, h) for h in hazards) for lon, lat in points
            )
            hazard = _probability(in_count, len(points))

    apogees = [r["apogee_agl_m"] for r in ok]
    sem = float(np.std(apogees, ddof=1) / math.sqrt(len(apogees))) if len(apogees) > 1 else None
    return CampaignSummary(
        done=len(ok),
        failed=len(rows) - len(ok),
        stats=stats,
        landing_center_east_m=ce,
        landing_center_north_m=cn,
        ellipses=ellipses,
        outside_boundary=outside,
        in_hazard=hazard,
        apogee_mean_standard_error_m=sem,
    )
