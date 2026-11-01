from typing import Annotated

from fastapi import APIRouter, Query

from apogee_api.deps import SettingsDep
from apogee_api.problems import ApiProblem, Problem
from simcore.results import ResultNotFound, ResultRecord, Series, read_record, read_series

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
