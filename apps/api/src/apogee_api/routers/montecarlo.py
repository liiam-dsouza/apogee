"""Monte Carlo campaigns: start (or resume) one, watch it, read its spread.

A campaign is split into chunks of samples, one job each, so every worker
shares it. Results are read from whatever chunks have finished, so the
dispersion fills in while the campaign runs.
"""

import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from apogee_api.deps import AssetStoreDep, QueueDep, SettingsDep
from apogee_api.problems import ApiProblem, Problem
from apogee_api.queue import MONTE_CARLO_CHUNK_TASK, JobQueue, QueueUnavailable
from apogee_api.routers.sim import _runnable_issues
from apogee_api.settings import Settings
from simcore.mission import Mission, load_mission
from simcore.montecarlo import OUTPUTS, CampaignSummary, summarize
from simcore.montecarlo.store import CampaignStore, campaign_key, chunks

router = APIRouter(prefix="/api", tags=["monte carlo"])


class CampaignRequest(BaseModel):
    mission: Mission = Field(description="The mission, with its monte_carlo settings.")


class CampaignState(BaseModel):
    id: str = Field(description="Campaign id: a hash of the mission and versions.")
    status: Literal["running", "done", "failed", "stalled"] = Field(
        description=(
            "running: chunks are queued or flying. done: every chunk finished. failed: a chunk's "
            "job failed. stalled: unfinished chunks have no job (restart lost them); start the "
            "campaign again to resume."
        )
    )
    created_utc: datetime = Field(description="When the campaign was first started.")
    samples: int = Field(description="Samples in the campaign.")
    samples_done: int = Field(description="Samples in finished chunks (flown or failed).")
    chunk_errors: list[str] = Field(description="Why chunk jobs failed, if any did.")


class LandingPoint(BaseModel):
    index: int = Field(description="Sample number.")
    longitude_deg: float = Field(description="Landing longitude, WGS84.")
    latitude_deg: float = Field(description="Landing latitude, WGS84.")
    apogee_agl_m: float = Field(description="That sample's apogee above the pad.")


class CampaignResult(BaseModel):
    state: CampaignState = Field(description="Progress.")
    summary: CampaignSummary = Field(description="Statistics over the samples so far.")
    points: list[LandingPoint] = Field(description="Every landing so far.")


def _store(settings: Settings) -> CampaignStore:
    return CampaignStore(settings.data_dir / "campaigns")


def _job_id(campaign_id: str, k: int) -> str:
    return f"mc:{campaign_id}:{k}"


async def _state(campaign_id: str, store: CampaignStore, queue: JobQueue) -> CampaignState:
    meta = store.meta(campaign_id)
    done = store.done_chunks(campaign_id)
    split = chunks(meta["samples"])
    samples_done = sum(len(split[k]) for k in done)
    if len(done) == len(split):
        status: Literal["running", "done", "failed", "stalled"] = "done"
        errors: list[str] = []
    else:
        errors, live = [], False
        try:
            for k in range(len(split)):
                if k in done:
                    continue
                job = await queue.state(_job_id(campaign_id, k))
                if job.status == "failed":
                    errors.append(f"Samples {split[k][0]}-{split[k][-1]}: {job.error}")
                elif job.status in ("queued", "running"):
                    live = True
        except QueueUnavailable:
            live = True  # can't tell; don't call it stalled
        status = "running" if live else "failed" if errors else "stalled"
    return CampaignState(
        id=campaign_id,
        status=status,
        created_utc=meta["created_utc"],
        samples=meta["samples"],
        samples_done=samples_done,
        chunk_errors=errors,
    )


