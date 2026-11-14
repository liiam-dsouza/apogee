"""Recovery sizing: steady descent rates under each device."""

import contextlib

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.routers.sim import RunState, start_flight
from simcore.mission import Mission
from simcore.mission.models import quantity
from simcore.mission.validation import point_in_polygon
from simcore.recovery import (
    LABELS,
    DeviceDescent,
    FailureMode,
    descent_table,
    failure_modes,
    with_failure,
)
from simcore.recovery.descent import descent_mass_kg
from simcore.results import ResultNotFound, read_record, result_key
from simcore.structures import BayCheck, check_bay

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


class EjectionRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")


class EjectionResponse(BaseModel):
    flight_run: bool = Field(description="The mission's single flight has been run.")
    coast_drag_deceleration_ms2: float | None = Field(
        description="Highest drag deceleration in coast, from that flight.",
        json_schema_extra={"units": "m/s²"},
    )
    bays: list[BayCheck] = Field(description="One per bay, in the mission's order.")


@router.post("/ejection", operation_id="ejectionCharges")
def ejection(body: EjectionRequest, settings: SettingsDep) -> EjectionResponse:
    """Black-powder charge per bay, and whether its pins hold the joint through coast."""
    mission = body.mission
    flight_run, coast = False, None
    if mission.rocket is not None and mission.motor is not None and mission.site is not None:
        with contextlib.suppress(ResultNotFound):
            summary = read_record(
                settings.results_dir, result_key(mission, ascent_only=False)
            ).summary
            flight_run, coast = True, summary.max_coast_drag_deceleration_ms2
    return EjectionResponse(
        flight_run=flight_run,
        coast_drag_deceleration_ms2=coast,
        bays=[check_bay(b, coast) for b in mission.ejection.bays],
    )


class FailuresRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")


class FailureOutcome(BaseModel):
    mode: FailureMode = Field(description="What fails.")
    label: str = Field(description="What fails, in words.")
    devices: list[str] = Field(description="The devices still in the mission.")
    run: RunState = Field(description="The flight of the mission with that failure.")
    landing_speed_ms: float | None = quantity("m/s", "Touchdown speed, once flown.")
    landing_energy_j: float | None = quantity("J", "Touchdown energy, whole rocket as one body.")
    drift_m: float | None = quantity("m", "How far from the pad it lands.")
    landing_lon_lat: tuple[float, float] | None = Field(
        description="Where it lands, [longitude, latitude]."
    )
    outside_boundary: bool | None = Field(
        description="Lands outside the range boundary. None without a boundary or a flight."
    )
    opening_speed_ms: float | None = quantity(
        "m/s", "Speed when the first remaining device opens: the shock it takes."
    )


class FailuresResponse(BaseModel):
    nominal_landing_speed_ms: float | None = quantity(
        "m/s", "Touchdown speed with everything working, if that flight has been run."
    )
    outcomes: list[FailureOutcome] = Field(description="One per failure the recovery can have.")


@router.post(
    "/failures",
    operation_id="recoveryFailures",
    responses={503: {"model": Problem, "description": "No job queue."}},
)
async def failures(
    body: FailuresRequest, queue: QueueDep, settings: SettingsDep
) -> FailuresResponse:
    """Fly the mission with each part of its recovery failed. Starts what isn't stored yet."""
    mission = body.mission
    if mission.rocket is None or mission.motor is None or mission.site is None:
        raise ApiProblem(
            422, "not_ready", "Recovery failures need a rocket, a motor and a launch site"
        )
    nominal = None
    with contextlib.suppress(ResultNotFound):
        landing = read_record(
            settings.results_dir, result_key(mission, ascent_only=False)
        ).summary.landing
        nominal = landing.speed_ms if landing else None
    boundary = mission.site.boundary
    outcomes = []
    for mode in failure_modes(mission):
        failed = with_failure(mission, mode)
        run = await start_flight(failed, False, queue, settings)
        outcome = FailureOutcome(
            mode=mode,
            label=LABELS[mode],
            devices=[d.name for d in failed.recovery.devices],
            run=run,
            landing_speed_ms=None,
            landing_energy_j=None,
            drift_m=None,
            landing_lon_lat=None,
            outside_boundary=None,
            opening_speed_ms=None,
        )
        if run.status == "done":
            s = read_record(settings.results_dir, run.result_id).summary
            if s.landing:
                at = (s.landing.longitude_deg, s.landing.latitude_deg)
                outcome.landing_speed_ms = s.landing.speed_ms
                outcome.landing_energy_j = s.landing.kinetic_energy_j
                outcome.drift_m = s.landing.drift_distance_m
                outcome.landing_lon_lat = at
                outcome.outside_boundary = not point_in_polygon(*at, boundary) if boundary else None
            if s.parachute_events:
                outcome.opening_speed_ms = s.parachute_events[0].speed_ms
        outcomes.append(outcome)
    return FailuresResponse(nominal_landing_speed_ms=nominal, outcomes=outcomes)
