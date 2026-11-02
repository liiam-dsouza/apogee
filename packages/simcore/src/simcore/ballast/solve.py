"""The ballast that puts apogee on target, and everything it changes.

Apogee falls monotonically with added mass over any sane range, so the solve
is a one-dimensional root find (Brent's method) on ascent-only flights. The
answer is rounded to the plates the team has, then checked: a full flight and
a small Monte Carlo at that mass, judged on the mission's rules. The number is
never returned without that report.
"""

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field
from scipy.optimize import brentq

from simcore.assets import AssetStore
from simcore.ballast.mass import with_ballast
from simcore.constraints import Board, board, from_row, from_summary, get_profile
from simcore.engine import run_flight
from simcore.mission.models import Constraint, ConstraintSettings, Mission, quantity
from simcore.montecarlo import run_samples

#: Checks used when the mission has no rules of its own: the brief's list.
BUILT_IN_CHECKS = [
    Constraint(
        id="rail_exit_stability",
        label="Stability margin at rail exit",
        metric="stability_margin_at_rail_exit_cal",
        min=1.5,
        reference="Built-in check",
    ),
    Constraint(
        id="rail_exit_velocity",
        label="Rail exit velocity",
        metric="rail_exit_velocity_ms",
        min=20,
        reference="Built-in check",
    ),
    Constraint(
        id="thrust_to_weight",
        label="Thrust to weight",
        metric="thrust_to_weight",
        min=5,
        reference="Built-in check",
    ),
    Constraint(
        id="landing_speed",
        label="Touchdown speed",
        metric="landing_speed_ms",
        max=11,
        reference="Built-in check",
    ),
]


class CurvePoint(BaseModel):
    mass_kg: float = quantity("kg", "Ballast added.")
    apogee_agl_m: float = quantity("m", "Nominal apogee with it.")


class BallastSolution(BaseModel):
    status: Literal["ok", "too_low", "too_high"] = Field(
        description=(
            "ok: solved. too_low: apogee is under the target even with no ballast. "
            "too_high: still over it with the bay full."
        )
    )
    target_apogee_m: float = quantity("m", "The target, above the pad.")
    target_source: str = Field(description="Where the target came from.")
    exact_kg: float | None = quantity("kg", "Mass that hits the target exactly.")
    recommended_kg: float | None = quantity("kg", "Rounded to the increment.")
    increments: int | None = Field(description="How many increments that is.")
    increment_kg: float = quantity("kg", "One increment.")
    apogee_agl_m: float | None = quantity("m", "Nominal apogee at the recommended mass.")
    apogee_p5_m: float | None = quantity("m", "5th percentile of the Monte Carlo apogee.")
    apogee_p95_m: float | None = quantity("m", "95th percentile of the Monte Carlo apogee.")
    samples: int = Field(description="Monte Carlo flights at the recommended mass.")
    gradient_m_per_100g: float | None = quantity("m", "Apogee change per 100 g added, locally.")
    curve: list[CurvePoint] = Field(description="Every nominal flight the solve flew.")
    report: Board | None = Field(description="Every rule, judged at the recommended mass.")
    built_in_checks: bool = Field(description="True if the mission had no rules of its own.")


def target_for(mission: Mission) -> tuple[float, str]:
    if mission.ballast.target_apogee_m is not None:
        return mission.ballast.target_apogee_m, "the mission's ballast target"
    c = mission.constraints
    if c.profile and c.category:
        profile = get_profile(c.profile)
        category = next((x for x in profile.categories if x.id == c.category), None)
        if category and category.apogee_target_m:
            return category.apogee_target_m, f"{profile.name}, {category.name}"
    raise ValueError("set ballast.target_apogee_m, or choose a competition category")


def solve(mission: Mission, assets: AssetStore, *, samples: int = 100) -> BallastSolution:
    """Solve for ballast, then check the recommendation. Slow: about ``samples`` + 10 flights."""
    target, source = target_for(mission)
    b = mission.ballast
    if b.position_m is None:
        raise ValueError("set ballast.position_m, the bay's position")
    curve: dict[float, float] = {}

    def apogee(mass: float) -> float:
        if mass not in curve:
            flown = with_ballast(mission, mass)
            curve[mass] = run_flight(flown, assets, terminate_on_apogee=True).summary.apogee_agl_m
        return curve[mass]

    def points() -> list[CurvePoint]:
        return [CurvePoint(mass_kg=m, apogee_agl_m=a) for m, a in sorted(curve.items())]

    base = dict(target_apogee_m=target, target_source=source, increment_kg=b.increment_kg)
    lo, hi = apogee(0.0) - target, apogee(b.max_kg) - target
    if lo < 0 or hi > 0:
        # Fill in the curve so the UI can show how far off the target is.
        for m in np.linspace(0, b.max_kg, 5)[1:-1]:
            apogee(float(m))
        return BallastSolution(
            status="too_low" if lo < 0 else "too_high",
            exact_kg=None,
            recommended_kg=None,
            increments=None,
            apogee_agl_m=None,
            apogee_p5_m=None,
            apogee_p95_m=None,
            samples=0,
            gradient_m_per_100g=None,
            curve=points(),
            report=None,
            built_in_checks=False,
            **base,
        )

    exact = float(brentq(lambda m: apogee(m) - target, 0.0, b.max_kg, xtol=0.005, rtol=1e-4))
    n = round(exact / b.increment_kg)
    recommended = min(n * b.increment_kg, b.max_kg)
    step = min(0.1, b.max_kg - recommended) or -0.1
    gradient = (apogee(recommended + step) - apogee(recommended)) / step * 0.1

    flown = with_ballast(mission, recommended)
    nominal = run_flight(flown, assets).summary
    flown.monte_carlo.samples = max(samples, 10)
    rows = [r for r in run_samples(flown, assets, list(range(samples))) if r["error"] is None]
    apogees = [r["apogee_agl_m"] for r in rows]

    own_rules = bool(mission.constraints.profile or mission.constraints.additional)
    settings = mission.constraints if own_rules else ConstraintSettings(additional=BUILT_IN_CHECKS)
    report = board(settings, from_summary(nominal), [from_row(r) for r in rows])
    return BallastSolution(
        status="ok",
        exact_kg=exact,
        recommended_kg=recommended,
        increments=n,
        apogee_agl_m=nominal.apogee_agl_m,
        apogee_p5_m=float(np.quantile(apogees, 0.05)) if apogees else None,
        apogee_p95_m=float(np.quantile(apogees, 0.95)) if apogees else None,
        samples=len(rows),
        gradient_m_per_100g=gradient if math.isfinite(gradient) else None,
        curve=points(),
        report=report,
        built_in_checks=not own_rules,
        **base,
    )
