"""Every forecast fetched, kept as fetched, so the field laptop can fly the last one offline."""

import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ulid import ULID

#: Forecasts fetched within this distance of a site count as "for that site".
NEARBY_M = 25_000.0


class ForecastNotFound(LookupError):
    pass


@dataclass(frozen=True)
class CachedForecast:
    id: str
    fetched_utc: datetime
    latitude: float
    longitude: float
    source: str
    response: dict[str, Any]


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine), good enough to say "near"."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


class ForecastCache:
    """One JSON file per fetch, named by a ULID (so names sort by fetch time)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(
        self, latitude: float, longitude: float, source: str, response: dict[str, Any]
    ) -> CachedForecast:
        self.root.mkdir(parents=True, exist_ok=True)
        entry = CachedForecast(
            id=str(ULID()),
            fetched_utc=datetime.now(UTC),
            latitude=latitude,
            longitude=longitude,
            source=source,
            response=response,
        )
        body = json.dumps(
            {**entry.__dict__, "fetched_utc": entry.fetched_utc.isoformat()}, separators=(",", ":")
        )
        tmp = self.root / f".{entry.id}.tmp"
        tmp.write_text(body)
        os.replace(tmp, self.root / f"{entry.id}.json")
        return entry

    def get(self, forecast_id: str) -> CachedForecast:
        if not forecast_id.isalnum():
            raise ForecastNotFound(forecast_id)
        try:
            raw = json.loads((self.root / f"{forecast_id}.json").read_text())
        except FileNotFoundError as e:
            raise ForecastNotFound(forecast_id) from e
        return CachedForecast(**{**raw, "fetched_utc": datetime.fromisoformat(raw["fetched_utc"])})

    def near(self, latitude: float, longitude: float) -> list[CachedForecast]:
        """Forecasts fetched for points near this one, newest first."""
        if not self.root.is_dir():
            return []
        found = []
        for path in sorted(self.root.glob("*.json"), reverse=True):
            entry = self.get(path.stem)
            if _distance_m(latitude, longitude, entry.latitude, entry.longitude) <= NEARBY_M:
                found.append(entry)
        return found
