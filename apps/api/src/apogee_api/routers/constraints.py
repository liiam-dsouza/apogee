"""Competition profiles and the go/no-go board.

The board is judged on the mission exactly as sent: its single flight and its
campaign are found by their cache keys, so a result for a different version
of the mission is never used by mistake.
"""

import contextlib

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import SettingsDep
from apogee_api.problems import ApiProblem, Problem
from simcore.constraints import (
    Board,
    Profile,
    ProfileError,
    board,
    from_row,
    from_summary,
    load_profiles,
)
from simcore.mission import Mission
from simcore.montecarlo.store import CampaignStore, campaign_key
from simcore.results import ResultNotFound, read_record, result_key

router = APIRouter(prefix="/api", tags=["constraints"])


@router.get("/profiles", operation_id="listProfiles")
def list_profiles() -> list[Profile]:
    """Every competition profile, with its rules."""
    return list(load_profiles().values())


class BoardRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")


class FlightBasis(BaseModel):
    result_id: str = Field(description="The single flight's result id for this mission.")
    available: bool = Field(description="Whether that flight has been run.")


class CampaignBasis(BaseModel):
    campaign_id: str = Field(description="The campaign id for this mission.")
    samples: int = Field(description="Samples in the campaign.")
    samples_done: int = Field(description="Samples finished so far (0 if never run).")


class BoardResponse(BaseModel):
    board: Board = Field(description="Every rule, judged.")
    flight: FlightBasis = Field(description="The single flight it is based on.")
    campaign: CampaignBasis = Field(description="The campaign it is based on.")


@router.post(
    "/constraints/board",
    operation_id="goNoGoBoard",
    responses={422: {"model": Problem, "description": "The constraint settings are wrong."}},
)
def go_no_go(body: BoardRequest, settings: SettingsDep) -> BoardResponse:
    """Judge the mission's rules on its single flight and its Monte Carlo campaign."""
    mission = body.mission
    rid = result_key(mission, ascent_only=False)
    nominal = None
    with contextlib.suppress(ResultNotFound):
        nominal = from_summary(read_record(settings.results_dir, rid).summary)

    store = CampaignStore(settings.data_dir / "campaigns")
    cid = campaign_key(mission)
    samples = None
    done = 0
    if store.exists(cid):
        rows = store.rows(cid)
        done = len(rows)
        samples = [from_row(r) for r in rows if r.get("error") is None]
    try:
        judged = board(mission.constraints, nominal, samples)
    except (ProfileError, ValueError) as e:
        raise ApiProblem(422, "bad_constraints", "The constraint settings are wrong", str(e)) from e
    return BoardResponse(
        board=judged,
        flight=FlightBasis(result_id=rid, available=nominal is not None),
        campaign=CampaignBasis(
            campaign_id=cid,
            samples=mission.monte_carlo.samples,
            samples_done=done,
        ),
    )
