"""Mission CRUD, validation, import and export.

Missions are stored as the same YAML the export produces, so what the team
commits to Git and what the API holds are byte-for-byte the same document.
"""

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from apogee_api.db import MissionRecord, get_session
from apogee_api.problems import ApiProblem, Problem
from simcore.mission import (
    Issue,
    Mission,
    ValidationReport,
    dump_yaml,
    mission_hash,
    parse_yaml,
    validate_mission,
)
from simcore.mission.validation import physical_checks

router = APIRouter(prefix="/api/missions", tags=["missions"])

SessionDep = Annotated[Session, Depends(get_session)]

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": Problem, "description": "No mission with that id."},
    409: {"model": Problem, "description": "Conflicts with a stored mission."},
    422: {"model": Problem, "description": "The mission is not valid."},
}


class MissionSummary(BaseModel):
    id: str = Field(description="Mission id (ULID).")
    name: str = Field(description="Mission name.")
    config_hash: str = Field(description="sha256 of the canonical config.")
    updated_utc: datetime = Field(description="Last saved, UTC.")


class MissionDocument(BaseModel):
    mission: Mission = Field(description="The full mission config.")
    config_hash: str = Field(description="sha256 of the canonical config.")
    updated_utc: datetime = Field(description="Last saved, UTC.")
    issues: list[Issue] = Field(description="Warnings from physical checks (never errors).")


def _to_document(record: MissionRecord, mission: Mission) -> MissionDocument:
    return MissionDocument(
        mission=mission,
        config_hash=record.config_hash,
        updated_utc=record.updated_utc,
        issues=physical_checks(mission),
    )


def _reject_errors(mission: Mission) -> None:
    errors = [i for i in physical_checks(mission) if i.severity == "error"]
    if errors:
        raise ApiProblem(
            422,
            "invalid_mission",
            "The mission is not valid",
            f"{len(errors)} problem(s) found.",
            errors,
        )


def _get_record(session: Session, mission_id: str) -> MissionRecord:
    record = session.get(MissionRecord, mission_id)
    if record is None:
        raise ApiProblem(404, "mission_not_found", "Mission not found", f"No mission {mission_id}.")
    return record


def _save(session: Session, mission: Mission, record: MissionRecord | None) -> MissionRecord:
    now = datetime.now(UTC)
    if record is None:
        record = MissionRecord(
            id=mission.meta.id,
            name=mission.meta.name,
            yaml="",
            config_hash="",
            created_utc=mission.meta.created_utc,
        )
    record.name = mission.meta.name
    record.yaml = dump_yaml(mission)
    record.config_hash = mission_hash(mission)
    record.updated_utc = now
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.post("/validate", operation_id="validateMission")
def validate(data: Annotated[dict[str, Any], Body()]) -> ValidationReport:
    """Check a mission config without storing or simulating it.

    Accepts any schema version; older configs are migrated first. Always
    returns 200 with a report: errors block a run, warnings do not.
    """
    _, report = validate_mission(data)
    return report


@router.get("", operation_id="listMissions")
def list_missions(session: SessionDep) -> list[MissionSummary]:
    records = session.exec(select(MissionRecord).order_by(col(MissionRecord.updated_utc).desc()))
    return [
        MissionSummary(id=r.id, name=r.name, config_hash=r.config_hash, updated_utc=r.updated_utc)
        for r in records
    ]


@router.post(
    "",
    operation_id="createMission",
    status_code=status.HTTP_201_CREATED,
    responses=PROBLEM_RESPONSES,
)
def create_mission(mission: Mission, session: SessionDep) -> MissionDocument:
    _reject_errors(mission)
    if session.get(MissionRecord, mission.meta.id) is not None:
        raise ApiProblem(
            409,
            "mission_exists",
            "A mission with this id already exists",
            "Use PUT to update it, or give the copy a new meta.id.",
        )
    return _to_document(_save(session, mission, None), mission)


@router.get("/{mission_id}", operation_id="getMission", responses=PROBLEM_RESPONSES)
def get_mission(mission_id: str, session: SessionDep) -> MissionDocument:
    record = _get_record(session, mission_id)
    return _to_document(record, Mission.model_validate(parse_yaml(record.yaml)))


@router.put("/{mission_id}", operation_id="updateMission", responses=PROBLEM_RESPONSES)
def update_mission(mission_id: str, mission: Mission, session: SessionDep) -> MissionDocument:
    if mission.meta.id != mission_id:
        raise ApiProblem(
            422,
            "id_mismatch",
            "meta.id does not match the URL",
            issues=[
                Issue(
                    path="meta.id",
                    message="Must match the mission being updated.",
                    code="id_mismatch",
                    severity="error",
                )
            ],
        )
    _reject_errors(mission)
    record = _get_record(session, mission_id)
    return _to_document(_save(session, mission, record), mission)


@router.delete(
    "/{mission_id}",
    operation_id="deleteMission",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=PROBLEM_RESPONSES,
)
def delete_mission(mission_id: str, session: SessionDep) -> None:
    session.delete(_get_record(session, mission_id))
    session.commit()


@router.post(
    "/import",
    operation_id="importMission",
    status_code=status.HTTP_201_CREATED,
    responses={**PROBLEM_RESPONSES, 415: {"model": Problem, "description": "Unsupported file."}},
)
async def import_mission(file: UploadFile, session: SessionDep) -> MissionDocument:
    """Import a mission.yaml (any schema version). Bundles (.mission.zip) are not supported yet."""
    name = file.filename or ""
    if name.endswith(".zip"):
        raise ApiProblem(415, "bundle_not_supported", "Mission bundles are not supported yet")
    try:
        data = parse_yaml((await file.read()).decode())
    except Exception as e:
        raise ApiProblem(
            415, "unreadable_file", "The file is not a YAML or JSON mission", str(e)
        ) from e
    mission, report = validate_mission(data)
    if mission is None or not report.valid:
        raise ApiProblem(
            422,
            "invalid_mission",
            "The mission is not valid",
            f"{len(report.issues)} problem(s) found.",
            report.issues,
        )
    if session.get(MissionRecord, mission.meta.id) is not None:
        raise ApiProblem(
            409,
            "mission_exists",
            "A mission with this id already exists",
            f"'{mission.meta.name}' is already stored. Delete it or edit meta.id.",
        )
    return _to_document(_save(session, mission, None), mission)


@router.get(
    "/{mission_id}/export",
    operation_id="exportMission",
    responses={
        **PROBLEM_RESPONSES,
        200: {"content": {"application/yaml": {}}, "description": "The mission file."},
        501: {"model": Problem, "description": "Format not implemented yet."},
    },
    response_class=Response,
)
def export_mission(
    mission_id: str,
    session: SessionDep,
    format: Annotated[Literal["yaml", "zip"], Query()] = "yaml",
) -> Response:
    record = _get_record(session, mission_id)
    if format == "zip":
        raise ApiProblem(501, "bundle_not_supported", "Mission bundles are not supported yet")
    slug = re.sub(r"[^a-z0-9]+", "-", record.name.lower()).strip("-") or "mission"
    return Response(
        record.yaml,
        media_type="application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{slug}.mission.yaml"'},
    )
