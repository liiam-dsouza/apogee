"""ThrustCurve.org: the motor catalogue and its thrust curves.

Searches are kept on disk for a week and curves in the asset store, so a
search that has been made once works offline afterwards.
"""

import json
import time
import urllib.error
import urllib.request
from base64 import b64decode
from pathlib import Path
from typing import Any

from apogee_api.problems import ApiProblem
from simcore.assets import DirectoryAssetStore

THRUSTCURVE_API = "https://www.thrustcurve.org/api/v1"
#: ThrustCurve.org refuses Python's default User-Agent with 403; say who we are.
USER_AGENT = "Apogee/0.1 (rocketry flight simulation; motor lookup)"
SEARCH_MAX_AGE_S = 7 * 24 * 3600


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{THRUSTCURVE_API}/{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        parsed: dict[str, Any] = json.loads(resp.read())
        return parsed


def call(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST to the API. Raises 502 if the site refuses, 503 if it can't be reached."""
    try:
        return _post(path, body)
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


def _cache_dir(data_dir: Path) -> Path:
    path = data_dir / "thrustcurve"
    path.mkdir(parents=True, exist_ok=True)
    return path


def search_diameter(
    data_dir: Path, diameter_mm: float, discontinued: bool
) -> tuple[list[dict[str, Any]], float]:
    """Every catalogue motor of a diameter, and when the list was fetched (epoch seconds).

    A cached list younger than a week is used as is; an older one is used if
    the site can't be reached.
    """
    availability = "all" if discontinued else "available"
    cached = _cache_dir(data_dir) / f"search-{round(diameter_mm)}-{availability}.json"
    stale = None
    if cached.exists():
        stale = json.loads(cached.read_text())
        if time.time() - stale["fetched_at"] < SEARCH_MAX_AGE_S:
            return stale["results"], stale["fetched_at"]
    try:
        found = call(
            "search.json",
            {"diameter": round(diameter_mm), "availability": availability, "maxResults": 1000},
        )
    except ApiProblem:
        if stale is None:
            raise
        return stale["results"], stale["fetched_at"]
    entry = {"fetched_at": time.time(), "results": found.get("results", [])}
    cached.write_text(json.dumps(entry))
    return entry["results"], entry["fetched_at"]


def curves(
    data_dir: Path, store: DirectoryAssetStore, motor_ids: list[str]
) -> tuple[dict[str, tuple[str, bytes]], bool]:
    """RASP (.eng) curve per motor id, as (sha256, content), and whether every one was asked.

    Fetches the ones not stored yet. A motor ThrustCurve.org has no RASP file
    for is left out (and remembered, so it isn't asked for again). If the site
    can't be reached, the stored ones come back and the flag is False.
    """
    index_path = _cache_dir(data_dir) / "curves.json"
    #: motor id -> sha256, or "" for a motor with no RASP file.
    index: dict[str, str] = json.loads(index_path.read_text()) if index_path.exists() else {}
    stored = [i for i in motor_ids if index.get(i) and store.has(index[i])]
    out = {i: (index[i], store.read(index[i])) for i in stored}
    missing = [i for i in motor_ids if i not in out and index.get(i) != ""]
    if not missing:
        return out, True
    try:
        files = call("download.json", {"motorIds": missing, "format": "RASP", "data": "file"})
    except ApiProblem:
        return out, False
    for f in files.get("results", []):
        motor_id = f.get("motorId")
        if motor_id in missing and motor_id not in out and f.get("format") == "RASP":
            content = b64decode(f["data"])
            out[motor_id] = (store.put(content), content)
    index |= {i: out[i][0] if i in out else "" for i in missing}
    index_path.write_text(json.dumps(index))
    return out, True
