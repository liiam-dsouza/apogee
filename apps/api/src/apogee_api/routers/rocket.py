"""The rocket's drag, as the mission will fly it and as estimated from its shape."""

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep
from apogee_api.problems import ApiProblem, Problem
from simcore.aero.drag import DEFAULT_FIN_THICKNESS_M, model_for, reference_reynolds
from simcore.assets import AssetError
from simcore.mission import Mission
from simcore.mission.models import quantity
from simcore.motors.finder import drag_functions

router = APIRouter(prefix="/api/rocket", tags=["rocket"])

#: Mach numbers the curves are sampled at.
MACHS = [round(float(m), 2) for m in np.arange(0.05, 2.51, 0.05)]


class DragRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")


class DragPoint(BaseModel):
    mach: float = quantity("1", "Mach number.")
    power_off: float = quantity("1", "The mission's power-off CD, multiplier applied.")
    power_on: float = quantity("1", "The mission's power-on CD, multiplier applied.")
    estimate_off: float = quantity("1", "Estimated power-off CD, multiplier applied.")
    estimate_on: float = quantity("1", "Estimated power-on CD, multiplier applied.")
    # The parts of estimate_off: they sum to it.
    friction: float = quantity("1", "Estimated power-off CD from skin friction.")
    nose: float = quantity("1", "Estimated CD from nose pressure drag.")
    tail: float = quantity("1", "Estimated CD from the boat-tail.")
    fins: float = quantity("1", "Estimated CD from fin leading and trailing edges.")
    base: float = quantity("1", "Estimated power-off CD from the base.")


class DragResponse(BaseModel):
    elevation_m: float = quantity(
        "m", "Site elevation the curves are taken at (standard atmosphere); 0 with no site."
    )
    points: list[DragPoint] = Field(description="CD against Mach, every 0.05 to Mach 2.5.")
    notes: list[str] = Field(description="Assumptions behind the estimate, in plain language.")


@router.post(
    "/drag",
    operation_id="rocketDrag",
    responses={
        422: {"model": Problem, "description": "No rocket yet, or a drag table is missing."}
    },
)
def drag(body: DragRequest, store: AssetStoreDep) -> DragResponse:
    """CD against Mach: the curves the mission flies, the estimate, and what makes it up.

    Reynolds number follows Mach through the standard atmosphere at the site,
    which is what a flight sees near the pad.
    """
    mission = body.mission
    rocket = mission.rocket
    if rocket is None:
        raise ApiProblem(422, "not_ready", "Drag needs a rocket")
    try:
        cd_on, cd_off = drag_functions(mission, store)
    except AssetError as e:
        raise ApiProblem(422, "asset_missing", "A drag table is not stored", str(e)) from e
    model = model_for(mission)
    elevation = mission.site.elevation_m if mission.site else 0.0
    k = rocket.drag.multiplier
    points = []
    for mach in MACHS:
        re = reference_reynolds(mach, model.length, elevation)
        off = model.breakdown(mach, re, power_on=False)
        on = model.breakdown(mach, re, power_on=True)
        points.append(
            DragPoint(
                mach=mach,
                power_off=cd_off(mach),
                power_on=cd_on(mach),
                estimate_off=off.total * k,
                estimate_on=on.total * k,
                friction=off.friction * k,
                nose=off.nose * k,
                tail=off.tail * k,
                fins=off.fins * k,
                base=off.base * k,
            )
        )
    notes = [
        f"Fin set {i}: no thickness, so {DEFAULT_FIN_THICKNESS_M * 1000:g} mm is assumed."
        for i, f in enumerate(rocket.fins, start=1)
        if f.thickness_m is None
    ]
    if mission.motor is None:
        notes.append("No motor yet, so power-on drag has no nozzle: it equals power-off.")
    notes.append("Rail buttons and launch lugs are not in the estimate (usually under 2%).")
    return DragResponse(elevation_m=elevation, points=points, notes=notes)
