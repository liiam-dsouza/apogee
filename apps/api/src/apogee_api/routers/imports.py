"""Importing designs and motors from other tools.

Parsing happens here (it is fast and needs no physics); anything that flies
the rocket goes through the job queue like every other simulation.
"""

import json
import logging
import urllib.error
import urllib.request
import uuid
from base64 import b64decode
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.queue import ORK_CROSS_CHECK_TASK, QueueUnavailable
from apogee_api.routers.assets import AssetInfo, ThrustCurveInfo
from simcore.assets import AssetError
from simcore.importers.openrocket import (
    MAX_ORK_BYTES,
    CrossCheck,
    ImportReport,
    MotorReference,
    OrkError,
    RailSettings,
    cross_check_mission,
    import_openrocket,
)
from simcore.importers.thrust import (
    ThrustCurveError,
    generic_motor_estimate,
    parse_thrust_curve,
)
from simcore.mission.models import Asset, GenericMotor, Recovery, Rocket

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/imports", tags=["imports"])

CROSS_CHECK_WAIT_S = 30.0
THRUSTCURVE_API = "https://www.thrustcurve.org/api/v1"
#: ThrustCurve.org refuses Python's default User-Agent with 403; say who we are.
USER_AGENT = "Apogee/0.1 (rocketry flight simulation; motor lookup)"


class OpenRocketImport(BaseModel):
    """A draft to review: nothing is saved until the user applies it to a mission."""

    rocket: Rocket = Field(description="Draft rocket section.")
    recovery: Recovery = Field(description="Draft recovery section.")
    motor: GenericMotor | None = Field(
        description="Draft motor, if a thrust curve was supplied with the design."
    )
    motor_reference: MotorReference | None = Field(
        description="The motor OpenRocket's default configuration names."
    )
    rail: RailSettings | None = Field(
        description="Rod settings from the reference simulation, to apply to the site if wanted."
    )
    assets: dict[str, Asset] = Field(
        description="Entries to add to the mission's assets (already stored)."
    )
    report: ImportReport = Field(description="What came across, and how it compares.")


def _motor_from_curve(
    filename: str, data: bytes, store: Any
) -> tuple[GenericMotor, str, Asset, Any]:
    curve = parse_thrust_curve(filename, data)
    sha = store.put(data)
    motor = GenericMotor(kind="generic", thrust_curve=sha, **generic_motor_estimate(curve))  # type: ignore[arg-type]
    return motor, sha, Asset(kind="thrust_curve", filename=filename, size=len(data)), curve


@router.post(
    "/openrocket",
    operation_id="importOpenRocket",
    responses={
        422: {"model": Problem, "description": "Not a readable OpenRocket design."},
        413: {"model": Problem, "description": "File too large."},
    },
)
async def import_ork(
    file: UploadFile,
    store: AssetStoreDep,
    queue: QueueDep,
    settings: SettingsDep,
    thrust_curve: Annotated[
        UploadFile | None, File(description="Optional .eng for the motor.")
    ] = None,
    thrust_curve_sha: Annotated[
        str | None,
        Form(description="Or an already-stored thrust curve, e.g. fetched from ThrustCurve.org."),
    ] = None,
) -> OpenRocketImport:
    """Parse an .ork into draft rocket and recovery sections, with an import report.

    With a thrust curve, the draft also gets a motor and the report gets
    flight cross-checks (apogee, max Mach, rail exit, centre of pressure)
    against OpenRocket's own saved simulation.
    """
    data = await file.read(MAX_ORK_BYTES + 1)
    if len(data) > MAX_ORK_BYTES:
        raise ApiProblem(413, "file_too_large", "The design is larger than 64 MB")
    try:
        result = import_openrocket(data)
    except OrkError as e:
        raise ApiProblem(
            422, "unreadable_ork", "This is not an OpenRocket design Apogee can read", str(e)
        ) from e

    assets: dict[str, Asset] = {}
    for sha, (name, content) in result.assets.items():
        store.put(content)
        assets[sha] = Asset(kind="drag_table", filename=name, size=len(content))

    motor = None
    report = result.report
    curve_source: tuple[str, bytes] | None = None
    if thrust_curve is not None:
        curve_source = (
            thrust_curve.filename or "motor.eng",
            await thrust_curve.read(10 * 1024 * 1024),
        )
    elif thrust_curve_sha:
        try:
            curve_source = (f"{thrust_curve_sha[:12]}.eng", store.read(thrust_curve_sha))
        except AssetError as e:
            raise ApiProblem(
                404, "asset_not_found", "That thrust curve is not stored", str(e)
            ) from e
    if curve_source is not None:
        name, content = curve_source
        try:
            motor, sha, asset, curve = _motor_from_curve(name, content, store)
        except ThrustCurveError as e:
            raise ApiProblem(422, "unreadable_asset", f"{name} could not be read", str(e)) from e
        assets[sha] = asset
        ref = result.motor
        if ref and curve.designation.split("-")[0].upper() != ref.designation.split("-")[0].upper():
            report.warnings.append(
                f"The thrust curve is for {curve.designation}, but the design's motor is "
                f"{ref.designation}. Check you uploaded the right file."
            )
        report.cross_checks.extend(
            await _flight_cross_checks(result, motor, assets, queue, str(settings.data_dir))
        )
    elif result.motor is not None:
        report.warnings.append(
            f"OpenRocket names the motor ({result.motor.manufacturer} {result.motor.designation}) "
            "but does not store its thrust curve. Add the .eng file, or fetch it from "
            "ThrustCurve.org, to fly this rocket and run the flight cross-checks."
        )

    return OpenRocketImport(
        rocket=result.rocket,
        recovery=result.recovery,
        motor=motor,
        motor_reference=result.motor,
        rail=result.rail,
        assets=assets,
        report=report,
    )


