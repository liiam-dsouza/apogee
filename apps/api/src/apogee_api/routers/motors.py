"""Motor finder: ThrustCurve.org motors that fit the mount, ranked against a target apogee."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api import thrustcurve
from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.routers.assets import AssetInfo, ThrustCurveInfo
from apogee_api.routers.sim import RunState, start_flight
from simcore.constraints.metrics import from_summary
from simcore.constraints.profiles import ProfileError
from simcore.importers.thrust import ThrustCurveError, parse_eng
from simcore.mission import Mission
from simcore.mission.models import GenericMotor, quantity
from simcore.motors import (
    Candidate,
    Estimate,
    Judgement,
    Mount,
    candidate_from_thrustcurve,
    category_target_m,
    drag_functions,
    fits,
    judge,
    mount_from_motor,
    screen,
    with_motor,
)
from simcore.results import read_record

router = APIRouter(prefix="/api/motors", tags=["motors"])

MAX_FLIGHTS = 20


class FinderRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")
    target_apogee_m: float | None = quantity(
        "m", "Apogee to aim for, above the pad. Unset: the category's target.", default=None, gt=0
    )
    mount: Mount | None = Field(
        default=None, description="The motor mount. Unset: the current motor's diameter and length."
    )
    flights: int = Field(
        default=8, ge=0, le=MAX_FLIGHTS, description="How many of the best-screened motors to fly."
    )
    also_fly: list[str] = Field(
        default_factory=list,
        max_length=MAX_FLIGHTS,
        description="ThrustCurve.org motor ids to fly as well, wherever they screened.",
    )
    discontinued: bool = Field(
        default=False, description="Include motors that are out of production."
    )


class Flown(BaseModel):
    apogee_agl_m: float = quantity("m", "Apogee above the pad.")
    rail_exit_velocity_ms: float = quantity("m/s", "Speed off the rail.")
    stability_margin_at_rail_exit_cal: float = quantity("cal", "Stability at rail exit.")
    min_stability_margin_cal: float = quantity("cal", "Lowest stability margin.")
    thrust_to_weight: float = quantity("1", "Thrust to weight.")
    max_mach: float = quantity("1", "Highest Mach number.")


class FinderRow(BaseModel):
    candidate: Candidate = Field(description="The motor.")
    estimate: Estimate = Field(description="The screen's estimate.")
    run: RunState | None = Field(description="Its full flight, if it is being flown.")
    flown: Flown | None = Field(description="What the full flight gives, once done.")
    judgement: Judgement | None = Field(description="The flight against the rules, once done.")
    motor: GenericMotor | None = Field(
        description="The motor section it flies with, to put in the mission."
    )
    asset: AssetInfo | None = Field(description="Its stored thrust curve.")


class FinderResponse(BaseModel):
    target_apogee_m: float = quantity("m", "Apogee aimed for.")
    target_from: Literal["request", "category"] = Field(description="Where the target came from.")
    mount: Mount = Field(description="The mount searched for.")
    catalogue_count: int = Field(description="ThrustCurve.org motors of that diameter.")
    catalogue_fetched_at: float = Field(
        description="When that list was fetched from ThrustCurve.org (Unix seconds)."
    )
    curves_fetched: bool = Field(
        description="False if some curves couldn't be fetched: those motors are only screened."
    )
    rows: list[FinderRow] = Field(
        description=(
            "Every motor that fits: flown ones first (GO, then nearest the target), "
            "then the rest by screened apogee nearest the target."
        )
    )


def _bad_constraints(e: Exception) -> ApiProblem:
    return ApiProblem(422, "bad_constraints", "The constraint settings are wrong", str(e))


def _rank(row: FinderRow, target: float) -> tuple[int, float]:
    if row.flown is not None and row.judgement is not None:
        tier = {"go": 0, "incomplete": 1, "no_go": 2}[row.judgement.verdict]
        return tier, abs(row.flown.apogee_agl_m - target)
    if row.run is not None:
        return 3, abs(row.estimate.apogee_agl_m - target)
    return 4, abs(row.estimate.apogee_agl_m - target)


@router.post(
    "/finder",
    operation_id="findMotors",
    responses={
        422: {"model": Problem, "description": "No rocket, site, target or mount."},
        502: {"model": Problem, "description": "ThrustCurve.org refused the request."},
        503: {
            "model": Problem,
            "description": "ThrustCurve.org unreachable with nothing cached, or no job queue.",
        },
    },
)
async def find_motors(
    body: FinderRequest, queue: QueueDep, store: AssetStoreDep, settings: SettingsDep
) -> FinderResponse:
    """Screen every catalogue motor that fits, and fly the best. Ask again until they land.

    Flights are cached like any other, so asking again only starts what hasn't
    been flown.
    """
    mission = body.mission
    if mission.rocket is None or mission.site is None:
        raise ApiProblem(422, "not_ready", "The motor finder needs a rocket and a launch site")
    mount = body.mount or mount_from_motor(mission, store)
    if mount is None:
        raise ApiProblem(
            422,
            "no_mount",
            "Set the motor mount's diameter and length",
            "There is no motor to take them from.",
        )
    target_from: Literal["request", "category"] = "request"
    target = body.target_apogee_m
    if target is None:
        try:
            target = category_target_m(mission.constraints)
        except ProfileError as e:
            raise _bad_constraints(e) from e
        target_from = "category"
    if target is None:
        raise ApiProblem(
            422,
            "no_target",
            "Set a target apogee",
            "Give one, or choose a competition category with a target on the go/no-go board.",
        )

    catalogue, fetched_at = thrustcurve.search_diameter(
        settings.data_dir, mount.diameter_mm, body.discontinued
    )
    candidates = [
        c for c in map(candidate_from_thrustcurve, catalogue) if c is not None and fits(c, mount)
    ]
    cd_on, cd_off = drag_functions(mission, store)
    rows = [
        FinderRow(
            candidate=c,
            estimate=screen(mission, c, cd_on, cd_off),
            run=None,
            flown=None,
            judgement=None,
            motor=None,
            asset=None,
        )
        for c in candidates
    ]
    rows.sort(key=lambda r: abs(r.estimate.apogee_agl_m - target))
    picked = [r for r in rows[: body.flights]]
    picked += [r for r in rows if r.candidate.motor_id in body.also_fly and r not in picked]

    files, curves_fetched = thrustcurve.curves(
        settings.data_dir, store, [r.candidate.motor_id for r in picked]
    )
    for row in picked:
        c = row.candidate
        if c.motor_id not in files:
            continue  # no .eng on ThrustCurve.org: screened only
        sha, content = files[c.motor_id]
        try:
            curve = parse_eng(content.decode("utf-8", errors="replace"))
        except ThrustCurveError:
            continue
        filename = f"{c.manufacturer}_{c.designation}.eng".replace(" ", "_")
        flying = with_motor(mission, curve, sha, filename, len(content))
        row.motor = flying.motor  # type: ignore[assignment]
        row.asset = AssetInfo(
            sha256=sha,
            kind="thrust_curve",
            filename=filename,
            size=len(content),
            thrust_curve=ThrustCurveInfo(
                designation=curve.designation,
                total_impulse_ns=curve.total_impulse_ns,
                burn_time_s=curve.burn_time_s,
                propellant_mass_kg=curve.propellant_mass_kg,
            ),
        )
        row.run = await start_flight(flying, False, queue, settings)
        if row.run.status != "done":
            continue
        summary = read_record(settings.results_dir, row.run.result_id).summary
        row.flown = Flown.model_validate(summary.model_dump(include=set(Flown.model_fields)))
        try:
            row.judgement = judge(mission.constraints, from_summary(summary))
        except (ProfileError, ValueError) as e:
            raise _bad_constraints(e) from e

    rows.sort(key=lambda r: _rank(r, target))
    return FinderResponse(
        target_apogee_m=target,
        target_from=target_from,
        mount=mount,
        catalogue_count=len(catalogue),
        catalogue_fetched_at=fetched_at,
        curves_fetched=curves_fetched,
        rows=rows,
    )
