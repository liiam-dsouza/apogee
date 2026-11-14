"""Site presets: launch sites the team flies from again and again.

Loading a preset copies its Site into the mission. Missions never point at a
preset, so editing one (the club moves its rail, the range redraws a hazard)
never changes a mission already planned or flown against the old site.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select
from ulid import ULID

from apogee_api.db import SitePresetRecord, get_session
from apogee_api.problems import ApiProblem, Problem
from simcore.mission import Mission
from simcore.mission.models import MissionMeta, Site
from simcore.mission.validation import physical_checks

router = APIRouter(prefix="/api/sites", tags=["sites"])

SessionDep = Annotated[Session, Depends(get_session)]

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": Problem, "description": "No preset with that id."},
    409: {"model": Problem, "description": "Another preset has that name."},
    422: {"model": Problem, "description": "The site is not valid."},
}


class SitePresetInput(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="Name shown in the picker.")
    site: Site = Field(description="The launch site and range geometry.")


class SitePreset(SitePresetInput):
    id: str = Field(description="Preset id (ULID).")
    updated_utc: datetime = Field(description="Last saved, UTC.")


def _to_preset(record: SitePresetRecord) -> SitePreset:
    return SitePreset(
        id=record.id,
        name=record.name,
        site=Site.model_validate_json(record.site),
        updated_utc=record.updated_utc,
    )


def _get_record(session: Session, preset_id: str) -> SitePresetRecord:
    record = session.get(SitePresetRecord, preset_id)
    if record is None:
        raise ApiProblem(404, "site_not_found", "Site preset not found", f"No preset {preset_id}.")
    return record


def _check(session: Session, body: SitePresetInput, preset_id: str | None) -> None:
    """Refuse a duplicate name, or a site every mission using it would fail on."""
    clash = session.exec(select(SitePresetRecord).where(SitePresetRecord.name == body.name)).first()
    if clash is not None and clash.id != preset_id:
        raise ApiProblem(
            409,
            "site_exists",
            "A site preset with this name already exists",
            f"Rename it, or update '{body.name}' instead.",
        )
    # The site checks need a mission around the site; only their issues are kept.
    probe = Mission(meta=MissionMeta(name=body.name), site=body.site)
    errors = [
        i for i in physical_checks(probe) if i.severity == "error" and i.path.startswith("site")
    ]
    if errors:
        raise ApiProblem(
            422, "invalid_site", "The site is not valid", f"{len(errors)} problem(s) found.", errors
        )


def _save(session: Session, record: SitePresetRecord, body: SitePresetInput) -> SitePreset:
    record.name = body.name
    record.site = body.site.model_dump_json()
    record.updated_utc = datetime.now(UTC)
    session.add(record)
    session.commit()
    session.refresh(record)
    return _to_preset(record)


@router.get("", operation_id="listSitePresets")
def list_site_presets(session: SessionDep) -> list[SitePreset]:
    records = session.exec(select(SitePresetRecord).order_by(col(SitePresetRecord.name)))
    return [_to_preset(r) for r in records]


@router.post(
    "",
    operation_id="createSitePreset",
    status_code=status.HTTP_201_CREATED,
    responses=PROBLEM_RESPONSES,
)
def create_site_preset(body: SitePresetInput, session: SessionDep) -> SitePreset:
    _check(session, body, None)
    record = SitePresetRecord(id=str(ULID()), name=body.name, site="")
    return _save(session, record, body)


@router.put("/{preset_id}", operation_id="updateSitePreset", responses=PROBLEM_RESPONSES)
def update_site_preset(preset_id: str, body: SitePresetInput, session: SessionDep) -> SitePreset:
    record = _get_record(session, preset_id)
    _check(session, body, preset_id)
    return _save(session, record, body)


@router.delete(
    "/{preset_id}",
    operation_id="deleteSitePreset",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=PROBLEM_RESPONSES,
)
def delete_site_preset(preset_id: str, session: SessionDep) -> None:
    session.delete(_get_record(session, preset_id))
    session.commit()
