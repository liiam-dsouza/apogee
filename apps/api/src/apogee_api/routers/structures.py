"""Structural checks from a flight: fin flutter."""

import contextlib

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apogee_api.deps import SettingsDep
from apogee_api.problems import ApiProblem, Problem
from simcore.constraints.evaluate import resolve
from simcore.mission import Mission
from simcore.mission.models import quantity
from simcore.results import ResultNotFound, read_record, result_key
from simcore.structures import FIN_MATERIALS, FinFlutter, FinMaterialPreset, thickness_for_margin

router = APIRouter(prefix="/api/structures", tags=["structures"])

#: The margin asked for when no rule sets one: AURC Spec 4.2.1's.
DEFAULT_MARGIN = 1.5


class FlutterRequest(BaseModel):
    mission: Mission = Field(description="The mission, saved or not.")


class FinSetFlutter(BaseModel):
    fin_set: int = Field(description="Which fin set, from 1.")
    checked: bool = Field(description="The fin set has a thickness and material.")
    flutter: FinFlutter | None = Field(
        description="From this mission's single flight, if it has been run and the set is checked."
    )
    thinnest_m: float | None = quantity(
        "m", "Thinnest fin of this material that keeps the required margin on this flight."
    )


class FlutterResponse(BaseModel):
    required_margin: float = quantity("1", "Flutter speed over flight speed the check asks for.")
    required_by: str = Field(description="The rule that sets it, or why it is the default.")
    flight_run: bool = Field(description="The mission's single flight has been run.")
    fin_sets: list[FinSetFlutter] = Field(description="One per fin set, in the mission's order.")


def _required_margin(mission: Mission) -> tuple[float, str]:
    with contextlib.suppress(ValueError):  # an unknown profile or category: the board says so
        rules, _ = resolve(mission.constraints)
        mins = [
            (r.lower, r.constraint)
            for r in rules
            if r.constraint.metric == "min_fin_flutter_margin" and r.lower is not None
        ]
        if mins:
            lower, c = max(mins, key=lambda m: m[0])
            return lower, " ".join(
                x for x in (c.label or c.id, c.reference and f"({c.reference})") if x
            )
    return DEFAULT_MARGIN, "No rule in this mission sets one; 1.5 is AURC's (Spec 4.2.1)."


@router.get("/fin-materials", operation_id="listFinMaterials")
def fin_materials() -> list[FinMaterialPreset]:
    """Typical fin materials and their shear moduli, to start from."""
    return FIN_MATERIALS


@router.post(
    "/flutter",
    operation_id="finFlutter",
    responses={422: {"model": Problem, "description": "No rocket yet."}},
)
def flutter(body: FlutterRequest, settings: SettingsDep) -> FlutterResponse:
    """Flutter margin per fin set from the mission's single flight, and the thinnest safe fin."""
    mission = body.mission
    if mission.rocket is None:
        raise ApiProblem(422, "not_ready", "Fin flutter needs a rocket")
    margin, required_by = _required_margin(mission)
    found: list[FinFlutter] | None = None
    with contextlib.suppress(ResultNotFound):
        found = read_record(
            settings.results_dir, result_key(mission, ascent_only=False)
        ).summary.fin_flutter
    by_set = {f.fin_set: f for f in found or []}
    rows = []
    for i, fins in enumerate(mission.rocket.fins, start=1):
        f = by_set.get(i)
        rows.append(
            FinSetFlutter(
                fin_set=i,
                checked=fins.thickness_m is not None and fins.material is not None,
                flutter=f,
                thinnest_m=thickness_for_margin(f, margin) if f else None,
            )
        )
    return FlutterResponse(
        required_margin=margin, required_by=required_by, flight_run=found is not None, fin_sets=rows
    )
