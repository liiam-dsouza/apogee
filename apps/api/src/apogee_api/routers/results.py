from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from apogee_api.deps import SettingsDep
from apogee_api.problems import ApiProblem, Problem
from simcore.mission.diff import Difference, diff_missions
from simcore.results import (
    FlightPath,
    ResultNotFound,
    ResultRecord,
    Series,
    list_records,
    read_flown_mission,
    read_path,
    read_record,
    read_series,
)

router = APIRouter(prefix="/api/results", tags=["results"])

NOT_FOUND = {404: {"model": Problem, "description": "No result with that id."}}


@router.get("/{result_id}", operation_id="getResult", responses=NOT_FOUND)
def get_result(result_id: str, settings: SettingsDep) -> ResultRecord:
    """Summary, provenance and available channels for a result."""
    try:
        return read_record(settings.results_dir, result_id)
    except ResultNotFound as e:
        raise ApiProblem(404, "result_not_found", "Result not found") from e


@router.get(
    "/{result_id}/series",
    operation_id="getResultSeries",
    responses={**NOT_FOUND, 422: {"model": Problem, "description": "Unknown channel."}},
)
def get_series(
    result_id: str,
    settings: SettingsDep,
    vars: Annotated[str, Query(description="Comma-separated channel names.")],
    max_points: Annotated[int, Query(ge=10, le=100_000)] = 2000,
) -> list[Series]:
    """Trajectory channels, downsampled with LTTB to at most ``max_points`` each."""
    names = [v.strip() for v in vars.split(",") if v.strip()]
    try:
        return read_series(settings.results_dir, result_id, names, max_points=max_points)
    except ResultNotFound as e:
        raise ApiProblem(404, "result_not_found", "Result not found") from e
    except KeyError as e:
        raise ApiProblem(422, "unknown_channel", str(e.args[0])) from e


@router.get("/{result_id}/path", operation_id="getResultPath", responses={**NOT_FOUND})
def get_path(
    result_id: str,
    settings: SettingsDep,
    max_points: Annotated[int, Query(ge=10, le=20_000)] = 1500,
) -> FlightPath:
    """The trajectory in 3D: east, north, altitude and speed at the same instants."""
    try:
        return read_path(settings.results_dir, result_id, max_points=max_points)
    except ResultNotFound as e:
        raise ApiProblem(404, "result_not_found", "Result not found") from e


@router.get("", operation_id="listResults")
def list_results(
    settings: SettingsDep,
    mission_id: Annotated[str | None, Query(description="Only this mission's flights.")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[ResultRecord]:
    """Stored single flights, newest first."""
    return list_records(settings.results_dir, mission_id=mission_id, limit=limit)


#: Mission sections a single flight doesn't depend on (also left out of its cache key).
FLIGHT_IRRELEVANT = {"monte_carlo", "constraints"}


class Comparison(BaseModel):
    a: ResultRecord = Field(description="The first run.")
    b: ResultRecord = Field(description="The second run.")
    settings_known: bool = Field(
        description="Whether both runs recorded their mission (older runs didn't)."
    )
    differences: list[Difference] = Field(
        description="Mission settings that differ, a to b (campaign settings and rules left out)."
    )


@router.get("/compare/{a}/{b}", operation_id="compareResults", responses=NOT_FOUND)
def compare_results(a: str, b: str, settings: SettingsDep) -> Comparison:
    """Two runs, and what differs between the missions that produced them."""
    try:
        ra, rb = read_record(settings.results_dir, a), read_record(settings.results_dir, b)
        ma = read_flown_mission(settings.results_dir, a)
        mb = read_flown_mission(settings.results_dir, b)
    except ResultNotFound as e:
        raise ApiProblem(404, "result_not_found", "Result not found") from e
    if ma is None or mb is None:
        return Comparison(a=ra, b=rb, settings_known=False, differences=[])
    # Campaign settings and rules never change a single flight: not why it differs.
    flight_only = [{k: v for k, v in m.items() if k not in FLIGHT_IRRELEVANT} for m in (ma, mb)]
    return Comparison(a=ra, b=rb, settings_known=True, differences=diff_missions(*flight_only))
