"""Results on disk: ``<root>/<id>/result.json`` and ``trajectory.parquet``.

A result directory is written once and never changed, so its id (a hash of
everything that determines it) is also a cache key.
"""

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from simcore.engine.result import TRAJECTORY_CHANNELS, FlightResult, FlightSummary
from simcore.mission import Mission, canonical_json
from simcore.results.downsample import lttb
from simcore.versions import rocketpy_version, simcore_version


class ResultNotFound(LookupError):
    pass


class Provenance(BaseModel):
    """Where a number came from: everything needed to reproduce it."""

    mission_id: str = Field(description="Mission the result was run from.")
    mission_name: str = Field(description="Mission name at run time.")
    mission_hash: str = Field(description="sha256 of the canonical mission config.")
    rocketpy_version: str = Field(description="RocketPy version that simulated it.")
    simcore_version: str = Field(description="simcore version that built the simulation.")
    git_sha: str = Field(description="Commit of the running build.")
    atmosphere: str = Field(description="Atmosphere source, and its time for a profile.")
    thrust_curve: str | None = Field(description="sha256 of the thrust curve used.")
    drag: str = Field(description="Drag source and multiplier.")
    seed: int | None = Field(description="Random seed; None for a deterministic flight.")
    computed_utc: datetime = Field(description="When the simulation ran.")


class ChannelInfo(BaseModel):
    name: str = Field(description="Channel id, used in series requests.")
    units: str = Field(description="Units of the values.")
    description: str = Field(description="What the channel measures.")


class ResultRecord(BaseModel):
    id: str = Field(description="Result id; also its cache key.")
    kind: str = Field(description="Result type. Only 'flight' so far.")
    ascent_only: bool = Field(description="True if the flight stopped at apogee.")
    summary: FlightSummary = Field(description="Summary scalars.")
    provenance: Provenance = Field(description="Where the result came from.")
    channels: list[ChannelInfo] = Field(description="Trajectory channels available as series.")
    points: int = Field(description="Full-resolution samples per channel.")
    warnings: list[str] = Field(description="Warnings RocketPy raised during the run.")


class Series(BaseModel):
    name: str = Field(description="Channel id.")
    units: str = Field(description="Units of y.")
    t: list[float] = Field(description="Time since ignition, s.")
    y: list[float] = Field(description="Values, in units.")


def result_key(mission: Mission, *, ascent_only: bool) -> str:
    """Cache key: same mission, versions and mode give the same id."""
    payload = "\n".join(
        [
            canonical_json(mission.model_dump(mode="json")),
            rocketpy_version(),
            simcore_version(),
            "ascent" if ascent_only else "full",
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _describe_atmosphere(mission: Mission) -> str:
    atmosphere = mission.environment.atmosphere
    if atmosphere.kind == "standard":
        return "Standard atmosphere, no wind"
    when = atmosphere.valid_utc.isoformat() if atmosphere.valid_utc else "time unknown"
    return f"Profile from {atmosphere.source}, valid {when}"


def _describe_drag(mission: Mission) -> str:
    if mission.rocket is None:
        return "none"
    d = mission.rocket.drag
    parts = []
    for label, curve in (("off", d.power_off), ("on", d.power_on)):
        src = f"table {curve.table[:12]}" if curve.table else f"constant {curve.constant_cd}"
        parts.append(f"power {label}: {src}")
    return f"{'; '.join(parts)}; multiplier {d.multiplier:g}"


def write_flight(
    root: Path, result_id: str, mission: Mission, result: FlightResult, *, git_sha: str
) -> ResultRecord:
    """Store a flight result. Atomic: readers see all of it or none."""
    final = root / result_id
    record = ResultRecord(
        id=result_id,
        kind="flight",
        ascent_only=result.ascent_only,
        summary=result.summary,
        provenance=Provenance(
            mission_id=mission.meta.id,
            mission_name=mission.meta.name,
            mission_hash=hashlib.sha256(
                canonical_json(mission.model_dump(mode="json")).encode()
            ).hexdigest(),
            rocketpy_version=rocketpy_version(),
            simcore_version=simcore_version(),
            git_sha=git_sha,
            atmosphere=_describe_atmosphere(mission),
            thrust_curve=mission.motor.thrust_curve if mission.motor else None,
            drag=_describe_drag(mission),
            seed=None,
            computed_utc=result.computed_utc,
        ),
        channels=[
            ChannelInfo(name=n, units=u, description=d)
            for n, (u, d) in TRAJECTORY_CHANNELS.items()
            if n != "time_s"
        ],
        points=len(result.trajectory["time_s"]),
        warnings=result.warnings,
    )
    if final.exists():
        return read_record(root, result_id)
    # A private temp dir per writer: two workers may compute the same result at once.
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{result_id}.", dir=root))
    table = pa.table({k: pa.array(v, type=pa.float64()) for k, v in result.trajectory.items()})
    pq.write_table(table, tmp / "trajectory.parquet", compression="zstd")
    (tmp / "result.json").write_text(record.model_dump_json(indent=2))
    try:
        tmp.rename(final)
    except OSError:
        # Another writer stored it first; identical by construction, so keep theirs.
        shutil.rmtree(tmp, ignore_errors=True)
    return record


def read_record(root: Path, result_id: str) -> ResultRecord:
    path = root / result_id / "result.json"
    if not result_id.isalnum() or not path.exists():
        raise ResultNotFound(result_id)
    return ResultRecord.model_validate(json.loads(path.read_text()))


def read_series(
    root: Path, result_id: str, names: list[str], *, max_points: int = 2000
) -> list[Series]:
    """Channels downsampled (LTTB) to at most ``max_points`` each."""
    record = read_record(root, result_id)
    known = {c.name: c for c in record.channels}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise KeyError(f"unknown channels: {', '.join(unknown)}")
    table = pq.read_table(root / result_id / "trajectory.parquet", columns=["time_s", *names])
    t = table.column("time_s").to_numpy()
    out = []
    for name in names:
        y = table.column(name).to_numpy()
        finite = np.isfinite(y)
        ts, ys = lttb(t[finite], y[finite], max_points)
        out.append(Series(name=name, units=known[name].units, t=ts.tolist(), y=ys.tolist()))
    return out
