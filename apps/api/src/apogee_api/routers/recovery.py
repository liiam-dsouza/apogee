"""Recovery sizing: steady descent rates under each device."""

import contextlib

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import SettingsDep
from apogee_api.problems import ApiProblem, Problem
from simcore.mission import Mission
from simcore.recovery import DeviceDescent, descent_table
from simcore.recovery.descent import descent_mass_kg
from simcore.results import ResultNotFound, read_record, result_key

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


class DescentRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")
    target_rates_ms: dict[str, float] = Field(
        default_factory=dict,
        description="Wanted descent rate per device name, at the bottom of its stretch.",
    )


class DescentResponse(BaseModel):
    mass_kg: float = Field(
        description="Rocket and burnt-out motor.", json_schema_extra={"units": "kg"}
    )
    apogee_agl_m: float | None = Field(
        description="From this mission's single flight, if it has been run.",
        json_schema_extra={"units": "m"},
    )
    devices: list[DeviceDescent] = Field(description="Highest first.")


@router.post(
    "/descent",
    operation_id="descentRates",
    responses={422: {"model": Problem, "description": "No rocket, motor or site yet."}},
)
def descent(body: DescentRequest, settings: SettingsDep) -> DescentResponse:
    """Steady descent rate under each device, where it opens and where the next takes over."""
    mission = body.mission
    if mission.rocket is None or mission.motor is None or mission.site is None:
        raise ApiProblem(422, "not_ready", "Descent rates need a rocket, a motor and a launch site")
    apogee = None
    with contextlib.suppress(ResultNotFound):
        apogee = read_record(
            settings.results_dir, result_key(mission, ascent_only=False)
        ).summary.apogee_agl_m
    return DescentResponse(
        mass_kg=descent_mass_kg(mission),
        apogee_agl_m=apogee,
        devices=descent_table(mission, apogee, body.target_rates_ms),
    )
