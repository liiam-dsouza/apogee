"""Content-addressed file uploads: thrust curves and drag tables.

Files are parsed on upload, so a curve that cannot be simulated is refused
here rather than failing a run later. The response is exactly the entry the
mission's ``assets`` map needs.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Form, Response, UploadFile, status
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep
from apogee_api.problems import ApiProblem, Problem
from simcore.importers.drag import DragTableError, parse_drag_csv
from simcore.importers.thrust import ThrustCurveError, parse_thrust_curve

router = APIRouter(prefix="/api/assets", tags=["assets"])

MAX_ASSET_BYTES = 10 * 1024 * 1024


class ThrustCurveInfo(BaseModel):
    designation: str = Field(description="Motor designation from the file header.")
    total_impulse_ns: float = Field(
        description="Area under the curve.", json_schema_extra={"units": "N·s"}
    )
    burn_time_s: float = Field(description="Last thrust point.", json_schema_extra={"units": "s"})
    propellant_mass_kg: float = Field(
        description="From the file header.", json_schema_extra={"units": "kg"}
    )


class AssetInfo(BaseModel):
    sha256: str = Field(description="Content hash; how missions refer to the file.")
    kind: Literal["thrust_curve", "drag_table"] = Field(description="What the file is.")
    filename: str = Field(description="Original filename.")
    size: int = Field(description="File size.", json_schema_extra={"units": "bytes"})
    thrust_curve: ThrustCurveInfo | None = Field(
        default=None, description="Parsed motor data, for thrust curves."
    )


@router.post(
    "",
    operation_id="uploadAsset",
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": Problem, "description": "The file does not parse."}},
)
async def upload_asset(
    file: UploadFile,
    kind: Annotated[Literal["thrust_curve", "drag_table"], Form()],
    store: AssetStoreDep,
) -> AssetInfo:
    data = await file.read(MAX_ASSET_BYTES + 1)
    if len(data) > MAX_ASSET_BYTES:
        raise ApiProblem(413, "file_too_large", "The file is larger than 10 MB")
    filename = file.filename or "upload"
    info: ThrustCurveInfo | None = None
    try:
        if kind == "thrust_curve":
            curve = parse_thrust_curve(filename, data)
            info = ThrustCurveInfo(
                designation=curve.designation,
                total_impulse_ns=curve.total_impulse_ns,
                burn_time_s=curve.burn_time_s,
                propellant_mass_kg=curve.propellant_mass_kg,
            )
        else:
            parse_drag_csv(data)
    except (ThrustCurveError, DragTableError) as e:
        raise ApiProblem(422, "unreadable_asset", f"{filename} could not be read", str(e)) from e
    sha = store.put(data)
    return AssetInfo(sha256=sha, kind=kind, filename=filename, size=len(data), thrust_curve=info)


@router.get(
    "/{sha256}",
    operation_id="downloadAsset",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}, 404: {"model": Problem}},
)
def download_asset(sha256: str, store: AssetStoreDep) -> Response:
    from simcore.assets import AssetError

    try:
        data = store.read(sha256)
    except AssetError as e:
        raise ApiProblem(404, "asset_not_found", "Asset not found", str(e)) from e
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
