"""The metrics constraints are written against, from a flight summary or a campaign row."""

from typing import Any, get_args

from simcore.engine.result import FlightSummary
from simcore.mission.models import Metric

#: name -> (units, label). Keys must match ``Metric``.
METRICS: dict[str, tuple[str, str]] = {
    "apogee_agl_m": ("m", "Apogee above the pad"),
    "rail_exit_velocity_ms": ("m/s", "Rail exit velocity"),
    "stability_margin_at_rail_exit_cal": ("cal", "Stability margin at rail exit"),
    "min_stability_margin_cal": ("cal", "Lowest stability margin"),
    "max_stability_margin_cal": ("cal", "Highest stability margin"),
    "stability_margin_at_launch_pct_length": ("% of length", "Stability margin at launch"),
    "min_stability_margin_pct_length": ("% of length", "Lowest stability margin"),
    "max_stability_margin_pct_length": ("% of length", "Highest stability margin"),
    "thrust_to_weight": ("1", "Thrust to weight"),
    "max_mach": ("1", "Max Mach"),
    "max_acceleration_ms2": ("m/s²", "Max acceleration"),
    "max_dynamic_pressure_pa": ("Pa", "Max dynamic pressure"),
    "landing_speed_ms": ("m/s", "Touchdown speed"),
    "landing_kinetic_energy_j": ("J", "Landing kinetic energy (whole rocket)"),
    "main_deploy_agl_m": ("m", "Main deployment altitude"),
    "drogue_descent_rate_ms": ("m/s", "Descent rate under drogue, at main deployment"),
    "descent_time_s": ("s", "Descent time, apogee to touchdown"),
    "drift_m": ("m", "Drift from the pad"),
    "flight_time_s": ("s", "Flight time"),
}

assert set(METRICS) == set(get_args(Metric)), "METRICS and Metric must list the same names"


def from_summary(summary: FlightSummary) -> dict[str, float]:
    """Every metric a single flight provides (landing metrics only if it landed)."""
    pct = 100 * summary.reference_diameter_m / summary.rocket_length_m  # calibers -> % of length
    values = {
        "apogee_agl_m": summary.apogee_agl_m,
        "rail_exit_velocity_ms": summary.rail_exit_velocity_ms,
        "stability_margin_at_rail_exit_cal": summary.stability_margin_at_rail_exit_cal,
        "min_stability_margin_cal": summary.min_stability_margin_cal,
        "max_stability_margin_cal": summary.max_stability_margin_cal,
        "stability_margin_at_launch_pct_length": summary.stability_margin_at_launch_cal * pct,
        "min_stability_margin_pct_length": summary.min_stability_margin_cal * pct,
        "max_stability_margin_pct_length": summary.max_stability_margin_cal * pct,
        "thrust_to_weight": summary.thrust_to_weight,
        "max_mach": summary.max_mach,
        "max_acceleration_ms2": summary.max_acceleration_ms2,
        "max_dynamic_pressure_pa": summary.max_dynamic_pressure_pa,
    }
    if summary.main_deploy_agl_m is not None:
        values["main_deploy_agl_m"] = summary.main_deploy_agl_m
    if summary.drogue_descent_rate_ms is not None:
        values["drogue_descent_rate_ms"] = summary.drogue_descent_rate_ms
    if summary.landing:
        values |= {
            "landing_speed_ms": summary.landing.speed_ms,
            "landing_kinetic_energy_j": summary.landing.kinetic_energy_j,
            "descent_time_s": summary.landing.flight_time_s - summary.apogee_time_s,
            "drift_m": summary.landing.drift_distance_m,
            "flight_time_s": summary.landing.flight_time_s,
        }
    return values


def from_row(row: dict[str, Any]) -> dict[str, float]:
    """The metrics a Monte Carlo sample recorded (older campaigns may lack some)."""
    return {k: row[k] for k in METRICS if row.get(k) is not None}