async def _flight_cross_checks(
    result: Any, motor: GenericMotor, assets: dict[str, Asset], queue: Any, data_dir: str
) -> list[CrossCheck]:
    if "apogee_m" not in result.reference:
        return []
    mission = cross_check_mission(
        result.rocket,
        result.recovery,
        motor.model_dump(mode="json"),
        {k: v.model_dump() for k, v in assets.items()},
        result.reference,
    )
    unavailable = CrossCheck(
        quantity="Apogee, max Mach, CP",
        units="",
        ours=None,
        openrocket=result.reference.get("apogee_m"),
        tolerance="",
        status="unavailable",
        note="",
    )
    try:
        job_id = await queue.submit(
            ORK_CROSS_CHECK_TASK,
            f"ork-check:{uuid.uuid4().hex}",
            mission_data=mission.model_dump(mode="json"),
            reference=result.reference,
            data_dir=data_dir,
        )
        state = await queue.wait(job_id, CROSS_CHECK_WAIT_S)
    except QueueUnavailable:
        return [unavailable.model_copy(update={"note": "No simulation workers are running."})]
    if state.status != "done":
        reason = state.error or "it did not finish in time"
        return [unavailable.model_copy(update={"note": f"The cross-check flight failed: {reason}"})]
    return [CrossCheck.model_validate(row) for row in await queue.result(job_id)]


class ThrustCurveRequest(BaseModel):
    manufacturer: str = Field(description="e.g. 'AeroTech'.")
    designation: str = Field(description="e.g. 'M1340W'.")


class ThrustCurveImport(BaseModel):
    asset: AssetInfo = Field(description="The stored thrust curve.")
    motor: GenericMotor = Field(description="A motor section estimated from the curve's header.")
    source: str = Field(description="Where the curve came from.")


def _thrustcurve(path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{THRUSTCURVE_API}/{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        parsed: dict[str, Any] = json.loads(resp.read())
        return parsed


@router.post(
    "/thrustcurve",
    operation_id="fetchThrustCurve",
    responses={
        404: {"model": Problem, "description": "No such motor on ThrustCurve.org."},
        502: {"model": Problem, "description": "ThrustCurve.org refused the request."},
        503: {"model": Problem, "description": "ThrustCurve.org is not reachable (offline?)."},
    },
)
def fetch_thrust_curve(body: ThrustCurveRequest, store: AssetStoreDep) -> ThrustCurveImport:
    """Fetch a motor's RASP (.eng) curve from ThrustCurve.org and store it.

    Needs internet. Fetched curves are stored like uploads, so they work
    offline afterwards.
    """
    try:
        found = _thrustcurve("search.json", body.model_dump()).get("results", [])
        if not found:
            raise ApiProblem(
                404,
                "motor_not_found",
                f"ThrustCurve.org has no {body.manufacturer} {body.designation}",
            )
        motor_id = found[0]["motorId"]
        files = _thrustcurve(
            "download.json", {"motorIds": [motor_id], "format": "RASP", "data": "file"}
        )
    except urllib.error.HTTPError as e:
        # Reached the site, but it said no: not an offline problem.
        raise ApiProblem(
            502,
            "thrustcurve_refused",
            f"ThrustCurve.org refused the request (HTTP {e.code})",
            "Try again later, or download the .eng file from thrustcurve.org and upload it.",
        ) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ApiProblem(
            503,
            "thrustcurve_unreachable",
            "ThrustCurve.org could not be reached",
            "You may be offline. Download the .eng file elsewhere and upload it instead.",
        ) from e
    rasp = next((f for f in files.get("results", []) if f.get("format") == "RASP"), None)
    if rasp is None:
        raise ApiProblem(
            404, "no_rasp_file", f"ThrustCurve.org has no .eng file for {body.designation}"
        )
    content = b64decode(rasp["data"])
    filename = f"{body.manufacturer}_{body.designation}.eng".replace(" ", "_")
    try:
        motor, sha, _, curve = _motor_from_curve(filename, content, store)
    except ThrustCurveError as e:
        raise ApiProblem(
            422, "unreadable_asset", "ThrustCurve.org returned an unreadable file", str(e)
        ) from e
    return ThrustCurveImport(
        asset=AssetInfo(
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
        ),
        motor=motor,
        source=(
            f"ThrustCurve.org motor {motor_id} "
            f"({rasp.get('source', 'unknown')} data, {rasp.get('license', 'licence unknown')})"
        ),
    )