@router.post(
    "/sim/montecarlo",
    operation_id="runMonteCarlo",
    responses={
        422: {"model": Problem, "description": "The mission cannot be flown yet."},
        503: {"model": Problem, "description": "No job queue."},
    },
)
async def run_monte_carlo(
    body: CampaignRequest, queue: QueueDep, assets: AssetStoreDep, settings: SettingsDep
) -> CampaignState:
    """Start a campaign, or resume one: chunks without a finished result or a live job
    are (re)queued. The same mission and versions always give the same campaign."""
    mission = body.mission
    issues = _runnable_issues(mission, assets)
    if issues:
        raise ApiProblem(
            422,
            "not_runnable",
            "This mission cannot be flown yet",
            f"{len(issues)} problem(s).",
            issues,
        )
    store = _store(settings)
    campaign_id = campaign_key(mission)
    if not store.exists(campaign_id):
        store.create(campaign_id, mission, settings.git_sha)
    done = store.done_chunks(campaign_id)
    data = mission.model_dump(mode="json")
    try:
        for k in range(len(chunks(mission.monte_carlo.samples))):
            if k not in done:
                await queue.submit(
                    MONTE_CARLO_CHUNK_TASK,
                    _job_id(campaign_id, k),
                    mission_data=data,
                    campaign_id=campaign_id,
                    chunk=k,
                    data_dir=str(settings.data_dir),
                )
    except QueueUnavailable as e:
        raise ApiProblem(
            503,
            "queue_unavailable",
            "Simulations are unavailable",
            "The job queue is not reachable. Check that Redis and a worker are running.",
        ) from e
    return await _state(campaign_id, store, queue)


@router.get(
    "/campaigns/{campaign_id}",
    operation_id="getCampaign",
    responses={404: {"model": Problem, "description": "No such campaign."}},
)
async def get_campaign(campaign_id: str, queue: QueueDep, settings: SettingsDep) -> CampaignResult:
    """Progress, statistics and landing points, over the samples finished so far."""
    store = _store(settings)
    try:
        meta = store.meta(campaign_id)
    except KeyError as e:
        raise ApiProblem(404, "campaign_not_found", "No such campaign") from e
    rows = store.rows(campaign_id)
    mission = load_mission(meta["mission"])
    points = [
        LandingPoint(
            index=r["index"],
            longitude_deg=r["landing_longitude_deg"],
            latitude_deg=r["landing_latitude_deg"],
            apogee_agl_m=r["apogee_agl_m"],
        )
        for r in rows
        if r.get("error") is None and r.get("landing_latitude_deg") is not None
    ]
    return CampaignResult(
        state=await _state(campaign_id, store, queue),
        summary=summarize(mission, rows),
        points=points,
    )


@router.get(
    "/campaigns/{campaign_id}/samples.csv",
    operation_id="campaignSamplesCsv",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "One row per sample."},
        404: {"model": Problem, "description": "No such campaign."},
    },
)
def campaign_csv(campaign_id: str, settings: SettingsDep) -> Response:
    """Every sample's inputs and outputs side by side, for a spreadsheet."""
    store = _store(settings)
    try:
        store.meta(campaign_id)
    except KeyError as e:
        raise ApiProblem(404, "campaign_not_found", "No such campaign") from e
    rows = sorted(store.rows(campaign_id), key=lambda r: r["index"])
    columns: list[str] = []
    for r in rows:
        columns += [c for c in r if c not in columns]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id[:12]}.csv"'},
    )


class Distribution(BaseModel):
    name: str = Field(description="Output name.")
    label: str = Field(description="What it is.")
    units: str = Field(description="Units.")
    values: list[float] = Field(description="One value per successful sample, in sample order.")


@router.get(
    "/campaigns/{campaign_id}/distributions",
    operation_id="campaignDistributions",
    responses={404: {"model": Problem, "description": "No such campaign."}},
)
def campaign_distributions(campaign_id: str, settings: SettingsDep) -> list[Distribution]:
    """Every sample's value of each output, for histograms."""
    store = _store(settings)
    try:
        store.meta(campaign_id)
    except KeyError as e:
        raise ApiProblem(404, "campaign_not_found", "No such campaign") from e
    rows = sorted(
        (r for r in store.rows(campaign_id) if r.get("error") is None), key=lambda r: r["index"]
    )
    return [
        Distribution(
            name=name,
            label=label,
            units=units,
            values=[r[name] for r in rows if r.get(name) is not None],
        )
        for name, (units, label) in OUTPUTS.items()
        if any(r.get(name) is not None for r in rows)
    ]
