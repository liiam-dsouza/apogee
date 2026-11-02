"""Campaigns on disk: ``<data dir>/campaigns/<id>/``.

``campaign.json`` holds the mission and how it was split; each finished chunk
of samples is ``chunk-<k>.json``. A chunk file appears atomically when its
job finishes, so progress is simply which chunks exist, and any reader sees
whole chunks only.
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simcore.mission import Mission, canonical_json
from simcore.versions import rocketpy_version, simcore_version

#: Samples per job. Small enough to spread over workers and show progress, large
#: enough that queue overhead is negligible (a Calisto flight is ~0.4 s).
CHUNK_SIZE = 20


def campaign_key(mission: Mission) -> str:
    """Same mission (campaign settings included) and versions give the same campaign.

    Constraints are judged on a campaign, not part of it, so they are left out.
    """
    data = mission.model_dump(mode="json", exclude={"constraints"})
    payload = "\n".join([canonical_json(data), rocketpy_version(), simcore_version()])
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def chunks(samples: int, size: int = CHUNK_SIZE) -> list[list[int]]:
    return [list(range(i, min(i + size, samples))) for i in range(0, samples, size)]


def _atomic_write(path: Path, data: Any) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    os.replace(tmp, path)


class CampaignStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _dir(self, campaign_id: str) -> Path:
        if not campaign_id.isalnum():
            raise KeyError(campaign_id)
        return self.root / campaign_id

    def exists(self, campaign_id: str) -> bool:
        return (self._dir(campaign_id) / "campaign.json").exists()

    def create(self, campaign_id: str, mission: Mission, git_sha: str) -> None:
        d = self._dir(campaign_id)
        d.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            d / "campaign.json",
            {
                "id": campaign_id,
                "created_utc": datetime.now(UTC).isoformat(),
                "samples": mission.monte_carlo.samples,
                "chunks": len(chunks(mission.monte_carlo.samples)),
                "git_sha": git_sha,
                "rocketpy_version": rocketpy_version(),
                "simcore_version": simcore_version(),
                "mission": mission.model_dump(mode="json"),
            },
        )

    def meta(self, campaign_id: str) -> dict[str, Any]:
        try:
            raw = (self._dir(campaign_id) / "campaign.json").read_text()
            data: dict[str, Any] = json.loads(raw)
        except FileNotFoundError as e:
            raise KeyError(campaign_id) from e
        return data

    def write_chunk(self, campaign_id: str, k: int, rows: list[dict[str, Any]]) -> None:
        _atomic_write(self._dir(campaign_id) / f"chunk-{k}.json", rows)

    def done_chunks(self, campaign_id: str) -> set[int]:
        return {int(p.stem.split("-")[1]) for p in self._dir(campaign_id).glob("chunk-*.json")}

    def rows(self, campaign_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for k in sorted(self.done_chunks(campaign_id)):
            out.extend(json.loads((self._dir(campaign_id) / f"chunk-{k}.json").read_text()))
        return out
